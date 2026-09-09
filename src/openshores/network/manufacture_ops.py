
from __future__ import annotations

import asyncio
import struct
import time as _time

from openshores.core.logging import get_logger
from openshores.database.repositories.city_site import _city_id_variants
from openshores.database.repositories.city_sim_state import _persist_city_sim
from openshores.gameplay import gd_tables as _gd
from openshores.gameplay import player_run as _prun
from openshores.gameplay.city.zone import _city_zone
from openshores.gameplay.city_seed import native_ledger_values
from openshores.gameplay.city_sim import ItemStock
from openshores.gameplay.empire_read import _empire_for
from openshores.gameplay.manufacturing_ops import (
    _MFG_INDUSTRIES,
    _MFG_RUN_TASKS,
    _MFG_SUB_STOP,
    _MFG_SUBS_ADD,
    _MFG_SUBS_PRIORITY,
    _MPROC_CFG_KEY,
    _mfg_dev_for,
    _mfg_environment_pass,
    _mfg_resolve_target,
    _mfg_set_cfg,
    _mfg_set_cfg_map,
)
from openshores.network.building_broadcast import _construction_rebroadcast
from openshores.world.sim_time import _current_sim_time_ms

logger = get_logger(__name__)

_MFG_FETCH_SEC: float = 10.0


async def on_bd_manufacture(payload: bytes, actor: int, *, conn,
                            _bd_row_by_auid, _bd_rows_for_empire,
                            _city_buildings_blob_io,
                            _CITIZEN_EMPIRE_OVERRIDE,
                            _SPAWNED_BUILDINGS, _live_avatars,
                            _ZONE_CACHE, _CITY_SIM,
                            anchor_full) -> None:
    body = bytes(payload[1:])
    if len(body) < 7:
        logger.warning("0x79 reject: short body (%dB) hex=%s",
                       len(body), payload.hex())
        return
    sub = body[0]
    mpid = struct.unpack_from(">h", body, 1)[0]
    target = struct.unpack_from(">I", body, 3)[0]
    if sub in _MFG_SUBS_PRIORITY:
        await _mfg_reorder(
            conn, target, actor, mpid, _MFG_SUBS_PRIORITY[sub], sub,
            _bd_row_by_auid=_bd_row_by_auid,
            _city_buildings_blob_io=_city_buildings_blob_io,
            _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
            _live_avatars=_live_avatars, _ZONE_CACHE=_ZONE_CACHE,
            _CITY_SIM=_CITY_SIM, anchor_full=anchor_full)
        return
    if sub not in _MFG_SUBS_ADD and sub != _MFG_SUB_STOP:
        _rname = ""
        try:
            _r = _gd.process_by_id(mpid)
            if _r is not None:
                _rname = f" ({_r.name}, industry 0x{_r.industry_id:02x})"
        except Exception as exc:
            logger.debug("Recipe name for mpid %s unavailable. %r",
                         mpid, exc)
        logger.warning(
            "0x79 sub=0x%02x UNIDENTIFIED slot. No-op. mpid=%s%s target=0x%08x hex=%s",
            sub, mpid, _rname, target, payload.hex())
        return
    row = None
    if target:
        row = await _bd_row_by_auid(conn, target)
        if row is None:
            logger.warning("0x79 sub=0x%02x reject: target 0x%08x matches no a_Bd row (mpid=%s)",
                           sub, target & 0xFFFFFFFF, mpid)
            return
    else:
        emp = await _empire_for(
            conn, actor,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
        rows = await _bd_rows_for_empire(conn, emp)
        producers = [r for r in rows
                     if int(r.get("industry") or 0) in _MFG_INDUSTRIES]
        pick = producers or rows
        if len(pick) != 1:
            logger.warning("0x79 sub=0x%02x reject: target AuId=0 and %d producer(s) / %d building(s) for empire 0x%08x. Ambiguous (mpid=%s)",
                           sub, len(producers), len(rows), emp, mpid)
            return
        row = pick[0]
        logger.info("0x79 target AuId=0 -> resolved to sole %s 0x%08x '%s'",
                    "producer" if producers else "building",
                    int(row["id"]) & 0xFFFFFFFF, row.get("name", ""))
    bauid = int(row["id"]) & 0xFFFFFFFF
    cid = int(row.get("capitol") or 0) & 0xFFFFFFFF
    verb = "ADD" if sub in _MFG_SUBS_ADD else "STOP"
    changed = {"n": 0, "matched": False, "list": None}

    def _mut(blds):
        entries = [e for e in blds if isinstance(e, dict)
                   and int(e.get("bauid") or 0) == bauid]
        if not entries:
            byc = [e for e in blds if isinstance(e, dict)
                   and int(e.get("cpid") or 0) ==
                   (int(row.get("industry") or 0) & 0x7F)]
            if len(byc) == 1:
                entries = byc
        for e in entries:
            changed["matched"] = True
            cur = [int(v) for v in (e.get("manproc") or [])]
            if sub in _MFG_SUBS_ADD and mpid not in cur:
                cur.append(mpid)
                changed["n"] += 1
            elif sub == _MFG_SUB_STOP and mpid in cur:
                cur.remove(mpid)
                changed["n"] += 1
            e["manproc"] = cur
            changed["list"] = cur
        return blds

    if cid:
        await _city_buildings_blob_io(conn, cid, mutate=_mut)
    try:
        _info = _SPAWNED_BUILDINGS.get(bauid)
        if _info is not None:
            _l = [int(v) for v in (_info.get("manproc") or [])]
            if sub in _MFG_SUBS_ADD and mpid not in _l:
                _l.append(mpid)
            elif sub == _MFG_SUB_STOP and mpid in _l:
                _l.remove(mpid)
            _info["manproc"] = _l
            if changed["list"] is None:
                changed["list"] = _l
    except Exception as exc:
        logger.warning("Live-registry update err: %r", exc)
    logger.info("0x79 %s mpid=%s building=0x%08x '%s' city=0x%08x "
                "persisted=%s changed=%s manproc=%s",
                verb, mpid, bauid, row.get("name", ""), cid,
                bool(cid and changed["matched"]), changed["n"],
                changed["list"])
    try:
        _info = _SPAWNED_BUILDINGS.get(bauid)
        if _info is not None:
            await _construction_rebroadcast(
                bauid, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                _live_avatars=_live_avatars, conn=conn,
                _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                anchor_full=anchor_full)
            logger.info("Re-emitted 0x%08x with %d process(es)",
                        bauid, len(_info.get("manproc") or []))
        else:
            logger.warning('0x%08x not in the live registry.', bauid)
    except Exception as exc:
        logger.warning("Re-emit err for 0x%08x: %r", bauid, exc)


_MFG_SUB_BUILDING = 0x67


async def _mfg_reorder(conn, target, actor, mpid, delta, sub, *,
                       _bd_row_by_auid, _city_buildings_blob_io,
                       _SPAWNED_BUILDINGS, _live_avatars,
                       _ZONE_CACHE, _CITY_SIM, anchor_full):
    row, bauid, cid = await _mfg_resolve_target(
        conn, target, actor, _bd_row_by_auid=_bd_row_by_auid)
    if row is None:
        return
    verb = "RAISE" if delta < 0 else "LOWER"
    moved = {"n": 0, "list": None}

    def _reorder(lst):
        cur = [int(v) for v in (lst or [])]
        if mpid not in cur:
            return cur
        i = cur.index(mpid)
        j = i + delta
        if j < 0 or j >= len(cur):
            return cur
        cur[i], cur[j] = cur[j], cur[i]
        moved["n"] += 1
        return cur

    def _mut(blds):
        for e in blds:
            if isinstance(e, dict) and (int(e.get("bauid") or 0) & 0xFFFFFFFF) == bauid:
                e["manproc"] = _reorder(e.get("manproc"))
                moved["list"] = e["manproc"]
        return blds

    if cid:
        await _city_buildings_blob_io(conn, cid, mutate=_mut)
    try:
        _info = _SPAWNED_BUILDINGS.get(bauid)
        if _info is not None:
            _info["manproc"] = _reorder(_info.get("manproc"))
            if moved["list"] is None:
                moved["list"] = _info["manproc"]
    except Exception as exc:
        logger.warning("Live-registry reorder err: %r", exc)

    logger.info("0x79 sub=0x%02x %s mpid=%s building=0x%08x "
                "city=0x%08x moved=%s manproc=%s",
                sub, verb, mpid, bauid, cid, moved["n"],
                moved["list"])
    await _mfg_reemit(bauid, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                      _live_avatars=_live_avatars, conn=conn,
                      _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                      anchor_full=anchor_full)


async def _mfg_reemit(bauid, *, _SPAWNED_BUILDINGS, _live_avatars,
                      conn, _ZONE_CACHE, _CITY_SIM, anchor_full):
    try:
        if _SPAWNED_BUILDINGS.get(bauid) is not None:
            await _construction_rebroadcast(
                bauid, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                _live_avatars=_live_avatars, conn=conn,
                _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                anchor_full=anchor_full)
    except Exception as exc:
        logger.warning("Re-emit err for 0x%08x: %r", bauid, exc)


async def on_bd_set_shops(payload: bytes, actor: int, *, conn,
                          _bd_row_by_auid, _city_buildings_blob_io,
                          _SPAWNED_BUILDINGS, _live_avatars, _ZONE_CACHE,
                          _CITY_SIM, anchor_full) -> None:
    body = bytes(payload[1:])
    if len(body) < 11 or body[0] != _MFG_SUB_BUILDING:
        logger.warning("0x71 sub=0x%02x unhandled shape (%dB); hex=%s",
                       body[0] if body else 0, len(body),
                       bytes(payload).hex())
        return
    mpid = struct.unpack_from(">h", body, 1)[0]
    count = struct.unpack_from(">i", body, 3)[0]
    target = struct.unpack_from(">I", body, 7)[0]
    row, bauid, cid = await _mfg_resolve_target(
        conn, target, actor, _bd_row_by_auid=_bd_row_by_auid)
    if row is None:
        return
    res = await _mfg_set_cfg(
        conn, cid, bauid, mpid, "shops", max(0, count),
        _city_buildings_blob_io=_city_buildings_blob_io,
        _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS)
    logger.info("SHOPS mpid=%s -> %s on 0x%08x '%s' persisted=%s "
                "cfg=%s", mpid, count, bauid, row.get("name", ""),
                res["ok"], res["cfg"])
    await _mfg_reemit(bauid, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                      _live_avatars=_live_avatars, conn=conn,
                      _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                      anchor_full=anchor_full)


async def on_bd_set_min_quality(payload: bytes, actor: int, *, conn,
                                _bd_row_by_auid, _city_buildings_blob_io,
                                _SPAWNED_BUILDINGS, _live_avatars, _ZONE_CACHE,
                                _CITY_SIM, anchor_full) -> None:
    body = bytes(payload[1:])
    if len(body) < 8 or body[0] != _MFG_SUB_BUILDING:
        logger.warning("0xC9 sub=0x%02x unhandled shape (%dB); hex=%s",
                       body[0] if body else 0, len(body),
                       bytes(payload).hex())
        return
    mpid = struct.unpack_from(">h", body, 1)[0]
    minq = body[3]
    target = struct.unpack_from(">I", body, 4)[0]
    row, bauid, cid = await _mfg_resolve_target(
        conn, target, actor, _bd_row_by_auid=_bd_row_by_auid)
    if row is None:
        return
    res = await _mfg_set_cfg(
        conn, cid, bauid, mpid, "minq", minq,
        _city_buildings_blob_io=_city_buildings_blob_io,
        _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS)
    logger.info("MINQ mpid=%s -> %s on 0x%08x '%s' persisted=%s "
                "cfg=%s", mpid, minq, bauid, row.get("name", ""),
                res["ok"], res["cfg"])
    await _mfg_reemit(bauid, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                      _live_avatars=_live_avatars, conn=conn,
                      _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                      anchor_full=anchor_full)


async def on_bd_run_process(payload: bytes, actor: int, *, conn,
                            _bd_row_by_auid, _city_buildings_blob_io,
                            _SPAWNED_BUILDINGS, _live_avatars, _ZONE_CACHE,
                            _CITY_SIM, anchor_full) -> None:
    body = bytes(payload[1:])
    if len(body) < 7 or body[0] != _MFG_SUB_BUILDING:
        logger.warning("0x75 sub=0x%02x unhandled shape (%dB); hex=%s",
                       body[0] if body else 0, len(body),
                       bytes(payload).hex())
        return
    mpid = struct.unpack_from(">h", body, 1)[0]
    target = struct.unpack_from(">I", body, 3)[0]
    row, bauid, cid = await _mfg_resolve_target(
        conn, target, actor, _bd_row_by_auid=_bd_row_by_auid)
    if row is None:
        return
    _name = ""
    try:
        _r = _gd.process_by_id(mpid)
        if _r is not None:
            _name = _r.name
    except Exception as exc:
        logger.debug("Recipe name for mpid %s unavailable. %r",
                     mpid, exc)
    res = await _mfg_set_cfg(
        conn, cid, bauid, mpid, "run", 1,
        _city_buildings_blob_io=_city_buildings_blob_io,
        _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS)
    logger.info("RUN mpid=%s (%s) on 0x%08x '%s' persisted=%s",
                mpid, _name, bauid, row.get("name", ""), res["ok"])
    await _mfg_execute_run(
        conn, cid, bauid, mpid, _name, row,
        _city_buildings_blob_io=_city_buildings_blob_io,
        _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
        _live_avatars=_live_avatars, _ZONE_CACHE=_ZONE_CACHE,
        _CITY_SIM=_CITY_SIM, anchor_full=anchor_full)
    await _mfg_reemit(bauid, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                      _live_avatars=_live_avatars, conn=conn,
                      _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                      anchor_full=anchor_full)


async def _mfg_execute_run(conn, cid, bauid, mpid, name, row, *,
                           _city_buildings_blob_io,
                           _SPAWNED_BUILDINGS, _live_avatars,
                           _ZONE_CACHE, _CITY_SIM, anchor_full):
    info = _CITY_SIM.get(int(cid) & 0xFFFFFFFF)
    if info is None:
        logger.warning('RUN: city 0x%08x is not in the live sim registry yet.',
                       int(cid) & 0xFFFFFFFF)
        return
    snap = info.get("sim_snapshot") or {}
    zone = None
    try:
        zone = await _city_zone(conn, int(cid) & 0xFFFFFFFF,
                                _ZONE_CACHE=_ZONE_CACHE,
                                _CITY_SIM=_CITY_SIM)
    except Exception as exc:
        logger.warning("RUN: zone lookup failed: %r", exc)

    dev = await _mfg_dev_for(
        conn, cid, bauid,
        _city_buildings_blob_io=_city_buildings_blob_io) or {}
    one = dict((dev.get(_MPROC_CFG_KEY) or {}).get(str(mpid)) or {})
    industry = int(row.get("industry") or 0) & 0xFF
    quality = int(dev.get("quality") or 0) or 100

    proc, stores = _prun.build_line(
        int(mpid), stock=ItemStock.from_json(snap.get("stock")), zone=zone,
        industry=industry, building_quality=quality,
        shops=int(one.get("shops") or 1),
        minimum_quality=int(one.get("minq") or 0))
    if proc is None:
        logger.warning("RUN: mpid %s is not a recipe this GD knows",
                       mpid)
        return

    _carry = one.get("have") or {}
    for c in proc.components:
        prev = int(_carry.get(str(c.commodity)) or 0)
        if prev > c.have:
            c.have = min(prev, c.required) if c.required else prev

    now = int(_time.time() * 1000)
    res = _prun.start(proc, stores, now)
    if not res.started:
        logger.info("RUN mpid=%s (%s) not started: %s",
                    mpid, name, res.reason)
        await _mfg_set_cfg_map(
            conn, cid, bauid, mpid, "have",
            {str(c.commodity): int(c.have)
             for c in proc.components if c.have},
            _city_buildings_blob_io=_city_buildings_blob_io)
        return

    logger.info("RUN mpid=%s (%s) STARTED on 0x%08x. %s s to go",
                mpid, name, bauid, res.seconds)
    try:
        _wire_deadline = int(_current_sim_time_ms(
            anchor_full=anchor_full)) + res.seconds * 1000
    except Exception as exc:
        logger.warning("RUN deadline clock unavailable; shipping 0. "
                       "%r", exc)
        _wire_deadline = 0
    await _mfg_set_cfg(
        conn, cid, bauid, mpid, "deadline", _wire_deadline,
        _city_buildings_blob_io=_city_buildings_blob_io,
        _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS)

    async def _finish():
        try:
            await asyncio.sleep(max(0.0, (res.deadline_ms - now) / 1000.0))
            h = _prun.harvest(proc, stores, zone, int(_time.time() * 1000))
            if not h.outputs and h.reason == "not finished":
                _left = (proc.deadline_ms - int(_time.time() * 1000))
                logger.debug("RUN mpid=%s harvest was %s ms early; "
                             "waiting it out", mpid, _left)
                await asyncio.sleep(max(0.05, _left / 1000.0 + 0.05))
                h = _prun.harvest(proc, stores, zone,
                                  int(_time.time() * 1000))
            if not h.outputs:
                logger.warning("RUN mpid=%s (%s) finished with no "
                               "output: %s", mpid, name, h.reason)
                return
            live = _CITY_SIM.get(int(cid) & 0xFFFFFFFF)
            lsnap = (live or {}).get("sim_snapshot")
            if not live or not lsnap:
                logger.warning(
                    "RUN: city 0x%08x has no live sim snapshot; %s x cid %s not persisted (nothing else was overwritten)",
                    int(cid) & 0xFFFFFFFF, h.quantity, h.commodity)
                return
            lsnap["stock"] = _prun.stores_to_stock(stores).to_json()
            live["sim_snapshot"] = lsnap
            try:
                await _persist_city_sim(
                    conn, int(cid) & 0xFFFFFFFF, lsnap,
                    live.get("reports") or [], bump_tock=False,
                    _city_id_variants=_city_id_variants,
                    native_ledger_values=native_ledger_values)
            except Exception as pexc:
                logger.warning("RUN persist err: %r", pexc)
            logger.info("RUN mpid=%s (%s) PRODUCED %s x cid %s at "
                        "quality %s -> city 0x%08x stock",
                        mpid, name, h.quantity, h.commodity,
                        h.quality, int(cid) & 0xFFFFFFFF)
            await _mfg_set_cfg(
                conn, cid, bauid, mpid, "deadline", 0,
                _city_buildings_blob_io=_city_buildings_blob_io,
                _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS)
            await _mfg_set_cfg_map(
                conn, cid, bauid, mpid, "have", {},
                _city_buildings_blob_io=_city_buildings_blob_io)
            await _mfg_reemit(
                bauid, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                _live_avatars=_live_avatars, conn=conn,
                _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                anchor_full=anchor_full)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("RUN harvest err: %r", exc)
        finally:
            # Runs on the error path too. This entry is what the next Go press cancels,
            # so a task that died without clearing it leaves the button doing nothing.
            _MFG_RUN_TASKS.get(bauid, {}).pop(int(mpid), None)

    slot = _MFG_RUN_TASKS.setdefault(bauid, {})
    old = slot.get(int(mpid))
    if old is not None and not old.done():
        old.cancel()
    slot[int(mpid)] = asyncio.create_task(_finish())


async def _mfg_environment_loop(*, conn, _CITY_SIM, _ZONE_CACHE,
                                _city_buildings_blob_io):
    interval = _MFG_FETCH_SEC
    logger.info("Environmental accumulation every %.0fs (the engine's development-tick cadence)", interval)

    while True:
        await asyncio.sleep(interval)
        try:
            await _mfg_environment_pass(
                conn, _CITY_SIM=_CITY_SIM, _ZONE_CACHE=_ZONE_CACHE,
                _city_buildings_blob_io=_city_buildings_blob_io)
        except Exception as exc:
            logger.warning("Pass err: %r", exc)
