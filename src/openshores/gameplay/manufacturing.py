
import math

from openshores.gameplay import commodity_flags

BASE_LABOUR_RATE = 8

ELECTRICITY_CID = 3
ELECTRICITY_LABOUR_BOOST = 5
ELECTRICITY_PRODUCTION_BOOST = 1

APPLIED_LABOUR_BOOST = 5

RESTART_THROTTLE_MS = 11000

MONEY_CID = 0x9d

CITY_CYCLE_SEC = 5400.0 / 7.0

COMPEFFECT_DECREASE_TIME = 2
COMPEFFECT_CONSUMED_OR_REQUIRED = 5
COMPEFFECT_INCREASE_OUTPUT = 6


def _s8(v):
    v = int(v) & 0xFF
    return v - 256 if v >= 128 else v


def run_seconds(work_units, labour_boost=0, workers=1):
    work = int(work_units)
    rate = int(labour_boost) + BASE_LABOUR_RATE
    if rate <= 0:
        rate = 1
    secs = -(-work // rate) if work > 0 else 0
    w = int(workers)
    if w > 1:
        secs //= w
    return secs if secs >= 1 else 1


def output_quantity(base_qty, production_boost=0, workers=1):
    base = int(base_qty)
    mult = int(workers) if int(workers) != 0 else 1
    stored = _s8(mult * int(production_boost))
    if stored > 0:
        bonus = (stored * base) // 10
        if bonus < stored:
            bonus = stored
        return base + bonus
    return base


def output_quality(commodity, base_quality, input_qualities=(),
                   zone_quality=0, tech_cap=255):
    if int(commodity) == ELECTRICITY_CID:
        return 255

    total = 0
    n = 0
    for q, c in input_qualities:
        q = int(q)
        c = int(c)
        if q and c:
            total += q * c
            n += c
    if int(zone_quality):
        total += int(zone_quality)
        n += 1

    base = int(base_quality)
    if n == 0:
        q = base
    else:
        q = total // n if n > 1 else total
        if q == 0:
            q = 1
        q = (q + base + 1) >> 1

    cap = int(tech_cap)
    if q > cap:
        q = cap
    return q if q >= 1 else 1


def runs_per_interval(work_units, seconds, labour_boost=0, workers=1):
    secs = run_seconds(work_units, labour_boost, workers)
    period = secs + RESTART_THROTTLE_MS / 1000.0
    if period <= 0:
        return 0
    return int(float(seconds) // period)


def yield_per_interval(proc, seconds, labour_boost=0, production_boost=0,
                       workers=1):
    runs = runs_per_interval(proc.work_units, seconds, labour_boost, workers)
    if runs <= 0:
        return 0
    return runs * output_quantity(proc.output_qty, production_boost, workers)


_RESEARCH_RECIPE_MARKER = ", Method for"


def is_goods(proc):
    return not commodity_flags.is_patent(proc.commodity)


def production_processes(industry_id, procs, commodity=None):
    out = [p for p in procs
           if p.industry_id == int(industry_id) and is_goods(p)]
    if commodity is not None:
        out = [p for p in out if p.commodity == int(commodity)]
    return out


def output_per_worker(industry_id, procs, commodity=None,
                      seconds=CITY_CYCLE_SEC,
                      labour_boost=0, production_boost=0):
    cands = production_processes(industry_id, procs, commodity)
    if not cands:
        return 0
    tally = {}
    for p in cands:
        tally[(p.output_qty, p.work_units)] = \
            tally.get((p.output_qty, p.work_units), 0) + 1
    (qty, work), _ = max(tally.items(), key=lambda kv: (kv[1], kv[0][0]))
    runs = runs_per_interval(work, seconds, labour_boost, 1)
    return runs * output_quantity(qty, production_boost, 1)


def describe(proc, labour_boost=0, production_boost=0, workers=1,
             seconds=CITY_CYCLE_SEC):
    secs = run_seconds(proc.work_units, labour_boost, workers)
    qty = output_quantity(proc.output_qty, production_boost, workers)
    runs = runs_per_interval(proc.work_units, seconds, labour_boost, workers)
    return ("%s: %d work / (%d+%d) -> %ds run, +%ds throttle; "
            "%d unit(s) x %d run(s) = %d per %.0fs"
            % (proc.name, proc.work_units, labour_boost, BASE_LABOUR_RATE,
               secs, RESTART_THROTTLE_MS // 1000, qty, runs,
               runs * qty, seconds))
