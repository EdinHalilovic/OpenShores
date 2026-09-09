
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.static_tables import (
    already_sent as _repo_already_sent,
    mark_sent as _repo_mark_sent,
)

logger = get_logger(__name__)


async def _static_tables_already_sent(conn, peer) -> bool:
    key = _static_tables_key(peer)
    if not key:
        return False
    try:
        return await _repo_already_sent(conn, key)
    except Exception as exc:
        logger.warning("[scene]   static-table gate unreadable (%r); "
                       "streaming", exc)
        return False


async def _static_tables_mark_sent(conn, peer) -> None:
    key = _static_tables_key(peer)
    if not key:
        return
    try:
        await _repo_mark_sent(conn, key)
    except Exception as exc:
        logger.warning("[scene]   static-table mark failed: %r", exc)


def _static_tables_key(peer) -> str:
    try:
        if isinstance(peer, (tuple, list)) and peer:
            return str(peer[0])
        return str(peer or "")
    except Exception:
        return ""
