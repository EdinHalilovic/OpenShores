
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from openshores.protocol.rng import AuDice
from openshores.gameplay import gd_tables
from openshores.gameplay.worldgen import zone_resources as zr
from openshores.gameplay.city_sim import DEFAULT_STOCK_QUALITY, ItemStock
from openshores.gameplay.process_model import (
    COMPEFFECT_MATERIAL,
    ManufacturingProcess,
    finish_output,
    set_workers_present,
)
from openshores.gameplay.production import (
    BuildingSlots,
    CityStores,
    Item,
    fetch_manufacturing_materials,
    is_critical_to_survival,
    make_one,
    operated_by_citizens,
)


@dataclass
class Output:

    commodity: int
    quality: int
    quantity: int
    mpid: int


_PROC_INDEX: Optional[Dict[int, object]] = None


def _processes_by_id():
    global _PROC_INDEX
    if _PROC_INDEX is None:
        _PROC_INDEX = {p.process_id: p for p in
                       gd_tables.load_manufacturing_processes()}
    return _PROC_INDEX


def build_process(mpid: int, *, building_quality: int = 0,
                  workers: int = 1, shops_enabled: int = 1,
                  tenfold: Optional[bool] = None) -> Optional[ManufacturingProcess]:
    row = _processes_by_id().get(int(mpid))
    if row is None:
        return None

    comps = [
        zr.ProcessComponent(c.commodity, required=c.quantity,
                            effect=c.effect)
        for c in gd_tables.components_for_process(int(mpid))
    ]
    proc = ManufacturingProcess(
        components=comps,
        process_id=int(mpid),
        output_commodity=int(row.commodity),
        building_quality=int(building_quality),
        shops_enabled=int(shops_enabled),
    )
    set_workers_present(proc, int(workers), design_row=_DesignRow(row),
                        component_rows=gd_tables.components_for_process(int(mpid)),
                        tenfold=tenfold)
    proc.work_units = proc.design_work_units
    return proc


class _DesignRow:

    __slots__ = ("work_units", "base_quantity")

    def __init__(self, row):
        self.work_units = int(row.work_units)
        self.base_quantity = int(getattr(row, "output_qty", 0) or 0)


@dataclass
class BuildingProduction:

    industry: int = 0
    building: BuildingSlots = field(default_factory=BuildingSlots)
    mpids: List[int] = field(default_factory=list)

    def sync(self, mpids: Iterable[int], *, levels: int, quality: int,
             jobs: int, staffed: int, damage: int = 0, hits_total: int = 1,
             workers_per_slot: int = 1) -> None:
        want = [int(m) for m in mpids if m]
        if levels > 0:
            want = want[:levels]

        old = {p.process_id: p for p in self.building.processes}
        procs = []
        for mpid in want:
            p = old.get(mpid)
            if p is None:
                p = build_process(mpid, building_quality=quality,
                                  workers=workers_per_slot)
                if p is None:
                    continue
            else:
                p.building_quality = quality
            procs.append(p)

        self.building.processes = procs
        self.building.quality = quality
        self.building.jobs = jobs
        self.building.staffed = staffed
        self.building.damage = damage
        self.building.hits_total = hits_total
        self.mpids = want


def tick_building(bp: BuildingProduction, city: CityStores,
                  zone: zr.AuZoneResource, now_ms: int, dice: AuDice, *,
                  motivation: float,
                  enclosure: int = zr.ENCLOSURE_NONE,
                  sunlight_available: bool = True,
                  food_cids=None) -> List[Output]:
    outputs = _collect(bp, zone, now_ms)

    def run_slot(proc: ManufacturingProcess) -> None:
        fetch_manufacturing_materials(proc, city, zone, bp.industry,
                                      enclosure, sunlight_available, dice)
        make_one(proc, city, None, now_ms, dice)

    operated_by_citizens(bp.building, city, now_ms, dice,
                         motivation=motivation, run_slot=run_slot,
                         food_cids=food_cids)
    return outputs


def _collect(bp: BuildingProduction, zone: zr.AuZoneResource,
             now_ms: int) -> List[Output]:
    out = []
    for proc in bp.building.processes:
        if proc.deadline_ms == 0 or now_ms < proc.deadline_ms:
            continue
        zone_q = zr.quality(zone, proc.output_commodity)
        finish_output(proc, zone_quality=zone_q)
        proc.tick(now_ms)
        if proc.output_quantity > 0:
            out.append(Output(proc.output_commodity, proc.output_quality,
                              proc.output_quantity, proc.process_id))
        proc.consume_applied_inventory()
    return out


def deposit(city: CityStores, outputs: Iterable[Output]) -> None:
    for o in outputs:
        for it in city.stock:
            if it.commodity == o.commodity and it.quality == o.quality:
                it.quantity += o.quantity
                break
        else:
            city.stock.append(Item(o.commodity, quality=o.quality,
                                   quantity=o.quantity, uses=1))


def stock_to_stores(stock, *, quality: int = DEFAULT_STOCK_QUALITY,
                    tools: Optional[List[Item]] = None,
                    **kw) -> CityStores:
    if isinstance(stock, ItemStock):
        stacks = stock.stacks
    else:
        tmp = ItemStock()
        for cid, qty in dict(stock).items():
            tmp.add(int(cid), int(qty), int(quality))
        stacks = tmp.stacks
    items = [Item(int(s.commodity), quality=int(s.quality),
                  quantity=int(s.quantity), uses=1)
             for s in stacks if int(s.quantity) > 0]
    return CityStores(stock=items, tools=list(tools or []), **kw)


def stores_to_stock(city: CityStores) -> ItemStock:
    out = ItemStock()
    for it in city.stock:
        if it.quantity > 0:
            out.add(int(it.commodity), int(it.quantity), int(it.quality))
    return out
