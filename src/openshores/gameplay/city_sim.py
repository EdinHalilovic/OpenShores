from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass, field

from openshores.gameplay.manufacturing import output_quality

COMMODITY_AIR = 5
COMMODITY_POWER = 3
NO_POWER_PENALTY = 2
SATISFACTION_FLOOR = -20
SATISFACTION_CAP = 20

NEED_PENALTY_FOOD = 2
STARVATION_COST_PER = 500
SUFFOCATION_COST_PER = 1000
HOUSING_PENALTY_FLOOR = -2


DEFAULT_STOCK_QUALITY = 100


@dataclass
class Stack:

    commodity: int
    quality: int
    quantity: int


class ItemStock(MutableMapping):

    __slots__ = ("_stacks",)

    def __init__(self, initial=None):
        self._stacks = []
        if initial is None:
            return
        if isinstance(initial, ItemStock):
            self._stacks = [Stack(s.commodity, s.quality, s.quantity)
                            for s in initial._stacks]
        elif isinstance(initial, dict):
            for cid, qty in initial.items():
                self[int(cid)] = int(qty)
        else:
            for cid, quality, qty in initial:
                self._stacks.append(Stack(int(cid), int(quality), int(qty)))

    def stacks_of(self, cid: int):
        cid = int(cid)
        return [s for s in self._stacks if s.commodity == cid]

    @property
    def stacks(self):
        return list(self._stacks)

    def add(self, cid: int, quantity: int, quality: int = DEFAULT_STOCK_QUALITY):
        cid, quantity, quality = int(cid), int(quantity), int(quality)
        if quantity <= 0:
            return
        for s in self._stacks:
            if s.commodity == cid and s.quality == quality:
                s.quantity += quantity
                return
        self._stacks.append(Stack(cid, quality, quantity))

    def take(self, cid: int, amount: int) -> int:
        cid, amount = int(cid), int(amount)
        if amount <= 0:
            return 0
        got = 0
        for s in list(self._stacks):
            if s.commodity != cid:
                continue
            use = min(s.quantity, amount - got)
            s.quantity -= use
            got += use
            if s.quantity <= 0:
                self._stacks.remove(s)
            if got >= amount:
                break
        return got

    def best_quality(self, cid: int) -> int:
        qs = [s.quality for s in self.stacks_of(cid) if s.quantity > 0]
        return max(qs) if qs else 0

    def __getitem__(self, cid):
        cid = int(cid)
        total = sum(s.quantity for s in self._stacks if s.commodity == cid)
        if total == 0 and not any(s.commodity == cid for s in self._stacks):
            raise KeyError(cid)
        return total

    def __setitem__(self, cid, quantity):
        cid, quantity = int(cid), int(quantity)
        current = sum(s.quantity for s in self._stacks if s.commodity == cid)
        if quantity < current:
            self.take(cid, current - quantity)
        elif quantity > current:
            self.add(cid, quantity - current, DEFAULT_STOCK_QUALITY)
        elif quantity == 0 and current == 0:
            if not any(s.commodity == cid for s in self._stacks):
                self._stacks.append(Stack(cid, DEFAULT_STOCK_QUALITY, 0))

    def __delitem__(self, cid):
        cid = int(cid)
        keep = [s for s in self._stacks if s.commodity != cid]
        if len(keep) == len(self._stacks):
            raise KeyError(cid)
        self._stacks = keep

    def __iter__(self):
        seen = []
        for s in self._stacks:
            if s.commodity not in seen:
                seen.append(s.commodity)
                yield s.commodity

    def __len__(self):
        return len(set(s.commodity for s in self._stacks))

    def __repr__(self):
        return f"ItemStock({dict(self)!r})"

    def to_json(self):
        return [[s.commodity, s.quality, s.quantity] for s in self._stacks]

    @classmethod
    def from_json(cls, raw):
        if not raw:
            return cls()
        if isinstance(raw, dict):
            return cls({int(k): int(v) for k, v in raw.items()})
        return cls((int(c), int(q), int(n)) for c, q, n in raw)


@dataclass
class CityState:
    population: int = 0
    meal_size: int = 0
    satisfaction: int = 0
    housing_max: int = 0
    pop_target: int = 0
    secondary_pop: int = 0
    building_levels: int = 0
    enclosure_needed: bool = False
    on_ringworld: bool = False
    citizen_dna: bytes = b""
    stock: ItemStock = field(default_factory=ItemStock)
    tools: ItemStock = field(default_factory=ItemStock)
    food: int = 0
    buildings: list = field(default_factory=list)
    bank: float = 0.0
    salaries_paid: float = 0.0
    govt_income_tax: float = 0.0
    income_tax_pct: float = 0.0
    sales_tax_pct: float = 0.0
    govt_sales_tax: float = 0.0
    salary_income: float = 0.0
    sales_income: float = 0.0
    purchases_paid: float = 0.0
    govt: float = 0.0
    tribute_paid: float = 0.0
    last_tribute: float = 0.0
    food_quality: int = 0
    food_quality_source: int = 0
    linked_cities: list = field(default_factory=list)

    @property
    def has_power(self) -> bool:
        return bool(self.on_ringworld) or int(self.stock.get(COMMODITY_POWER, 0)) > 0

    def __setattr__(self, name, value):
        if name == "has_power":
            raise AttributeError(
                "CityState.has_power comes from stock (DaCity::HasPower).")
        if name in ("stock", "tools") and not isinstance(value, ItemStock):
            value = ItemStock(value)
        object.__setattr__(self, name, value)

    def food_needed(self) -> int:
        if self.meal_size < 2:
            return self.population * 10
        return self.meal_size * self.population

    def eat_food(self):
        need = self.food_needed()
        quality_before = self.current_food_quality()
        ate = 0
        for cid in sorted(food_commodity_ids()):
            if ate >= need:
                break
            got = self.stock.take(cid, need - ate)
            if got:
                ate += int(got)
        if ate < need and self.food > 0:
            from_scalar = min(self.food, need - ate)
            self.food -= from_scalar
            ate += from_scalar
        self.food_quality = quality_before if ate else 0
        return (need - ate) < 1, ate

    def current_food_quality(self) -> int:
        if self.food_quality_source:
            return int(self.food_quality_source)
        return stock_food_quality(self.stock)

    def consume_air(self, amount: int) -> int:
        return self.stock.take(COMMODITY_AIR, amount)

    def decrease_satisfaction(self, amount: int):
        if self.population == 0:
            self.satisfaction = 1
            return
        self.satisfaction -= int(amount)
        if self.satisfaction < SATISFACTION_FLOOR + 1:
            self.satisfaction = SATISFACTION_FLOOR

    def increase_satisfaction(self, amount: int):
        if self.population == 0:
            self.satisfaction = 1
            return
        self.satisfaction += int(amount)
        if self.satisfaction > SATISFACTION_CAP - 1:
            self.satisfaction = SATISFACTION_CAP

    def decrease_population(self, n: int, indigenous_dna: bytes = None):
        n = int(n)
        pop = self.population
        reclaimed = False
        if n < pop:
            self.population = pop - n
            self.secondary_pop = max(0, self.secondary_pop - n)
        else:
            self.population = 0
            self.secondary_pop = 0
            if indigenous_dna and indigenous_dna != self.citizen_dna:
                self.citizen_dna = indigenous_dna
                reclaimed = True
        if pop <= self.housing_max:
            drop = pop - self.population
            self.housing_max = max(self.population, self.housing_max - drop)
        return reclaimed

    def increase_population(self, n: int) -> bool:
        n = int(n)
        was_zero = self.population == 0
        if not was_zero:
            self.secondary_pop += n
            self.population += n
        else:
            self.population = n
            self.secondary_pop = n
        return was_zero


def air_penalty(air_need: int, consumed: int) -> int:
    air_need = int(air_need); consumed = int(consumed)
    if consumed >= air_need:
        return 0
    return 2 if consumed < (air_need >> 1) else 1


_FOOD_CIDS = None


def food_commodity_ids():
    global _FOOD_CIDS
    if _FOOD_CIDS is None:
        from openshores.gameplay.gd_tables import load_food_commodities
        _FOOD_CIDS = frozenset(load_food_commodities() or ())
    return _FOOD_CIDS


def stock_food_quality(stock, food_cids=None) -> int:
    cids = food_commodity_ids() if food_cids is None else food_cids
    if not cids:
        return 0
    best = 0
    for s in getattr(stock, "stacks", ()) or ():
        if int(s.quantity) <= 0 or int(s.commodity) not in cids:
            continue
        q = int(s.quality)
        if q > best:
            best = q
    return best


def food_quality_gain(quality: int) -> int:
    q = int(quality)
    if q >= 7:
        return 2
    g = q >> 2
    return 2 if g > 2 else g


HOMELESSNESS_DIVISOR = 4
HOMELESSNESS_CAP = 10


def homelessness_penalty(population: int, homes: int) -> int:
    excess = int(population) - int(homes)
    if excess <= 0:
        return 0
    n = _trunc_div(excess, HOMELESSNESS_DIVISOR)
    if n == 0:
        return 0
    return -min(n, HOMELESSNESS_CAP)


def overcrowding_penalty(population: int, homes: int) -> int:
    return -1 if int(population) >= int(homes) else 0


UNEMPLOYMENT_MULTIPLIER = 5.0


def unemployment_penalty(unemployed: int, population: int) -> int:
    pop = int(population)
    if pop <= 0:
        return 0
    n = int(float(int(unemployed)) / float(pop) * UNEMPLOYMENT_MULTIPLIER)
    return -n if n else 0


def apartment_imbalance_penalty(apartment_homes: int, other_homes: int) -> int:
    apts = int(apartment_homes)
    other = int(other_homes)
    if apts <= other:
        return 0
    if apts > 3 * other:
        return -3
    return -2 if apts > 2 * other else -1


DECAY_PENALTY_PER_MODE = 1


def decay_penalty(modes_fired: int) -> int:
    return -abs(int(modes_fired)) * DECAY_PENALTY_PER_MODE


LOYALTY_BONUS_HIGH = 2
LOYALTY_BONUS_LOW = 1
LOYALTY_THRESHOLD_HIGH = 0.9
LOYALTY_THRESHOLD_LOW = 0.5
LOYALTY_OCCUPIED_MULTIPLIER = 5.0
LOYALTY_VISIT_GRACE_DAYS = 14


def loyalty(counter: int, population: int) -> float:
    pop = int(population)
    n = int(counter)
    if pop <= n:
        return 1.0
    if pop == 0:
        return 0.0
    return float(n) / float(pop)


def loyalty_delta(loyalty_value: float, *, occupied: bool = False) -> int:
    v = float(loyalty_value)
    if occupied:
        return -int(v * LOYALTY_OCCUPIED_MULTIPLIER)
    if v > LOYALTY_THRESHOLD_HIGH:
        return LOYALTY_BONUS_HIGH
    if v > LOYALTY_THRESHOLD_LOW:
        return LOYALTY_BONUS_LOW
    return 0


def advance_loyalty_counter(counter: int, population: int, *,
                            empire_changed: bool = False,
                            empire_matches: bool = True,
                            days_since_visit: int = 0) -> int:
    n = int(counter)
    pop = int(population)
    if empire_changed:
        return 0
    if (not empire_matches) or int(days_since_visit) > LOYALTY_VISIT_GRACE_DAYS:
        return n - 1 if n > 1 else 0
    if n < pop:
        return n + 1
    if n > pop:
        return n - 1 if pop > 1 else 0
    return n


def cycle_needs(state: "CityState", *, air_need: int = None,
                housing_need: int = None, base_delta: int = 0,
                service_needs=None, homes: int = None,
                unemployed: int = None, decay_modes: int = 0,
                occupied: bool = False, apartment_homes: int = 0,
                other_homes: int = 0, destroyed_buildings: bool = False,
                skip_life_support: bool = False) -> dict:
    if air_need is None:
        air_need = state.population
    if homes is None:
        homes = max(0, int(state.pop_target))
    if unemployed is None:
        unemployed = int(state.secondary_pop)
    delta = int(base_delta)
    out = {"starving": False, "suffocating": False, "food_ate": 0,
           "air_consumed": 0, "air_needed": state.enclosure_needed,
           "housing_penalty": 0, "sat_delta": 0, "service_penalty": 0,
           "unemployment_penalty": 0, "overcrowding_penalty": 0,
           "loyalty": 0.0, "loyalty_delta": 0, "decay_penalty": 0,
           "apartment_penalty": 0, "power_penalty": 0, "food_gain": 0}

    if not skip_life_support:
        if not state.has_power:
            out["power_penalty"] = -NO_POWER_PENALTY
            delta -= NO_POWER_PENALTY

        fully_fed, ate = state.eat_food()
        out["food_ate"] = ate
        if not fully_fed:
            out["starving"] = True
            delta -= NEED_PENALTY_FOOD
        else:
            gain = food_quality_gain(state.food_quality)
            out["food_gain"] = gain
            delta += gain

        if state.enclosure_needed:
            consumed = state.consume_air(air_need)
            out["air_consumed"] = consumed
            ap = air_penalty(air_need, consumed)
            if ap:
                out["suffocating"] = True
                delta -= ap

    crisis = bool(out["starving"] or out["suffocating"])

    loy = loyalty(state.housing_max, state.population)
    out["loyalty"] = loy
    ld = loyalty_delta(loy, occupied=occupied)
    out["loyalty_delta"] = ld
    delta += ld

    dp = decay_penalty(decay_modes)
    out["decay_penalty"] = dp
    delta += dp

    up = unemployment_penalty(unemployed, state.population)
    out["unemployment_penalty"] = up
    delta += up

    hp = homelessness_penalty(state.population, homes)
    out["housing_penalty"] = hp
    delta += hp

    if up == 0:
        oc = overcrowding_penalty(state.population, homes)
        out["overcrowding_penalty"] = oc
        delta += oc

    ap_pen = apartment_imbalance_penalty(apartment_homes, other_homes)
    out["apartment_penalty"] = ap_pen
    delta += ap_pen

    if destroyed_buildings:
        out["destroyed_penalty"] = -1
        delta -= 1
    else:
        if service_needs is None:
            service_needs = build_service_needs(state)
        if service_needs:
            sp = city_needs_penalty(service_needs, crisis=crisis)
            out["service_penalty"] = sp
            delta += sp

    out["sat_delta"] = delta
    if delta < 0:
        state.decrease_satisfaction(-delta)
    elif delta > 0:
        state.increase_satisfaction(delta)
    return out


import math as _math

DEVTYPE_AIR_PRODUCER = 0x53


@dataclass
class Building:
    kind: str = ""
    jobs: int = 0
    employed: int = 0
    damage: int = 0
    hits_total: int = 0
    output_commodity: int = 0
    output_per_worker: int = 0
    needs_power: bool = False
    industry_id: int = 0
    levels: int = 1
    mpids: list = field(default_factory=list)
    quality: int = 0
    lat: float = 0.0
    lon: float = 0.0
    storage_per_level: int = 0
    capacitor_per_level: int = 0
    under_construction: bool = False
    burning: bool = False

    def is_destroyed(self) -> bool:
        return self.damage != 0 and self.hits_total <= self.damage


def reset_employment(buildings):
    for b in buildings:
        b.employed = 0


def employ_producers(buildings, pool: int, fraction: float, kind: str) -> int:
    pool = int(pool)
    for b in buildings:
        if b.kind != kind or pool == 0:
            continue
        if b.is_destroyed() or b.jobs == 0:
            continue
        assigned = int(_math.ceil(b.jobs * float(fraction)))
        if assigned > pool:
            assigned = pool
        b.employed += assigned
        pool -= assigned
    return pool


PRODUCER_PRIORITY_ENCLOSED = ("repair", "power", "air", "food", "other")
PRODUCER_PRIORITY_BREATHABLE = ("repair", "food", "power", "other")

PRODUCER_PRIORITY = ("repair", "power", "air", "food", "other")

STAFFING_RATIO_CAP = 1.0


def city_job_total(state) -> int:
    return sum(int(getattr(b, "jobs", 0) or 0)
               for b in getattr(state, "buildings", ()) or ())


def producer_priority(enclosure_needed: bool):
    return (PRODUCER_PRIORITY_ENCLOSED if enclosure_needed
            else PRODUCER_PRIORITY_BREATHABLE)


def staffing_ratio(population: int, jobs: int) -> float:
    p, j = int(population), int(jobs)
    if p == 0 or j == 0:
        return 0.0
    r = float(p) / float(j)
    return r if r <= STAFFING_RATIO_CAP else STAFFING_RATIO_CAP


def produce(state: "CityState") -> dict:
    made = {}
    for b in state.buildings:
        if b.employed <= 0 or b.is_destroyed():
            continue
        if b.needs_power and not state.has_power:
            continue
        out = int(b.employed) * int(b.output_per_worker)
        if out <= 0:
            continue
        if b.kind == "food" and not b.output_commodity:
            state.food += out
        else:
            state.stock.add(int(b.output_commodity), out,
                            quality=_produced_quality(b))
        made[b.kind] = made.get(b.kind, 0) + out
    return made


def _produced_quality(b) -> int:
    return int(output_quality(int(b.output_commodity),
                              int(getattr(b, "quality", 0) or 0), ()))


def run_cycle(state: "CityState", *, air_need: int = None, housing_need: int = None,
              base_delta: int = 0, service_needs=None, apply_deaths: bool = True,
              food_starving: bool = None, air_starving: bool = None,
              grow: bool = True, apply_migration_flag: bool = False,
              growth_service_shortage: int = None,
              growth_service_demand: int = 1, apply_decay: bool = True,
              decay_pick: int = 0, decay_empire_slack: float = 0.0,
              apply_production: bool = True, occupied: bool = False,
              destroyed_buildings: bool = False, apartment_homes: int = 0,
              other_homes: int = 0, empire_changed: bool = False,
              empire_matches: bool = True, days_since_visit: int = 0,
              advance_loyalty: bool = True) -> dict:
    decayed = {"mode0": 0, "mode1": 0, "mode2": 0}
    if apply_decay:
        decayed = decay_step(state, pick=decay_pick,
                             empire_slack=decay_empire_slack)

    reset_employment(state.buildings)
    pool = int(state.population)
    staffed = {}
    ratio = staffing_ratio(state.population, city_job_total(state))
    for kind in producer_priority(state.enclosure_needed):
        before = pool
        pool = employ_producers(state.buildings, pool,
                                1.0 if kind == "repair" else ratio, kind)
        staffed[kind] = before - pool
    state.secondary_pop = int(pool)
    made = produce(state) if apply_production else {}
    upgraded = tech_upgrade_buildings(state)
    if service_needs is None:
        service_needs = build_service_needs(state)
    if growth_service_shortage is None:
        growth_service_shortage = growth_shortage_from_needs(service_needs)
    needs = cycle_needs(state, air_need=air_need, housing_need=housing_need,
                        base_delta=base_delta, service_needs=service_needs,
                        decay_modes=len(decayed.get("fired", ())),
                        occupied=occupied,
                        destroyed_buildings=destroyed_buildings,
                        apartment_homes=apartment_homes,
                        other_homes=other_homes)
    work_units = sum(b.employed for b in state.buildings)
    economy = run_economy(state, work_units)
    wages = economy
    deaths = {"food_deaths": 0, "air_deaths": 0}
    if apply_deaths:
        if food_starving is None:
            food_starving = (state.population > 0
                             and int(needs.get("food_ate", 0)) == 0)
        if air_starving is None:
            air_starving = (state.enclosure_needed and state.population > 0
                            and int(needs.get("air_consumed", 0)) == 0)
        deaths = apply_vital_deaths(state, food_starving=food_starving,
                                    air_starving=air_starving)
    growth = 0
    if grow:
        growth = apply_growth(state, service_shortage=growth_service_shortage,
                              service_demand=growth_service_demand)
    migration = 0
    if apply_migration_flag:
        migration = apply_migration(state)
    if advance_loyalty:
        state.housing_max = advance_loyalty_counter(
            state.housing_max, state.population,
            empire_changed=empire_changed, empire_matches=empire_matches,
            days_since_visit=days_since_visit)
    return {"staffed": staffed, "workers_left": pool, "produced": made,
            "needs": needs, "wages": wages, "economy": economy,
            "deaths": deaths, "growth": growth, "migration": migration,
            "decayed": decayed, "loyalty": needs.get("loyalty", 0.0),
            "tech_upgraded": upgraded}


WAGE_PER_WORK = 25.0
INCOME_TAX_DIVISOR = 100.0
CITIZEN_SPEND_FRACTION = 0.5


def pay_wages(state: "CityState", work_units: int) -> dict:
    want = float(work_units) * WAGE_PER_WORK
    paid = state.bank if state.bank < want else want
    if paid < 0.0:
        paid = 0.0
    state.bank -= paid
    state.salaries_paid += paid
    rate = float(state.income_tax_pct)
    if rate <= 0.0:
        to_citizens, income_tax = paid, 0.0
    else:
        income_tax = (rate / INCOME_TAX_DIVISOR) * paid
        to_citizens = paid - income_tax
    state.govt_income_tax += income_tax
    state.govt += income_tax
    state.bank += to_citizens
    state.salary_income += to_citizens
    return {"wages": paid, "to_citizens": to_citizens, "income_tax": income_tax}


def citizen_spending(state: "CityState", gross_salary: float) -> float:
    g = float(gross_salary)
    if g <= 0.0:
        return 0.0
    rate = float(state.sales_tax_pct)
    return g * CITIZEN_SPEND_FRACTION * (1.0 - rate / INCOME_TAX_DIVISOR)


def run_economy(state: "CityState", work_units: int) -> dict:
    wages = pay_wages(state, work_units)
    spend = citizen_spending(state, wages["wages"])
    purch = debit_purchases(state, spend)
    sales = credit_sales(state, spend)
    return {"wages": wages["wages"], "to_citizens": wages["to_citizens"],
            "income_tax": wages["income_tax"], "spend": spend,
            "purchases": purch["paid"], "sales_net": sales["net"],
            "sales_tax": sales["sales_tax"]}


DECAY_MODE1_INDUSTRIES = frozenset({0x14, 0x15, 0x16, 0x1e, 0x20})
DECAY_MODE2_PROTECTED = frozenset({1, 2, 0x14, 0x15, 0x16, 0x1e, 0x20, 0x72})
CAPITOL_INDUSTRY = 1


def decay_candidates(state: "CityState", mode: int) -> list:
    bs = state.buildings
    if mode == 1:
        return [b for b in bs if b.kind != "road"
                and b.industry_id in DECAY_MODE1_INDUSTRIES]
    if mode == 2:
        return [b for b in bs if b.kind != "road"
                and b.industry_id not in DECAY_MODE2_PROTECTED]
    return [b for b in bs if b.kind == "road" or b.industry_id != CAPITOL_INDUSTRY]


def decay_one(state: "CityState", mode: int = 2, pick: int = 0) -> int:
    cands = decay_candidates(state, mode)
    if not cands:
        return 0
    b = cands[pick % len(cands)]
    industry = b.industry_id
    b.levels -= 1
    if b.levels <= 0:
        state.buildings.remove(b)
    return industry


DECAY_OVERBUILD_MARGIN = 25
DECAY_RATIO_FLOOR = 1.05


def decay_threshold(population: int, empire_slack: float = 0.0) -> float:
    pop = int(population)
    if pop <= 0:
        return DECAY_RATIO_FLOOR
    ratio = float(empire_slack) / float(pop)
    return ratio if ratio > DECAY_RATIO_FLOOR else DECAY_RATIO_FLOOR


def city_total_jobs(state: "CityState") -> int:
    return max(0, sum(int(b.jobs) for b in state.buildings))


def decay_step(state: "CityState", *, pick: int = 0,
               empire_slack: float = 0.0) -> dict:
    out = {"mode0": 0, "mode1": 0, "mode2": 0, "fired": []}
    pop = int(state.population)

    def _fire(mode):
        if not decay_candidates(state, mode):
            return
        out["mode%d" % mode] = decay_one(state, mode, pick)
        out["fired"].append(mode)

    if pop <= 1:
        _fire(0)
        return out

    thr = decay_threshold(pop, empire_slack)

    homes = max(0, int(state.pop_target))
    if homes > pop and (homes - DECAY_OVERBUILD_MARGIN) / float(pop) > thr:
        _fire(1)

    jobs = city_total_jobs(state)
    if (jobs - DECAY_OVERBUILD_MARGIN) / float(pop) > thr:
        _fire(2)

    return out


SALES_TAX_DIVISOR = 100.0


def credit_sales(state: "CityState", amount: float) -> dict:
    amount = float(amount)
    if amount <= 0.0:
        return {"net": 0.0, "sales_tax": 0.0}
    tax = 0.0
    rate = float(state.sales_tax_pct)
    if rate > 0.0:
        tax = (rate * amount) / SALES_TAX_DIVISOR
        state.govt_sales_tax += tax
        state.govt += tax
        amount -= tax
    state.sales_income += amount
    state.bank += amount
    return {"net": amount, "sales_tax": tax}


def debit_purchases(state: "CityState", amount: float) -> dict:
    want = float(amount)
    paid = state.bank if state.bank < want else want
    if paid < 0.0:
        paid = 0.0
    state.bank -= paid
    state.purchases_paid += paid
    return {"paid": paid}


def pay_tribute(state: "CityState", amount: float, can_send: bool = True) -> dict:
    if not can_send:
        return {"tribute": 0.0}
    want = float(amount)
    paid = state.govt if state.govt < want else want
    if paid < 0.0:
        paid = 0.0
    state.govt -= paid
    state.tribute_paid += paid
    state.last_tribute += paid
    return {"tribute": paid}


def development_jobs(base_jobs: int, construction_state=None) -> int:
    jobs = int(base_jobs)
    if construction_state is not None and not (0 <= (int(construction_state) - 2) < 2):
        jobs += 1
    return jobs


CITY_SERVICE_INDUSTRIES = (0x70, 0x69, 0x66, 0x78, 0x67, 0x79,
                           0x72, 0x7c, 0x68, 0x7d, 0x71)

CITY_SERVICE_FACILITY = {
    0x70: "Arena",
    0x69: "Lounge",
    0x66: "Casino",
    0x78: "Church",
    0x67: "Grocery store",
    0x79: "Hospital surgery unit",
    0x72: "Park",
    0x7c: "Police Station",
    0x68: "Retail Store",
    0x7d: "University",
    0x71: "Zoo",
}


def service_facility_name(industry: int) -> str:
    return CITY_SERVICE_FACILITY.get(int(industry), "industry 0x%02x" % int(industry))


def unmet_services(needs):
    out = []
    for item in needs:
        if len(item) != 3:
            continue
        ind, provided, demanded = item
        if provided < demanded:
            out.append((int(ind), service_facility_name(ind),
                        int(demanded) - int(provided)))
    return out

SERVICE_DEMAND_DIVISOR = {
    0x70: 175, 0x69: 50, 0x66: 200, 0x78: 45, 0x67: 100, 0x79: 80,
    0x72: 90, 0x7c: 60, 0x68: 55, 0x7d: 70, 0x71: 150,
}

NEED_PENALTY_CLAMP = -2

SERVICE_SURPLUS_CAP = 2
SERVICE_SURPLUS_CAP_CRISIS = 1
SERVICE_BONUS_0X69 = 1
SERVICE_SHORTFALL_CAP_0X79 = 2


def need_penalty(provided: int, demanded: int) -> int:
    diff = int(provided) - int(demanded)
    if diff >= 0:
        return 0
    return diff if diff >= NEED_PENALTY_CLAMP else NEED_PENALTY_CLAMP


def service_contribution(industry: int, provided: int, demanded: int, *,
                         crisis: bool = False) -> int:
    ind = int(industry)
    diff = int(provided) - int(demanded)
    if ind == 0x79:
        shortfall = -diff
        if shortfall <= 0:
            return 0
        return -min(shortfall, SERVICE_SHORTFALL_CAP_0X79)
    if diff == 0:
        return 0
    clamped = diff if diff >= NEED_PENALTY_CLAMP else NEED_PENALTY_CLAMP
    if ind == 0x78:
        cap = SERVICE_SURPLUS_CAP_CRISIS if crisis else SERVICE_SURPLUS_CAP
        return min(clamped, cap)
    if ind == 0x69:
        if not crisis and clamped >= 1:
            return SERVICE_BONUS_0X69
        return clamped if clamped < 0 else 0
    return clamped if clamped < 0 else 0


def city_needs_penalty(needs, *, crisis: bool = False) -> int:
    total = 0
    for item in needs:
        if len(item) == 3:
            ind, p, d = item
            total += service_contribution(ind, p, d, crisis=crisis)
        else:
            p, d = item
            total += need_penalty(p, d)
    return total


def service_demand(industry: int, population: int):
    d = SERVICE_DEMAND_DIVISOR.get(int(industry))
    if d is None:
        return None
    n = int(population)
    return n // d if n >= 0 else -((-n) // d)


def levels_by_industry_of(state: "CityState") -> dict:
    out = {}
    for b in state.buildings:
        if b.kind == "road":
            continue
        out[b.industry_id] = out.get(b.industry_id, 0) + int(b.levels)
    return out


def build_service_needs(state: "CityState", levels_by_industry=None):
    if levels_by_industry is None:
        levels_by_industry = levels_by_industry_of(state)
    out = []
    for ind in CITY_SERVICE_INDUSTRIES:
        demand = service_demand(ind, state.population)
        if demand is None:
            continue
        out.append((ind, int(levels_by_industry.get(ind, 0)), demand))
    return out


def growth_shortage_from_needs(needs) -> int:
    for item in needs:
        if len(item) == 3 and int(item[0]) == 0x79:
            shortfall = int(item[2]) - int(item[1])
            if shortfall <= 0:
                return 0
            return min(shortfall, SERVICE_SHORTFALL_CAP_0X79)
    return 0


VITAL_DEATH_FLOOR = 4
VITAL_DEATH_DIVISOR = 10
VITAL_DEATH_SAT_DOCK = 5


def starvation_deaths(population: int) -> int:
    pop = int(population)
    if pop <= 0:
        return 0
    n = pop // VITAL_DEATH_DIVISOR
    if n < VITAL_DEATH_FLOOR:
        n = VITAL_DEATH_FLOOR
    if n > pop:
        n = pop
    return n


def apply_vital_deaths(state: "CityState", *, food_starving: bool,
                       air_starving: bool) -> dict:
    pop0 = int(state.population)
    food_count = starvation_deaths(pop0) if food_starving else 0
    air_count = starvation_deaths(pop0) if air_starving else 0
    out = {"food_deaths": 0, "air_deaths": 0}
    if food_count:
        applied = min(food_count, state.population)
        state.decrease_population(food_count)
        out["food_deaths"] = applied
    if air_count:
        applied = min(air_count, state.population)
        if applied:
            state.decrease_population(applied)
        out["air_deaths"] = applied
    return out


POP_GROWTH_MAX = 2


def population_growth_step(population: int, target: int, *,
                           service_shortage: int = 0,
                           service_demand: int = 1) -> int:
    pop = int(population)
    homes = int(target)
    if homes < 0:
        homes = 0
    if not (pop > 1 and pop < homes):
        return 0
    grow = homes - pop
    if grow > POP_GROWTH_MAX:
        grow = POP_GROWTH_MAX
    sp = int(service_shortage)
    if sp > 0:
        if grow == POP_GROWTH_MAX:
            grow = POP_GROWTH_MAX - sp
    else:
        if grow != 0 and int(service_demand) == 0:
            grow = 1
    if grow < 0:
        grow = 0
    return grow


def apply_growth(state: "CityState", *, service_shortage: int = 0,
                 service_demand: int = 1) -> int:
    grow = population_growth_step(state.population, state.pop_target,
                                  service_shortage=service_shortage,
                                  service_demand=service_demand)
    if grow:
        state.increase_population(grow)
    return grow


MIGRATION_NUMERATOR = 2
MIGRATION_DIVISOR = 3


INDUSTRY_AIRPORT_TERMINAL = 0x6F


def isolated_emigration(morale: int) -> int:
    m = int(morale)
    if m >= 0:
        return 0
    return (-m + 3) >> 2


def _trunc_div(n: int, d: int) -> int:
    q = abs(int(n)) // abs(int(d))
    return -q if (n < 0) != (d < 0) else q


def migration_step(satisfaction: int, *, occupied: bool = False,
                   under_attack: bool = False, isolated: bool = False,
                   has_airport: bool = True, world_blocks: bool = False,
                   harsh: bool = False) -> int:
    morale = int(satisfaction)
    if morale == 0:
        return 0
    if under_attack and morale > 0:
        return 0
    if world_blocks:
        return 0
    cut_off = bool(isolated) and not bool(has_airport)
    if not harsh:
        if cut_off:
            return -isolated_emigration(morale)
    else:
        if cut_off and morale > 0:
            return 0
    if occupied:
        morale = _trunc_div(morale, 2)
        if morale == 0:
            return 0
    migration = _trunc_div(morale * MIGRATION_NUMERATOR, MIGRATION_DIVISOR)
    if migration == 0:
        migration = 1 if morale > 0 else -1
    return migration


def city_is_isolated(state: "CityState") -> bool:
    return not (getattr(state, "linked_cities", None) or ())


def city_has_airport(state: "CityState") -> bool:
    return int(levels_by_industry_of(state).get(INDUSTRY_AIRPORT_TERMINAL, 0)) > 0


def apply_migration(state: "CityState", *, occupied: bool = False,
                    under_attack: bool = False, isolated: bool = None,
                    has_airport: bool = None, world_blocks: bool = False,
                    harsh: bool = False) -> int:
    if isolated is None:
        isolated = city_is_isolated(state)
    if has_airport is None:
        has_airport = city_has_airport(state)
    migration = migration_step(state.satisfaction, occupied=occupied,
                               under_attack=under_attack, isolated=isolated,
                               has_airport=has_airport,
                               world_blocks=world_blocks, harsh=harsh)
    if migration > 0:
        free = max(0, int(state.pop_target)) - int(state.population)
        if free <= 0:
            return 0
        gain = min(migration, free)
        state.increase_population(gain)
        return gain
    if migration < 0:
        leaving = min(-migration, int(state.population))
        if leaving <= 0:
            return 0
        state.decrease_population(leaving)
        return -leaving
    return 0


TECH_UPGRADE_COMMODITY = {
    0x03: 177,
    0x04: 219,
    0x05: 658,
    0x0B: 186,
    0x0C: 175,
    0x12: 661,
    0x13: 643,
    0x14: 189,
    0x15: 188,
    0x16: 162,
    0x1B: 641,
    0x1C: 642,
    0x1D: 644,
    0x1E: 181,
    0x1F: 193,
    0x20: 201,
    0x22: 222,
    0x23: 348,
    0x28: 165,
    0x29: 167,
    0x2A: 178,
    0x2B: 184,
    0x2C: 194,
    0x2D: 196,
    0x2E: 214,
    0x2F: 216,
    0x30: 224,
    0x32: 197,
    0x33: 221,
    0x34: 659,
    0x3C: 174,
    0x3D: 183,
    0x3E: 190,
    0x3F: 191,
    0x40: 199,
    0x41: 200,
    0x42: 212,
    0x43: 223,
    0x44: 200,
    0x46: 158,
    0x47: 164,
    0x48: 170,
    0x49: 173,
    0x4A: 176,
    0x4B: 179,
    0x4C: 180,
    0x4D: 220,
    0x4E: 192,
    0x4F: 195,
    0x50: 198,
    0x51: 203,
    0x52: 204,
    0x53: 206,
    0x54: 208,
    0x55: 210,
    0x56: 211,
    0x57: 213,
    0x58: 218,
    0x59: 217,
    0x5A: 654,
    0x64: 166,
    0x65: 168,
    0x66: 171,
    0x67: 185,
    0x68: 207,
    0x69: 215,
    0x6D: 640,
    0x6E: 160,
    0x6F: 161,
    0x70: 163,
    0x71: 225,
    0x72: 202,
    0x77: 662,
    0x78: 172,
    0x79: 187,
    0x7A: 182,
    0x7B: 169,
    0x7C: 205,
    0x7D: 209,
    0x7E: 350,
    0x7F: 286,
}

MAX_BUILDING_QUALITY = 0xFF


def tech_upgrade(state: "CityState", b: "Building") -> bool:
    if b.is_destroyed():
        return False
    levels = int(b.levels) + (0 if getattr(b, "under_construction", False) else 1)
    if levels == 0:
        return False
    q = int(b.quality)
    if q >= MAX_BUILDING_QUALITY:
        return False
    cid = TECH_UPGRADE_COMMODITY.get(int(b.industry_id), 0)
    if not cid:
        return False
    stacks = state.stock.stacks_of(cid)
    if not stacks:
        return False
    stack = stacks[0]
    if q >= int(stack.quality):
        return False
    if state.stock.take(cid, 1) != 1:
        return False
    b.quality = int(stack.quality)
    return True


def tech_upgrade_buildings(state: "CityState") -> int:
    return sum(1 for b in state.buildings if tech_upgrade(state, b))


def city_storage(state: "CityState"):
    storage = capacitor = 0
    for b in state.buildings:
        if b.is_destroyed():
            continue
        levels = max(1, int(b.levels))
        storage += int(b.storage_per_level) * levels
        capacitor += int(b.capacitor_per_level) * levels
    return storage, capacitor


def storage_max(state: "CityState") -> int:
    return city_storage(state)[0]


def capacitor_max(state: "CityState") -> int:
    return city_storage(state)[1]


def stock_total(state: "CityState") -> int:
    return sum(int(s.quantity) for s in state.stock.stacks)


def storage_free(state: "CityState") -> int:
    return max(0, storage_max(state) - stock_total(state))


QUALITY_MULTIPLIER = (
    0.0, 0.9, 0.915205, 0.921441, 0.926182, 0.930143, 0.9336, 0.936697,
    0.939518, 0.942118, 0.944537, 0.946801, 0.948934, 0.950951, 0.952865, 0.954688,
    0.956428, 0.958093, 0.959689, 0.961221, 0.962694, 0.964112, 0.965479, 0.966797,
    0.96807, 0.969301, 0.97049, 0.971641, 0.972756, 0.973835, 0.97488, 0.975894,
    0.976876, 0.977829, 0.978753, 0.979649, 0.980519, 0.981362, 0.982181, 0.982975,
    0.983745, 0.984493, 0.985218, 0.985921, 0.986603, 0.987264, 0.987904, 0.988525,
    0.989126, 0.989708, 0.990272, 0.990817, 0.991344, 0.991853, 0.992345, 0.99282,
    0.993277, 0.993718, 0.994143, 0.994551, 0.994944, 0.99532, 0.995681, 0.996027,
    0.996357, 0.996673, 0.996973, 0.997258, 0.997529, 0.997785, 0.998027, 0.998254,
    0.998467, 0.998666, 0.998851, 0.999022, 0.999179, 0.999322, 0.999451, 0.999566,
    0.999668, 0.999756, 0.999831, 0.999892, 0.999939, 0.999973, 0.999993, 1.0,
    1.00003, 1.00011, 1.00024, 1.00043, 1.0006599, 1.00096, 1.0013, 1.0017,
    1.0021501, 1.00266, 1.00322, 1.00383, 1.0045, 1.0052201, 1.00599, 1.00682,
    1.0077, 1.00863, 1.00962, 1.0106699, 1.01176, 1.01292, 1.01412, 1.01539,
    1.0167, 1.01807, 1.0195, 1.02098, 1.0225199, 1.02411, 1.0257601, 1.02746,
    1.02922, 1.03104, 1.03291, 1.03484, 1.0368299, 1.03888, 1.04098, 1.0431401,
    1.04536, 1.04763, 1.04997, 1.0523601, 1.05481, 1.05732, 1.0599, 1.06253,
    1.06522, 1.06797, 1.0707901, 1.07366, 1.0766, 1.0796, 1.08266, 1.08579,
    1.0889699, 1.09223, 1.09554, 1.09893, 1.10237, 1.10588, 1.10946, 1.1131099,
    1.11682, 1.1206, 1.12445, 1.12837, 1.13235, 1.13641, 1.14054, 1.14474,
    1.1490099, 1.15335, 1.15777, 1.1622601, 1.1668299, 1.17147, 1.17619, 1.18099,
    1.18586, 1.19081, 1.19585, 1.20096, 1.2061599, 1.21144, 1.2168, 1.22225,
    1.22778, 1.2334, 1.23911, 1.24491, 1.2508, 1.25678, 1.26285, 1.26902,
    1.27529, 1.2816499, 1.28811, 1.29468, 1.30134, 1.30811, 1.31499, 1.32197,
    1.32906, 1.33627, 1.34359, 1.35102, 1.35857, 1.36625, 1.37404, 1.38197,
    1.39002, 1.3982, 1.40651, 1.41497, 1.42356, 1.4323, 1.44118, 1.45022,
    1.45941, 1.46876, 1.4782701, 1.48796, 1.49781, 1.50784, 1.51806, 1.52847,
    1.53907, 1.54987, 1.56089, 1.57212, 1.58357, 1.59526, 1.60719, 1.61937,
    1.6318099, 1.6445301, 1.65754, 1.67084, 1.68446, 1.69842, 1.71271, 1.72738,
    1.74244, 1.75791, 1.77382, 1.79019, 1.80707, 1.82449, 1.84249, 1.86112,
)
QUALITY_MULTIPLIER_VERIFIED = len(QUALITY_MULTIPLIER)


def quality_multiplier(quality: int) -> float:
    q = int(quality)
    if q <= 0:
        return QUALITY_MULTIPLIER[0]
    if q >= QUALITY_MULTIPLIER_VERIFIED:
        return QUALITY_MULTIPLIER[-1]
    return QUALITY_MULTIPLIER[q]


def building_hits_per_level(base_hits_per_level: int, quality: int) -> int:
    return int(round(quality_multiplier(quality) * int(base_hits_per_level)))


def building_hits_total(levels: int, hits_per_level: int,
                        under_construction: bool = False) -> int:
    lv = int(levels) + (0 if under_construction else 1)
    if lv <= 0 or int(hits_per_level) <= 0:
        return 0
    return int((_math.log2(lv) + 1.0) * int(hits_per_level)) & 0xFFFF


def add_damage(b: "Building", amount: int) -> bool:
    total = int(b.hits_total)
    if total == 0:
        return False
    new = min(0xFFFF, int(b.damage) + int(amount))
    if new < total:
        b.damage = new
        return False
    b.damage = total
    b.burning = False
    return True


def repair_damage(b: "Building") -> None:
    if int(b.damage) == 0:
        return
    b.damage = int(b.damage) - 1
    if b.damage == 0:
        b.burning = False


def is_damaged(b: "Building") -> bool:
    return int(b.damage) != 0


def building_hits_current(b: "Building") -> int:
    return max(0, int(b.hits_total) - int(b.damage))


def employ_building_repair(buildings, pool: int, reverse: bool = False) -> int:
    pool = int(pool)
    seq = list(reversed(list(buildings))) if reverse else list(buildings)
    for b in seq:
        b.employed = 0
    for b in seq:
        if pool <= 0:
            break
        if int(b.damage) != 0 and not getattr(b, "burning", False):
            b.employed = int(b.employed) + 1
            pool -= 1
    return pool


ROAD_DEV_TYPE = 0x1A
ROAD_DEV_KIND = 2


def road_endpoints(road: dict):
    out = []
    for a, b in (("lat1", "lon1"), ("lat2", "lon2")):
        if a in road or b in road:
            out.append((float(road.get(a, 0.0) or 0.0),
                        float(road.get(b, 0.0) or 0.0)))
    return out


def test_road_connection(city_roads, other_contains, *, same_city=False) -> bool:
    if same_city:
        return True
    for road in (city_roads or ()):
        if road.get("under_construction"):
            continue
        for ll in road_endpoints(road):
            if other_contains(ll):
                return True
    return False
