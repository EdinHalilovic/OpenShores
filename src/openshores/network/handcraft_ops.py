
from __future__ import annotations

import struct

from openshores.core.logging import get_logger
from openshores.gameplay import gear_wear
from openshores.gameplay.gear_slots import _add_gear_item
from openshores.gameplay.handcraft import (
    _COMMODITY_ELECTRICITY,
    _COMMODITY_MONEY,
    _TORCH_CIDS,
    _TYPEID_ITEM,
    _VEHICLE_CIDS,
    _actor_parent_world,
    _find_by_cid,
    _load_recipes,
    _persist,
    _player_current_industry,
    _remove_locs,
    _wear_tool,
    _zone_quality_for,
    compute_output_quality,
)
from openshores.network.flag_spawn import spawn_world_flag

logger = get_logger(__name__)


async def on_handcraft(payload: bytes, actor: int, *, conn, _get_augear,
                       industry_hooks, _person_zone,
                       _push_augear_refresh_for, grant_crafted_vehicle,
                       alloc_daitem_auid, _tock_state, _live_avatars,
                       _DROPPED_ITEMS, _DYNAMIC_SCENE_AUIDS) -> None:
    if len(payload) < 5:
        logger.warning(f"0x76 short packet {bytes(payload).hex()}")
        return

    actor_i = int(actor) & 0xFFFFFFFF
    if not actor_i:
        logger.warning("0x76: no actor"); return
    mpid = struct.unpack_from(">I", payload, 1)[0]
    procs, comps = _load_recipes()
    rec = procs.get(mpid)
    if rec is None:
        logger.warning(f"0x76 unknown mpid {mpid} ({bytes(payload).hex()})")
        return
    name = rec.get("name", f"mpid{mpid}")
    craft = int(rec.get("craft", 0))
    idi = int(rec.get("idi", 0)) & 0xFFFF
    if craft == 0:
        logger.info(f"Mpid {mpid} ({name}) is not handcraftable (craft=0)")
        return
    if craft == 2:
        ind, _in_building = _player_current_industry(
            actor_i, industry_hooks=industry_hooks)
        if ind is None:
            logger.warning(f"Mpid {mpid} ({name}) craft=2 needs industry {idi}.")
        elif ind != idi:
            logger.info(f"Mpid {mpid} ({name}) craft=2: not standing in correct industry (need {idi}, in {ind}) -> reject")
            return
        else:
            logger.debug(f"Mpid {mpid} ({name}) craft=2: industry {idi} OK")
    out_cid = int(rec.get("out", 0)) & 0xFFFF
    out_qty = max(1, int(rec.get("qty", 1)))
    gear = _get_augear(actor_i)

    ide5 = [c for c in comps.get(mpid, []) if int(c.get("ide", 0)) == 5]
    ingredients = [(int(c["cid"]) & 0xFFFF, int(c["consumed"]))
                   for c in ide5 if int(c["consumed"]) > 0]
    tools = [int(c["cid"]) & 0xFFFF for c in ide5 if int(c["consumed"]) == 0]

    consume_locs = []
    component_mins = []
    for cid, qty in ingredients:
        avail = [(loc, body) for loc, body in _find_by_cid(gear, cid)
                 if loc not in consume_locs]
        if len(avail) < qty:
            logger.info(f"Mpid {mpid} ({name}): need {qty}x cid {cid}, have {len(avail)} -> reject")
            return
        picked = avail[:qty]
        consume_locs.extend(loc for loc, _ in picked)
        if cid in (_COMMODITY_MONEY, _COMMODITY_ELECTRICITY):
            continue
        qmin = min(gear_wear.quality(body) for _, body in picked)
        component_mins.append((qmin, qty))

    tool_locs = []
    tool_qualities = []
    for cid in tools:
        found = _find_by_cid(gear, cid)
        if not found:
            logger.info(f"Mpid {mpid} ({name}): missing tool cid {cid} -> reject")
            return
        tool_locs.append(cid)
        tool_qualities.append(gear_wear.quality(found[0][1]))

    _remove_locs(gear, consume_locs)

    worn = []
    for cid in tool_locs:
        found = _find_by_cid(gear, cid)
        if not found:
            continue
        code, destroyed, before, after = _wear_tool(gear, found[0][0])
        worn.append((cid, before, after, destroyed))
        if destroyed:
            logger.info(f"Tool cid {cid} broke (condition reached 0)")

    zone_q = await _zone_quality_for(actor_i, out_cid,
                                     _person_zone=_person_zone)
    out_q = compute_output_quality(out_cid, component_mins, tool_qualities,
                                   zone_quality=zone_q)

    granted, dropped = await _grant_output(
        actor_i, gear, out_cid, out_qty, out_q,
        grant_crafted_vehicle=grant_crafted_vehicle,
        alloc_daitem_auid=alloc_daitem_auid, _tock_state=_tock_state,
        _live_avatars=_live_avatars, _DROPPED_ITEMS=_DROPPED_ITEMS,
        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)

    logger.info(f"mpid {mpid} ({name}) APPLY actor=0x{actor_i:08x}: "
                f"out cid {out_cid} x{granted}"
                + (f" (+{dropped} dropped)" if dropped else "")
                + f" Q{out_q} "
                f"[components={component_mins} zone_q={zone_q} tools={tool_qualities}]; "
                f"consumed {ingredients}; tools worn "
                + ", ".join(f"cid{c}:{b}->{a}{' BROKE' if d else ''}"
                            for c, b, a, d in worn))

    try:
        await _push_augear_refresh_for(actor_i, log_prefix="handcraft")
    except Exception as exc:
        logger.error(f"AuGear refresh err: {exc!r}")
    try:
        await _persist(conn, actor_i, gear)
    except Exception as exc:
        logger.error(f"Persist skipped: {exc!r}")


async def _grant_output(actor_i, gear, out_cid, out_qty, out_q, *,
                        grant_crafted_vehicle, alloc_daitem_auid,
                        _tock_state, _live_avatars, _DROPPED_ITEMS,
                        _DYNAMIC_SCENE_AUIDS):
    granted = dropped = 0

    if int(out_cid) in _VEHICLE_CIDS:
        auid = await grant_crafted_vehicle(actor_i, int(out_cid),
                                           quality=int(out_q))
        if auid is None:
            logger.error(f"Vehicle cid {out_cid} could not be placed.")
            return 0, 0
        logger.info(f"Vehicle cid {out_cid} spawned as 0x{auid:08x} and mounted")
        return 1, 0

    if int(out_cid) in _TORCH_CIDS:
        parent = _actor_parent_world(actor_i, _tock_state=_tock_state,
                                     _live_avatars=_live_avatars)
        if parent is None:
            logger.error(f"Torch/fire cid {out_cid}: no parent world for 0x{actor_i:08x}.")
            return 0, 0
        for _ in range(out_qty):
            try:
                auid = await spawn_world_flag(
                    actor_i, parent, flag_cid=int(out_cid), quality=int(out_q),
                    alloc_daitem_auid=alloc_daitem_auid,
                    _tock_state=_tock_state, _live_avatars=_live_avatars,
                    _DROPPED_ITEMS=_DROPPED_ITEMS,
                    _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
            except Exception as exc:
                logger.error(f"Torch drop err: {exc!r}")
                break
            if auid is None:
                break
            dropped += 1
        return 0, dropped

    for _ in range(out_qty):
        body = bytes([0x04]) + struct.pack(">H", int(out_cid) & 0xFFFF) \
            + bytes([100, int(out_q) & 0xFF])
        st, _sub = _add_gear_item(gear, _TYPEID_ITEM, body)
        if st is None:
            parent = _actor_parent_world(actor_i, _tock_state=_tock_state,
                                         _live_avatars=_live_avatars)
            if parent is None:
                logger.error(f"No gear room for cid {out_cid} and no parent world to drop it on (granted {granted}/{out_qty})")
                break
            try:
                auid = await spawn_world_flag(
                    actor_i, parent, flag_cid=int(out_cid), quality=int(out_q),
                    alloc_daitem_auid=alloc_daitem_auid,
                    _tock_state=_tock_state, _live_avatars=_live_avatars,
                    _DROPPED_ITEMS=_DROPPED_ITEMS,
                    _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
            except Exception as exc:
                logger.error(f"Overflow drop err: {exc!r}")
                break
            if auid is None:
                break
            dropped += 1
            continue
        granted += 1
    return granted, dropped
