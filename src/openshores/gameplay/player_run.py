

from __future__ import annotations

from typing import Optional

from openshores.gameplay import production as pr
from openshores.gameplay import production_manager as pmgr
from openshores.gameplay.worldgen import zone_resources as zr
from openshores.protocol.rng import AuDice
from openshores.gameplay.city_sim import ItemStock


def _dice(seed: int):
    return AuDice(int(seed) & 0xFFFFFFFF)


class RunResult:

    __slots__ = ("started", "reason", "deadline_ms", "seconds",
                 "outputs", "commodity", "quantity", "quality")

    def __init__(self, started=False, reason="", deadline_ms=0, seconds=0,
                 outputs=None, commodity=0, quantity=0, quality=0):
        self.started = bool(started)
        self.reason = reason
        self.deadline_ms = int(deadline_ms)
        self.seconds = int(seconds)
        self.outputs = list(outputs or [])
        self.commodity = int(commodity)
        self.quantity = int(quantity)
        self.quality = int(quality)

    def __repr__(self):
        if not self.started:
            return "RunResult(refused: %s)" % self.reason
        return ("RunResult(started, %d s, -> cid %d x%d q%d)"
                % (self.seconds, self.commodity, self.quantity, self.quality))


def build_line(mpid: int, *, stock, zone, industry: int = 0,
               building_quality: int = 1, shops: int = 1,
               minimum_quality: int = 0, enclosure: int = zr.ENCLOSURE_NONE,
               sunlight_available: bool = True, dice=None):
    proc = pmgr.build_process(int(mpid), building_quality=int(building_quality),
                              workers=max(1, int(shops)),
                              shops_enabled=max(1, int(shops)))
    if proc is None:
        return None, None
    proc.minimum_q_set = int(minimum_quality) & 0xFF
    stores = pmgr.stock_to_stores(stock)
    d = dice or _dice(int(mpid) * 2654435761)
    pr.fetch_manufacturing_materials(proc, stores, zone, int(industry),
                                     int(enclosure), bool(sunlight_available), d)
    return proc, stores


def start(proc, stores, now_ms: int, *, dice=None) -> RunResult:
    if proc is None:
        return RunResult(reason="unknown recipe")
    if proc.deadline_ms:
        return RunResult(reason="already running", deadline_ms=proc.deadline_ms)
    if proc.process_id == 0:
        return RunResult(reason="no process selected")
    if proc.minimum_q_set > proc.building_quality:
        return RunResult(reason="minimum quality %d exceeds building quality %d"
                                % (proc.minimum_q_set, proc.building_quality))
    if not proc.is_completed():
        missing = [c.commodity for c in proc.components
                   if c.effect == pr.COMPEFFECT_MATERIAL
                   and (c.have < c.required or (c.required == 0 and not c.have))]
        return RunResult(reason="materials missing: %s" % missing)

    d = dice or _dice(proc.process_id * 40503 + now_ms)
    ok = pr.player_run(proc, stores, None, int(now_ms), d, lambda _p: None)
    if not ok:
        return RunResult(reason="MakeOne refused")
    return RunResult(started=True, deadline_ms=proc.deadline_ms,
                     seconds=max(0, (proc.deadline_ms - int(now_ms)) // 1000))


def harvest(proc, stores, zone, now_ms: int) -> RunResult:
    if proc is None or proc.deadline_ms == 0:
        return RunResult(reason="not running")
    if int(now_ms) < proc.deadline_ms:
        return RunResult(reason="not finished", deadline_ms=proc.deadline_ms,
                         seconds=(proc.deadline_ms - int(now_ms)) // 1000)
    from openshores.gameplay.process_model import finish_output
    finish_output(proc, zone_quality=zr.quality(zone, proc.output_commodity)
                  if zone is not None else 0)
    proc.tick(int(now_ms))
    outs = []
    if proc.output_quantity > 0:
        outs.append(pmgr.Output(proc.output_commodity, proc.output_quality,
                                proc.output_quantity, proc.process_id))
        pmgr.deposit(stores, outs)
    proc.consume_applied_inventory()
    return RunResult(started=True, outputs=outs,
                     commodity=proc.output_commodity,
                     quantity=proc.output_quantity,
                     quality=proc.output_quality)


def stores_to_stock(stores) -> ItemStock:
    out = ItemStock()
    for it in stores.stock:
        if int(it.quantity) > 0:
            out.add(int(it.commodity), int(it.quantity), int(it.quality))
    return out


_GLOBAL_DICE = AuDice(0x5EED1E)


def gather(mpid: int, *, zone, industry: int = 0, shops: int = 1, have=None,
           enclosure: int = zr.ENCLOSURE_NONE, sunlight_available: bool = True,
           dice=None):
    proc = pmgr.build_process(int(mpid), building_quality=1,
                              workers=max(1, int(shops)),
                              shops_enabled=max(1, int(shops)))
    if proc is None:
        return None
    carry = have or {}
    for c in proc.components:
        prev = int(carry.get(str(c.commodity)) or 0)
        if prev:
            c.have = min(prev, c.required) if c.required else prev

    zr.fetch_manufacturing_materials(
        proc.components, zone, int(industry), int(enclosure),
        bool(sunlight_available), dice or _GLOBAL_DICE)

    return {str(c.commodity): int(c.have) for c in proc.components if c.have}


def environment_satisfied(mpid: int, have=None, *, shops: int = 1) -> bool:
    proc = pmgr.build_process(int(mpid), building_quality=1,
                              workers=max(1, int(shops)),
                              shops_enabled=max(1, int(shops)))
    if proc is None:
        return False
    carry = have or {}
    for c in proc.components:
        prev = int(carry.get(str(c.commodity)) or 0)
        if prev:
            c.have = min(prev, c.required) if c.required else prev
    return proc.is_completed()
