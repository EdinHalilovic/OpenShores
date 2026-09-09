
from __future__ import annotations

import asyncio
import time as _time

from openshores.core.config import (
    DEFAULT_CITY_CYCLE_SECONDS as CITY_CYCLE_INTERVAL_SEC,
)
from openshores.core.logging import get_logger
from openshores.database.repositories.city_sim_state import (
    _load_city_sim_snapshot,
    _persist_city_sim,
    city_roster_rows,
)
from openshores.database.repositories.city_site import _city_id_variants
from openshores.gameplay import city_report as _cr
from openshores.gameplay import city_sim as _cs
from openshores.gameplay import development as _dv
from openshores.gameplay.city.zone import _city_zone
from openshores.gameplay.city_registry import _CITY_SIM, _SPAWNED_CITIES
from openshores.gameplay.city_seed import native_ledger_values
from openshores.gameplay.city_snapshot import _staff_city, _write_city_report_html
from openshores.gameplay.city_structure import (
    _build_city_sim_state,
    _refresh_city_structure,
    _snapshot_city_sim,
)
from openshores.gameplay.worldgen import zone_resources as _zr
from openshores.protocol.rng import AuDice

logger = get_logger(__name__)


_MIGRATION_ENABLED = True

_PRODUCTION_ENABLED = True

_INFLIGHT: set = set()


async def _run_city_tock(conn, cid: int, info: dict, now_ms: int = None, *,
                         _dev_to_building, _design_reports_for):
    pop_before = int((info.get("sim_snapshot") or {}).get("population", 0))
    st = await _build_city_sim_state(conn, info,
                                     _dev_to_building=_dev_to_building)
    result = _cs.run_cycle(st, apply_production=not _PRODUCTION_ENABLED,
                           apply_migration_flag=_MIGRATION_ENABLED)
    info["sim_snapshot"] = _snapshot_city_sim(st, info.get("buildings", []))
    rep_id = info.get("capitol") or cid
    rep = _cr.build_report(rep_id, info.get("name", ""), pop_before, result, st,
                           int(now_ms if now_ms is not None else _time.time() * 1000),
                           buildings=info.get("buildings"),
                           design_reports=await _design_reports_for(
                               conn, info.get("buildings")))
    info.setdefault("reports", []).append(rep.to_dict())
    info["reports"] = info["reports"][-50:]
    info["last_report"] = rep.to_dict()
    info["last_result"] = result
    return rep


async def _city_sim_manager(conn, *, _city_info_from_row):
    logger.info("[city-sim] manager started (db-driven, scene-independent)")
    while True:
        interval = CITY_CYCLE_INTERVAL_SEC
        rows = []
        try:
            rows = await city_roster_rows(conn)
        except Exception as exc:
            logger.error(f"[city-sim] roster load err: {exc!r}")
        now = int(_time.time() * 1000)
        for row in rows:
          try:
            cid = int(row.get("id") or 0) & 0xFFFFFFFF
            if not cid:
                continue
            info = _CITY_SIM.get(cid)
            if info is None:
                info = await _city_info_from_row(conn, row)
                if not info.get("last_tock"):
                    info["last_tock"] = now - int(interval * 1000)
                _CITY_SIM[cid] = info
            else:
                _refresh_city_structure(info, row)
            continue
          except Exception as _cityexc:
            logger.error(f"[city-sim] city pass err 0x{int(row.get('id') or 0) & 4294967295:08x}: {_cityexc!r}.")
        await asyncio.sleep(max(1.0, min(interval, 15.0)))


_CITY_PRODUCTION = {}
_DEV_TICK_SEC = 1.0


def _run_city_cycle_from_tock(conn, cauid: int, info: dict, st, *,
                              design_reports) -> None:
    pop_before = int((info.get("sim_snapshot") or {}).get("population", 0))
    result = _cs.run_cycle(st, apply_production=False,
                           apply_migration_flag=_MIGRATION_ENABLED)
    info["sim_snapshot"] = _snapshot_city_sim(st, info.get("buildings", []))
    rep = _cr.build_report(info.get("capitol") or cauid, info.get("name", ""),
                           pop_before, result, st, int(_time.time() * 1000),
                           buildings=info.get("buildings"),
                           design_reports=design_reports)
    info.setdefault("reports", []).append(rep.to_dict())
    info["reports"] = info["reports"][-50:]
    info["last_report"] = rep.to_dict()
    info["last_result"] = result
    try:
        task = asyncio.get_running_loop().create_task(
            _persist_city_sim(conn, cauid, info["sim_snapshot"], info["reports"],
                              _city_id_variants=_city_id_variants,
                              native_ledger_values=native_ledger_values))
        _INFLIGHT.add(task)
        task.add_done_callback(_INFLIGHT.discard)
    except Exception as exc:
        logger.error(f"[city-prod] persist err "
                     f"0x{int(cauid) & 0xFFFFFFFF:08x}: {exc!r}")
    logger.info(f"[city-prod] city cycle 0x{int(cauid) & 0xFFFFFFFF:08x} "
                f"'{info.get('name','')}' pop={st.population} sat={st.satisfaction}")


async def _city_development_loop(conn, *, _dev_to_building, _design_reports_for,
                                 _make_is_dark, _ZONE_CACHE):
    logger.info("[city-prod] 10 s development tick ENABLED "
                "(city_sim.produce is off)")
    dice = AuDice()
    blank_zone = _zr.AuZoneResource()
    tick_sec = _DEV_TICK_SEC
    while True:
        now_ms = int(_time.time() * 1000)
        for cauid, info in list(_CITY_SIM.items()):
            try:
                ctx = _CITY_PRODUCTION.get(cauid)
                if ctx is None:
                    ctx = _dv.CityProduction.for_city(now_ms)
                    _CITY_PRODUCTION[cauid] = ctx
                st = await _build_city_sim_state(
                    conn, info, _dev_to_building=_dev_to_building)
                _staff_city(st)
                def _cycle(state, _cauid=cauid, _info=info):
                    _run_city_cycle_from_tock(
                        conn, _cauid, _info, state,
                        design_reports=design_reports)

                zone = await _city_zone(conn, cauid, _ZONE_CACHE=_ZONE_CACHE,
                                        _CITY_SIM=_CITY_SIM)
                design_reports = await _design_reports_for(
                    conn, info.get("buildings"))
                fired, made = _dv.run_tock(
                    ctx, st, now_ms, city_id=int(cauid) & 0xFFFFFFFF,
                    has_capitol=bool(info.get("capitol")),
                    jobs=sum(int(getattr(b, "jobs", 0) or 0) for b in st.buildings),
                    zone=zone or blank_zone, dice=dice,
                    motivation=1.0, is_dark=await _make_is_dark(conn, cauid),
                    on_employ=_staff_city, on_city_cycle=_cycle)
                if fired.get("development"):
                    info["sim_snapshot"] = _snapshot_city_sim(st, info.get("buildings", []))
                if made:
                    logger.info(f"[city-prod] 0x{int(cauid) & 0xFFFFFFFF:08x} "
                                f"'{info.get('name','')}' made "
                                + ", ".join(f"{o.quantity}x cid{o.commodity}@q{o.quality}"
                                            for o in made[:4]))
            except Exception as exc:
                logger.error(f"[city-prod] tick err "
                             f"0x{int(cauid) & 0xFFFFFFFF:08x}: {exc!r}")
        await asyncio.sleep(tick_sec)


async def _city_cycle_loop(conn, cauid: int, *, _dev_to_building,
                           _design_reports_for, report_dir):
    interval = CITY_CYCLE_INTERVAL_SEC
    info = _SPAWNED_CITIES.get(cauid)
    if info is not None and "sim_snapshot" not in info:
        state, reports = await _load_city_sim_snapshot(
            conn, cauid, _city_id_variants=_city_id_variants)
        if state is not None:
            info["sim_snapshot"] = state
        if reports:
            info["reports"] = reports
    while True:
        await asyncio.sleep(interval)
        info = _SPAWNED_CITIES.get(cauid)
        if not info:
            return
        try:
            pop_before = 0
            snap0 = info.get("sim_snapshot") or {}
            pop_before = int(snap0.get("population", 0))
            st = await _build_city_sim_state(
                conn, info, _dev_to_building=_dev_to_building)
            result = _cs.run_cycle(
                st, apply_migration_flag=_MIGRATION_ENABLED)
            info["sim_snapshot"] = _snapshot_city_sim(st, info.get("buildings", []))
            rep = _cr.build_report(cauid, info.get("name", ""), pop_before,
                                   result, st, int(_time.time() * 1000),
                                   buildings=info.get("buildings"),
                                   design_reports=await _design_reports_for(
                                       conn, info.get("buildings")))
            info.setdefault("reports", []).append(rep.to_dict())
            info["reports"] = info["reports"][-50:]
            await _persist_city_sim(conn, cauid, info["sim_snapshot"],
                                    info["reports"],
                                    _city_id_variants=_city_id_variants,
                                    native_ledger_values=native_ledger_values)
            info["last_result"] = result
            info["last_report"] = rep.to_dict()
            try:
                _write_city_report_html(cauid, info, _cr.format_report_html(rep),
                                        report_dir=report_dir)
            except Exception as exc:
                logger.error(f"[city-sim] html write err "
                             f"0x{cauid & 0xFFFFFFFF:08x}: {exc!r}")
        except Exception as exc:
            logger.error(f"[city-sim] cycle err "
                         f"0x{cauid & 0xFFFFFFFF:08x}: {exc!r}")


def start_city_simulation(conn, *, _city_info_from_row, _dev_to_building,
                          _design_reports_for, _make_is_dark,
                          _ZONE_CACHE) -> None:
    asyncio.create_task(_city_sim_manager(
        conn, _city_info_from_row=_city_info_from_row))
    asyncio.create_task(_city_development_loop(
        conn, _dev_to_building=_dev_to_building,
        _design_reports_for=_design_reports_for,
        _make_is_dark=_make_is_dark, _ZONE_CACHE=_ZONE_CACHE))
