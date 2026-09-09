
from __future__ import annotations

import asyncio
import http.server
import json
import socketserver
import threading
import time
from typing import Any

from openshores.core.logging import get_logger

logger = get_logger(__name__)


_boot_monotonic = time.monotonic()
_boot_unix_ms = int(time.time() * 1000)

_lock = threading.Lock()
_counters: dict[str, int] = {}
_tag_counters: dict[str, dict[str, int]] = {}
_gauges: dict[str, float] = {}

_providers: dict[str, "callable"] = {}

_server: socketserver.TCPServer | None = None
_server_thread: threading.Thread | None = None
_started: bool = False


def incr(name: str, by: int = 1, *, tag: str | None = None) -> None:
    with _lock:
        if tag is None:
            _counters[name] = _counters.get(name, 0) + by
        else:
            sub = _tag_counters.setdefault(name, {})
            sub[tag] = sub.get(tag, 0) + by


def set_gauge(name: str, value: float) -> None:
    with _lock:
        _gauges[name] = float(value)


def add_provider(name: str, fn) -> None:
    _providers[name] = fn


def _snapshot() -> dict[str, Any]:
    with _lock:
        out: dict[str, Any] = {
            "uptime_s": round(time.monotonic() - _boot_monotonic, 3),
            "boot_unix_ms": _boot_unix_ms,
            "counters": dict(_counters),
            "tag_counters": {k: dict(v) for k, v in _tag_counters.items()},
            "gauges": dict(_gauges),
        }
    providers_snapshot: dict[str, Any] = {}
    for name, fn in list(_providers.items()):
        try:
            providers_snapshot[name] = fn()
        except Exception as e:
            providers_snapshot[name] = f"<provider error: {e!r}>"
    out["providers"] = providers_snapshot
    return out


class _MetricsHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, default=str, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/metrics", "/metrics/"):
            self._send_json(_snapshot())
        elif self.path == "/healthz":
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found", "path": self.path},
                            status=404)


class _ThreadedHTTPServer(socketserver.ThreadingMixIn,
                          http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start(port: int, host: str = "0.0.0.0") -> None:
    global _server, _server_thread, _started
    if _started:
        return
    _server = _ThreadedHTTPServer((host, port), _MetricsHandler)
    _server_thread = threading.Thread(
        target=_server.serve_forever,
        name="metrics-http",
        daemon=True)
    _server_thread.start()
    _started = True
    logger.info("Metrics endpoint listening on http://%s:%d/metrics",
                host, port)


def start_if_configured(port: int) -> None:
    if port <= 0:
        return
    try:
        start(port)
    except OSError as e:
        logger.error("Metrics endpoint disabled: could not bind port %d (%s).",
                     port, e)


def stop() -> None:
    global _server, _server_thread, _started
    if _server is None:
        return
    _server.shutdown()
    _server.server_close()
    _server = None
    _server_thread = None
    _started = False


if __name__ == "__main__":  # pragma: no cover
    incr("test_counter")
    incr("test_counter")
    incr("exceptions_total", tag="ValueError")
    set_gauge("live_avatars", 4)
    add_provider("ad_hoc_sample", lambda: {"hello": "world"})
    logger.info("%s", json.dumps(_snapshot(), indent=2, default=str))
