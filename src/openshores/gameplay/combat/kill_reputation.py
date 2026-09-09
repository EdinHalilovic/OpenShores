
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.person import (
    update_person_state as _ups_rep,
)
from openshores.gameplay.reputation import (
    political_stance,
    reputation_delta_for_kill,
)
from openshores.gameplay.stance import STANCE_NAMES
from openshores.protocol.auid import _as_auid

logger = get_logger(__name__)


async def _award_kill_reputation(conn, victim_auid, killer_auid, *,
                                 tock_state,
                                 _CITIZEN_EMPIRE_OVERRIDE) -> int:
    try:
        killer = int(killer_auid) & 0xFFFFFFFF
        victim = int(victim_auid) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return 0
    if not killer or killer == victim:
        return 0
    stance = await political_stance(
        conn, killer, victim,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    delta = reputation_delta_for_kill(stance)
    if delta == 0:
        logger.debug("0x%08x killed 0x%08x (stance %s): no change",
                     killer, victim, STANCE_NAMES.get(stance, stance))
        return 0
    entry = tock_state.setdefault(killer, {})
    cur = int(entry.get("reputation") or 0)
    new = cur + delta
    entry["reputation"] = new
    try:
        await _ups_rep(conn, killer, social=new)
    except Exception as exc:
        logger.warning("Persist failed for 0x%08x: %r", killer, exc)
    logger.info("0x%08x killed 0x%08x (stance %s): reputation %d -> %d",
                killer, victim, STANCE_NAMES.get(stance, stance), cur, new)
    return delta


def _attacker_world_auid(attacker_auid=0, *,
                         _live_avatars,
                         world_atom_auids) -> int:
    try:
        _entry = _live_avatars.get(int(attacker_auid or 0) & 0xFFFFFFFF)
        _parent_world = (_entry or {}).get("parent_world")
        if _parent_world:
            _pw = _as_auid(_parent_world)
            if _pw in world_atom_auids:
                return _pw
    except Exception:
        logger.warning("Parent world for attacker %r could not be read.", attacker_auid)
    for _w in world_atom_auids:
        return int(_w) & 0xFFFFFFFF
    return 0
