
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from openshores.protocol.rng import AuDice
from openshores.gameplay import gd_tables
from openshores.gameplay import production_manager as pmgr
from openshores.gameplay import tock as _tock
from openshores.gameplay.worldgen import zone_resources as zr
from openshores.gameplay.production import CityStores


@dataclass
class CityProduction:

    tock: _tock.TockState
    stores: CityStores = field(default_factory=CityStores)
    buildings: Dict[object, pmgr.BuildingProduction] = field(default_factory=dict)
    started_ms: int = 0

    @classmethod
    def for_city(cls, now_ms: int) -> "CityProduction":
        return cls(tock=_tock.TockState(now_ms), started_ms=int(now_ms))


def building_key(index: int, b) -> object:
    bauid = int(getattr(b, "bauid", 0) or 0)
    return ("bauid", bauid) if bauid else ("idx", int(index),
                                           int(getattr(b, "industry_id", 0) or 0))


def _staffing(b) -> int:
    return int(getattr(b, "employed", 0) or 0)


def sync_buildings(ctx: CityProduction, buildings, *, workers_per_slot: int = 1) -> None:
    live = set()
    for i, b in enumerate(buildings):
        key = building_key(i, b)
        live.add(key)
        bp = ctx.buildings.get(key)
        if bp is None:
            bp = pmgr.BuildingProduction(industry=int(getattr(b, "industry_id", 0) or 0))
            ctx.buildings[key] = bp
        bp.industry = int(getattr(b, "industry_id", 0) or 0)
        bp.sync(list(getattr(b, "mpids", None) or []),
                levels=int(getattr(b, "levels", 1) or 1),
                quality=int(getattr(b, "quality", 0) or 0),
                jobs=int(getattr(b, "jobs", 0) or 0),
                staffed=_staffing(b),
                damage=int(getattr(b, "damage", 0) or 0),
                hits_total=int(getattr(b, "hits_total", 1) or 1),
                workers_per_slot=workers_per_slot)
    for gone in set(ctx.buildings) - live:
        del ctx.buildings[gone]


def development_tick(ctx: CityProduction, state, now_ms: int, *,
                     city_id: int = 0,
                     zone: Optional[zr.AuZoneResource] = None,
                     dice: Optional[AuDice] = None,
                     motivation: float = 1.0,
                     enclosure: int = zr.ENCLOSURE_NONE,
                     is_dark: Optional[Callable[[object], bool]] = None,
                     food_cids=None,
                     workers_per_slot: int = 1) -> List[pmgr.Output]:
    zone = zone if zone is not None else zr.AuZoneResource()
    dice = dice if dice is not None else AuDice()
    buildings = list(getattr(state, "buildings", None) or [])
    sync_buildings(ctx, buildings, workers_per_slot=workers_per_slot)

    ctx.stores.stock = pmgr.stock_to_stores(state.stock).stock
    ctx.stores.tools = pmgr.stock_to_stores(getattr(state, "tools", None) or {}).stock

    made: List[pmgr.Output] = []
    for i, b in enumerate(buildings):
        bp = ctx.buildings.get(building_key(i, b))
        if bp is None or not bp.building.processes:
            continue
        lit = True
        if is_dark is not None:
            lit = not is_dark(b)
        made.extend(pmgr.tick_building(
            bp, ctx.stores, zone, int(now_ms), dice,
            motivation=motivation, enclosure=enclosure,
            sunlight_available=lit, food_cids=food_cids))

    pmgr.deposit(ctx.stores, made)
    state.stock = pmgr.stores_to_stock(ctx.stores)
    state.tools = pmgr.stores_to_stock(CityStores(stock=ctx.stores.tools))
    _bank_food(state, made, food_cids)
    return made


def _food_cids():
    global _FOOD_CIDS
    if _FOOD_CIDS is None:
        _FOOD_CIDS = set(gd_tables.load_food_commodities() or {})
    return _FOOD_CIDS


_FOOD_CIDS = None


def _bank_food(state, made, food_cids=None) -> int:
    edible = set(food_cids) if food_cids else _food_cids()
    if not edible:
        return 0
    moved = 0
    for o in made:
        if o.commodity in edible and o.quantity > 0:
            taken = state.stock.take(o.commodity, o.quantity)
            state.food += taken
            moved += taken
    return moved


def run_tock(ctx: CityProduction, state, now_ms: int, *,
             city_id: int = 0, has_capitol: bool = True, jobs: int = 0,
             is_pirate: bool = False, owned: bool = True,
             **kw):
    on_employ = kw.pop("on_employ", None)
    on_city_cycle = kw.pop("on_city_cycle", None)
    fired = _tock.due(ctx.tock, now_ms, city_id=city_id,
                      has_capitol=has_capitol, jobs=jobs,
                      is_pirate=is_pirate, owned=owned)
    outputs: List[pmgr.Output] = []
    if fired.get("development"):
        outputs = development_tick(ctx, state, now_ms, city_id=city_id, **kw)
        if fired.get("employ") and on_employ is not None:
            on_employ(state)
        if fired.get("city_cycle") and on_city_cycle is not None:
            on_city_cycle(state)
    _tock.commit(ctx.tock, now_ms, fired)
    return fired, outputs
