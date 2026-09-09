from __future__ import annotations

import time

from openshores.gameplay.dpbody_maxes import max_hp as _mhp

from openshores.world.entities import (
    CITIZEN_KINDS,
    KIND_ANIMAL,
    KIND_NATIVE,
    KIND_OTHER,
    KIND_STORY,
)

FAUNA_AUID_PREFIX = 0xC0000000

DYING_HP = -15
DEAD_HP = -30

DEFAULT_MAX_HP = 20

def corpse_despawn_ms() -> int:
    sec = 300.0
    return max(0, int(sec * 1000))


class Damageable:

    __slots__ = ("auid", "kind", "name", "hp", "max_hp", "dna",
                 "mins_to_full_grown", "last_attacker", "last_attacker_ms",
                 "world_auid", "died_ms", "looted", "xyz",
                 "ai_last_attack_s", "home_xyz")

    def __init__(self, auid, max_hp, kind=KIND_OTHER, name="", dna=None,
                 mins_to_full_grown=0, world_auid=0):
        self.auid = int(auid) & 0xFFFFFFFF
        self.kind = kind
        self.name = str(name or "")
        self.max_hp = max(1, int(max_hp))
        self.hp = self.max_hp
        self.dna = bytes(dna) if dna else b""
        self.mins_to_full_grown = max(0, min(255, int(mins_to_full_grown)))
        self.last_attacker = 0
        self.last_attacker_ms = 0
        self.world_auid = int(world_auid) & 0xFFFFFFFF
        self.died_ms = 0
        self.looted = False
        self.xyz = None
        self.ai_last_attack_s = 0.0
        self.home_xyz = None

    @property
    def alive(self):
        return self.hp > DEAD_HP

    @property
    def dying(self):
        return DEAD_HP < self.hp < 1

    @property
    def is_citizen(self):
        return self.kind in CITIZEN_KINDS

    @property
    def is_corpse(self):
        return (not self.alive) and self.died_ms > 0

    def corpse_age_ms(self, now_ms=None):
        if not self.is_corpse:
            return 0
        now = int(now_ms if now_ms is not None else time.time() * 1000)
        return max(0, now - self.died_ms)

    @property
    def skinnable(self):
        return self.is_corpse and not self.looted and not self.is_citizen

    def __repr__(self):
        return ("Damageable(0x%08x %s %r hp=%d/%d)"
                % (self.auid, self.kind, self.name, self.hp, self.max_hp))


_REGISTRY: dict = {}


def max_hp_from_dna(dna) -> int:
    if not dna or len(dna) < 24:
        return DEFAULT_MAX_HP
    return max(1, int(_mhp(bytes(dna))))


def register(auid, kind=KIND_OTHER, name="", dna=None, max_hp=None,
             mins_to_full_grown=0, world_auid=0, xyz=None):
    auid = int(auid) & 0xFFFFFFFF
    existing = _REGISTRY.get(auid)
    if max_hp is None:
        max_hp = max_hp_from_dna(dna)
    d = Damageable(auid, max_hp, kind=kind, name=name, dna=dna,
                   mins_to_full_grown=mins_to_full_grown,
                   world_auid=world_auid)
    if xyz:
        try:
            d.xyz = tuple(float(v) for v in xyz)[:3]
            d.home_xyz = d.xyz
        except Exception:
            d.xyz = None
    if existing is not None:
        if not existing.alive:
            d.hp = existing.hp
        else:
            taken = max(0, existing.max_hp - existing.hp)
            d.hp = max(DYING_HP, min(d.max_hp, d.max_hp - taken))
        d.last_attacker = existing.last_attacker
        d.last_attacker_ms = existing.last_attacker_ms
        d.died_ms = existing.died_ms
        d.looted = existing.looted
        if d.xyz is None:
            d.xyz = existing.xyz
        d.home_xyz = existing.home_xyz or d.home_xyz
    _REGISTRY[auid] = d
    return d


def unregister(auid) -> bool:
    return _REGISTRY.pop(int(auid) & 0xFFFFFFFF, None) is not None


def clear():
    _REGISTRY.clear()


def get(auid):
    return _REGISTRY.get(int(auid) & 0xFFFFFFFF)


def is_damageable(auid) -> bool:
    return (int(auid) & 0xFFFFFFFF) in _REGISTRY


def is_damageable_candidate(auid, *,
                            idle_bodies,
                            story_atom_id,
                            story_npcs) -> bool:
    auid = int(auid) & 0xFFFFFFFF
    if auid in (idle_bodies or {}):
        return True
    if auid == (int(story_atom_id) & 0xFFFFFFFF):
        return True
    for _st in (story_npcs or {}).values():
        if auid == (int(_st.get("auid") or 0) & 0xFFFFFFFF):
            return True
    if (auid & 0xFF000000) == FAUNA_AUID_PREFIX:
        return True
    return False


def all_damageable():
    return list(_REGISTRY.values())


def growth_damage_scale(mins_to_full_grown, growth_time) -> float:
    remaining = int(mins_to_full_grown)
    total = int(growth_time)
    if remaining <= 0 or total <= 0:
        return 1.0
    denom = (total - remaining) + 1
    if denom <= 0:
        return 1.0
    return total / denom


def damage(auid, amount, attacker=0, growth_time=None):
    d = get(auid)
    if d is None:
        return None
    was_dead = not d.alive
    amt = int(amount)
    if amt > 0 and d.mins_to_full_grown and growth_time:
        amt = max(1, int(amt * growth_scale_for(d, growth_time)))
    if amt > 0 and attacker:
        att = int(attacker) & 0xFFFFFFFF
        if att and att != d.auid:
            d.last_attacker = att
            d.last_attacker_ms = int(time.time() * 1000)
    new_hp = d.hp - amt
    if amt > 0 and not was_dead and new_hp < 1:
        new_hp = DEAD_HP
    d.hp = max(DEAD_HP, new_hp)
    died = (not was_dead) and (not d.alive)
    if died:
        d.died_ms = int(time.time() * 1000)
    return d.hp, died, was_dead


def growth_scale_for(d, growth_time) -> float:
    return growth_damage_scale(d.mins_to_full_grown, growth_time)


def heal(auid, amount):
    d = get(auid)
    if d is None:
        return None
    d.hp = min(d.max_hp, d.hp + int(amount))
    return d.hp


def revive(auid):
    d = get(auid)
    if d is None:
        return None
    d.hp = d.max_hp
    d.last_attacker = 0
    d.last_attacker_ms = 0
    d.died_ms = 0
    d.looted = False
    return d.hp


def mark_looted(auid) -> bool:
    d = get(auid)
    if d is None or d.looted:
        return False
    d.looted = True
    return True


def skinnable_corpses():
    return sorted((d for d in _REGISTRY.values() if d.skinnable),
                  key=lambda d: d.died_ms)


def expired_corpses(now_ms=None):
    ttl = corpse_despawn_ms()
    if ttl <= 0:
        return []
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    return [d for d in _REGISTRY.values()
            if d.is_corpse and (now - d.died_ms) >= ttl]


def sweep_corpses(now_ms=None):
    gone = expired_corpses(now_ms)
    for d in gone:
        _REGISTRY.pop(d.auid, None)
    return gone


def experience_points_for_killing(d) -> int:
    mhp = int(d.max_hp)
    base = 1 if mhp < 6 else mhp // 5
    return base
