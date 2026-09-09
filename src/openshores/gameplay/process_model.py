
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from openshores.gameplay import gd_tables, manufacturing
from openshores.gameplay.worldgen.zone_resources import ProcessComponent


COMPEFFECT_NOTHING_A = 1
COMPEFFECT_DECREASE_TIME = 2
COMPEFFECT_DECREASE_MATERIALS = 3
COMPEFFECT_NOTHING_B = 4
COMPEFFECT_MATERIAL = 5
COMPEFFECT_INCREASE_OUTPUT = 6

UNAIDED_WORKER_RATE = 8

RESTART_THROTTLE_MS = 10999

COMMODITY_ELECTRICITY = 3
COMMODITY_AIR = 5
COMMODITY_MONEY = 0x9D
COMMODITY_WATER = 0x53
COMMODITY_WATER_IN_ENVIRONMENT = 0x58
COMMODITY_SUNLIGHT = 0x5E


@dataclass
class ManufacturingProcess:

    components: List[ProcessComponent] = field(default_factory=list)

    shops_enabled: int = 0
    workers_present: int = 0
    output_quantity_base: int = 0
    work_units: int = 0
    process_id: int = 0
    production_boost: int = 0
    minimum_q_required: int = 0
    minimum_q_set: int = 0
    deadline_ms: int = 0
    output_quality: int = 0
    output_quantity: int = 0
    output_commodity: int = 0
    design_work_units: int = 0
    design_output_quantity: int = 0
    last_worked_ms: int = 0
    building_quality: int = 0

    def is_completed(self) -> bool:
        for c in self.components:
            if c.effect != COMPEFFECT_MATERIAL:
                continue
            if c.required == 0:
                if c.have == 0:
                    return False
            elif c.have < c.required:
                return False
        return True

    def can_run(self) -> bool:
        return (self.deadline_ms == 0
                and self.process_id != 0
                and self.minimum_q_set <= self.building_quality
                and self.is_completed())

    def tick(self, now_ms: int) -> bool:
        if now_ms < self.deadline_ms:
            return False
        self.work_units = self.design_work_units
        self.deadline_ms = 0
        return True

    def run(self, now_ms: int, labour: int, production_boost: int) -> None:
        workers = self.workers_present
        self.output_quantity_base = self.design_output_quantity
        n = workers if workers != 0 else 1
        self.production_boost = _as_int8(n * production_boost)
        secs = (self.work_units - 1 + labour + UNAIDED_WORKER_RATE) \
            // (labour + UNAIDED_WORKER_RATE)
        if workers > 1:
            secs //= workers
        if secs == 0:
            secs = 1
        self.deadline_ms = now_ms + secs * 1000

    def worked(self, now_ms: int) -> None:
        self.last_worked_ms = now_ms

    def set_minimum_q(self, q: int) -> None:
        if self.minimum_q_required <= q:
            self.minimum_q_set = q & 0xFF

    def set_shops_enabled(self, n: int) -> None:
        self.shops_enabled = n

    def consume_applied_inventory(self) -> None:
        for c in self.components:
            c.have = 0
            c.quality = 0

    def throttled(self, now_ms: int) -> bool:
        return (self.last_worked_ms != 0
                and now_ms - self.last_worked_ms <= RESTART_THROTTLE_MS)


def _as_int8(v: int) -> int:
    v &= 0xFF
    return v - 256 if v >= 128 else v


def tenfold_output(commodity, *, broker_item=None) -> bool:
    cid = int(commodity)
    if cid in (COMMODITY_ELECTRICITY, COMMODITY_MONEY):
        return True
    if broker_item is None:
        if gd_tables.is_tech(cid) or gd_tables.is_patent(cid):
            return False
        broker_item = gd_tables.is_broker_item(cid)
    elif broker_item and _is_tech_or_patent(cid):
        return False
    return True if broker_item is None else bool(broker_item)


def _is_tech_or_patent(cid) -> bool:
    return bool(gd_tables.is_tech(cid) or gd_tables.is_patent(cid))


def set_workers_present(proc: ManufacturingProcess, n: int, *, design_row,
                        component_rows, tenfold: Optional[bool] = None) -> None:
    proc.workers_present = n
    if proc.process_id <= 0:
        return
    k = n if n != 0 else 1

    proc.design_work_units = design_row.work_units * k
    proc.design_output_quantity = design_row.base_quantity * k

    if tenfold is None:
        tenfold = tenfold_output(proc.output_commodity)
    if tenfold:
        proc.design_work_units *= 10
        proc.design_output_quantity *= 10

    if proc.deadline_ms == 0:
        proc.work_units = proc.design_work_units

    by_commodity = {}
    for row in component_rows:
        by_commodity.setdefault(row.commodity, row)
    for c in proc.components:
        if c.effect != COMPEFFECT_MATERIAL or c.required == 0:
            continue
        row = by_commodity.get(c.commodity)
        if row is None:
            continue
        c.required = row.quantity * k
        if c.commodity != COMMODITY_MONEY:
            c.required *= 10


def finish_output(proc: ManufacturingProcess, zone_quality: int = 0,
                  patent_cap: int = 255,
                  zone_quality_counts: bool = True) -> None:
    inputs = []
    for c in proc.components:
        if (c.effect == COMPEFFECT_MATERIAL and c.required != 0
                and c.commodity not in (COMMODITY_MONEY, COMMODITY_ELECTRICITY)
                and c.quality != 0 and c.have != 0):
            inputs.append((c.quality, c.have))

    proc.output_quality = manufacturing.output_quality(
        proc.output_commodity,
        proc.building_quality,
        inputs,
        zone_quality=zone_quality if zone_quality_counts else 0,
        tech_cap=patent_cap,
    )

    boost = proc.production_boost
    base = proc.output_quantity_base
    if boost > 0:
        extra = (boost * base) // 10
        if extra < boost:
            extra = boost
        proc.output_quantity = base + extra
    else:
        proc.output_quantity = base
