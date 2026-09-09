
from __future__ import annotations

import asyncio
from functools import partial

from openshores.core.logging import get_logger
from openshores.gameplay import construction_labor
from openshores.gameplay.blueprint_lookup import _work_site_loc
from openshores.gameplay.construction_process import (
    construction_percent,
    construction_step,
)
from openshores.gameplay.construction_site import _active_construction_job
from openshores.gameplay.gear_entry import _gear_cid_of
from openshores.gameplay.road_construction import (
    _ROAD_COMPEFFECT_MATERIAL,
    _ROAD_INSTANT_BUILD,
    _find_road_construction_job,
    _iter_road_construction_jobs,
    _road_job_complete_and_reemit,
    make_labor_accessors,
)
from openshores.gameplay.roads import _ROAD_AUTO_SUPPLY_ENABLED
from openshores.network.city_atom import spawn_city_atom
from openshores.network.construction_fetch import fetch_construction_materials

logger = get_logger(__name__)


_ROAD_TICKER_TASK = None


def ensure_road_construction_ticker(*, conn, _SAVE,
                                    city_buildings_blob_io, _city_identity,
                                    resend_planet_geo, _live_avatars,
                                    _SPAWNED_CITIES, _DYNAMIC_SCENE_AUIDS,
                                    _CITY_KEEPALIVE_TASKS):
    global _ROAD_TICKER_TASK
    if _ROAD_TICKER_TASK is not None and not _ROAD_TICKER_TASK.done():
        return
    try:
        _ROAD_TICKER_TASK = asyncio.get_running_loop().create_task(
            _road_construction_ticker(
                conn=conn, _SAVE=_SAVE,
                city_buildings_blob_io=city_buildings_blob_io,
                _city_identity=_city_identity,
                resend_planet_geo=resend_planet_geo,
                _live_avatars=_live_avatars,
                _SPAWNED_CITIES=_SPAWNED_CITIES,
                _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS))
        logger.info("Road construction ticker started.")
    except RuntimeError:
        _ROAD_TICKER_TASK = None


async def _road_construction_ticker(*, conn, _SAVE,
                                    city_buildings_blob_io, _city_identity,
                                    resend_planet_geo, _live_avatars,
                                    _SPAWNED_CITIES, _DYNAMIC_SCENE_AUIDS,
                                    _CITY_KEEPALIVE_TASKS):
    interval = 5.0
    while True:
        await asyncio.sleep(interval)
        jobs = [job async for job in _iter_road_construction_jobs(
            conn=conn, _SAVE=_SAVE,
            city_buildings_blob_io=city_buildings_blob_io)]
        if not jobs:
            logger.info("Road construction ticker: no jobs left; stopped.")
            return
        auto = _ROAD_AUTO_SUPPLY_ENABLED
        instant = _ROAD_INSTANT_BUILD
        if not (auto or instant):
            continue
        labor_per = 2
        mat_frac = 0.34
        touched = {}
        for cid, city, dev in jobs:
            st = dev["cstate"]
            if instant:
                st["labor"] = 0
                for comp in st["components"]:
                    if comp[2] == 5 and comp[3] > 0:
                        comp[4] = comp[3]
            else:
                construction_step(st, labor_per, mat_frac)
            done = await _road_job_complete_and_reemit(
                cid, dev, conn=conn,
                city_buildings_blob_io=city_buildings_blob_io)
            pct = construction_percent(st)
            logger.info("Tick %s %s %d%% labor=%s%s (city 0x%08x)",
                        dev.get('kind'), dev.get('rid'), pct, st['labor'],
                        ' COMPLETE' if done else '', cid)
            touched[cid] = city
        for cid, city in touched.items():
            await _reemit_road_city(
                cid, city, conn=conn, _SAVE=_SAVE,
                city_buildings_blob_io=city_buildings_blob_io,
                _city_identity=_city_identity,
                resend_planet_geo=resend_planet_geo,
                _live_avatars=_live_avatars,
                _SPAWNED_CITIES=_SPAWNED_CITIES,
                _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)


async def _reemit_road_city(cid, city, reason="road-change", *, conn,
                            _SAVE, city_buildings_blob_io,
                            _city_identity, resend_planet_geo, _live_avatars,
                            _SPAWNED_CITIES, _DYNAMIC_SCENE_AUIDS,
                            _CITY_KEEPALIVE_TASKS):
    wld = int(_SAVE.planet_auid) & 0xFFFFFFFF
    devs = await city_buildings_blob_io(conn, cid)
    b = [x for x in devs if x.get("kind", "building") == "building"]
    r = [x for x in devs if x.get("kind") == "road"]
    _, _cnm, _calleg = await _city_identity(conn, cid)
    try:
        await spawn_city_atom(cid, wld, (city["x"], city["y"], city["z"]),
                              b, roads=r, name=_cnm,
                              empire=(_calleg or int(city.get("empire", 0))),
                              is_capital=True, habitable_capital=True,
                              conn=conn, _live_avatars=_live_avatars,
                              _SPAWNED_CITIES=_SPAWNED_CITIES,
                              _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                              _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
    except Exception as exc:
        logger.error("City 0x%08x DaCity re-emit failed: %r", cid, exc)
    try:
        await resend_planet_geo(wld, reason=reason)
    except Exception as exc:
        logger.error("Planet 0x%08x geo re-emit failed: %r", wld, exc)


def _push_gear_refresh(actor_auid, *, _push_augear_refresh_for):
    try:
        asyncio.get_running_loop().create_task(
            _push_augear_refresh_for(actor_auid, log_prefix="gear-wear"))
    except RuntimeError:
        logger.debug("No running loop; the gear view for 0x%08x is refreshed "
                     "by the next push instead.", int(actor_auid) & 0xFFFFFFFF)
    except Exception as exc:
        logger.error("Gear refresh for 0x%08x failed: %r",
                     int(actor_auid) & 0xFFFFFFFF, exc)


async def _road_apply_labor(actor_auid, units=0, *, conn, _SAVE,
                            city_buildings_blob_io, _CITIZEN_EMPIRE_OVERRIDE,
                            _city_identity, resend_planet_geo, _get_augear,
                            _CITY_SIM, _push_augear_refresh_for,
                            _live_avatars, _SPAWNED_CITIES,
                            _DYNAMIC_SCENE_AUIDS, _CITY_KEEPALIVE_TASKS):
    job = await _find_road_construction_job(
        actor_auid, conn=conn, _SAVE=_SAVE,
        city_buildings_blob_io=city_buildings_blob_io,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if job is None:
        return False
    cid, city, dev = job
    st = dev["cstate"]
    comps = st.get("components") or []
    if units <= 0:
        p_has, p_use, c_has, c_use, power = make_labor_accessors(
            actor_auid, cid, _get_augear=_get_augear, _CITY_SIM=_CITY_SIM,
            _push_gear_refresh=partial(
                _push_gear_refresh,
                _push_augear_refresh_for=_push_augear_refresh_for))
        units, blocked = construction_labor.labor_units_for_work(
            comps, player_has=p_has, player_use=p_use,
            city_has=c_has, city_use=c_use, city_power=power)
        if blocked:
            logger.warning("%s blocked: required %s not in worker gear or city 0x%08x stock. No labor applied (%s)",
                           dev.get('rid'), [hex(b) for b in blocked], cid,
                           construction_labor.describe(comps))
            return False
    before, after, applied = construction_labor.apply_labor(st, units)
    if applied <= 0:
        return False
    done = await _road_job_complete_and_reemit(
        cid, dev, conn=conn, city_buildings_blob_io=city_buildings_blob_io)
    pct = construction_percent(st)
    logger.info("%s %s labor %s->%s (-%s) (%d%%)%s on city 0x%08x",
                dev.get('kind'), dev.get('rid'), before, after, applied, pct,
                ' COMPLETE' if done else '', cid)
    await _reemit_road_city(
        cid, city, conn=conn, _SAVE=_SAVE,
        city_buildings_blob_io=city_buildings_blob_io,
        _city_identity=_city_identity, resend_planet_geo=resend_planet_geo,
        _live_avatars=_live_avatars, _SPAWNED_CITIES=_SPAWNED_CITIES,
        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
        _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
    return True


async def _road_fetch_materials(actor_auid, *, conn, _SAVE,
                                city_buildings_blob_io,
                                _CITIZEN_EMPIRE_OVERRIDE, _city_identity,
                                resend_planet_geo, _get_augear,
                                _push_augear_refresh_for, _live_avatars,
                                _SPAWNED_CITIES, _DYNAMIC_SCENE_AUIDS,
                                _CITY_KEEPALIVE_TASKS):
    job = await _find_road_construction_job(
        actor_auid, conn=conn, _SAVE=_SAVE,
        city_buildings_blob_io=city_buildings_blob_io,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if job is None:
        return False
    cid, city, dev = job
    st = dev["cstate"]
    gear = _get_augear(actor_auid)
    moved = 0
    for comp in st["components"]:
        c_cid, b2, eff, req, applied = comp
        if eff != _ROAD_COMPEFFECT_MATERIAL or req <= 0 or applied >= req:
            continue
        need = req - applied
        avail = [e for e in gear
                 if int(e[2]) == 0x01 and _gear_cid_of(e) == c_cid]
        take = min(need, len(avail))
        if take > 0:
            drop = set(id(e) for e in avail[:take])
            gear[:] = [e for e in gear if id(e) not in drop]
            comp[4] = applied + take
            moved += take
            logger.info("%s fetched %dx cid0x%x (%s/%s) from 0x%08x gear",
                        dev.get('rid'), take, c_cid, comp[4], req,
                        actor_auid & 0xFFFFFFFF)
    if not moved:
        return False
    done = await _road_job_complete_and_reemit(
        cid, dev, conn=conn, city_buildings_blob_io=city_buildings_blob_io)
    try:
        await _push_augear_refresh_for(actor_auid, log_prefix="road-fetch")
    except Exception as exc:
        logger.error("Gear refresh for 0x%08x failed: %r",
                     actor_auid & 0xFFFFFFFF, exc)
    await _reemit_road_city(
        cid, city, conn=conn, _SAVE=_SAVE,
        city_buildings_blob_io=city_buildings_blob_io,
        _city_identity=_city_identity, resend_planet_geo=resend_planet_geo,
        _live_avatars=_live_avatars, _SPAWNED_CITIES=_SPAWNED_CITIES,
        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
        _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
    if done:
        logger.info("%s materials satisfied on 0x%08x", dev.get('rid'), cid)
    return True


async def on_construction_fetch(payload: bytes, actor: int, *, conn,
                                 _SAVE, city_buildings_blob_io,
                                 _CITIZEN_EMPIRE_OVERRIDE, _city_identity,
                                 resend_planet_geo, _get_augear,
                                 _push_augear_refresh_for, _CITY_SIM,
                                 _ZONE_CACHE, anchor_full, _live_avatars,
                                 _SPAWNED_BUILDINGS, _SPAWNED_CITIES,
                                 _DYNAMIC_SCENE_AUIDS,
                                 _BUILDING_KEEPALIVE_TASKS,
                                 _CITY_KEEPALIVE_TASKS) -> None:
    actor_i = int(actor) & 0xFFFFFFFF
    try:
        _work_site_loc(payload)
        if _active_construction_job(
                actor_i, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                _live_avatars=_live_avatars) is not None:
            await fetch_construction_materials(
                actor_i, _get_augear=_get_augear,
                _push_augear_refresh_for=_push_augear_refresh_for,
                _live_avatars=_live_avatars,
                _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                _BUILDING_KEEPALIVE_TASKS=_BUILDING_KEEPALIVE_TASKS,
                conn=conn, _CITY_SIM=_CITY_SIM, _ZONE_CACHE=_ZONE_CACHE,
                anchor_full=anchor_full)
        else:
            await _road_fetch_materials(
                actor_i,
                conn=conn, _SAVE=_SAVE,
                city_buildings_blob_io=city_buildings_blob_io,
                _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
                _city_identity=_city_identity,
                resend_planet_geo=resend_planet_geo, _get_augear=_get_augear,
                _push_augear_refresh_for=_push_augear_refresh_for,
                _live_avatars=_live_avatars,
                _SPAWNED_CITIES=_SPAWNED_CITIES,
                _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
    except Exception as exc:
        logger.error("0x74 work-site fetch for 0x%08x failed: %r",
                     actor_i, exc)


async def on_construction_labor(payload: bytes, actor: int, *, conn,
                                 _SAVE, city_buildings_blob_io,
                                 _CITIZEN_EMPIRE_OVERRIDE, _city_identity,
                                 resend_planet_geo, _get_augear,
                                 _push_augear_refresh_for, _CITY_SIM,
                                 _ZONE_CACHE, anchor_full, _live_avatars,
                                 _SPAWNED_BUILDINGS, _SPAWNED_CITIES,
                                 _DYNAMIC_SCENE_AUIDS,
                                 _BUILDING_KEEPALIVE_TASKS,
                                 _CITY_KEEPALIVE_TASKS,
                                 apply_construction_labor) -> None:
    actor_i = int(actor) & 0xFFFFFFFF
    try:
        _work_site_loc(payload)
        if _active_construction_job(
                actor_i, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                _live_avatars=_live_avatars) is not None:
            await apply_construction_labor(actor_i)
        else:
            await _road_apply_labor(
                actor_i,
                conn=conn, _SAVE=_SAVE,
                city_buildings_blob_io=city_buildings_blob_io,
                _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
                _city_identity=_city_identity,
                resend_planet_geo=resend_planet_geo, _get_augear=_get_augear,
                _CITY_SIM=_CITY_SIM,
                _push_augear_refresh_for=_push_augear_refresh_for,
                _live_avatars=_live_avatars,
                _SPAWNED_CITIES=_SPAWNED_CITIES,
                _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
    except Exception as exc:
        logger.error("0x75 work-site labor for 0x%08x failed: %r",
                     actor_i, exc)


