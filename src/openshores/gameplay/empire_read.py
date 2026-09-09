from __future__ import annotations

import struct
from typing import Optional, Tuple

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import empire_for_avatar

logger = get_logger(__name__)


async def _empire_for(conn, actor: int, *,
                      _CITIZEN_EMPIRE_OVERRIDE) -> int:
    try:
        return int(await empire_for_avatar(
            conn, int(actor),
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    except Exception:
        logger.warning("Empire for actor %r could not be resolved; "
                       "reading 0.", actor)
        return 0


def _office_tail(body: bytes) -> Tuple[Optional[int], Optional[str]]:
    end = len(body)
    n = (end - 8) & ~1
    while n >= 0:
        lp = end - 4 - n
        if lp >= 8 and struct.unpack_from(">I", body, lp)[0] == n:
            role = struct.unpack_from(">I", body, lp - 4)[0]
            try:
                return role, body[lp + 4:end].decode("utf-16-be")
            except Exception:
                logger.debug('Office tail candidate at %d does not decode as UTF-16BE.', lp)
        n -= 2
    return None, None
