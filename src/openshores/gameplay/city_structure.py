
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import city_sim as _cs
from openshores.gameplay import gd_tables as _gd
from openshores.gameplay.city_seed import _gd_industries
from openshores.gameplay.city_snapshot import (
    _restore_building_levels,
    _restore_building_quality,
    _snapshot_building_levels,
    _snapshot_building_quality,
    _split_developments,
)

logger = get_logger(__name__)


def _city_homes_from_buildings(buildings) -> int:
    table = _gd_industries()
    if not table:
        return 0
    total = 0
    for b in buildings or ():
        per = _gd.homes_per_level(int(getattr(b, "industry_id", 0) or 0), table)
        if per:
            total += per * max(1, int(getattr(b, "levels", 1) or 1))
    return total


async def _build_city_sim_state(conn, info: dict, *, _dev_to_building):
    snap = info.get("sim_snapshot") or {}
    st = _cs.CityState(
        population=int(snap.get("population", 0)),
        satisfaction=int(snap.get("satisfaction", 0)),
        pop_target=int(snap.get("pop_target", 0)),
        secondary_pop=int(snap.get("secondary_pop", snap.get("population", 0))),
        housing_max=int(snap.get("housing_max", 0)),
        meal_size=int(snap.get("meal_size", 0)),
        building_levels=int(snap.get("building_levels", 0)),
        enclosure_needed=bool(snap.get("enclosure_needed", False)),
        on_ringworld=bool(snap.get("on_ringworld", False)),
        food=int(snap.get("food", 0)),
        bank=float(snap.get("bank", 0.0)),
        govt=float(snap.get("govt", 0.0)),
        income_tax_pct=float(snap.get("income_tax_pct", 0.0)),
        sales_tax_pct=float(snap.get("sales_tax_pct", 0.0)),
        food_quality=int(snap.get("food_quality", 0)),
        food_quality_source=int(snap.get("food_quality_source", 0)),
        last_tribute=float(snap.get("last_tribute", 0.0)),
        salaries_paid=float(snap.get("salaries_paid", 0.0)),
        salary_income=float(snap.get("salary_income", 0.0)),
        sales_income=float(snap.get("sales_income", 0.0)),
        purchases_paid=float(snap.get("purchases_paid", 0.0)),
        govt_income_tax=float(snap.get("govt_income_tax", 0.0)),
        govt_sales_tax=float(snap.get("govt_sales_tax", 0.0)),
        tribute_paid=float(snap.get("tribute_paid", 0.0)),
    )
    st.stock = _cs.ItemStock.from_json(snap.get("stock"))
    st.tools = _cs.ItemStock.from_json(snap.get("tools"))
    st.buildings = [await _dev_to_building(conn, b, i)
                    for i, b in enumerate(info.get("buildings", []))]
    _restore_building_levels(st, snap)
    _restore_building_quality(st, snap, info.get("buildings", []))
    if _gd_industries():
        homes = _city_homes_from_buildings(st.buildings)
        st.building_levels = homes
        st.pop_target = homes
    return st


def _snapshot_city_sim(st, devs: list = None) -> dict:
    return {
        **({"building_quality": _snapshot_building_quality(st, devs),
            "building_levels_by_key": _snapshot_building_levels(st)}
           if devs is not None else {}),
        "population": st.population, "satisfaction": st.satisfaction,
        "pop_target": st.pop_target, "secondary_pop": st.secondary_pop,
        "housing_max": st.housing_max, "meal_size": st.meal_size,
        "building_levels": st.building_levels,
        "enclosure_needed": bool(st.enclosure_needed),
        "on_ringworld": bool(st.on_ringworld),
        "food": st.food, "stock": st.stock.to_json(),
        "tools": st.tools.to_json(),
        "bank": st.bank, "govt": st.govt,
        "income_tax_pct": st.income_tax_pct, "sales_tax_pct": st.sales_tax_pct,
        "food_quality": st.food_quality,
        "food_quality_source": st.food_quality_source,
        "last_tribute": st.last_tribute,
        "salaries_paid": st.salaries_paid, "salary_income": st.salary_income,
        "sales_income": st.sales_income, "purchases_paid": st.purchases_paid,
        "govt_income_tax": st.govt_income_tax,
        "govt_sales_tax": st.govt_sales_tax,
        "tribute_paid": st.tribute_paid,
    }


def _refresh_city_structure(info: dict, row: dict) -> bool:
    if "developments" not in row:
        return False
    blds, roads, areas = _split_developments(row.get("developments"))
    if (blds == info.get("buildings")
            and roads == info.get("roads")
            and areas == info.get("area_ops")):
        return False
    before = len(info.get("buildings") or [])
    info["buildings"], info["roads"], info["area_ops"] = blds, roads, areas
    if len(blds) != before:
        logger.info("[city-sim] structure changed: %d -> %d building(s), "
                    "%d road(s)", before, len(blds), len(roads))
    return True
