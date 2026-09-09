
from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.city_design import design_report_blobs
from openshores.gameplay import city_sim as _cs
from openshores.gameplay import gd_tables as _gd
from openshores.gameplay.city_seed import _gd_industries, _industry_producer_kind
from openshores.gameplay.city_snapshot import _building_state_key, _cs_max_levels
from openshores.gameplay.design_report import industry_info, parse_design_report
from openshores.gameplay.industry_econ import (
    _dev_industry_id,
    _industry_food_commodity,
    _industry_needs_power,
    _selected_recipe_commodity,
)
from openshores.gameplay.industry_yield import _industry_output_per_worker

logger = get_logger(__name__)

_BLOB_LEVEL_WARNED = set()

_DESIGN_REPORT_CACHE = {}


async def _design_jobs_for_dev(conn: asyncpg.Connection, dev, industry_id,
                               gd_row):
    try:
        bauid = int(dev.get("bauid") or 0) & 0xFFFFFFFF
    except (AttributeError, TypeError, ValueError):
        return None
    if not bauid or gd_row is None:
        return None
    try:
        if bauid not in _DESIGN_REPORT_CACHE:
            await _design_reports_for(conn, [dev])
        rep = _DESIGN_REPORT_CACHE.get(bauid)
        if not rep:
            return None
        levels, jobs = industry_info(rep, int(industry_id), gd_row)
        return max(0, int(levels) + int(jobs))
    except Exception as exc:
        logger.warning(f"[city-sim] design jobs lookup failed for bauid "
                       f"0x{bauid:08x}: {exc!r}")
        return None


async def _dev_to_building(conn: asyncpg.Connection, dev: dict, idx: int = 0):
    ind_id = _dev_industry_id(dev)
    levels = max(1, int(dev.get("levels", 1) or 1))
    if levels > _cs_max_levels():
        _key = (ind_id, levels)
        if _key not in _BLOB_LEVEL_WARNED:
            _BLOB_LEVEL_WARNED.add(_key)
            logger.warning(f"[city-sim] development levels={levels} exceeds the AddConstructedLevel cap of {_cs_max_levels()}. Treating it as mis-parsed placement data and using 1 (industry 0x{ind_id:02x})")
        levels = 1
    skey = _building_state_key(idx, dev)
    row = _gd_industries().get(ind_id)
    if row is None:
        b = _cs.Building(kind="other", jobs=0, employed=0,
                         industry_id=ind_id, output_per_worker=0,
                         levels=levels)
        b.sim_key = skey
        return b
    jobs = max(0, row.jobs) * levels
    _design_jobs = await _design_jobs_for_dev(conn, dev, ind_id, row)
    if _design_jobs is not None:
        jobs = _design_jobs
    kind, out_cid = _industry_producer_kind(ind_id)
    b = _cs.Building(kind=kind, jobs=jobs, employed=0,
                        industry_id=ind_id,
                        output_commodity=(
                            out_cid
                            or _selected_recipe_commodity(dev.get("manproc"))
                            or (_industry_food_commodity(
                                ind_id, dev.get("manproc"))
                                if kind == "food" else 0)),
                        output_per_worker=_industry_output_per_worker(
                            ind_id, kind, out_cid,
                            mpids=dev.get("manproc")),
                        needs_power=_industry_needs_power(
                            ind_id, dev.get("manproc")),
                        levels=levels,
                        mpids=[int(v) for v in (dev.get("manproc") or [])],
                        quality=int(dev.get("quality", 0) or 0),
                        lat=float(dev.get("lat", 0.0) or 0.0),
                        lon=float(dev.get("lon", 0.0) or 0.0),
                        storage_per_level=int(getattr(row, "storage", 0) or 0),
                        capacitor_per_level=int(getattr(row, "capacitor", 0) or 0),
                        under_construction=bool(dev.get("construction_blob")))
    b.sim_key = skey
    b.design_jobs = _design_jobs
    return b


def _city_homes_from_developments(devs) -> int:
    table = _gd_industries()
    if not table:
        return 0
    total = 0
    for dev in devs or ():
        if dev.get("kind", "building") != "building":
            continue
        ind = _dev_industry_id(dev)
        per = _gd.homes_per_level(ind, table)
        if per:
            total += per * max(1, int(dev.get("levels", 1) or 1))
    return total


async def _design_reports_for(conn: asyncpg.Connection, buildings) -> list:
    out = []
    devs = [b for b in (buildings or [])
            if isinstance(b, dict) and int(b.get("bauid") or 0)]
    if not devs:
        return out
    want = [int(b["bauid"]) & 0xFFFFFFFF for b in devs]
    missing = [a for a in want if a not in _DESIGN_REPORT_CACHE]
    if missing:
        try:
            for _bid, _blob in await design_report_blobs(conn, missing):
                _DESIGN_REPORT_CACHE[int(_bid) & 0xFFFFFFFF] = \
                    parse_design_report(_blob)
        except Exception as exc:
            logger.warning(f"[city-sim] design report read err: {exc!r}")
        for a in missing:
            _DESIGN_REPORT_CACHE.setdefault(a, None)
    for a in want:
        out.append(_DESIGN_REPORT_CACHE.get(a))
    return out
