
from __future__ import annotations

from openshores.gameplay import gd_tables as _gd
from openshores.gameplay.process_model import tenfold_output
from openshores.gameplay.worldgen import zone_resources as _zr


def _tenfold(commodity) -> bool:
    return bool(tenfold_output(int(commodity)))


EFFECT_DOES_NOTHING = 1
EFFECT_DECREASE_TIME = 2
EFFECT_DECREASE_MATERIALS = 3
EFFECT_CONSUMED_OR_REQUIRED = 5
EFFECT_INCREASE_OUTPUT = 6


class ProcessComponent:

    __slots__ = ("commodity", "quality", "effect", "required", "applied")

    def __init__(self, commodity, effect=EFFECT_CONSUMED_OR_REQUIRED,
                 required=0, applied=0, quality=0):
        self.commodity = int(commodity)
        self.quality = int(quality)
        self.effect = int(effect)
        self.required = int(required)
        self.applied = int(applied)

    def __repr__(self):
        return ("ProcessComponent(cid=%d, effect=%d, req=%d, applied=%d)"
                % (self.commodity, self.effect, self.required, self.applied))


class ManufacturingProcessState:

    __slots__ = ("process_id", "commodity", "name", "work_units",
                 "output_qty", "quality", "quantity", "components",
                 "deadline_ms", "last_run_ms", "auid", "workers_present",
                 "shops_enabled", "building_quality", "minimum_q_required",
                 "minimum_quality", "production_boost", "output_qty_base")

    def __init__(self, process_id=0, commodity=0, name="", work_units=0,
                 output_qty=0, quality=0, quantity=0, components=None,
                 deadline_ms=0, last_run_ms=0, auid=0, workers_present=0,
                 shops_enabled=1, building_quality=1, minimum_q_required=1,
                 minimum_quality=0, production_boost=0, output_qty_base=0):
        self.process_id = int(process_id)
        self.commodity = int(commodity)
        self.name = name or ""
        self.work_units = int(work_units)
        self.output_qty = int(output_qty)
        self.quality = int(quality)
        self.quantity = int(quantity)
        self.components = list(components or [])
        self.deadline_ms = int(deadline_ms)
        self.last_run_ms = int(last_run_ms)
        self.auid = int(auid)
        self.workers_present = int(workers_present)
        self.shops_enabled = int(shops_enabled)
        self.building_quality = int(building_quality)
        self.minimum_q_required = int(minimum_q_required)
        self.minimum_quality = int(minimum_quality)
        self.production_boost = int(production_boost)
        self.output_qty_base = int(output_qty_base)

    @property
    def running(self) -> bool:
        return self.deadline_ms != 0

    def scaled(self):
        n = max(1, int(self.workers_present))
        work, out = self.work_units * n, self.output_qty * n
        if _tenfold(self.commodity):
            work *= 10
            out *= 10
        return work, out

    def scaled_components(self):
        n = max(1, int(self.workers_present))
        out = []
        for c in self.components:
            req = c.required * n if c.effect == EFFECT_CONSUMED_OR_REQUIRED \
                and c.required else c.required
            out.append(ProcessComponent(c.commodity, effect=c.effect,
                                        required=req, applied=c.applied,
                                        quality=c.quality))
        return out

    def __repr__(self):
        return ("ManufacturingProcessState(mpid=%d, cid=%d, %r)"
                % (self.process_id, self.commodity, self.name))


def _zone_has(zone, cid) -> bool:
    return int(_zr.fetch_probability(zone, int(cid) & 0xFFFF) or 0) > 0


def process_from_recipe(mpid, *, auid=0, workers_present=0, quality=0,
                        quantity=0, deadline_ms=0, last_run_ms=0,
                        zone=None):
    row = _gd.process_by_id(mpid)
    if row is None:
        return None
    comps = []
    for c in _gd.components_for_process(mpid):
        applied = 0
        if zone is not None and _zone_has(zone, c.commodity):
            applied = max(int(c.quantity or 0), 1)
        comps.append(ProcessComponent(c.commodity, effect=c.effect,
                                      required=c.quantity, applied=applied))
    return ManufacturingProcessState(
        process_id=row.process_id, commodity=row.commodity, name=row.name,
        work_units=row.work_units, output_qty=row.output_qty,
        quality=quality, quantity=quantity, components=comps,
        deadline_ms=deadline_ms, last_run_ms=last_run_ms, auid=auid,
        workers_present=workers_present)


_MAX_DEADLINE_AHEAD_MS = 24 * 60 * 60 * 1000


def processes_from_mpids(mpids, cfg=None, sim_now_ms=0, **kw):
    cfg = cfg or {}
    out = []
    for m in (mpids or []):
        m = int(m)
        p = process_from_recipe(m, **kw)
        if p is None:
            continue
        one = cfg.get(str(m)) or cfg.get(m) or {}
        if one:
            shops = int(one.get("shops", 0) or 0)
            if shops:
                p.shops_enabled = shops
                p.workers_present = shops
            if one.get("minq") is not None:
                p.minimum_quality = int(one["minq"])
            _dl = int(one.get("deadline") or 0)
            if _dl and sim_now_ms:
                if sim_now_ms < _dl <= sim_now_ms + _MAX_DEADLINE_AHEAD_MS:
                    p.deadline_ms = _dl
            elif _dl:
                p.deadline_ms = _dl
        out.append(p)
    return out
