
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.gameplay import damageable as _dmg
from openshores.gameplay import skinning as _skin
from openshores.gameplay.combat.impact import _victim_world_xyz
from openshores.gameplay.combat.kill_reputation import (
    _attacker_world_auid,
    _award_kill_reputation,
)
from openshores.gameplay.food import _CORPSE_LINGER_S
from openshores.gameplay.npc_body import _forget_npc_body
from openshores.gameplay.npc_obituary import _file_npc_obituary
from openshores.gameplay.story_state import (
    _retire_task_done,
    _stop_story_for_dead_npc,
)
from openshores.network.broadcast import _force_scene_manifest_push
from openshores.network.ground_items import _spawn_ground_item
from openshores.protocol.auid import _as_auid

logger = get_logger(__name__)


async def _on_npc_killed(conn, d, killer_auid, *,
                         tock_state,
                         _CITIZEN_EMPIRE_OVERRIDE,
                         _live_avatars,
                         alloc_daitem_auid,
                         _DROPPED_ITEMS,
                         _DYNAMIC_SCENE_AUIDS,
                         story_npcs,
                         idle_bodies,
                         spawned_buildings) -> None:
    _xp = _dmg.experience_points_for_killing(d)
    logger.info(f"[kill] 0x{killer_auid:08x} killed {d.kind} 0x{d.auid:08x} "
                f"({d.name!r}); worth {_xp} xp")
    if _xp and killer_auid:
        try:
            _k = int(killer_auid) & 0xFFFFFFFF
            _ke = tock_state.setdefault(_k, {})
            _ke["xp"] = int(_ke.get("xp") or 0) + int(_xp)
            logger.info(f"[kill-xp]  0x{_k:08x} +{_xp} xp -> {_ke['xp']}")
        except Exception as exc:
            logger.error(f"[kill-xp] award failed: {exc!r}")
    try:
        _file_npc_obituary(d, killer_auid, live_avatars=_live_avatars)
    except Exception as exc:
        logger.error(f"[obituary] filing failed: {exc!r}")
    try:
        _stop_story_for_dead_npc(d)
    except Exception as exc:
        logger.error(f"[story] could not stop on death: {exc!r}")
    if d.is_citizen and killer_auid:
        try:
            await _award_kill_reputation(
                conn, d.auid, killer_auid, tock_state=tock_state,
                _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
        except Exception as exc:
            logger.error(f"[kill-rep] npc attribution failed: {exc!r}")
    try:
        _t = asyncio.create_task(_retire_npc_body(
            d, alloc_daitem_auid=alloc_daitem_auid,
            _live_avatars=_live_avatars, _DROPPED_ITEMS=_DROPPED_ITEMS,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
            story_npcs=story_npcs, idle_bodies=idle_bodies,
            spawned_buildings=spawned_buildings))
        _t.add_done_callback(
            lambda t, _a=int(d.auid): _retire_task_done(t, _a))
    except Exception as exc:
        logger.error(f"[carcass] retire scheduling failed: {exc!r}")


async def _retire_npc_body(d, *,
                           alloc_daitem_auid,
                           _live_avatars,
                           _DROPPED_ITEMS,
                           _DYNAMIC_SCENE_AUIDS,
                           story_npcs,
                           idle_bodies,
                           spawned_buildings) -> int:
    if d is None:
        return 0
    auid = int(d.auid) & 0xFFFFFFFF
    linger = _CORPSE_LINGER_S
    if linger:
        await asyncio.sleep(linger)
    dropped = 0
    try:
        dropped = await _spawn_carcass_for(
            d, alloc_daitem_auid=alloc_daitem_auid,
            _live_avatars=_live_avatars, _DROPPED_ITEMS=_DROPPED_ITEMS,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
            story_npcs=story_npcs, idle_bodies=idle_bodies,
            spawned_buildings=spawned_buildings)
    except Exception as exc:
        logger.error(f"[carcass] drop for 0x{auid:08x} failed: {exc!r}")
    _forget_npc_body(auid, _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
    await _force_scene_manifest_push(
        f"0x{auid:08x} ({d.name!r}) died"
        + (f" -> DaItem 0x{dropped:08x}" if dropped else " -- dropped nothing"),
        _live_avatars=_live_avatars)
    logger.info(f"[carcass] {d.kind} 0x{auid:08x} ({d.name!r}) body retired "
                f"after {linger:.0f}s"
                + (f", replaced by DaItem 0x{dropped:08x}" if dropped
                   else " (nothing to drop)"))
    return dropped


async def _spawn_carcass_for(d, *,
                             alloc_daitem_auid,
                             _live_avatars,
                             _DROPPED_ITEMS,
                             _DYNAMIC_SCENE_AUIDS,
                             story_npcs,
                             idle_bodies,
                             spawned_buildings) -> int:
    if d is None:
        return 0
    if not (getattr(d, "is_corpse", False) and not getattr(d, "looted", True)):
        return 0
    drops = _skin.carcass_from_kill(d)
    if not drops:
        return 0
    xyz = _victim_world_xyz(d.auid, story_npcs=story_npcs,
                            idle_bodies=idle_bodies,
                            spawned_buildings=spawned_buildings) or getattr(
                                d, "xyz", None)
    if not xyz:
        logger.warning(f'[carcass] 0x{d.auid:08x} ({d.name!r}) died with no known position.')
        return 0
    world = int(getattr(d, "world_auid", 0) or 0) & 0xFFFFFFFF
    if not world:
        logger.warning(f"[carcass] 0x{d.auid:08x} has no world_auid. Nothing dropped")
        return 0
    if not _dmg.mark_looted(d.auid):
        return 0
    last = 0
    for cid, qty, quality in drops:
        for _ in range(max(1, int(qty))):
            try:
                last = await _spawn_ground_item(
                    parent_world_auid=world, xyz=xyz,
                    cid=int(cid), quality=int(quality),
                    tag="carcass", alloc_daitem_auid=alloc_daitem_auid,
                    _live_avatars=_live_avatars,
                    _DROPPED_ITEMS=_DROPPED_ITEMS,
                    _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS) or last
            except Exception as exc:
                logger.error(f"[carcass] drop failed for cid={cid}: {exc!r}")
    if last:
        logger.info(f"[carcass] {d.kind} 0x{d.auid:08x} ({d.name!r}) left "
                    f"{sum(q for _c, q, _q in drops)} carcass item(s) at "
                    f"{tuple(round(float(v), 1) for v in xyz)}")
    return last


async def _drop_player_corpse(auid, *,
                              alloc_daitem_auid,
                              _live_avatars,
                              _DROPPED_ITEMS,
                              _DYNAMIC_SCENE_AUIDS,
                              world_atom_auids) -> int:
    key = int(auid) & 0xFFFFFFFF
    entry = _live_avatars.get(key) or {}
    xyz = entry.get("xyz")
    world = _as_auid(entry.get("parent_world")) or _attacker_world_auid(
        key, _live_avatars=_live_avatars,
        world_atom_auids=world_atom_auids)
    if not xyz or not world:
        logger.warning(f'[death]     0x{key:08x} died with no known position/world (xyz={xyz!r} world=0x{world:08x}).')
        return 0
    try:
        dropped = await _spawn_ground_item(
            parent_world_auid=int(world), xyz=tuple(xyz),
            cid=int(_skin.CID_HEAD), quality=100, tag="corpse",
            alloc_daitem_auid=alloc_daitem_auid, _live_avatars=_live_avatars,
            _DROPPED_ITEMS=_DROPPED_ITEMS,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
    except Exception as exc:
        logger.error(f"[death]     corpse item failed: {exc!r}")
        return 0
    if dropped:
        logger.info(f"[death]     0x{key:08x} ({entry.get('name') or '?'}) left a "
                    f"body at {tuple(round(float(v), 1) for v in xyz)} "
                    f"-> DaItem 0x{int(dropped):08x}")
    return int(dropped or 0)
