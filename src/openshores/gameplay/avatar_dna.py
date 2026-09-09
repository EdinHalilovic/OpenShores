
from __future__ import annotations

from openshores.core.logging import get_logger

logger = get_logger(__name__)


async def _dna_for_actor(conn, actor_auid: int = 0, *,
                        resolve_avatar_record,
                        last_avatar_dna: bytes) -> bytes:
    if int(actor_auid or 0):
        try:
            rec = await resolve_avatar_record(conn, int(actor_auid))
            if rec and rec.dna and len(rec.dna) >= 24:
                return bytes(rec.dna[:24])
        except Exception as exc:
            logger.warning('DNA lookup for actor 0x%08x failed (%r).', int(actor_auid) & 0xFFFFFFFF, exc)
    return last_avatar_dna
