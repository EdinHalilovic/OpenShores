from __future__ import annotations

import time

from openshores.gameplay import gear_wear as _gw

CON_ACID = 1
CON_BOUNTY = 2
CON_DISEASE = 3
CON_FIRE = 4
CON_IMPLANT = 5
CON_PARALYSIS = 6
CON_POISON = 7
CON_PREGNANT = 8
CON_THOUGHT = 9

CONDITION_NAMES = {
    CON_ACID: "Acid", CON_BOUNTY: "Bounty", CON_DISEASE: "Disease",
    CON_FIRE: "Fire", CON_IMPLANT: "Implant", CON_PARALYSIS: "Paralysis",
    CON_POISON: "Poison", CON_PREGNANT: "Pregnant", CON_THOUGHT: "Thought",
}

TREATABLE = frozenset({CON_ACID, CON_DISEASE, CON_PARALYSIS, CON_POISON})

HAS_ICON = frozenset({CON_ACID, CON_DISEASE, CON_IMPLANT, CON_PARALYSIS,
                      CON_POISON, CON_PREGNANT})


EFFECT_TO_CONDITION = {
    1: CON_ACID,
    3: CON_PARALYSIS,
    4: CON_POISON,
    6: CON_DISEASE,
    14: CON_IMPLANT,
}

FIRE_CHANCE_PERCENT = 10

TICK_INTERVAL_MS = 10_000

_SPEED_SCALE = 100.0


class Condition:

    __slots__ = ("type", "severity", "quality", "strain", "started_ms",
                 "source", "dna")

    def __init__(self, ctype, severity=0, quality=0, strain=0,
                 started_ms=None, source=0, dna=None):
        self.type = int(ctype)
        self.severity = max(0, min(255, int(severity)))
        self.quality = int(quality) & 0xFF
        self.strain = int(strain) & 0xFF
        self.started_ms = (int(time.time() * 1000)
                           if started_ms is None else int(started_ms))
        self.source = int(source) & 0xFFFFFFFF
        self.dna = bytes(dna) if dna else b""

    @property
    def name(self):
        return CONDITION_NAMES.get(self.type, "Condition%d" % self.type)

    @property
    def treatable(self):
        return self.type in TREATABLE

    def age_ms(self, now_ms=None):
        now = int(time.time() * 1000) if now_ms is None else int(now_ms)
        return max(0, now - self.started_ms)

    def to_dict(self):
        d = {"type": self.type, "severity": self.severity,
             "quality": self.quality, "strain": self.strain,
             "started_ms": self.started_ms, "source": self.source}
        if self.dna:
            d["dna"] = self.dna.hex()
        return d

    @classmethod
    def from_dict(cls, d):
        dna = d.get("dna")
        return cls(d["type"], d.get("severity", 0), d.get("quality", 0),
                   d.get("strain", 0), d.get("started_ms"),
                   d.get("source", 0),
                   bytes.fromhex(dna) if dna else None)

    def __repr__(self):
        return ("Condition(%s sev=%d q=%d)"
                % (self.name, self.severity, self.quality))


def has_condition(conditions, ctype) -> bool:
    return any(c.type == int(ctype) for c in conditions or ())


def add_condition(conditions, cond) -> bool:
    if cond.type in (CON_ACID, CON_DISEASE, CON_PARALYSIS, CON_POISON,
                     CON_PREGNANT):
        if has_condition(conditions, cond.type):
            return False
    conditions.append(cond)
    return True


def remove_condition(conditions, ctype) -> int:
    before = len(conditions)
    conditions[:] = [c for c in conditions if c.type != int(ctype)]
    return before - len(conditions)


def reduce_condition(conditions, ctype, amount=1) -> int:
    removed = 0
    keep = []
    for c in conditions:
        if c.type == int(ctype):
            c.severity = max(0, c.severity - int(amount))
            if c.severity == 0:
                removed += 1
                continue
        keep.append(c)
    conditions[:] = keep
    return removed


def has_treatable_conditions(conditions) -> bool:
    return any(c.treatable for c in conditions or ())


def speed_effect(conditions) -> float:
    total = sum(c.severity for c in conditions or ()
                if c.type == CON_PARALYSIS)
    if total >= 100:
        return 0.0
    if total > 0:
        return (_SPEED_SCALE - total) / _SPEED_SCALE
    return 1.0


def conditions_from_hit(effect1, damage1, effect2, damage2, quality,
                        existing=None, incendiary=False, attacker=0,
                        dice=None, strain=0, dna=None):
    existing = existing or []
    out = []
    for effect, damage in ((int(effect1), int(damage1)),
                           (int(effect2), int(damage2))):
        if not damage:
            continue
        ctype = EFFECT_TO_CONDITION.get(effect)
        if ctype is None:
            continue
        if ctype == CON_DISEASE and not attacker:
            continue
        if has_condition(existing, ctype) or has_condition(out, ctype):
            continue
        out.append(Condition(ctype, severity=damage & 0xFF, quality=quality,
                             strain=strain if ctype == CON_DISEASE else 0,
                             source=attacker,
                             dna=dna if ctype == CON_IMPLANT else None))
    if incendiary and (damage1 or damage2):
        roll = _roll_1_100(dice)
        if roll <= FIRE_CHANCE_PERCENT:
            out.append(Condition(CON_FIRE, quality=quality, source=attacker))
    return out


def _roll_1_100(dice=None) -> int:
    if dice is not None:
        return int(dice.roll(1, 100))
    return int(_gw._DICE.roll(1, 100))


def should_tick(last_tick_ms, now_ms=None) -> bool:
    if not last_tick_ms:
        return True
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    return (now - int(last_tick_ms)) >= TICK_INTERVAL_MS


def tick(conditions, now_ms=None):
    hp_delta = 0
    expired = []
    keep = []
    for c in conditions or ():
        if c.type in (CON_POISON, CON_ACID, CON_DISEASE):
            hp_delta -= 1
            c.severity = max(0, c.severity - 1)
            if c.severity == 0:
                expired.append(c)
                continue
        elif c.type == CON_FIRE:
            hp_delta -= 1
        elif c.type == CON_PARALYSIS:
            c.severity = max(0, c.severity - 1)
            if c.severity == 0:
                expired.append(c)
                continue
        keep.append(c)
    if conditions is not None:
        conditions[:] = keep
    return hp_delta, expired


def to_json(conditions) -> str:
    import json
    return json.dumps([c.to_dict() for c in conditions or ()],
                      separators=(",", ":"))


def from_json(text):
    import json
    if not text:
        return []
    try:
        return [Condition.from_dict(d) for d in json.loads(text)]
    except Exception:
        return []


