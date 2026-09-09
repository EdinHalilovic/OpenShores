
from __future__ import annotations

import time as _lt

from openshores.core.logging import get_logger
from openshores.gameplay.dispatch import register

logger = get_logger(__name__)


@register(0x18)
async def handle_0x18_lookat(session, payload: bytes, *,
                             _DROPPED_ITEMS) -> None:
    if len(payload) < 5:
        return
    tgt = int.from_bytes(payload[1:5], "big")
    _now_lt = _lt.monotonic()
    if tgt != session.lookat_target_auid:
        if tgt in _DROPPED_ITEMS:
            logger.debug("Reticle moved onto dropped item 0x%08x, was "
                         "0x%08x.", tgt, session.lookat_target_auid)
        session.lookat_target_auid = tgt
        session.lookat_since_ts = _now_lt
