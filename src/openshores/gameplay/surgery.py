from __future__ import annotations

from openshores.gameplay import conditions as _cx
from openshores.gameplay import gear_wear as _gw

TREAT_HEAL = "heal"
TREAT_SURGERY = "surgery"
TREAT_PHYSICAL_THERAPY = "physical_therapy"
TREAT_ANTIDOTE = "antidote"
TREAT_ANTITOXIN = "antitoxin"
TREAT_DECONTAMINATE = "decontaminate"
TREAT_DEFIBRILLATE = "defibrillate"

ALL_TREATMENTS = (TREAT_HEAL, TREAT_SURGERY, TREAT_PHYSICAL_THERAPY,
                  TREAT_ANTIDOTE, TREAT_ANTITOXIN, TREAT_DECONTAMINATE,
                  TREAT_DEFIBRILLATE)

TREATS_CONDITION = {
    TREAT_ANTIDOTE: _cx.CON_POISON,
    TREAT_ANTITOXIN: _cx.CON_DISEASE,
    TREAT_DECONTAMINATE: _cx.CON_ACID,
    TREAT_PHYSICAL_THERAPY: _cx.CON_PARALYSIS,
    TREAT_SURGERY: _cx.CON_IMPLANT,
}

SURGERY_ALSO_TREATS = (_cx.CON_PREGNANT,)

TREATMENT_COMMODITY = {
    TREAT_ANTIDOTE: 0x77,
    TREAT_ANTITOXIN: 0x78,
}

TREATMENT_CONSUMES_NOTHING = frozenset({TREAT_PHYSICAL_THERAPY})

MEDICAL_SYSTEM = 10

MISUSE_EFFECT = 4
MISUSE_DAMAGE_SIDES = 10

OUTCOME_CURED = "cured"
OUTCOME_REDUCED = "reduced"
OUTCOME_NOT_CURED = "not_cured"
OUTCOME_NOT_REDUCED = "not_reduced"
OUTCOME_IMPROPER = "improper"
OUTCOME_INCORRECT = "incorrect"
OUTCOME_NO_STOCK = "no_stock"

THOUGHT = {
    OUTCOME_CURED: "%1 cured using %2.",
    OUTCOME_REDUCED: "%1 reduced using %2.",
    OUTCOME_NOT_CURED: "%1 not cured by %2.",
    OUTCOME_NOT_REDUCED: "%1 not reduced by %2.",
    OUTCOME_IMPROPER: "Improper use of %1.",
    OUTCOME_INCORRECT: "Incorrect medical treatment with %1.",
    OUTCOME_NO_STOCK: "Ship's pharmacy has no %1.",
}
THOUGHT_CONSUMED = "%1 consumed from ship's pharmacy."


class Result:

    __slots__ = ("outcome", "condition", "potency", "harm", "consumed")

    def __init__(self, outcome, condition=None, potency=0, harm=0,
                 consumed=False):
        self.outcome = outcome
        self.condition = condition
        self.potency = int(potency)
        self.harm = int(harm)
        self.consumed = bool(consumed)

    @property
    def helped(self):
        return self.outcome in (OUTCOME_CURED, OUTCOME_REDUCED)

    @property
    def thought(self):
        return THOUGHT.get(self.outcome, "")

    def __repr__(self):
        return ("Result(%s potency=%d harm=%d)"
                % (self.outcome, self.potency, self.harm))


def potency(system_quality, medicine_quality) -> int:
    return min(int(system_quality) & 0xFF, int(medicine_quality) & 0xFF)


def treats(treatment, condition) -> bool:
    if condition is None:
        return False
    want = TREATS_CONDITION.get(treatment)
    if want is not None and condition.type == want:
        return True
    if treatment == TREAT_SURGERY and condition.type in SURGERY_ALSO_TREATS:
        return True
    return False


def apply_treatment(conditions, treatment, condition, system_quality,
                    medicine_quality, in_stock=True, dice=None):
    if not in_stock:
        return Result(OUTCOME_NO_STOCK)

    pot = potency(system_quality, medicine_quality)
    consumed = not _test_quality(medicine_quality, dice)

    if condition is None:
        return Result(OUTCOME_IMPROPER, harm=_misuse_damage(dice),
                      potency=pot, consumed=consumed)
    if not treats(treatment, condition):
        return Result(OUTCOME_INCORRECT, condition=condition,
                      harm=_misuse_damage(dice), potency=pot,
                      consumed=consumed)

    if pot >= condition.severity:
        removed = _cx.remove_condition(conditions, condition.type)
        outcome = OUTCOME_CURED if removed else OUTCOME_NOT_CURED
    else:
        before = condition.severity
        _cx.reduce_condition(conditions, condition.type, pot)
        outcome = (OUTCOME_REDUCED if condition.severity < before
                   else OUTCOME_NOT_REDUCED)
    return Result(outcome, condition=condition, potency=pot,
                  consumed=consumed)


def _test_quality(quality, dice=None) -> bool:
    return _gw.test_quality(quality, dice)


def _misuse_damage(dice=None) -> int:
    if dice is not None:
        return int(dice.roll(1, MISUSE_DAMAGE_SIDES))
    return int(_gw._DICE.roll(1, MISUSE_DAMAGE_SIDES))


