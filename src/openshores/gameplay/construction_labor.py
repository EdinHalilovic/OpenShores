
COMPEFFECT_NOTHING_A = 1
COMPEFFECT_DECREASES_TIME = 2
COMPEFFECT_DECREASES_MATERIALS = 3
COMPEFFECT_NOTHING_B = 4
COMPEFFECT_REQUIRED = 5
COMPEFFECT_INCREASES_OUTPUT = 6

COMPEFFECT_NAMES = {
    1: "Does Nothing",
    2: "Decreases Time",
    3: "Decreases Materials",
    4: "Does Nothing",
    5: "Required",
    6: "Increases Output",
}

BASE_LABOR_PER_WORK = 4
ITEM_LABOR_BOOST = 5
ELECTRICITY_CID = 3
ELECTRICITY_BOOST = 1


def _cid(comp):
    return int(comp[0]) & 0xFFFF


def _effect(comp):
    return int(comp[2])


def _required(comp):
    return int(comp[3])


def _applied(comp):
    return int(comp[4])


def is_satisfied(comp):
    req = _required(comp)
    return _applied(comp) >= req if req > 0 else _applied(comp) > 0


def missing_required_tools(components, *, player_has, city_has, city_power):
    blocked = []
    for comp in components or ():
        if _effect(comp) != COMPEFFECT_REQUIRED or _required(comp) != 0:
            continue
        if is_satisfied(comp):
            continue
        cid = _cid(comp)
        if cid == ELECTRICITY_CID:
            if not city_power:
                blocked.append(cid)
        elif not (player_has(cid) or city_has(cid)):
            blocked.append(cid)
    return blocked


def labor_units_for_work(components, *, player_has, player_use, city_has,
                         city_use, city_power):
    components = list(components or ())
    blocked = missing_required_tools(components, player_has=player_has,
                                     city_has=city_has, city_power=city_power)
    if blocked:
        return 0, blocked

    boost = 0
    for comp in components:
        eff = _effect(comp)
        cid = _cid(comp)
        if eff == COMPEFFECT_DECREASES_TIME:
            if cid == ELECTRICITY_CID:
                if city_power:
                    comp[4] = 1
                    boost += ELECTRICITY_BOOST
                else:
                    comp[4] = 0
            elif player_use(cid) or city_use(cid):
                comp[4] = 1
                boost += ITEM_LABOR_BOOST
            else:
                comp[4] = 0
        elif eff == COMPEFFECT_REQUIRED and _required(comp) == 0 \
                and not is_satisfied(comp):
            if cid == ELECTRICITY_CID:
                comp[4] = 1 if city_power else 0
            else:
                comp[4] = 1 if (player_use(cid) or city_use(cid)) else 0
    return BASE_LABOR_PER_WORK + boost, []


def apply_labor(cstate, units):
    before = int(cstate.get("labor", 0) or 0)
    n = max(0, min(int(units), before))
    cstate["labor"] = before - n
    return before, cstate["labor"], n


def describe(components):
    out = []
    for comp in components or ():
        eff = _effect(comp)
        req = _required(comp)
        label = ("material" if eff == COMPEFFECT_REQUIRED and req > 0
                 else COMPEFFECT_NAMES.get(eff, "effect%d" % eff))
        out.append("0x%x:%s%s" % (_cid(comp), label,
                                  "(%d/%d)" % (_applied(comp), req) if req else ""))
    return ", ".join(out) or "none"


MAX_CONSTRUCTED_LEVELS = 0x1F


def add_constructed_level(b) -> bool:
    lv = int(getattr(b, "levels", 0) or 0)
    if lv >= MAX_CONSTRUCTED_LEVELS:
        return False
    b.levels = lv + 1
    return True


def is_complete(cstate) -> bool:
    return int((cstate or {}).get("labor", 0) or 0) <= 0
