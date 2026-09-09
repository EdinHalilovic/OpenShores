
from __future__ import annotations

from openshores.core.config import (
    DEFAULT_CITY_CYCLE_SECONDS as CITY_CYCLE_INTERVAL_SEC,
)
from openshores.core.logging import get_logger
from openshores.gameplay import city_sim as _cs
from openshores.gameplay import gd_tables as _gd
from openshores.gameplay import manufacturing as _mf
from openshores.gameplay.city_seed import _gd_industries, _manufacturing_procs
from openshores.gameplay.city_sim import food_commodity_ids
from openshores.gameplay.food import _edible_cids
from openshores.gameplay.process_model import (
    COMPEFFECT_MATERIAL as _COMPEFFECT_MATERIAL,
)

logger = get_logger(__name__)


def _dev_industry_id(dev: dict) -> int:
    cpid = int(dev.get("cpid", 0) or 0)
    if not cpid:
        return 0
    try:
        ind = _gd.construction_process_industry(cpid)
    except Exception as exc:
        logger.warning("[gd] ConstructionProcessIndustry failed for cpid %d: %r", cpid, exc)
        ind = 0
    if ind:
        return ind
    return cpid if cpid in _gd_industries() else 0


_NEEDS_POWER_CACHE = {}


def _industry_needs_power(industry_id, mpids=None) -> bool:
    key = (int(industry_id), tuple(sorted(int(m) for m in (mpids or []))))
    if key in _NEEDS_POWER_CACHE:
        return _NEEDS_POWER_CACHE[key]
    if not mpids:
        _NEEDS_POWER_CACHE[key] = False
        return False
    val = False
    try:
        want = {int(m) for m in mpids}
        for r in (_manufacturing_procs() or []):
            if int(r.process_id) not in want:
                continue
            if any(int(c.commodity) == _cs.COMMODITY_POWER
                   and int(c.effect) == _COMPEFFECT_MATERIAL
                   and int(c.quantity) == 0
                   for c in _gd.components_for_process(int(r.process_id))):
                val = True
                break
    except Exception as exc:
        logger.warning("[gd] power-requirement scan failed for industry %r: %r", industry_id, exc)
        val = False
    _NEEDS_POWER_CACHE[key] = val
    return val


def _selected_recipe_commodity(mpids):
    if not mpids:
        return 0
    procs = _manufacturing_procs()
    if not procs:
        return 0
    for m in mpids:
        row = _gd.process_by_id(int(m), procs)
        if row is not None and _mf.is_goods(row):
            return int(row.commodity)
    return 0


def _selected_output_per_worker(mpids, kind, out_cid):
    if not mpids:
        return None
    procs = _manufacturing_procs()
    if not procs:
        return None
    total = 0
    matched = 0
    for m in mpids:
        row = _gd.process_by_id(int(m), procs)
        if row is None or not _mf.is_goods(row):
            continue
        if kind in ("air", "power") and row.commodity != int(out_cid):
            continue
        if kind == "food" and int(row.commodity) not in _edible_cids():
            continue
        matched += 1
        total += _mf.runs_per_interval(
            row.work_units, CITY_CYCLE_INTERVAL_SEC) * row.output_qty
    if not matched:
        return None
    return int(total // matched)


def _industry_food_commodity(industry_id, mpids=None):
    procs = _manufacturing_procs()
    if not procs:
        return 0
    edible = food_commodity_ids()
    if not edible:
        return 0
    chosen = [int(m) for m in (mpids or [])]
    if chosen:
        for p in procs:
            if int(getattr(p, "process_id", 0) or 0) in chosen                     and int(p.commodity) in edible:
                return int(p.commodity)
    return 0


def _jobs_for(b) -> int:
    dj = getattr(b, "design_jobs", None)
    if dj is not None:
        return max(0, int(dj))
    row = _gd_industries().get(int(getattr(b, "industry_id", 0) or 0))
    if row is None:
        return int(getattr(b, "jobs", 0) or 0)
    return max(0, int(row.jobs)) * max(1, int(getattr(b, "levels", 1) or 1))
