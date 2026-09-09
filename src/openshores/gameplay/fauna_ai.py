from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

ECO_CARNIVORE = 0
ECO_HERBIVORE = 1
ECO_OMNIVORE = 2
ECO_SCAVENGER = 3

ECO_NAMES = {
    ECO_CARNIVORE: "Carnivorous",
    ECO_HERBIVORE: "Herbivorous",
    ECO_OMNIVORE: "Omnivorous",
    ECO_SCAVENGER: "Scavenging",
}

HOSTILE_ROLES = frozenset({ECO_CARNIVORE})
FLEEING_ROLES = frozenset({ECO_HERBIVORE})
WARY_ROLES = frozenset({ECO_SCAVENGER})
OPPORTUNIST_ROLES = frozenset({ECO_OMNIVORE})

STATE_IDLE = "idle"
STATE_WANDER = "wander"
STATE_FLEE = "flee"
STATE_CHASE = "chase"
STATE_ATTACK = "attack"
STATE_DEAD = "dead"

SCAVENGE_RADIUS_M = 40.0

ATTACK_REACH_M = 2.5

ATTACK_PERIOD_S = 2.0

FLEE_ESCAPE_FACTOR = 1.5

DEFAULT_SIGHT_M = 30.0

SPEED_WANDER_MPS = 1.0
SPEED_CHASE_MPS = 4.5
SPEED_FLEE_MPS = 6.0

WANDER_CHANCE_PCT = 7

WANDER_LEASH_M = 25.0


def attack_damage(max_hp: int) -> int:
    return max(1, int(max_hp) // 10)


def sight_range_m(dna=None, default=DEFAULT_SIGHT_M) -> float:
    if dna is None:
        return default
    try:
        r = float(dna.sight_range_m())
        return r if r > 0 else default
    except Exception:
        return default


def notice_range_m(dna=None) -> float:
    return sight_range_m(dna)


def engage_range_m(dna=None) -> float:
    return sight_range_m(dna) / 2.0


def is_hostile(eco_role: int) -> bool:
    return int(eco_role) in HOSTILE_ROLES


def _omnivore_is_bold(target_hp_frac: float, hunger_frac: float) -> bool:
    return target_hp_frac <= 0.5 or hunger_frac <= 0.25


@dataclass
class AnimalView:
    auid: int
    eco_role: int
    xyz: tuple
    hp: int
    max_hp: int
    hunger: int = 0
    max_hunger: int = 0
    dna: object = None
    state: str = STATE_IDLE
    last_attack_s: float = 0.0
    pose: int = 0x24
    home_xyz: Optional[tuple] = None

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def hunger_frac(self) -> float:
        if not self.max_hunger:
            return 1.0
        return max(0.0, min(1.0, self.hunger / float(self.max_hunger)))


@dataclass
class PersonView:
    auid: int
    xyz: tuple
    hp: int = 1
    max_hp: int = 1

    @property
    def hp_frac(self) -> float:
        if not self.max_hp:
            return 1.0
        return max(0.0, min(1.0, self.hp / float(self.max_hp)))


@dataclass
class Intent:
    state: str
    move_to: Optional[tuple] = None
    face_rad: float = 0.0
    pose: Optional[int] = None
    attack_target: int = 0
    attack_damage: int = 0

    @property
    def moved(self) -> bool:
        return self.move_to is not None


def distance_m(a, b) -> float:
    return math.sqrt(sum((float(p) - float(q)) ** 2 for p, q in zip(a, b)))


def _step_toward(src, dst, metres):
    d = distance_m(src, dst)
    if d <= 1e-6:
        return tuple(float(v) for v in src)
    if metres >= d:
        return tuple(float(v) for v in dst)
    f = metres / d
    return tuple(float(s) + (float(t) - float(s)) * f for s, t in zip(src, dst))


def _step_away(src, threat, metres):
    d = distance_m(src, threat)
    if d <= 1e-6:
        return (float(src[0]) + metres, float(src[1]), float(src[2]))
    f = metres / d
    return tuple(float(s) + (float(s) - float(t)) * f
                 for s, t in zip(src, threat))


def _bearing_rad(src, dst) -> float:
    return math.atan2(float(dst[1]) - float(src[1]),
                      float(dst[0]) - float(src[0]))


def nearest_person(animal: AnimalView, people) -> Optional[PersonView]:
    best, best_d = None, None
    for p in people or ():
        d = distance_m(animal.xyz, p.xyz)
        if best_d is None or d < best_d:
            best, best_d = p, d
    return best


def _wander(animal: AnimalView, dice) -> Intent:
    if dice is None:
        return Intent(state=STATE_IDLE)
    if dice.roll(1, 100) > WANDER_CHANCE_PCT:
        return Intent(state=STATE_IDLE)
    home = animal.home_xyz or animal.xyz
    if distance_m(animal.xyz, home) >= WANDER_LEASH_M:
        return Intent(state=STATE_WANDER,
                      move_to=_step_toward(animal.xyz, home,
                                           SPEED_WANDER_MPS),
                      face_rad=_bearing_rad(animal.xyz, home))
    bearing = math.radians(dice.roll(1, 360) - 1)
    dest = (float(animal.xyz[0]) + math.cos(bearing) * SPEED_WANDER_MPS,
            float(animal.xyz[1]) + math.sin(bearing) * SPEED_WANDER_MPS,
            float(animal.xyz[2]))
    return Intent(state=STATE_WANDER, move_to=dest, face_rad=bearing)


def decide(animal: AnimalView, people, now_s: float,
           carcasses=(), dice=None) -> Intent:
    if not animal.alive:
        return Intent(state=STATE_DEAD)

    dt_speed = 1.0
    person = nearest_person(animal, people)
    role = int(animal.eco_role)

    if person is None:
        if role == ECO_SCAVENGER and carcasses:
            target = min(carcasses,
                         key=lambda c: distance_m(animal.xyz, c))
            if distance_m(animal.xyz, target) <= SCAVENGE_RADIUS_M:
                return Intent(state=STATE_CHASE,
                              move_to=_step_toward(animal.xyz, target,
                                                   SPEED_WANDER_MPS * dt_speed),
                              face_rad=_bearing_rad(animal.xyz, target))
        return _wander(animal, dice)

    d = distance_m(animal.xyz, person.xyz)
    notice = notice_range_m(animal.dna)
    engage = engage_range_m(animal.dna)

    if d > notice:
        return _wander(animal, dice)

    if role in FLEEING_ROLES:
        if d >= notice * FLEE_ESCAPE_FACTOR:
            return _wander(animal, dice)
        return Intent(state=STATE_FLEE,
                      move_to=_step_away(animal.xyz, person.xyz,
                                         SPEED_FLEE_MPS * dt_speed),
                      face_rad=_bearing_rad(person.xyz, animal.xyz))

    if role in WARY_ROLES:
        if d < engage:
            return Intent(state=STATE_FLEE,
                          move_to=_step_away(animal.xyz, person.xyz,
                                             SPEED_WANDER_MPS * dt_speed),
                          face_rad=_bearing_rad(person.xyz, animal.xyz))
        return _wander(animal, dice)

    if role in OPPORTUNIST_ROLES:
        if not _omnivore_is_bold(person.hp_frac, animal.hunger_frac):
            return _wander(animal, dice)

    if d <= ATTACK_REACH_M:
        if (now_s - animal.last_attack_s) < ATTACK_PERIOD_S:
            return Intent(state=STATE_ATTACK,
                          face_rad=_bearing_rad(animal.xyz, person.xyz),
                          attack_target=person.auid, attack_damage=0)
        return Intent(state=STATE_ATTACK,
                      face_rad=_bearing_rad(animal.xyz, person.xyz),
                      attack_target=person.auid,
                      attack_damage=attack_damage(animal.max_hp))
    if d <= engage:
        return Intent(state=STATE_CHASE,
                      move_to=_step_toward(animal.xyz, person.xyz,
                                           SPEED_CHASE_MPS * dt_speed),
                      face_rad=_bearing_rad(animal.xyz, person.xyz))
    return _wander(animal, dice)


def describe(animal: AnimalView, intent: Intent) -> str:
    return (f"0x{animal.auid:08x} {ECO_NAMES.get(int(animal.eco_role), '?')} "
            f"{intent.state}"
            + (f" -> attack 0x{intent.attack_target:08x} "
               f"for {intent.attack_damage}" if intent.attack_damage else "")
            + (" (moved)" if intent.moved else ""))
