
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Sequence, Set

from openshores.protocol.rng import AuDice
from openshores.gameplay import commodity_flags
from openshores.gameplay.worldgen import zone_resources as zr
from openshores.gameplay.gear_wear import au_item_use
from openshores.gameplay.process_model import (
    COMMODITY_AIR,
    COMMODITY_ELECTRICITY,
    COMMODITY_SUNLIGHT,
    COMMODITY_WATER,
    COMMODITY_WATER_IN_ENVIRONMENT,
    COMPEFFECT_DECREASE_TIME,
    COMPEFFECT_INCREASE_OUTPUT,
    COMPEFFECT_MATERIAL,
    ManufacturingProcess,
)
from openshores.gameplay.worldgen.zone_resources import NaturalItem as Item


VEHICLE_COMMODITIES = frozenset({
    6, 7, 8, 9, 0x1C, 0x36, 0x46, 0x47, 0x4D, 0x52, 0x67, 0x68, 0x84, 0x85,
    0xE7,
})

LABOR_BOOST = 5
PRODUCTION_BOOST = 1


@dataclass
class CityStores:

    stock: List[Item] = field(default_factory=list)
    tools: List[Item] = field(default_factory=list)
    patents: Set[int] = field(default_factory=set)
    vehicles: Set[int] = field(default_factory=set)
    on_ringworld: bool = False

    citizen_balance: float = 0.0
    empire_income_tax: float = 0.0
    govt_income_tax_collected: float = 0.0

    def has_power(self) -> bool:
        if self.on_ringworld:
            return True
        return any(i.commodity == COMMODITY_ELECTRICITY and i.quantity > 0
                   for i in self.stock)

    def _check_out_tool(self, cid: int) -> Optional[Item]:
        for it in self.tools:
            if it.commodity == cid:
                return it
        for it in list(self.stock):
            if it.commodity == cid:
                self.stock.remove(it)
                self.tools.append(it)
                return it
        return None

    def has_tool_or_vehicle(self, cid: int) -> bool:
        if cid in VEHICLE_COMMODITIES:
            return cid in self.vehicles
        return self._check_out_tool(cid) is not None

    def apply_tool_or_vehicle(self, cid: int, dice: AuDice) -> bool:
        if cid in VEHICLE_COMMODITIES:
            return cid in self.vehicles
        it = self._check_out_tool(cid)
        if it is None:
            return False
        if not _use_item(it, dice):
            it.quantity -= 1
            if it.quantity <= 0:
                self.tools.remove(it)
        return True

    def get_labor_boost(self, cid: int, dice: AuDice) -> int:
        return LABOR_BOOST if self.apply_tool_or_vehicle(cid, dice) else 0

    def get_production_boost(self, cid: int, dice: AuDice) -> int:
        return PRODUCTION_BOOST if self.apply_tool_or_vehicle(cid, dice) else 0


def _use_item(item: Item, dice: AuDice) -> bool:
    from openshores.gameplay.gear_wear import test_quality
    if item.uses <= 0:
        return False
    if test_quality(item.quality, dice):
        return True
    item.uses -= 1
    return item.uses != 0


@dataclass
class Worker:

    gear: List[Item] = field(default_factory=list)
    balance: float = 0.0

    def find_ready_item(self, cid: int) -> Optional[Item]:
        for it in self.gear:
            if it.commodity == cid and it.quantity > 0 and it.uses > 0:
                return it
        return None

    def use_gear_item(self, item: Item, dice: AuDice) -> None:
        if not _use_item(item, dice):
            item.quantity -= 1
            if item.quantity <= 0 and item in self.gear:
                self.gear.remove(item)

    def get_labor_boost(self, cid: int, dice: AuDice) -> int:
        it = self.find_ready_item(cid)
        if it is None:
            return 0
        self.use_gear_item(it, dice)
        return LABOR_BOOST

    def get_production_boost(self, cid: int, dice: AuDice) -> int:
        it = self.find_ready_item(cid)
        if it is None:
            return 0
        self.use_gear_item(it, dice)
        return PRODUCTION_BOOST

    def credit_account(self, amount: float) -> None:
        self.balance += amount


def apply_inventory_material(component: zr.ProcessComponent, item: Item,
                             sun_q: int, wat_q: int, min_q: int,
                             dice: AuDice) -> int:
    if component.required != 0 and item.quality < min_q:
        return 0

    if sun_q and component.commodity == COMMODITY_SUNLIGHT \
            and item.commodity == COMMODITY_ELECTRICITY:
        saved = item.quality
        item.quality = sun_q
        consumed, _ = zr.apply_material(component, item, dice)
        item.quality = 255
        del saved
        return consumed

    if wat_q and component.commodity == COMMODITY_WATER_IN_ENVIRONMENT \
            and item.commodity == COMMODITY_WATER:
        saved = item.quality
        item.quality = wat_q
        consumed, _ = zr.apply_material(component, item, dice)
        item.quality = saved
        return consumed

    if component.required == 0 or component.have == 0:
        consumed, _ = zr.apply_material(component, item, dice)
        return consumed

    if component.quality < min_q:
        component.quality = min_q
    consumed, _ = zr.apply_material(component, item, dice)
    if component.quality < min_q:
        component.quality = min_q
    return consumed


def _best_item(items: Sequence[Item], cid: int) -> Optional[Item]:
    best = None
    for it in items:
        if it.commodity != cid or it.quantity <= 0:
            continue
        if best is None or best.quality < it.quality:
            best = it
    return best


def fetch_materials(proc: ManufacturingProcess, city: CityStores,
                    sun_q: int, wat_q: int, dice: AuDice,
                    is_patent: Optional[Callable[[int], bool]] = None) -> bool:
    if is_patent is None:
        is_patent = commodity_flags.is_patent

    changed_any = False
    while True:
        changed = False
        for c in proc.components:
            if c.required == 0:
                if c.have != 0:
                    continue
            elif c.have >= c.required:
                continue

            if is_patent(c.commodity):
                if c.commodity in city.patents:
                    c.have = 1
                    c.quality = 0
                    changed = True
                continue

            source = c.commodity
            if sun_q and c.commodity == COMMODITY_SUNLIGHT:
                source = COMMODITY_ELECTRICITY
            elif wat_q and c.commodity == COMMODITY_WATER_IN_ENVIRONMENT:
                source = COMMODITY_WATER

            item = _best_item(city.tools, source) or _best_item(city.stock, source)
            if item is None:
                continue

            before = item.quantity
            applied = apply_inventory_material(c, item, sun_q, wat_q,
                                               proc.minimum_q_set, dice)
            proc.work_units += applied
            if item.quantity <= 0:
                for bag in (city.tools, city.stock):
                    if item in bag:
                        bag.remove(item)
                changed = True
            elif item.quantity != before:
                changed = True
        changed_any = changed_any or changed
        if not changed:
            return changed_any


def fetch_manufacturing_materials(proc: ManufacturingProcess,
                                  city: CityStores,
                                  zone: zr.AuZoneResource,
                                  industry: int,
                                  enclosure: int,
                                  sunlight_available: bool,
                                  dice: AuDice,
                                  is_patent=None) -> bool:
    _, _, sun_q, wat_q = zr.fetch_manufacturing_materials(
        proc.components, zone, industry, enclosure, sunlight_available, dice)
    return fetch_materials(proc, city, sun_q, wat_q, dice, is_patent)


def make_one(proc: ManufacturingProcess, city: CityStores,
             worker: Optional[Worker], now_ms: int, dice: AuDice) -> bool:
    if proc.process_id == 0:
        return False

    if not proc.is_completed():
        for c in proc.components:
            if not (c.effect == COMPEFFECT_MATERIAL and c.required == 0
                    and c.have == 0):
                continue
            if c.commodity == COMMODITY_ELECTRICITY:
                if not city.has_power():
                    return False
            else:
                held = worker is not None \
                    and worker.find_ready_item(c.commodity) is not None
                if not held and not city.has_tool_or_vehicle(c.commodity):
                    return False

    if not proc.can_run():
        return False

    labour = 0
    production = 0
    for c in proc.components:
        if c.effect == COMPEFFECT_DECREASE_TIME:
            if c.commodity == COMMODITY_ELECTRICITY:
                if c.have:
                    labour += LABOR_BOOST
                    continue
                if not city.has_power():
                    continue
                labour += LABOR_BOOST
            else:
                if c.have:
                    labour += LABOR_BOOST
                    continue
                b = worker.get_labor_boost(c.commodity, dice) if worker else 0
                if b == 0:
                    b = city.get_labor_boost(c.commodity, dice)
                if b == 0:
                    continue
                labour += b
            c.have = 1

        elif c.effect == COMPEFFECT_INCREASE_OUTPUT:
            if c.commodity == COMMODITY_ELECTRICITY:
                if c.have:
                    production += PRODUCTION_BOOST
                    continue
                if not city.has_power():
                    continue
                production += PRODUCTION_BOOST
            else:
                if c.have:
                    production += PRODUCTION_BOOST
                    continue
                b = worker.get_production_boost(c.commodity, dice) if worker else 0
                if b == 0:
                    b = city.get_production_boost(c.commodity, dice)
                if b == 0:
                    continue
                production += b
            c.have = 1

        elif (c.effect == COMPEFFECT_MATERIAL and c.required == 0
                and c.have == 0):
            if c.commodity == COMMODITY_ELECTRICITY:
                if city.has_power():
                    c.have = 1
            else:
                if worker is not None:
                    it = worker.find_ready_item(c.commodity)
                    if it is not None:
                        c.have = 1
                        worker.use_gear_item(it, dice)
                        continue
                if city.apply_tool_or_vehicle(c.commodity, dice):
                    c.have = 1

    proc.run(now_ms, labour, production)

    if worker is not None:
        _pay(city, worker)
    return True


WAGE_PER_MAKE_ONE = 1.0


def _pay(city: CityStores, worker: Worker) -> None:
    balance = city.citizen_balance
    wage = WAGE_PER_MAKE_ONE
    if balance < wage:
        wage = balance
    if not (balance >= WAGE_PER_MAKE_ONE or wage > 0.0):
        return
    city.citizen_balance -= wage
    tax = city.empire_income_tax
    if tax == 0.0:
        worker.credit_account(wage)
    else:
        t = (tax / 100.0) * wage
        worker.credit_account(wage - t)
        city.govt_income_tax_collected += t


def motivation_to_work(empire_income_tax: float, loyalty: float = 0.0,
                       allegiance_mismatch: bool = False) -> float:
    if empire_income_tax >= 100.0:
        return 0.0
    m = 1.0 - empire_income_tax / 100.0
    if allegiance_mismatch:
        m *= (1.0 - loyalty)
    return m


def is_worker_available(staffed: int, jobs: int, dice: AuDice) -> bool:
    if staffed == 0 or jobs == 0:
        return False
    if staffed == jobs:
        return True
    return dice.roll(1, jobs) <= staffed


@dataclass
class BuildingSlots:

    processes: List[ManufacturingProcess] = field(default_factory=list)
    quality: int = 0
    damage: int = 0
    hits_total: int = 1
    staffed: int = 0
    jobs: int = 0

    def is_ok_to_manufacture(self) -> bool:
        if self.damage == 0:
            return True
        return self.damage < self.hits_total


def operated_by_citizens(building: BuildingSlots, city: CityStores,
                         now_ms: int, dice: AuDice, *,
                         motivation: float,
                         run_slot: Callable[[ManufacturingProcess], None],
                         food_cids=None) -> bool:
    if not building.is_ok_to_manufacture():
        return False
    if not building.processes:
        return False

    worker_available = is_worker_available(building.staffed, building.jobs, dice)
    any_attempted = False

    for proc in building.processes:
        if proc.shops_enabled == 0:
            continue
        if proc.deadline_ms != 0:
            continue
        if proc.minimum_q_set > building.quality:
            continue
        if proc.throttled(now_ms):
            continue
        if not worker_available:
            continue

        proc.last_worked_ms = now_ms
        any_attempted = True

        if not (is_critical_to_survival(proc, food_cids=food_cids)
                or motivation >= 1.0
                or dice.roll(1, 100) <= motivation * 100.0):
            continue

        run_slot(proc)

    return any_attempted


CRITICAL_COMMODITIES = frozenset({
    COMMODITY_ELECTRICITY, COMMODITY_AIR, COMMODITY_WATER,
})


def is_critical_to_survival(proc: ManufacturingProcess,
                            food_only: bool = False,
                            food_cids=None) -> bool:
    cid = proc.output_commodity
    if cid <= 0:
        return False
    if not food_only and cid in CRITICAL_COMMODITIES:
        return True
    if food_cids is None:
        from openshores.gameplay import gd_tables
        food_cids = gd_tables.load_food_commodities()
    return cid in food_cids


def player_run(proc: ManufacturingProcess, city: CityStores, worker: Worker,
               now_ms: int, dice: AuDice,
               fetch: Callable[[ManufacturingProcess], None]) -> bool:
    proc.worked(now_ms)
    fetch(proc)
    return make_one(proc, city, worker, now_ms, dice)
