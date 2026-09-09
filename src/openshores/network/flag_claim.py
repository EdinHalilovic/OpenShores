
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import (
    empire_for_avatar,
    found_empire,
)
from openshores.database.repositories.world import (
    claim_world,
    world_claim_state,
    world_exists,
)
from openshores.network.flag_spawn import spawn_world_flag

logger = get_logger(__name__)


_FLAG_CLAIM_CODES = frozenset({0x9A, 0x9C})


async def _maybe_flag_claim(actor_auid, action, arg, target, hit_target,
                            aim_x, aim_y, *, _SAVE,
                            _FLAG_CLAIM_CANDIDATE_SEEN, conn,
                            _CITIZEN_EMPIRE_OVERRIDE, alloc_daitem_auid,
                            _tock_state, _live_avatars, _DROPPED_ITEMS,
                            _DYNAMIC_SCENE_AUIDS) -> bool:
    a = int(action) & 0xFF
    if a < 0x64 or a > 0xAB:
        return False
    hit = int(hit_target) & 0xFFFFFFFF
    codes = _FLAG_CLAIM_CODES
    if a not in codes:
        if a not in _FLAG_CLAIM_CANDIDATE_SEEN:
            _FLAG_CLAIM_CANDIDATE_SEEN.add(a)
            logger.debug("CANDIDATE player-CI action=0x%02x arg=0x%04x "
                         "hit=0x%08x aim=(%.2f,%.2f) actor=0x%08x",
                         a, int(arg) & 0xFFFF, hit, aim_x, aim_y,
                         int(actor_auid) & 0xFFFFFFFF)
        return False
    person = int(actor_auid) & 0xFFFFFFFF
    world = hit if await world_exists(conn, hit) else 0
    if not world:
        world = int(_SAVE.planet_auid) & 0xFFFFFFFF
    if not world:
        logger.info("action=0x%02x: no world to claim (hit=0x%08x)", a, hit)
        return True
    cb, ci = await world_claim_state(conn, world)
    if cb or ci:
        logger.info("World 0x%08x already claimed (person 0x%08x / empire 0x%08x); ignoring", world, cb, ci)
        return True
    empire = int(await empire_for_avatar(
        conn, person,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    if not empire:
        empire = int(await found_empire(
            conn, person, "",
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE) or 0) & 0xFFFFFFFF
        logger.info("Free avatar 0x%08x founded empire 0x%08x before claiming",
                    person, empire)
    if not empire:
        logger.info("No empire for 0x%08x; cannot claim", person)
        return True
    ok = await claim_world(conn, person, empire, world, lon=float(aim_x),
                           lat=float(aim_y), empire_name="")
    logger.info("action=0x%02x CLAIM result=%s world=0x%08x empire=0x%08x",
                a, ok, world, empire)
    if ok:
        try:
            await spawn_world_flag(
                person, world, alloc_daitem_auid=alloc_daitem_auid,
                _tock_state=_tock_state, _live_avatars=_live_avatars,
                _DROPPED_ITEMS=_DROPPED_ITEMS,
                _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
        except Exception as _fe:
            logger.warning("Flag spawn err: %r", _fe)
    return True
