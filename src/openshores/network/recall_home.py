
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.person import read_spawn_record
from openshores.gameplay.agent_powers import _actor_entry
from openshores.network.agent import _longlat_to_xyz, notify, teleport_actor

logger = get_logger(__name__)


async def _execute_recall_home(actor_auid: int, *, conn, live_avatars,
                               agent_bits, manifest_suppress,
                               force_scene_manifest_push,
                               peer_upright_euler, _stamina_byte,
                               retarget_bundle_to_avatar,
                               broadcast_to_peers) -> bool:
    actor = int(actor_auid) & 0xFFFFFFFF
    if not actor:
        logger.warning("No actor auid; ignoring")
        return False
    _TELEPORT_KW = dict(
            manifest_suppress=manifest_suppress,
            force_scene_manifest_push=force_scene_manifest_push,
            peer_upright_euler=peer_upright_euler,
            _stamina_byte=_stamina_byte,
            retarget_bundle_to_avatar=retarget_bundle_to_avatar,
            broadcast_to_peers=broadcast_to_peers)

    row = None
    try:
        row = await read_spawn_record(conn, actor)
    except Exception as exc:
        logger.warning("Spawn lookup failed: %r", exc)
        return False
    if row is None:
        logger.warning("0x%08x has no a_Person row", actor)
        return False

    (city, city_name, sx, sy, ship, ship_name, berth,
     arena_in, arena_parent, ax, ay, az) = row
    logger.info("0x%08x spawn record: city=%r (%r) lonlat=(%r,%r) ship=%r "
                "(%r) berth=%r arena=%r",
                actor, city, city_name, sx, sy, ship, ship_name, berth,
                arena_in)

    if arena_in and arena_parent and None not in (ax, ay, az):
        ok = await teleport_actor(
            conn, live_avatars, agent_bits, actor,
            (float(ax), float(ay), float(az)),
            int(arena_parent) & 0xFFFFFFFF, label="recall:arena-exit",
            **_TELEPORT_KW)
        await notify(live_avatars, actor, "You have left the arena.")
        return bool(ok)

    if ship:
        logger.info('0x%08x has a berth on ship %r but berths are not implemented.', actor, ship)
        await notify(
            live_avatars, actor,
            "Your berth cannot be reached from here yet.")

    if city and sx is not None and sy is not None:
        entry = _actor_entry(live_avatars, actor)
        if entry is None:
            logger.warning("0x%08x is not in a scene", actor)
            return False
        xyz = _longlat_to_xyz(entry, float(sx), float(sy))
        if xyz is None:
            await notify(live_avatars, actor,
                         "You must be on a world to recall.")
            return False
        ok = await teleport_actor(conn, live_avatars, agent_bits, actor,
                                  xyz, 0, label="recall:home-city",
                                  **_TELEPORT_KW)
        if ok:
            await notify(
                live_avatars, actor,
                f"Recalled to {city_name or 'your home city'}.")
        return bool(ok)

    logger.info("0x%08x has no declared home; nothing to recall to", actor)
    await notify(
        live_avatars, actor,
        "You have not declared a home. Use Declare Home City first.")
    return False
