from __future__ import annotations

from openshores.core.config import Deployment
from openshores.core.logging import get_logger
from openshores.database.repositories.city_sim_state import _load_city_founder
from openshores.database.repositories.city_site import _city_id_variants
from openshores.database.repositories.empire import (
    empire_for_avatar,
    found_empire,
)
from openshores.database.repositories.empire_schema import (
    _FOUNDED_BUILDING_BASE,
    _persist_placed_building_bd,
    _store_empire_flag,
    _sync_founding_seqs_from_db,
)
from openshores.gameplay import city_model as _cm
from openshores.gameplay import jurisdiction as _juris
from openshores.gameplay.city_founding import (
    _FOUNDED_BUILDING_SEQ,
    _FOUNDED_CITY_SEQ,
    _FOUNDING_SEQ_SYNCED,
    _find_city_for_building,
    _load_capitol_blueprint_report,
    _town_square_bld,
)
from openshores.gameplay.empire_read import _empire_for
from openshores.network.city_atom import spawn_city_atom
from openshores.network.flag_spawn import spawn_world_flag
from openshores.network.town_square_design import serve_town_square_design
from openshores.protocol.atoms.png import _extract_png
from openshores.protocol.completion_chain import build_scene_scene_logged_in
from openshores.protocol.empire_chat_parse import (
    _parse_found_city,
    _parse_town_square,
    _read_qstring_be,
)
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


async def on_create_empire(payload: bytes, actor: int, *, conn,
                           _CITIZEN_EMPIRE_OVERRIDE, _live_avatars) -> None:
    actor_i = int(actor) & 0xFFFFFFFF
    name = ""
    try:
        name, _ = _read_qstring_be(payload, 2)
    except Exception as _pe:
        logger.warning(f"[empire-create] 0xCA name parse err: {_pe!r}")
    cur = await _empire_for(
        conn, actor_i, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if cur:
        logger.warning(f"[empire-create] 0xCA: actor 0x{actor_i:08x} already in empire "
                       f"0x{cur:08x}; ignoring create (name={name!r})")
        return
    eid = await found_empire(
        conn, actor_i, name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.error(f"[empire-create] 0xCA: found_empire failed for 0x{actor_i:08x} (name={name!r})")
        return
    try:
        _png = _extract_png(payload)
        if _png[:4] == b"\x89PNG":
            if await _store_empire_flag(conn, eid, _png):
                logger.info(f"[empire-create] 0xCA flag stored {len(_png)}B "
                            f"(sig={_png[:8].hex()}) for empire 0x{eid:08x}")
        else:
            logger.info("[empire-create] 0xCA: no PNG flag found in packet")
    except Exception as _fe:
        logger.error(f"[empire-create] 0xCA flag store err: {_fe!r}")
    logger.info(f"[empire-create] 0xCA CREATE apply: actor 0x{actor_i:08x} -> empire 0x{eid:08x} name={name!r}.")
    try:
        entry = _live_avatars.get(actor_i)
        w = entry.get("writer") if isinstance(entry, dict) else None
        if w is not None and not w.is_closing():
            deployment = Deployment.from_env()
            sli = build_scene_scene_logged_in(
                scene_name=deployment.public_host,
                port=deployment.scene_port, flag=2)
            await write_framed(w, sli)
            logger.info(f"[empire-create] 0xCA -> 0x29 reconnect sent to "
                        f"0x{actor_i:08x}")
        else:
            logger.warning(f'[empire-create] 0xCA: no live writer for 0x{actor_i:08x}.')
    except Exception as _re:
        logger.error(f"[empire-create] 0xCA reconnect err: {_re!r}")

async def _place_building(actor_i, empire, world, info, payload, *, conn,
                          _city_identity, _city_buildings_blob_io,
                          spawn_city_building, _live_avatars,
                          _SPAWNED_CITIES, _DYNAMIC_SCENE_AUIDS,
                          _CITY_KEEPALIVE_TASKS):
    btype = int(info.get("idi", 0)) & 0xFF
    _cfg = info.get("config")
    logger.info(f"[place-building] type=0x{btype:02x} design=0x{info.get('design_serial',0):08x} "
                f"mat=0x{info.get('material',0):04x} "
                f"xyz=({info['xyz'][0]:.1f},{info['xyz'][1]:.1f},{info['xyz'][2]:.1f}) "
                f"yaw={info.get('yaw',0.0):.3f}"
                + (f" config={_cfg} (0xE3/0x02 tail)" if _cfg is not None else ""))
    city = await _find_city_for_building(conn, world, empire, info["xyz"])
    if not city:
        logger.warning(f"[place-building] reject: no empire-0x{int(empire) & 4294967295:08x} city near the placement point.")
        return
    cid = int(city["id"]) & 0xFFFFFFFF
    cap_auid, city_name, city_alleg = await _city_identity(conn, cid)
    report_bytes, bp_name, bp_did, bp_cblob, bp_dmat = await _load_capitol_blueprint_report(
        conn, payload=payload, design_serial=info.get("design_serial", 0))
    if not report_bytes:
        logger.warning("[place-building] no blueprint matched the design serial; not rendered")
        return
    await _sync_founding_seqs_from_db(
        conn, _FOUNDING_SEQ_SYNCED=_FOUNDING_SEQ_SYNCED,
        _FOUNDED_BUILDING_SEQ=_FOUNDED_BUILDING_SEQ,
        _FOUNDED_CITY_SEQ=_FOUNDED_CITY_SEQ)
    _FOUNDED_BUILDING_SEQ[0] += 1
    bauid = (_FOUNDED_BUILDING_BASE + _FOUNDED_BUILDING_SEQ[0]) & 0xFFFFFFFF
    yaw = float(info.get("yaw", 0.0) or 0.0)
    _fnd = (await _load_city_founder(
        conn, cid, _city_id_variants=_city_id_variants) if cid else None) or {}
    try:
        await spawn_city_building(
            bauid, world, info["xyz"], report_bytes, name=bp_name, empire=empire,
            rot=(0.0, 0.0, yaw), btype=btype, design_id=bp_did,
            construction_blob=(bp_cblob or None),
            build_material=int(info.get("material", 0)) & 0xFFFF,
            design_material=int(bp_dmat) & 0xFFFF,
            capitol_auid=cap_auid, city_name=city_name,
            founder_auid=int(_fnd.get("auid") or actor_i) & 0xFFFFFFFF,
            founder_name=_fnd.get("name") or "")
    except Exception as exc:
        logger.error(f"[place-building] render err: {exc!r}")
        return
    lat, lon = _cm.xyz_to_latlon(info["xyz"])
    bld = {"type": _cm.DEV_BUILDING,
           "cpid": _cm.industry_to_cpid_safe(btype, default_cpid=btype & 0x7F),
           "lat": lat, "lon": lon,
           "facing": yaw, "levels": int(info.get("levels", 1) or 1),
           "xyz": tuple(float(v) for v in info["xyz"]),
           "bauid": int(bauid) & 0xFFFFFFFF}
    if _cfg is not None:
        bld["config"] = int(_cfg)
    try:
        await _persist_placed_building_bd(conn, bauid, world, info["xyz"], yaw,
                                          bp_name, empire, btype, bp_did,
                                          report_bytes,
                                          city_id=cid, city_name=city_name)
    except Exception as _bexc:
        logger.error(f"[place-building] reject: a_Bd persist failed ({_bexc!r}).")
        return
    all_blds = await _city_buildings_blob_io(conn, cid, add=bld)
    _blds = [d for d in all_blds if (d.get("kind") or "building") == "building"]
    _roads = [d for d in all_blds if d.get("kind") == "road"]
    try:
        await spawn_city_atom(cid, world, (city["x"], city["y"], city["z"]),
                              _blds, name=city_name,
                              empire=(city_alleg or empire),
                              roads=_roads,
                              is_capital=True, habitable_capital=True,
                              conn=conn, _live_avatars=_live_avatars,
                              _SPAWNED_CITIES=_SPAWNED_CITIES,
                              _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                              _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
    except Exception as exc:
        logger.error(f"[place-building] city-atom re-emit err: {exc!r}")
    logger.info(f"[place-building] OK: '{bp_name}' (design 0x{bp_did:08x}) -> city 0x{cid:08x} "
                f"building 0x{bauid:08x} ({len(all_blds)} buildings)")

async def on_found_city(payload: bytes, actor: int, *, conn,
                        _SAVE, _CITIZEN_EMPIRE_OVERRIDE,
                        found_city, _city_identity,
                        _city_buildings_blob_io, spawn_city_building,
                        alloc_daitem_auid, _tock_state, _live_avatars,
                        _DROPPED_ITEMS, _SPAWNED_CITIES,
                        _DYNAMIC_SCENE_AUIDS,
                        _CITY_KEEPALIVE_TASKS) -> None:
    actor_i = int(actor) & 0xFFFFFFFF
    info = _parse_found_city(payload)
    if info is None:
        return
    if int(info.get("idi", 0)) not in (0x7b, 0x1c) and info.get("disc", 0) != 0x01:
        _emp = _wld = 0
        try:
            _emp = int(await empire_for_avatar(
                conn, actor_i,
                _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
        except Exception as _ee:
            logger.warning(f'[found-city] 0xE3 empire lookup for 0x{actor_i:08x} failed ({_ee!r}).')
        _wld = int(_SAVE.planet_auid) & 0xFFFFFFFF
        await _place_building(
            actor_i, _emp, _wld, info, payload, conn=conn,
            _city_identity=_city_identity,
            _city_buildings_blob_io=_city_buildings_blob_io,
            spawn_city_building=spawn_city_building,
            _live_avatars=_live_avatars, _SPAWNED_CITIES=_SPAWNED_CITIES,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
            _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
        return
    empire = 0
    try:
        empire = int(await empire_for_avatar(
            conn, actor_i,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    except Exception as _ee:
        logger.warning(f'[found-city] 0xE3 empire lookup for 0x{actor_i:08x} failed ({_ee!r}).')
    world = int(_SAVE.planet_auid) & 0xFFFFFFFF
    logger.info(f"[found-city] 0xE3 actor=0x{actor_i:08x} empire=0x{empire:08x} "
                f"world=0x{world:08x} idi=0x{info['idi']:02x} city={info['city']!r} "
                f"system={info['system']!r} sector={info['sector']!r} "
                f"xyz=({info['xyz'][0]:.1f},{info['xyz'][1]:.1f},{info['xyz'][2]:.1f}) "
                f"yaw={info.get('yaw', 0.0):.3f}rad levels={info.get('levels', 0)}")
    if info.get('xyz') and world:
        try:
            _existing = await _juris.load_planet_cities(conn, world)
            _blocked, _reason = _juris.founding_blocked(info['xyz'], empire, _existing)
            if _blocked:
                logger.warning(f"[found-city] reject founding: {_reason} (world=0x{world:08x} empire=0x{empire:08x} existing={len(_existing)}).")
                return
        except Exception as _fg_exc:
            logger.error(f"[found-city] jurisdiction check error (allowing): {_fg_exc!r}")
    cap_id = 0
    try:
        cid, cap_id = await found_city(conn, actor_i, empire, world, info)
        if cid:
            logger.info(f"[found-city] city 0x{cid:08x} '{info['city']}' persisted "
                        f"(capitol 0x{cap_id:08x})")
        else:
            logger.warning("[found-city] city persist skipped (no a_City/a_Bd table)")
    except Exception as exc:
        logger.error(f"[found-city] founding err: {exc!r}")
    rendered = False
    _rb_probe, _, _did_probe, _cb_probe, _dmat_probe = await _load_capitol_blueprint_report(
        conn, payload=payload, design_serial=info.get("design_serial", 0))
    logger.info(f"[found-city] render-check: cap=0x{cap_id:08x} "
                f"world=0x{(world or 0) & 0xFFFFFFFF:08x} have_xyz={bool(info.get('xyz'))} "
                f"report={len(_rb_probe) if _rb_probe else 0}B design=0x{_did_probe:08x} "
                f"construction={len(_cb_probe)}B")
    try:
        if info.get("xyz") and world and cap_id:
            report_bytes, _bp_name, _bp_did, _bp_cblob, _bp_dmat = await _load_capitol_blueprint_report(
                conn, payload=payload, design_serial=info.get("design_serial", 0))
            if report_bytes:
                _yaw = float(info.get("yaw", 0.0) or 0.0)
                _fnd = (await _load_city_founder(
                    conn, cid,
                    _city_id_variants=_city_id_variants) if cid else None) or {}
                b = await spawn_city_building(
                    cap_id, world, info["xyz"], report_bytes,
                    name=info["city"], empire=empire,
                    rot=(0.0, 0.0, _yaw),
                    btype=int(info.get("idi", 0x7b)) & 0xFF,
                    design_id=_bp_did,
                    construction_blob=(_bp_cblob or None),
                    build_material=int(info.get("material", 0)) & 0xFFFF,
                    design_material=int(_bp_dmat) & 0xFFFF,
                    capitol_auid=cap_id, city_name=info["city"],
                    founder_auid=int(_fnd.get("auid") or actor_i) & 0xFFFFFFFF,
                    founder_name=_fnd.get("name") or "")
                rendered = bool(b)
            else:
                logger.warning("[found-city] no blueprint report found; capitol not rendered")
    except Exception as exc:
        logger.error(f"[found-city] capitol render err: {exc!r}")
    try:
        if info.get("xyz") and world and cid:
            cap_bld = _cm.capitol_building_from_info(info, bauid=cap_id)
            await spawn_city_atom(cid, world, info["xyz"], [cap_bld],
                                  name=info["city"], empire=empire,
                                  is_capital=True, habitable_capital=True,
                                  conn=conn, _live_avatars=_live_avatars,
                                  _SPAWNED_CITIES=_SPAWNED_CITIES,
                                  _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                                  _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
    except Exception as exc:
        logger.error(f"[found-city] city-atom emit err: {exc!r}")
    try:
        if info.get("xyz") and world:
            marker = await spawn_world_flag(
                actor_i, world, xyz=info["xyz"],
                alloc_daitem_auid=alloc_daitem_auid, _tock_state=_tock_state,
                _live_avatars=_live_avatars, _DROPPED_ITEMS=_DROPPED_ITEMS,
                _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
            logger.info(f"[found-city] flag marker DaItem 0x{(marker or 0) & 0xFFFFFFFF:08x} "
                        f"dropped (building rendered={rendered})")
    except Exception as exc:
        logger.error(f"[found-city] city marker spawn err: {exc!r}")

async def on_found_town_square(payload: bytes, actor: int, *, conn,
                               _SAVE, _CITIZEN_EMPIRE_OVERRIDE,
                               found_town_square, _ACTIVE_CHAT_WRITER,
                               _live_avatars, _SPAWNED_CITIES,
                               _DYNAMIC_SCENE_AUIDS,
                               _CITY_KEEPALIVE_TASKS) -> None:
    actor_i = int(actor) & 0xFFFFFFFF
    info = _parse_town_square(payload)
    if info is None or not info.get("city"):
        logger.warning("[town-square] parse failed or no city name; ignored")
        return
    empire = 0
    try:
        empire = int(await empire_for_avatar(
            conn, actor_i,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    except Exception as _ee:
        logger.warning(f'[town-square] 0x07 empire lookup for 0x{actor_i:08x} failed ({_ee!r}).')
    world = info.get("world") or 0
    if not world:
        world = int(_SAVE.planet_auid) & 0xFFFFFFFF
    logger.info(f"[town-square] 0x07 actor=0x{actor_i:08x} empire=0x{empire:08x} "
                f"world=0x{world:08x} city={info['city']!r} "
                f"xyz=({info['xyz'][0]:.1f},{info['xyz'][1]:.1f},{info['xyz'][2]:.1f}) "
                f"yaw={info['yaw']:.3f}")
    if info.get('xyz') and world:
        try:
            _existing = await _juris.load_planet_cities(conn, world)
            _blocked, _reason = _juris.founding_blocked(info['xyz'], empire, _existing)
            if _blocked:
                logger.warning(f"[town-square] reject founding: {_reason}")
                return
        except Exception as _fg:
            logger.error(f"[town-square] jurisdiction check error (allowing): {_fg!r}")
    cid, ts_id = await found_town_square(conn, actor_i, empire, world, info)
    if not cid:
        logger.error("[town-square] founding persist failed")
        return
    logger.info(f"[town-square] city 0x{cid:08x} '{info['city']}' persisted "
                f"(town square 0x{ts_id:08x})")
    try:
        import asyncio as _asyncio
        _w = _ACTIVE_CHAT_WRITER
        if _w is not None:
            await serve_town_square_design(_w)
            await _asyncio.sleep(0.3)
            logger.info("[town-square] proactively served design before atom")
        else:
            logger.warning("[town-square] no chat writer for proactive serve")
    except Exception as _pe:
        logger.error(f"[town-square] proactive serve err: {_pe!r}")
    try:
        _ts_bld = _town_square_bld(info)
        _ts_bld["bauid"] = ts_id
        await spawn_city_atom(cid, world, tuple(info["xyz"]),
                              [_ts_bld], name=info["city"],
                              empire=empire, is_capital=True,
                              habitable_capital=True,
                              conn=conn, _live_avatars=_live_avatars,
                              _SPAWNED_CITIES=_SPAWNED_CITIES,
                              _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                              _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
        logger.info(f"[town-square] re-emitted DaCity 0x{cid:08x} with Town Square")
    except Exception as exc:
        logger.error(f"[town-square] DaCity emit err: {exc!r}")
