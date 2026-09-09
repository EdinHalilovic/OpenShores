
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import empire_for_avatar
from openshores.gameplay.stance import (
    STANCE_EMPIRE,
    STANCE_ENEMY,
    STANCE_NEUTRAL,
    STANCE_VASSAL,
)

logger = get_logger(__name__)


async def political_stance(conn, a_auid, b_auid, *,
                           _CITIZEN_EMPIRE_OVERRIDE) -> int:
    try:
        ea = int(await empire_for_avatar(
            conn, int(a_auid),
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE) or 0)
        eb = int(await empire_for_avatar(
            conn, int(b_auid),
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE) or 0)
    except Exception:
        logger.warning("Stance for (%r, %r) could not be resolved; reading NEUTRAL.",
                       a_auid, b_auid)
        return STANCE_NEUTRAL
    if not ea or not eb:
        return STANCE_NEUTRAL
    return STANCE_EMPIRE if ea == eb else STANCE_ENEMY


def reputation_delta_for_kill(stance: int) -> int:
    s = int(stance)
    if s == STANCE_ENEMY:
        return 1
    if s == STANCE_VASSAL:
        return 0
    return -1
