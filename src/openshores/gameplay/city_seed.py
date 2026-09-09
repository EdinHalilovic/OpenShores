
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.city_ledger import (
    NATIVE_LEDGER_COLUMNS,
)
from openshores.gameplay import gd_tables as _gd

logger = get_logger(__name__)


def add_city_building(city_auid: int, building: dict, *,
                      _SPAWNED_CITIES):
    info = _SPAWNED_CITIES.get(int(city_auid) & 0xFFFFFFFF)
    if not info:
        return False
    info.setdefault("buildings", []).append(dict(building))
    return True


_GD_INDUSTRIES_CACHE = None


def _gd_industries():
    global _GD_INDUSTRIES_CACHE
    if _GD_INDUSTRIES_CACHE is None:
        try:
            _GD_INDUSTRIES_CACHE = _gd.load_industries()
            if _GD_INDUSTRIES_CACHE:
                _jobs = sum(1 for r in _GD_INDUSTRIES_CACHE.values() if r.jobs > 0)
                logger.info("[gd] DbIndustry loaded: %d industries "
                            "(%d provide jobs)",
                            len(_GD_INDUSTRIES_CACHE), _jobs)
            else:
                logger.warning('[gd] DbIndustry unavailable.')
        except Exception as exc:
            logger.error("[gd] DbIndustry load error: %r", exc)
            _GD_INDUSTRIES_CACHE = {}
    return _GD_INDUSTRIES_CACHE


_MANU_PROCS = None


def _manufacturing_procs():
    global _MANU_PROCS
    if _MANU_PROCS is None:
        try:
            _MANU_PROCS = _gd.load_manufacturing_processes()
        except Exception as exc:
            logger.error("[gd] DbManufacturingProcess load error: %r", exc)
            _MANU_PROCS = []
    return _MANU_PROCS


def _industry_producer_kind(industry_id):
    kind = _gd.producer_kind(industry_id)
    cid = {"air": _gd.COMMODITY_AIR, "power": _gd.COMMODITY_POWER}.get(kind, 0)
    return (kind, cid)


def native_ledger_values(snapshot: dict) -> dict:
    out = {}
    for col, (key, _why) in NATIVE_LEDGER_COLUMNS.items():
        try:
            out[col] = float(snapshot.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            logger.debug("Native ledger %s: %r is not a number",
                         col, snapshot.get(key))
            out[col] = 0.0
    return out


def _city_seed_defaults() -> dict:
    target = 100
    return {
        "population": 10,
        "pop_target": target,
        "secondary_pop": 10,
        "building_levels": target,
        "meal_size": 1,
        "satisfaction": 0,
        "enclosure_needed": False,
    }
