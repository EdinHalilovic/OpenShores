from __future__ import annotations

import json as _json

from openshores.core.logging import get_logger
from openshores.database.repositories.city_buildings import (
    bd_row_ids,
    city_development_rows,
    read_city_developments,
    write_city_developments,
)
from openshores.database.repositories.city_found import (
    founder_name,
    founder_name_and_dna,
    replace_bd_row,
    replace_city_row,
    set_city_sim_state,
)
from openshores.database.repositories.empire_schema import (
    _FOUNDED_CAPITOL_BASE,
    _FOUNDED_CITY_BASE,
    _sync_founding_seqs_from_db,
)
from openshores.database.repositories.world import _table_columns
from openshores.gameplay import city_model as _cm
from openshores.gameplay.city_founding import (
    _FOUNDED_BUILDING_SEQ,
    _FOUNDED_CITY_SEQ,
    _FOUNDING_SEQ_SYNCED,
    _town_square_bld,
)
from openshores.gameplay.roads import _DUP_PLACEMENT_M, _is_duplicate_placement

logger = get_logger(__name__)


async def found_city(conn, person_auid: int, empire_id: int, world_auid: int,
                     info: dict):
    await _sync_founding_seqs_from_db(
        conn, _FOUNDING_SEQ_SYNCED=_FOUNDING_SEQ_SYNCED,
        _FOUNDED_BUILDING_SEQ=_FOUNDED_BUILDING_SEQ,
        _FOUNDED_CITY_SEQ=_FOUNDED_CITY_SEQ)
    _FOUNDED_CITY_SEQ[0] += 1
    city_id = (_FOUNDED_CITY_BASE + _FOUNDED_CITY_SEQ[0]) & 0xFFFFFFFF
    cap_id = (_FOUNDED_CAPITOL_BASE + _FOUNDED_CITY_SEQ[0]) & 0xFFFFFFFF
    x, y, z = info["xyz"]
    try:
        async def cols(t):
            return await _table_columns(conn, t)
        ac = await cols("a_City")
        if ac:
            vals = {"id": city_id, "name": info["city"], "idp": world_auid,
                    "allegiance": empire_id, "capitol": cap_id,
                    "locX": x, "locY": y, "locZ": z}
            try:
                cap_bld = _cm.capitol_building_from_info(info, bauid=cap_id)
                vals["developments"] = _cm.developments_to_blob([cap_bld])
            except Exception as _dev_exc:
                logger.error(f"[found-city] developments encode err: {_dev_exc!r}")
            await replace_city_row(conn, vals, ac)
        ab = await cols("a_Bd")
        if ab:
            vals = {"id": cap_id, "idp": world_auid, "locX": x, "locY": y, "locZ": z,
                    "rotZ": float(info.get("yaw", 0.0) or 0.0),
                    "name": info["city"], "cityName": info["city"], "capitol": city_id,
                    "allegiance": empire_id, "industry": info["idi"]}
            await replace_bd_row(conn, vals, ab)
        try:
            _fr = await founder_name_and_dna(conn, person_auid)
            _fname = (_fr[0] if _fr else "") or ""
            _fdna = bytes(_fr[1]).hex() if (_fr and _fr[1]) else ""
            if ac and "sim_state" in ac:
                _fdoc = {"founder": {"auid": person_auid & 0xFFFFFFFF, "name": _fname,
                                     "empire": empire_id & 0xFFFFFFFF, "dna": _fdna}}
                await set_city_sim_state(conn, _json.dumps(_fdoc), city_id)
                logger.info(f"[found-city] founder registered 0x{person_auid & 0xFFFFFFFF:08x} "
                            f"'{_fname}'")
        except Exception as _fexc:
            logger.error(f"[found-city] founder register err: {_fexc!r}")
        return (city_id, cap_id)
    except Exception as exc:
        logger.error(f"[found-city] sql err: {exc!r}")
        return (0, 0)


async def found_town_square(conn, person_auid, empire_id, world_auid, info):
    await _sync_founding_seqs_from_db(
        conn, _FOUNDING_SEQ_SYNCED=_FOUNDING_SEQ_SYNCED,
        _FOUNDED_BUILDING_SEQ=_FOUNDED_BUILDING_SEQ,
        _FOUNDED_CITY_SEQ=_FOUNDED_CITY_SEQ)
    _FOUNDED_CITY_SEQ[0] += 1
    city_id = (_FOUNDED_CITY_BASE + _FOUNDED_CITY_SEQ[0]) & 0xFFFFFFFF
    ts_id = (_FOUNDED_CAPITOL_BASE + _FOUNDED_CITY_SEQ[0]) & 0xFFFFFFFF
    x, y, z = info["xyz"]
    ts_bld = _town_square_bld(info)
    ts_bld["bauid"] = ts_id
    try:
        async def cols(t):
            return await _table_columns(conn, t)
        ac = await cols("a_City")
        if ac:
            vals = {"id": city_id, "name": info["city"], "idp": world_auid,
                    "allegiance": empire_id, "capitol": ts_id,
                    "locX": x, "locY": y, "locZ": z}
            try:
                vals["developments"] = _cm.developments_to_blob([ts_bld])
            except Exception as _de:
                logger.error(f"[town-square] developments encode err: {_de!r}")
            await replace_city_row(conn, vals, ac)
            if "sim_state" in ac:
                try:
                    _fr = await founder_name(conn, person_auid)
                    _fname = (_fr[0] if _fr else "") or ""
                except Exception:
                    _fname = ""
                _doc = {"style": "old",
                        "founder": {"auid": person_auid & 0xFFFFFFFF,
                                    "name": _fname, "empire": empire_id & 0xFFFFFFFF}}
                await set_city_sim_state(conn, _json.dumps(_doc), city_id)
        return (city_id, ts_id)
    except Exception as exc:
        logger.error(f"[town-square] sql err: {exc!r}")
        return (0, 0)


async def _city_buildings_blob_io(conn, cid, add=None, mutate=None):
    blds = []
    try:
        blob = await read_city_developments(conn, cid)
        blds = _cm.developments_from_blob(blob) if blob else []
        dirty = False
        if add is not None:
            if _is_duplicate_placement(blds, add):
                logger.warning(f"[place-building] duplicate placement ignored: "
                               f"cpid={add.get('cpid')} already present within "
                               f"{_DUP_PLACEMENT_M:.0f} m (city 0x{cid:08x})")
                add = None
        if add is not None:
            blds = list(blds) + [add]
            dirty = True
        if mutate is not None:
            blds = mutate(list(blds)) or blds
            dirty = True
        if dirty:
            await write_city_developments(
                conn, cid, _cm.developments_to_blob(blds))
    except Exception as exc:
        logger.error(f"[place-building] developments io err: {exc!r}")
    return blds


async def prune_ghost_developments(conn, cid=None, dry_run=False):
    out = {}
    try:
        have = await bd_row_ids(conn)
        rows = await city_development_rows(conn, cid)
    except Exception as exc:
        logger.error(f"[ghost-prune] db read err: {exc!r}")
        return out

    for city_id, blob in rows:
        if not blob:
            continue
        devs = _cm.developments_from_blob(blob) or []
        keep, dropped = [], []
        for d in devs:
            b = int(d.get("bauid") or 0) & 0xFFFFFFFF if isinstance(d, dict) else 0
            if b and b not in have:
                dropped.append(d)
            else:
                keep.append(d)
        if not dropped:
            continue
        out[int(city_id) & 0xFFFFFFFF] = dropped
        for d in dropped:
            logger.warning(f"[ghost-prune] city 0x{int(city_id) & 0xFFFFFFFF:08x}: "
                           f"cpid={d.get('cpid')} bauid=0x{int(d.get('bauid') or 0):08x} "
                           f"has no a_Bd row -> {'would drop' if dry_run else 'dropped'}")
        if not dry_run:
            await _city_buildings_blob_io(
                conn, int(city_id), mutate=lambda _l, k=keep: k)
    return out
