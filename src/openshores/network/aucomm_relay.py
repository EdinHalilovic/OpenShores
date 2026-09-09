
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.protocol.framing import write_framed
from openshores.world.chat_writer import _chat_only_writer

logger = get_logger(__name__)


async def _send_aucomm_to_avatar(target_auid: int, pkt: bytes, *,
                                 _live_avatars) -> bool:
    ent = _live_avatars.get(int(target_auid) & 0xFFFFFFFF)
    if not ent:
        return False
    w = _chat_only_writer(ent)
    if w is None:
        logger.warning('DROPPED AuComm for 0x%08x: no chat channel yet.',
                       int(target_auid) & 0xFFFFFFFF)
        return False
    try:
        await write_framed(w, pkt)
        return True
    except Exception as exc:
        logger.warning("Send to 0x%08x failed: %r",
                       int(target_auid) & 0xFFFFFFFF, exc)
        return False
