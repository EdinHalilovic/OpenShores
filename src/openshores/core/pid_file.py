
from __future__ import annotations

import atexit
import os
from pathlib import Path

from openshores.core.logging import get_logger

logger = get_logger(__name__)


def _clear_pid_file(path: Path, pid: int) -> None:
    try:
        if path.exists() and path.read_text().strip() == str(pid):
            path.unlink()
    except Exception as exc:
        logger.debug("[stats] could not clear %s: %r", path, exc)


def install_pid_file(pid_file: str | Path) -> Path | None:
    if not pid_file:
        return None
    pid = os.getpid()
    try:
        path = Path(pid_file).resolve()
        path.write_text(str(pid))
        atexit.register(_clear_pid_file, path, pid)
    except Exception as exc:
        logger.warning("[stats] pid-file drop failed: %r", exc)
        return None
    logger.info("[stats] pid %d -> %s", pid, path)
    return path
