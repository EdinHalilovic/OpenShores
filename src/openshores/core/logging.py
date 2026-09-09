
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")

_LEVEL_ALIASES = {"WARN": "WARNING", "OFF": "CRITICAL", "NONE": "CRITICAL"}

_FORMAT = "%(asctime)s %(levelname)-7s %(name)-28s %(message)s"
_DATEFMT = "%H:%M:%S"

_log_handler: logging.StreamHandler | None = None


def configure(level: str = "INFO", stream=None,
              log_file: str | Path | None = None) -> None:
    name = _LEVEL_ALIASES.get(level.upper(), level.upper())
    if name not in LEVELS and name not in _LEVEL_ALIASES.values():
        raise ValueError(
            f"Unknown log level {level!r}; expected one of {', '.join(LEVELS)} (or {', '.join(sorted(_LEVEL_ALIASES))})")

    console = sys.stderr if stream is None else stream
    if isinstance(console, _Tee):
        console = console.stream

    handler = logging.StreamHandler(console)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, name))

    if log_file:
        install_file_log(log_file)
    elif _log_handler is not None:
        root.addHandler(_log_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class _Tee:

    def __init__(self, stream, fh):
        self._stream = stream
        self._fh = fh

    @property
    def stream(self):
        return self._stream

    def write(self, s):
        try:
            self._stream.write(s)
        except UnicodeEncodeError:
            self._stream.write(
                s.encode("ascii", "backslashreplace").decode("ascii"))
        self._fh.write(s)
        return len(s)

    def flush(self):
        self._stream.flush()
        self._fh.flush()

    def isatty(self):
        return self._stream.isatty()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install_file_log(path: str | Path) -> str:
    global _log_handler
    root = logging.getLogger()
    if _log_handler is not None:
        if _log_handler not in root.handlers:
            root.addHandler(_log_handler)
        return str(_log_handler.stream.name)

    fh = open(path, "a", encoding="utf-8", errors="backslashreplace",
              buffering=1)

    handler = logging.StreamHandler(fh)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    _log_handler = handler
    root.addHandler(handler)
    fh.write("\n==== server start %s ====\n"
             % time.strftime("%Y-%m-%d %H:%M:%S"))

    sys.stdout = _Tee(sys.stdout, fh)
    sys.stderr = _Tee(sys.stderr, fh)

    _prev_hook = sys.excepthook

    def _hook(exc_type, exc, tb):
        import traceback as _tb
        fh.write("\n==== UNHANDLED EXCEPTION %s ====\n"
                 % time.strftime("%Y-%m-%d %H:%M:%S"))
        _tb.print_exception(exc_type, exc, tb, file=fh)
        fh.flush()
        _prev_hook(exc_type, exc, tb)

    sys.excepthook = _hook
    return str(path)


