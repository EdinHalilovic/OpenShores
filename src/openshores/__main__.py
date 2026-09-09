
from __future__ import annotations

import asyncio
from dataclasses import replace
import sys

from openshores.core.config import Config
from openshores.core.logging import configure, get_logger
from openshores.root import (build_registry, report, serve,
                             unbound_boot_arguments)

logger = get_logger(__name__)

_CHECK = "--check-wiring"


def _flag_value(argv: list[str], flag: str) -> str | None:
    if flag not in argv:
        return None
    i = argv.index(flag)
    return argv[i + 1] if i + 1 < len(argv) else None


def _apply_cli_overrides(config: Config, argv: list[str]) -> Config:
    dep = config.deployment
    changed: dict[str, object] = {}

    host = _flag_value(argv, "--public-host")
    if host is not None:
        changed["public_host"] = host
        logger.info("[boot] PUBLIC_HOST overridden -> %s", host)

    probe = _flag_value(argv, "--probe")
    if probe is not None:
        changed["scene_probe"] = probe
        logger.info("[boot] SCENE_PROBE_NAME -> %s", probe)

    if "--show-acks" in argv:
        changed["show_acks"] = True
        logger.info("[boot] --show-acks: logging ACK opcodes 0x18/0x42")

    if not changed:
        return config
    return replace(config, deployment=replace(dep, **changed))


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    # Named before anything reads it, so find_gd and the rest agree with the
    # boot config about which file the server was configured from.
    Config.use(_flag_value(args, "--config"))
    config = Config.load()
    if _CHECK in args:
        configure()
        registry = build_registry(config=config, conn=None, pool=None,
                                  save=None, anchor=None)
        logger.info("[root] %s", report(registry))
        raise SystemExit(1 if unbound_boot_arguments(registry) else 0)
    configure(config.deployment.log_level)
    config = _apply_cli_overrides(config, args)
    try:
        asyncio.run(serve(config))
    except KeyboardInterrupt:
        logger.info("[boot] shutting down")


if __name__ == "__main__":
    main()
