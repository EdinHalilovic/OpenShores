
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import empire_for_avatar
from openshores.gameplay.demolish import _dev_distance, _nearest_development
from openshores.gameplay.development_lookup import (
    TOWN_SQUARE_CPID,
    _demolish_refuse_cpids,
    _find_development_by_bauid,
    _spawned_building_near,
)
from openshores.network.building_broadcast import _building_broadcast_stop
from openshores.network.city_atom import spawn_city_atom
from openshores.network.manufacture_ops import (
    _MFG_SUB_BUILDING,
    on_bd_run_process,
)
from openshores.network.road_ticker import (
    on_construction_fetch,
    on_construction_labor,
)
from openshores.protocol.empire_chat_parse import parse_chat_demolish
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


_WORK_BUTTON_SUBS = (0x65, 0x66)


async def _on_work_site_fetch(payload: bytes, actor: int, *, conn,
                              _SAVE, _city_buildings_blob_io,
                              _CITIZEN_EMPIRE_OVERRIDE, _city_identity,
                              resend_planet_geo, _get_augear,
                              _push_augear_refresh_for, _CITY_SIM,
                              _ZONE_CACHE, anchor_full, _live_avatars,
                              _SPAWNED_BUILDINGS, _SPAWNED_CITIES,
                              _DYNAMIC_SCENE_AUIDS,
                              _BUILDING_KEEPALIVE_TASKS,
                              _CITY_KEEPALIVE_TASKS) -> None:
    await on_construction_fetch(
        payload, actor,
        conn=conn, _SAVE=_SAVE,
        city_buildings_blob_io=_city_buildings_blob_io,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _city_identity=_city_identity,
        resend_planet_geo=resend_planet_geo, _get_augear=_get_augear,
        _push_augear_refresh_for=_push_augear_refresh_for,
        _CITY_SIM=_CITY_SIM, _ZONE_CACHE=_ZONE_CACHE,
        anchor_full=anchor_full, _live_avatars=_live_avatars,
        _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
        _SPAWNED_CITIES=_SPAWNED_CITIES,
        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
        _BUILDING_KEEPALIVE_TASKS=_BUILDING_KEEPALIVE_TASKS,
        _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)


async def _on_work_site_labor(payload: bytes, actor: int, *, conn,
                              _SAVE, _city_buildings_blob_io,
                              _CITIZEN_EMPIRE_OVERRIDE, _city_identity,
                              resend_planet_geo, _get_augear,
                              _push_augear_refresh_for, _CITY_SIM,
                              _ZONE_CACHE, anchor_full, _live_avatars,
                              _SPAWNED_BUILDINGS, _SPAWNED_CITIES,
                              _DYNAMIC_SCENE_AUIDS,
                              _BUILDING_KEEPALIVE_TASKS,
                              _CITY_KEEPALIVE_TASKS,
                              apply_construction_labor, _bd_row_by_auid) -> None:
    body = bytes(payload[1:])
    if len(body) >= 7 and body[0] == _MFG_SUB_BUILDING:
        await on_bd_run_process(
            payload, actor, conn=conn,
            _bd_row_by_auid=_bd_row_by_auid,
            _city_buildings_blob_io=_city_buildings_blob_io,
            _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
            _live_avatars=_live_avatars, _ZONE_CACHE=_ZONE_CACHE,
            _CITY_SIM=_CITY_SIM, anchor_full=anchor_full)
        return
    await on_construction_labor(
        payload, actor,
        conn=conn, _SAVE=_SAVE,
        city_buildings_blob_io=_city_buildings_blob_io,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _city_identity=_city_identity,
        resend_planet_geo=resend_planet_geo, _get_augear=_get_augear,
        _push_augear_refresh_for=_push_augear_refresh_for,
        _CITY_SIM=_CITY_SIM, _ZONE_CACHE=_ZONE_CACHE,
        anchor_full=anchor_full, _live_avatars=_live_avatars,
        _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
        _SPAWNED_CITIES=_SPAWNED_CITIES,
        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
        _BUILDING_KEEPALIVE_TASKS=_BUILDING_KEEPALIVE_TASKS,
        _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS,
        apply_construction_labor=apply_construction_labor)


_DEMOLISH_MAX_DIST_M = 100.0


def _demolish_forget_atom(bd_id, *, _SPAWNED_BUILDINGS,
                          _BUILDING_KEEPALIVE_TASKS,
                          _DYNAMIC_SCENE_AUIDS, _live_avatars):
    bd_id = int(bd_id) & 0xFFFFFFFF
    if not bd_id:
        return
    popped = _SPAWNED_BUILDINGS.pop(bd_id, None) is not None
    try:
        _building_broadcast_stop(
            bd_id, _BUILDING_KEEPALIVE_TASKS=_BUILDING_KEEPALIVE_TASKS)
    except Exception:
        logger.warning("[demolish] DaBd 0x%08x keepalive cancel failed",
                       bd_id, exc_info=True)
    try:
        _DYNAMIC_SCENE_AUIDS.discard(bd_id)
    except Exception:
        logger.warning("[demolish] DaBd 0x%08x scene-AuId discard "
                       "failed", bd_id, exc_info=True)
    logger.info('[demolish] DaBd 0x%08x keepalive %s.',
                bd_id, 'stopped' if popped else 'not running')

    async def _reemit_manifests():
        n = 0
        try:
            for _ent in list(_live_avatars.values()):
                _w = _ent.get("writer")
                _b = getattr(_w, "_scene_manifest_builder", None) if _w else None
                if not _b:
                    continue
                try:
                    await write_framed(_w, _b())
                    n += 1
                except Exception:
                    logger.warning("[demolish] scene manifest re-emit "
                                   "failed for one peer", exc_info=True)
        except Exception:
            logger.error("[demolish] scene manifest re-emit loop failed",
                         exc_info=True)
        if n:
            logger.info("[demolish] scene manifest re-emitted to %d "
                        "peer(s)", n)
    try:
        asyncio.get_running_loop().create_task(_reemit_manifests())
    except Exception:
        logger.debug("[demolish] no running loop; scene manifest not "
                     "re-emitted", exc_info=True)


async def on_chat_demolish(payload: bytes, actor: int, *, conn,
                           _SAVE, _CITIZEN_EMPIRE_OVERRIDE,
                           _demolish_db_lookup, _demolish_delete_bd_row,
                           _find_city_for_building, _city_identity,
                           _city_buildings_blob_io, resend_planet_geo,
                           _SPAWNED_BUILDINGS, _SPAWNED_CITIES,
                           _DYNAMIC_SCENE_AUIDS, _BUILDING_KEEPALIVE_TASKS,
                           _CITY_KEEPALIVE_TASKS, _live_avatars) -> None:
    actor_i = int(actor) & 0xFFFFFFFF
    try:
        d = parse_chat_demolish(payload)
    except Exception as exc:
        logger.error("[demolish] 0x02 parse err: %r raw=%s",
                     exc, bytes(payload[:64]).hex())
        return
    if d["leftover"]:
        logger.warning("[demolish] 0x02: %d leftover byte(s) past spec: "
                       "%s (continuing)",
                       d['leftover'], bytes(payload)[29:].hex())
    auid, pos = d["auid"], d["pos"]
    logger.info("[demolish] 0x02 actor=0x%08x target=0x%08x "
                "pos=(%.2f,%.2f,%.2f)",
                actor_i, auid, pos[0], pos[1], pos[2])
    emp = wld = 0
    try:
        emp = int(await empire_for_avatar(
            conn, actor_i,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    except Exception:
        logger.warning("[demolish] empire lookup failed for 0x%08x",
                       actor_i, exc_info=True)
    wld = int(_SAVE.planet_auid) & 0xFFFFFFFF
    kind, row = await _demolish_db_lookup(conn, auid)
    bd_id = 0
    if kind == "city":
        cid = int(row) & 0xFFFFFFFF
    elif kind == "building":
        bd_id = int(row["id"]) & 0xFFFFFFFF
        cid = int(row.get("capitol") or 0) & 0xFFFFFFFF
        if not cid:
            city = await _find_city_for_building(conn, wld, emp, pos)
            cid = int(city["id"]) & 0xFFFFFFFF if city else 0
        if all(k in row for k in ("locX", "locY", "locZ")):
            pos = [float(row["locX"]), float(row["locY"]), float(row["locZ"])]
    else:
        city = await _find_city_for_building(conn, wld, emp, pos)
        cid = int(city["id"]) & 0xFFFFFFFF if city else 0
        logger.warning("[demolish] AuId 0x%08x unknown; nearest-city "
                       "fallback -> 0x%08x", auid, cid)
    if not cid:
        logger.warning("[demolish] reject: no city resolved for the demolish point")
        return
    cap_auid, city_name, city_alleg = await _city_identity(conn, cid)
    if bd_id and bd_id == cap_auid:
        logger.warning("[demolish] refuse: target 0x%08x is city 0x%08x's capitol (city razing out of scope).",
                       bd_id, cid)
        return
    devs = await _city_buildings_blob_io(conn, cid)
    if not devs:
        logger.warning("[demolish] reject: city 0x%08x has no developments", cid)
        return
    idx = dev = dist = None
    if bd_id:
        idx, dev = _find_development_by_bauid(devs, bd_id)
        if idx is not None:
            dist = _dev_distance(dev, pos) or 0.0
            logger.info("[demolish] exact match: development[%d] "
                        "bauid=0x%08x cpid=%s (%.1f m from the click)",
                        idx, bd_id, dev.get('cpid'), dist)
    if idx is None and bd_id:
        idx, dev, dist = _nearest_development(devs, pos, buildings_only=True)
        if idx is not None:
            logger.info("[demolish] no bauid match for 0x%08x; nearest "
                        "BUILDING development[%d] at %.1f m",
                        bd_id, idx, dist)
    if idx is None:
        idx, dev, dist = _nearest_development(devs, pos)
    if idx is None:
        logger.warning("[demolish] reject: no development of city 0x%08x has usable coordinates", cid)
        return
    dkind = dev.get("kind", "building")
    if dist > _DEMOLISH_MAX_DIST_M:
        logger.warning("[demolish] reject: nearest development (%s cpid=%s) is %.1f m from the point (> %.0f m sanity limit)",
                       dkind, dev.get('cpid'), dist, _DEMOLISH_MAX_DIST_M)
        return
    _cpid = int(dev.get("cpid") or 0)
    if dkind == "building" and _cpid in _demolish_refuse_cpids():
        logger.warning("[demolish] refuse: nearest development is the %s (cpid 0x%02x, %.1f m). Demolishing it razes city 0x%08x.",
                       'Town Square' if _cpid == TOWN_SQUARE_CPID
                       else 'Capitol', _cpid, dist, cid)
        return

    def _drop(lst):
        if 0 <= idx < len(lst) and lst[idx] == dev:
            del lst[idx]
        else:
            for i, it in enumerate(lst):
                if it == dev:
                    del lst[i]
                    break
        return lst
    devs2 = await _city_buildings_blob_io(conn, cid, mutate=_drop)
    if len(devs2) >= len(devs):
        logger.error("[demolish] blob removal failed for city 0x%08x; "
                     "abort", cid)
        return

    deleted_bd = 0
    if dkind == "building":
        _near = dev.get("xyz") or pos
        deleted_bd = await _demolish_delete_bd_row(
            conn, bid=bd_id or None, near_xyz=_near, keep_id=cap_auid)
        _forget = (deleted_bd or bd_id
                   or _spawned_building_near(
                       _near, keep_id=cap_auid,
                       _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS))
        _demolish_forget_atom(
            _forget, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
            _BUILDING_KEEPALIVE_TASKS=_BUILDING_KEEPALIVE_TASKS,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
            _live_avatars=_live_avatars)

    logger.info("[demolish] removed %s (cpid=%s, %.1f m) from city "
                "0x%08x; a_Bd row %s; %d development(s) remain",
                dkind, dev.get('cpid'), dist, cid,
                ('0x%08x deleted' % deleted_bd) if deleted_bd else 'none',
                len(devs2))

    _bldgs = [b for b in devs2 if b.get("kind", "building") == "building"]
    _roads = [b for b in devs2 if b.get("kind") == "road"]
    try:
        _cxyz = None
        try:
            _crow = await _find_city_for_building(conn, wld, emp, pos)
            if _crow and (int(_crow["id"]) & 0xFFFFFFFF) == cid:
                _cxyz = (_crow["x"], _crow["y"], _crow["z"])
        except Exception:
            logger.warning("[demolish] city row lookup failed for the "
                           "DaCity re-emit position", exc_info=True)
        if _cxyz is None:
            _sc = _SPAWNED_CITIES.get(cid)
            _cxyz = _sc["xyz"] if _sc else tuple(pos)
        await spawn_city_atom(cid, wld, _cxyz, _bldgs,
                              roads=_roads, name=city_name,
                              empire=(city_alleg or emp),
                              is_capital=True, habitable_capital=True,
                              conn=conn, _live_avatars=_live_avatars,
                              _SPAWNED_CITIES=_SPAWNED_CITIES,
                              _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                              _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
        logger.info("[demolish] re-emitted DaCity 0x%08x "
                    "(%d bld, %d road)", cid, len(_bldgs), len(_roads))
    except Exception as _rexc:
        logger.error("[demolish] DaCity re-emit err: %r", _rexc)
    try:
        await resend_planet_geo(wld, reason="demolish")
    except Exception as _gexc:
        logger.error("[demolish] geo re-emit err: %r", _gexc)
