from __future__ import annotations

import struct
import time

from openshores.core.logging import get_logger
from openshores.database.repositories.city_buildings import _city_identity
from openshores.database.repositories.empire import empire_for_avatar
from openshores.gameplay import city_model as _cm
from openshores.gameplay.city_founding import _find_city_for_building
from openshores.gameplay.city_persist import _city_buildings_blob_io
from openshores.gameplay.road_construction import (
    _ROAD_INSTANT_BUILD,
    _ROAD_OPTYPES,
    build_area_construction_demand,
    build_road_construction_demand,
)
from openshores.gameplay.roads import _cm_units_fpm
from openshores.network.city_atom import spawn_city_atom
from openshores.network.road_ticker import ensure_road_construction_ticker
from openshores.protocol.empire_chat_parse import (
    _parse_construction_op,
    parse_chat_construction_op,
)

logger = get_logger(__name__)


async def on_construction_op(payload: bytes, actor: int, *, conn,
                             _SAVE, _CITIZEN_EMPIRE_OVERRIDE,
                             resend_planet_geo, _live_avatars,
                             _SPAWNED_CITIES, _DYNAMIC_SCENE_AUIDS,
                             _CITY_KEEPALIVE_TASKS) -> None:
    actor_i = int(actor) & 0xFFFFFFFF
    try:
        d = _parse_construction_op(payload, units_fpm=_cm_units_fpm())
    except Exception as exc:
        logger.error(f"[construct-op] parse err: {exc!r} "
                     f"raw={bytes(payload[:64]).hex()}")
        return
    emp = wld = 0
    try:
        emp = int(await empire_for_avatar(
            conn, actor_i,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    except Exception as _ee:
        logger.warning(f'[construct-op] empire lookup for 0x{actor_i:08x} failed ({_ee!r}).')
    wld = int(_SAVE.planet_auid) & 0xFFFFFFFF
    mid = tuple((d["p1"][i] + d["p2"][i]) / 2.0 for i in range(3))
    city = await _find_city_for_building(conn, wld, emp, mid)
    logger.info(f"[construct-op] {d['op']} (subtype{d['subtype']} optype0x{d['optype']:02x}) "
                f"p1={tuple(round(v) for v in d['p1'])} p2={tuple(round(v) for v in d['p2'])} "
                f"-> city 0x{(int(city['id']) & 0xFFFFFFFF) if city else 0:08x}")
    if not city:
        logger.warning("[construct-op] no city near the op location; not stored")
        return
    cid = int(city["id"]) & 0xFFFFFFFF
    try:
        _cla, _clo = _cm.xyz_to_latlon((city.get("x", 0.0), city.get("y", 0.0),
                                        city.get("z", 0.0)))
        _ela1, _elo1 = _cm.xyz_to_latlon(d["p1"])
        _ela2, _elo2 = _cm.xyz_to_latlon(d["p2"])
        logger.debug(f"[construct-op][LL] (radians) city-center=({_cla:.4f},{_clo:.4f}) "
                     f"road p1=({_ela1:.4f},{_elo1:.4f}) p2=({_ela2:.4f},{_elo2:.4f}) "
                     f"d_lat={_ela1-_cla:+.4f} d_lon={_elo1-_clo:+.4f}")
    except Exception as _dexc:
        logger.debug(f"[construct-op][LL] diag err: {_dexc!r}")
    if not (d["subtype"] == 0 and d["optype"] in _ROAD_OPTYPES):
        logger.warning(f"[construct-op] not A ROAD: sub=0x{d['subtype']:02x} optype=0x{d['optype']:02x} -> stored as area_op (bookkeeping only: no DaCity road entry, no geo feature, so it can never be worked or demolished as a road).")
    if d["subtype"] == 0 and d["optype"] in _ROAD_OPTYPES:
        _la1, _lo1 = _cm.xyz_to_latlon(d["p1"])
        _la2, _lo2 = _cm.xyz_to_latlon(d["p2"])
        _alt1 = _alt2 = 0.0
        try:
            _rg = await _cm._sea_level_radius_m(
                conn, await _cm.city_world_auid(conn, cid) or wld)
            _alt1 = sum(v * v for v in d["p1"]) ** 0.5 - _rg
            _alt2 = sum(v * v for v in d["p2"]) ** 0.5 - _rg
        except Exception as _aexc:
            logger.debug(f"[construct-op] altMSL err: {_aexc!r}; "
                         f"road {d['op']} graded to sea level")
        _cpid = _cm.ROAD_OPTYPE_TO_CPID.get(d["optype"], 2)
        rec = {"kind": "road", "type": _cm.DEV_GLOBE_ROAD, "road_type": d["optype"],
               "cpid": _cpid, "op": d["op"], "p1": d["p1"], "p2": d["p2"],
               "width_wire": d.get("width_wire"), "width_m": d.get("width"),
               "lat1": _la1, "lon1": _lo1,
               "lat2": _la2, "lon2": _lo2, "alt1": _alt1, "alt2": _alt2,
               "rid": "%x" % time.time_ns()}
        _demand = build_road_construction_demand(
            d["optype"], _cpid, d["p1"], d["p2"], d.get("width"))
        if not _ROAD_INSTANT_BUILD and _demand is not None:
            rec["under_construction"] = True
            rec["cstate"] = _demand
            _dm = [(hex(c[0]), c[3]) for c in _demand["components"] if c[2] == 5]
            _dt = [(hex(c[0]), c[3]) for c in _demand["components"] if c[2] != 5]
            logger.info(f"[construct-op] road demand (GD cpid {_cpid}): "
                        f"labor={_demand['labor']} "
                        f"materials={_dm or 'none (labor-only)'} tools={_dt}")
    else:
        rec = {"kind": "area_op", "op": d["op"], "subtype": d["subtype"],
               "optype": d["optype"], "p1": d["p1"], "p2": d["p2"],
               "width_m": d.get("width"), "radius": d.get("radius"),
               "radius_wire": d.get("radius_wire"),
               "params": d.get("params"), "rid": "%x" % time.time_ns()}
        if not _ROAD_INSTANT_BUILD:
            rec["under_construction"] = True
            rec["cstate"] = build_area_construction_demand(d["optype"])
    devs = await _city_buildings_blob_io(conn, cid, add=rec)
    _bldgs = [b for b in devs if b.get("kind", "building") == "building"]
    _roads = [b for b in devs if b.get("kind") == "road"]
    _na = sum(1 for b in devs if b.get("kind") == "area_op")
    logger.info(f"[construct-op] stored {d['op']} on city 0x{cid:08x} "
                f"(now {len(_roads)} road(s), {_na} area-op(s))")
    if rec.get("under_construction"):
        ensure_road_construction_ticker(
            conn=conn, _SAVE=_SAVE,
            city_buildings_blob_io=_city_buildings_blob_io,
            _city_identity=_city_identity,
            resend_planet_geo=resend_planet_geo,
            _live_avatars=_live_avatars, _SPAWNED_CITIES=_SPAWNED_CITIES,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
            _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
    _, _cnm, _calleg = await _city_identity(conn, cid)
    try:
        await spawn_city_atom(cid, wld, (city["x"], city["y"], city["z"]),
                              _bldgs, roads=_roads, name=_cnm,
                              empire=(_calleg or int(city.get("empire", 0))),
                              is_capital=True, habitable_capital=True,
                              conn=conn, _live_avatars=_live_avatars,
                              _SPAWNED_CITIES=_SPAWNED_CITIES,
                              _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                              _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
        logger.info(f"[construct-op] re-emitted DaCity 0x{cid:08x} "
                    f"({len(_bldgs)} bld, {len(_roads)} road)")
    except Exception as _rexc:
        logger.error(f"[construct-op] DaCity re-emit err: {_rexc!r}")
    try:
        await resend_planet_geo(wld, reason="road laid")
    except Exception as _gexc:
        logger.error(f"[construct-op] geo re-emit err: {_gexc!r}")


async def on_chat_construction_op(payload: bytes, actor: int, *, conn,
                                  _SAVE, _CITIZEN_EMPIRE_OVERRIDE,
                                  resend_planet_geo, _live_avatars,
                                  _SPAWNED_CITIES, _DYNAMIC_SCENE_AUIDS,
                                  _CITY_KEEPALIVE_TASKS) -> None:
    _raw = bytes(payload)
    logger.debug(f"[construct-op][raw] len={len(_raw)}B {_raw.hex()}")
    if len(_raw) >= 56:
        logger.debug(f"[construct-op][raw] op=0x{_raw[0]:02x} sub=0x{_raw[1]:02x} | sub0 would read flag=0x{_raw[50]:02x} width={struct.unpack_from('>f', _raw, 51)[0]:.5f} optype=0x{_raw[55]:02x}"
                     + (f" | sub1 reads radius="
                        f"{struct.unpack_from('>f', _raw, 50)[0]:.5f} "
                        f"tail={_raw[54:59].hex()}" if len(_raw) >= 59 else ""))
    try:
        d = parse_chat_construction_op(payload)
    except Exception as exc:
        logger.error(f"[construct-op] chat 0x06 parse err: {exc!r} "
                     f"raw={bytes(payload[:64]).hex()}")
        return
    if d["leftover"]:
        logger.warning(f"[construct-op] chat 0x06 sub{d['subtype']}: {d['leftover']} "
                       f"leftover byte(s) past spec: "
                       f"{bytes(payload)[len(payload) - d['leftover']:].hex()} "
                       f"(routing anyway)")
    logger.info(f"[construct-op] chat 0x06 -> {d['op']} "
                f"(sub{d['subtype']} optype0x{d['optype']:02x}"
                + (f" width={d['width']:.4f}" if d["subtype"] == 0
                   else f" radius={d['radius']:.4f}")
                + f") actor=0x{int(actor) & 0xFFFFFFFF:08x}")
    await on_construction_op(
        payload, actor, conn=conn, _SAVE=_SAVE,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        resend_planet_geo=resend_planet_geo, _live_avatars=_live_avatars,
        _SPAWNED_CITIES=_SPAWNED_CITIES,
        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
        _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
