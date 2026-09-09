from __future__ import annotations

import math
import struct

from openshores.gameplay import conditions as _cx


MODE_NOT = 0
MODE_AREA = 1
MODE_CONTACT = 2
MODE_DETONATOR = 3
MODE_FUSE = 4
MODE_PROJECTILE = 5
MODE_PSIONIC = 6

MODE_NAMES = {
    MODE_NOT: "Not", MODE_AREA: "Area", MODE_CONTACT: "Contact",
    MODE_DETONATOR: "Detonator", MODE_FUSE: "Fuse",
    MODE_PROJECTILE: "Projectile", MODE_PSIONIC: "Psionic",
}


EFF_NO = 0
EFF_ACID = 1
EFF_SUFFOCATION = 2
EFF_STUN = 3
EFF_POISON = 4
EFF_RADIATION = 5
EFF_DISEASE = 6
EFF_ELECTRICAL = 7
EFF_BLUDGEON = 8
EFF_FREEZING = 9
EFF_CRUSHING = 10
EFF_SONIC = 11
EFF_BURNING = 12
EFF_PIERCING = 13
EFF_IMPLANT = 14
EFF_SLASHING = 15
EFF_ENERGY = 16
EFF_KINETIC = 17
EFF_BLEEDING = 18
EFF_STARVATION = 19
EFF_CORROSION = 20

EFFECT_NAMES = {
    EFF_NO: "No", EFF_ACID: "Acid", EFF_SUFFOCATION: "Suffocation",
    EFF_STUN: "Stun", EFF_POISON: "Poison", EFF_RADIATION: "Radiation",
    EFF_DISEASE: "Disease", EFF_ELECTRICAL: "Electrical",
    EFF_BLUDGEON: "Bludgeon", EFF_FREEZING: "Freezing",
    EFF_CRUSHING: "Crushing", EFF_SONIC: "Sonic", EFF_BURNING: "Burning",
    EFF_PIERCING: "Piercing", EFF_IMPLANT: "Implant",
    EFF_SLASHING: "Slashing", EFF_ENERGY: "Energy", EFF_KINETIC: "Kinetic",
    EFF_BLEEDING: "Bleeding", EFF_STARVATION: "Starvation",
    EFF_CORROSION: "Corrosion",
}

EFFECTS_WITH_CONDITIONS = frozenset(_cx.EFFECT_TO_CONDITION)


CRIT_ROLL_THRESHOLD = 95
CRIT_ARMOR_MULTIPLIER = 0.5


_ROW_EFFECT_ABSORB = 6
_ROW_EFFECT_BLOCK = 23
_ROW_MODE_ABSORB = 40
_ROW_MODE_BLOCK = 44
_ROW_ARMOR_SPEC = 48

_EFFECT_TABLE_LEN = 17
_MODE_TABLE_LEN = 4

MODE_ARMOR_SLOT = {
    MODE_AREA: 0, MODE_DETONATOR: 0, MODE_FUSE: 0,
    MODE_CONTACT: 1,
    MODE_PROJECTILE: 2,
    MODE_PSIONIC: 3,
}

BLOCK_SCALE = 1.0 / 100.0
ABSORB_SCALE = 1.0

ARMOR_SLOTS = frozenset({2, 3, 4, 5, 6, 7, 8, 9})


class ArmorProfile:

    __slots__ = ("cid", "effect_absorb", "effect_block", "mode_absorb",
                 "mode_block", "specialty")

    def __init__(self, cid=0, effect_absorb=(), effect_block=(),
                 mode_absorb=(), mode_block=(), specialty=0):
        self.cid = int(cid)
        self.effect_absorb = tuple(effect_absorb) or (0,) * _EFFECT_TABLE_LEN
        self.effect_block = tuple(effect_block) or (0,) * _EFFECT_TABLE_LEN
        self.mode_absorb = tuple(mode_absorb) or (0,) * _MODE_TABLE_LEN
        self.mode_block = tuple(mode_block) or (0,) * _MODE_TABLE_LEN
        self.specialty = int(specialty) & 0xFF

    @property
    def empty(self):
        return not (any(self.effect_absorb) or any(self.effect_block)
                    or any(self.mode_absorb) or any(self.mode_block))

    def effect_pair(self, effect):
        i = int(effect)
        if not (0 <= i < _EFFECT_TABLE_LEN):
            return (0, 0)
        return (self.effect_absorb[i], self.effect_block[i])

    def mode_pair(self, mode):
        slot = MODE_ARMOR_SLOT.get(int(mode))
        if slot is None:
            return (0, 0)
        return (self.mode_absorb[slot], self.mode_block[slot])

    def __repr__(self):
        return ("ArmorProfile(cid=%d mode_abs=%s mode_blk=%s spec=%s)"
                % (self.cid, list(self.mode_absorb), list(self.mode_block),
                   EFFECT_NAMES.get(self.specialty, self.specialty)))


EMPTY_ARMOR = ArmorProfile()

_ARMOR_CACHE = {}


def armor_profile_for_cid(cid):
    cid = int(cid) & 0xFFFF
    hit = _ARMOR_CACHE.get(cid)
    if hit is not None:
        return hit
    prof = EMPTY_ARMOR
    row = _commodity_row(cid)
    if row is not None and row.raw and len(row.raw) > _ROW_ARMOR_SPEC:
        raw = row.raw
        prof = ArmorProfile(
            cid,
            raw[_ROW_EFFECT_ABSORB:_ROW_EFFECT_ABSORB + _EFFECT_TABLE_LEN],
            raw[_ROW_EFFECT_BLOCK:_ROW_EFFECT_BLOCK + _EFFECT_TABLE_LEN],
            raw[_ROW_MODE_ABSORB:_ROW_MODE_ABSORB + _MODE_TABLE_LEN],
            raw[_ROW_MODE_BLOCK:_ROW_MODE_BLOCK + _MODE_TABLE_LEN],
            raw[_ROW_ARMOR_SPEC])
    _ARMOR_CACHE[cid] = prof
    return prof


def _commodity_row(cid):
    from openshores.gameplay import gd_tables as _gd
    return _gd.load_commodities().get(int(cid) & 0xFFFF)


def set_armor_profile(cid, profile):
    _ARMOR_CACHE[int(cid) & 0xFFFF] = profile


def reset_caches():
    _ARMOR_CACHE.clear()
    _WEAPON_CACHE.clear()


class Worn:

    __slots__ = ("cid", "quality", "slot")

    def __init__(self, cid, quality=0, slot=5):
        self.cid = int(cid) & 0xFFFF
        self.quality = int(quality) & 0xFF
        self.slot = int(slot) & 0xFF

    @property
    def armor(self):
        return armor_profile_for_cid(self.cid)

    def __repr__(self):
        return "Worn(cid=%d q=%d slot=%d)" % (self.cid, self.quality,
                                              self.slot)


def worn_from_gear(gear):
    from openshores.gameplay import gear_wear as _gw
    out = []
    for e in gear or ():
        try:
            slot = int(e[0]) & 0xFF
            body = bytes(e[3])
        except Exception:
            continue
        if slot not in ARMOR_SLOTS or len(body) < 3:
            continue
        cid = int.from_bytes(body[1:3], "big") & 0xFFFF
        if armor_profile_for_cid(cid).empty:
            continue
        out.append(Worn(cid, _gw.quality(body), slot))
    return out


def combat_armor_hits(worn, mode=MODE_CONTACT, dice=None):
    return list(worn or ())


SPECIALTY_BONUS_ABSORB = 2
SPECIALTY_BONUS_BLOCK = 1


def armor_specialty_bonus(profile, effect):
    return (0, 0)


def quality_multiplier(quality):
    from openshores.gameplay import city_sim as _cs
    return float(_cs.quality_multiplier(int(quality)))


def combat_armor_effectiveness(worn, effect, mode, dice=None):
    absorb_a = block_a = absorb_b = block_b = 0.0
    for piece in combat_armor_hits(worn, mode, dice):
        prof = piece.armor
        if prof.empty:
            continue
        qmul = quality_multiplier(piece.quality)
        ea, eb = prof.effect_pair(effect)
        ma, mb = prof.mode_pair(mode)
        ba, bb = armor_specialty_bonus(prof, effect)
        absorb_a += (ea + ba) * ABSORB_SCALE
        block_a += (eb + bb) * BLOCK_SCALE * qmul
        absorb_b += ma * ABSORB_SCALE
        block_b += mb * BLOCK_SCALE * qmul
    return (absorb_a, min(1.0, block_a), absorb_b, min(1.0, block_b))


class PersonWeapon:

    __slots__ = ("kind", "mode", "range_", "qty",
                 "effect1", "damage1", "modifier1", "radius1", "pierce1",
                 "strike1",
                 "effect2", "damage2", "modifier2", "radius2", "pierce2",
                 "strike2")

    def __init__(self, kind=0, mode=MODE_NOT, range_=0, qty=0,
                 effect1=EFF_NO, damage1=0, modifier1=0, radius1=0,
                 pierce1=0, strike1=0,
                 effect2=EFF_NO, damage2=0, modifier2=0, radius2=0,
                 pierce2=0, strike2=0):
        self.kind = int(kind)
        self.mode = int(mode)
        self.range_ = int(range_)
        self.qty = int(qty)
        self.effect1 = int(effect1)
        self.damage1 = int(damage1)
        self.modifier1 = int(modifier1)
        self.radius1 = int(radius1)
        self.pierce1 = int(pierce1)
        self.strike1 = int(strike1)
        self.effect2 = int(effect2)
        self.damage2 = int(damage2)
        self.modifier2 = int(modifier2)
        self.radius2 = int(radius2)
        self.pierce2 = int(pierce2)
        self.strike2 = int(strike2)

    @classmethod
    def from_mode(cls, mode):
        return cls(mode=int(mode))

    @property
    def armed(self):
        return self.effect1 != EFF_NO or self.effect2 != EFF_NO

    def damage_range(self, slot=1):
        d = self.damage1 if slot == 1 else self.damage2
        m = self.modifier1 if slot == 1 else self.modifier2
        if d <= 0:
            return (0, 0)
        return (m + 1, m + d)

    def __repr__(self):
        lo, hi = self.damage_range(1)
        return ("PersonWeapon(cid=%d %s %s %d-%d)"
                % (self.kind, MODE_NAMES.get(self.mode, self.mode),
                   EFFECT_NAMES.get(self.effect1, self.effect1), lo, hi))


_WB_RANGE = 0
_WB_EFFECT1, _WB_DAMAGE1, _WB_MOD1, _WB_RADIUS1, _WB_AP1, _WB_ST1 = (
    2, 3, 5, 6, 8, 9)
_WB_EFFECT2, _WB_DAMAGE2, _WB_MOD2, _WB_RADIUS2, _WB_AP2, _WB_ST2 = (
    11, 12, 14, 15, 17, 18)

_WEAPON_CACHE = {}


def weapon_from_commodity(cid, sub=1):
    key = (int(cid) & 0xFFFF, int(sub))
    hit = _WEAPON_CACHE.get(key)
    if hit is not None:
        return hit if hit is not False else None
    row = _commodity_row(cid)
    blk = _weapon_block_bytes(row, sub) if row is not None else None
    if blk is None:
        _WEAPON_CACHE[key] = False
        return None
    mode, b = blk
    w = PersonWeapon(
        kind=int(cid) & 0xFFFF, mode=mode,
        range_=struct.unpack_from(">h", b, _WB_RANGE)[0],
        effect1=b[_WB_EFFECT1],
        damage1=struct.unpack_from(">h", b, _WB_DAMAGE1)[0],
        modifier1=b[_WB_MOD1],
        radius1=struct.unpack_from(">h", b, _WB_RADIUS1)[0],
        pierce1=b[_WB_AP1],
        strike1=struct.unpack_from(">h", b, _WB_ST1)[0],
        effect2=b[_WB_EFFECT2],
        damage2=struct.unpack_from(">h", b, _WB_DAMAGE2)[0],
        modifier2=b[_WB_MOD2],
        radius2=struct.unpack_from(">h", b, _WB_RADIUS2)[0],
        pierce2=b[_WB_AP2],
        strike2=struct.unpack_from(">h", b, _WB_ST2)[0])
    _WEAPON_CACHE[key] = w
    return w


def _weapon_block_bytes(row, sub):
    from openshores.gameplay import gd_tables as _gd
    offs = _gd._field_offsets(row.raw)
    if offs is None:
        return None
    mi = offs[_gd._FLD_MODE1 if sub == 1 else _gd._FLD_MODE2]
    bi = offs[_gd._FLD_WEAPON1 if sub == 1 else _gd._FLD_WEAPON2]
    raw = row.raw
    if mi >= len(raw) or bi + 20 > len(raw):
        return None
    return (raw[mi], raw[bi:bi + 20])


def weapon_from_gun_and_ammo(gun_cid, ammo_cid, sub=1):
    gun = weapon_from_commodity(gun_cid, sub)
    if gun is None:
        return None
    if not ammo_cid:
        return gun
    ammo = weapon_from_commodity(ammo_cid, 1)
    if ammo is None or (ammo.damage1 <= 0 and ammo.damage2 <= 0):
        return gun
    return PersonWeapon(
        kind=gun.kind, mode=gun.mode,
        range_=gun.range_ or ammo.range_, qty=gun.qty,
        effect1=ammo.effect1, damage1=ammo.damage1,
        modifier1=ammo.modifier1, radius1=ammo.radius1,
        pierce1=ammo.pierce1, strike1=ammo.strike1,
        effect2=ammo.effect2, damage2=ammo.damage2,
        modifier2=ammo.modifier2, radius2=ammo.radius2,
        pierce2=ammo.pierce2, strike2=ammo.strike2)


_SYNTH_FLAG_MASK = 0x300


def weapon_synth(cid, quality=0):
    row = _commodity_row(cid)
    if row is None:
        return None
    bits = int(row.flags) & _SYNTH_FLAG_MASK
    if not bits:
        return None
    scalar = _damage_scalar(row)
    dmg = int(round(quality_multiplier(quality) * scalar))
    effect = (EFF_SLASHING if bits == _SYNTH_FLAG_MASK
              else EFF_PIERCING if bits & 0x200 else EFF_BLUDGEON)
    return PersonWeapon(kind=int(cid) & 0xFFFF, mode=MODE_CONTACT, range_=1,
                        effect1=effect, damage1=max(0, dmg), modifier1=0)


_FLD_DAMAGE_SCALAR = 12


def _damage_scalar(row):
    from openshores.gameplay import gd_tables as _gd
    offs = _gd._field_offsets(row.raw)
    if offs is None:
        return 0
    i = offs[_FLD_DAMAGE_SCALAR]
    return row.raw[i] if i < len(row.raw) else 0


def weapon_for_cursor(cid, type_id, mode, *, quality=0, ammo_cid=0):
    if int(mode) == 0:
        return weapon_synth(cid, quality)
    sub = 2 if int(mode) == 2 else 1
    return weapon_from_gun_and_ammo(cid, ammo_cid, sub)


LOC_NONE = 0
LOC_FOREARM = 1
LOC_MOUTH = 2
LOC_HORN = 3
LOC_ARMS = 4
LOC_TEETH = 5
LOC_TAIL = 6
LOC_TORSO = 7

SLOT_PUNCH = -7
SLOT_BITE = -6
SLOT_HORN = -5
SLOT_CLAWS = -4
SLOT_TEETH = -3
SLOT_TAIL = -2
SLOT_WEAPON = -1

BODY_SLOTS = (SLOT_PUNCH, SLOT_BITE, SLOT_HORN, SLOT_CLAWS, SLOT_TEETH,
              SLOT_TAIL, SLOT_WEAPON)

NATURAL_SLOTS = (SLOT_HORN, SLOT_CLAWS, SLOT_TEETH, SLOT_TAIL)

BODY_SLOT_NAMES = {
    SLOT_PUNCH: "Punch", SLOT_BITE: "Bite", SLOT_HORN: "Horn",
    SLOT_CLAWS: "Claws", SLOT_TEETH: "Bite", SLOT_TAIL: "Tail",
    SLOT_WEAPON: "Body Slam",
}


def weaponloc(slot):
    return int(slot) + 8


def slot_for_weaponloc(loc):
    return int(loc) - 8


NATURAL_HP_DIVISOR = 100.0
SPECIAL_HP_DIVISOR = 50.0
SPECIAL_AREA_RADIUS_SCALE = 20.0
SPECIAL_DAMAGE_BIAS = 1.0
PSIONIC_RANGE_SCALE = 0.25
PROJECTILE_RANGE_DIVISOR = 3.0

BODY_SOUND_BASE = 0x57
BODY_SOUND_STRIDE = 0x18

DEFAULT_MAX_HP = 20

CONTACT_RANGE_FLOOR = 6.0


def body_melee_range_m():
    return CONTACT_RANGE_FLOOR


BODY_MELEE_RANGE_M = CONTACT_RANGE_FLOOR


def _dna_words(dna24):
    if not dna24 or len(dna24) < 24:
        return None
    try:
        return struct.unpack("<6I", bytes(dna24[:24]))
    except Exception:
        return None


def max_hp_from_dna(dna24, fallback=DEFAULT_MAX_HP):
    if not dna24 or len(dna24) < 24:
        return int(fallback)
    try:
        from openshores.gameplay.dpbody_maxes import max_hp as _mhp
        return max(1, int(_mhp(bytes(dna24[:24]))))
    except Exception:
        return int(fallback)


def has_arms(words):
    if not words:
        return False
    legs = words[0] & 0x300
    if not legs:
        return False
    return (words[0] & 0x60000) == 0 or legs > 0x100


def sight_range(words):
    if not words:
        return 90.0
    r = float((((words[1] >> 26) & 3) + 1) * 90)
    if (words[1] & 0x400) and (words[0] & 0x300) and (words[0] & 0x60000):
        r += r
    return r


def signature_effect(words):
    return (words[0] >> 12) & 0xF if words else EFF_NO


def weapon_location(dna24):
    words = _dna_words(dna24) if not isinstance(dna24, tuple) else dna24
    if not words:
        return LOC_NONE
    w0, w1, w2, w3, w4, w5 = words
    if (w0 & 0xF000) == 0:
        return LOC_NONE
    if not (w1 & 0x4000):
        return LOC_TEETH

    horn_head = (w1 & 0xC000000) > 0x4000000
    tail = (w3 & 0xC00000) > 0x400000
    claws = has_arms(words) and (w2 & 0x1F000000) > 0x1000000
    horns = bool(w3 & 0x0C) and (w2 & 0x1F0000) > 0x10000

    def _carriage():
        c = (w5 & 0xE0) >> 5
        return LOC_TEETH if c == 0 else (LOC_TORSO if c == 1 else LOC_FOREARM)

    sel = (w4 >> 22) & 3
    if sel == 0:
        return LOC_FOREARM
    if sel == 2:
        if tail:
            return LOC_TAIL
        if horn_head:
            return LOC_MOUTH
        return LOC_FOREARM if (w5 & 0xE0) else LOC_TEETH
    if sel == 3:
        if has_arms(words):
            return LOC_ARMS
        return LOC_TORSO if (w5 & 0xE0) else LOC_TEETH
    if horn_head:
        return LOC_MOUTH
    early_tail = (w4 & 7) in (0, 5)
    if early_tail and tail:
        return LOC_TAIL
    if claws:
        return LOC_ARMS
    if horns:
        return LOC_HORN
    if not early_tail and tail:
        return LOC_TAIL
    return _carriage()


def _natural_weapon(loc, words, hp_scale, slot):
    empty = PersonWeapon(kind=slot, mode=MODE_NOT)
    if words is None:
        return empty
    if loc == LOC_HORN:
        if not (words[3] & 0x0C):
            return empty
        klass = words[2] & 0xE00000
        effect = (EFF_SLASHING if klass in (0, 0xC00000) else EFF_BLUDGEON)
        field = ((words[2] >> 16) & 0x1F) + 1
    elif loc == LOC_ARMS:
        if not has_arms(words):
            return empty
        arms = words[2]
        effect = (EFF_SLASHING
                  if (arms < 0x20000000 or (arms & 0xE0000000) == 0xC0000000)
                  else EFF_BLUDGEON)
        field = ((words[2] >> 24) & 0x1F) + 1
    elif loc == LOC_TEETH:
        effect = EFF_PIERCING
        field = max(words[3] & 3, (words[3] >> 6) & 3) * 8 + 1
    elif loc == LOC_TAIL:
        if not ((words[3] & 0xC00000) > 0x400000):
            return empty
        effect = EFF_BLUDGEON
        field = ((words[3] >> 22) & 3) * 8 + 1
    else:
        return empty
    return PersonWeapon(
        kind=slot, mode=MODE_CONTACT, range_=body_melee_range_m(),
        qty=BODY_SOUND_BASE,
        effect1=effect, damage1=int(field * hp_scale) + 1,
        modifier1=int(hp_scale))


SPECIAL_MODE_BY_SELECTOR = {
    0: MODE_AREA,
    1: MODE_CONTACT,
    2: MODE_PROJECTILE,
    3: MODE_PSIONIC,
}


def _special_weapon(loc, words, hp_scale, slot):
    empty = PersonWeapon(kind=slot, mode=MODE_NOT)
    if words is None or loc == LOC_NONE or loc != weapon_location(words):
        return empty
    dna_effect = signature_effect(words)
    scale2 = ((words[5] >> 13) & 7) * 4
    if loc in (LOC_FOREARM, LOC_TORSO):
        scale1 = max(words[5] & 0x1F, (words[4] >> 27) & 0x1F)
    elif loc == LOC_MOUTH:
        scale1 = ((words[1] >> 26) & 3) * 8
    elif loc == LOC_HORN:
        scale1 = (words[2] >> 16) & 0x1F
    elif loc == LOC_ARMS:
        scale1 = (words[2] >> 24) & 0x1F
    elif loc == LOC_TEETH:
        scale1 = max(words[3] & 3, (words[3] >> 6) & 3) * 8
    elif loc == LOC_TAIL:
        scale1 = ((words[3] >> 22) & 3) * 8
    else:
        scale1 = 0

    w = PersonWeapon(kind=slot)
    w.qty = BODY_SOUND_BASE + BODY_SOUND_STRIDE * ((words[5] >> 13) & 7)
    selector = (words[4] >> 22) & 3
    w.mode = SPECIAL_MODE_BY_SELECTOR[selector]
    if selector == 0:
        w.range_ = 0
        w.radius1 = int(hp_scale * SPECIAL_AREA_RADIUS_SCALE)
        w.effect1, w.effect2 = dna_effect, EFF_NO
        scale1 = scale2
    elif selector == 2:
        w.range_ = sight_range(words) / PROJECTILE_RANGE_DIVISOR
        w.effect1, w.effect2 = EFF_PIERCING, dna_effect
    elif selector == 3:
        w.range_ = sight_range(words) * PSIONIC_RANGE_SCALE
        w.effect1, w.effect2 = dna_effect, EFF_NO
        scale1 = scale2
    else:
        w.range_ = body_melee_range_m()
        if loc in (LOC_FOREARM, LOC_MOUTH):
            w.effect1, w.effect2 = dna_effect, EFF_NO
            scale1 = scale2
        elif loc == LOC_HORN:
            klass = words[2] & 0xE00000
            w.effect1 = (EFF_SLASHING if klass == 0 else
                         EFF_PIERCING if klass == 0xC00000 else EFF_BLUDGEON)
            w.effect2 = dna_effect
        elif loc == LOC_ARMS:
            arms = words[2]
            w.effect1 = (EFF_SLASHING if arms < 0x20000000 else
                         EFF_PIERCING
                         if (arms & 0xE0000000) == 0xC0000000 else
                         EFF_BLUDGEON)
            w.effect2 = dna_effect
        elif loc == LOC_TORSO:
            w.effect1, w.effect2 = EFF_BLUDGEON, dna_effect
        else:
            w.effect1, w.effect2 = EFF_PIERCING, dna_effect
    w.damage1 = int((scale1 + SPECIAL_DAMAGE_BIAS) * hp_scale) + 1
    w.damage2 = int((scale2 + SPECIAL_DAMAGE_BIAS) * hp_scale) + 1
    w.modifier1 = w.modifier2 = int(hp_scale)
    return w


def body_weapon(slot, dna24=None, *, special=False, max_hp=None,
                mins_to_full_grown=0, growth_time=0):
    slot = int(slot)
    if slot not in BODY_SLOT_NAMES:
        return None
    words = _dna_words(dna24)
    hp = int(max_hp) if max_hp else max_hp_from_dna(dna24)
    if special and int(mins_to_full_grown):
        special = False
    if special:
        w = _special_weapon(weaponloc(slot), words,
                            hp / SPECIAL_HP_DIVISOR, slot)
    else:
        w = _natural_weapon(weaponloc(slot), words,
                            hp / NATURAL_HP_DIVISOR, slot)
    return _apply_growth(w, mins_to_full_grown, growth_time)


def _apply_growth(weapon, mins_to_full_grown, growth_time):
    remaining = int(mins_to_full_grown or 0)
    total = int(growth_time or 0)
    if remaining <= 0 or total <= 0:
        return weapon
    grown = (total - remaining) + 1
    if weapon.damage1:
        weapon.damage1 = (grown * weapon.damage1) // total
    if weapon.damage2:
        weapon.damage2 = (grown * weapon.damage2) // total
    return weapon


def body_weapon_slots(dna24):
    words = _dna_words(dna24)
    if words is None:
        return [SLOT_TEETH]
    out = []
    if words[3] & 0x0C:
        out.append(SLOT_HORN)
    if has_arms(words):
        out.append(SLOT_CLAWS)
    out.append(SLOT_TEETH)
    if (words[3] & 0xC00000) > 0x400000:
        out.append(SLOT_TAIL)
    return out


def signature_slot(dna24):
    loc = weapon_location(dna24)
    return slot_for_weaponloc(loc) if loc != LOC_NONE else None


def body_weapon_cycle(dna24, mins_to_full_grown=0):
    out = [(s, 0) for s in body_weapon_slots(dna24)]
    if not int(mins_to_full_grown or 0):
        sig = signature_slot(dna24)
        if sig is not None:
            out.append((sig, 1))
    return out


def body_weapons(dna24, slots=None, mins_to_full_grown=0, growth_time=0):
    if slots is None:
        slots = body_weapon_cycle(dna24, mins_to_full_grown)
    max_hp = max_hp_from_dna(dna24)
    out = {}
    for entry in slots:
        if isinstance(entry, (tuple, list)):
            slot, sub = int(entry[0]), int(entry[1])
        else:
            slot, sub = int(entry), 0
        w = body_weapon(slot, dna24, special=bool(sub), max_hp=max_hp,
                        mins_to_full_grown=mins_to_full_grown,
                        growth_time=growth_time)
        if w is not None:
            out[(slot, sub) if sub else slot] = w
    return out


class CombatResult:

    __slots__ = ("absorbed1", "absorbed2", "blocked1", "blocked2",
                 "damage1", "damage2", "critical", "killed")

    def __init__(self, absorbed1=0, absorbed2=0, blocked1=0, blocked2=0,
                 damage1=0, damage2=0, critical=0, killed=False):
        self.absorbed1 = int(absorbed1)
        self.absorbed2 = int(absorbed2)
        self.blocked1 = int(blocked1)
        self.blocked2 = int(blocked2)
        self.damage1 = int(damage1)
        self.damage2 = int(damage2)
        self.critical = int(critical)
        self.killed = bool(killed)

    @property
    def total(self):
        return self.damage1 + self.damage2

    @property
    def stopped(self):
        return (self.absorbed1 + self.absorbed2
                + self.blocked1 + self.blocked2)

    def __repr__(self):
        return ("CombatResult(dmg=%d+%d absorbed=%d+%d blocked=%d+%d crit=%d)"
                % (self.damage1, self.damage2, self.absorbed1,
                   self.absorbed2, self.blocked1, self.blocked2,
                   self.critical))


def _roll(dice, n, sides, mod=0):
    if dice is not None:
        return int(dice.roll(n, sides, mod))
    from openshores.gameplay import gear_wear as _gw
    return int(_gw._DICE.roll(n, sides, mod))


def target_attacked(worn, weapon, dice=None):
    res = CombatResult()
    if weapon is None:
        return res

    if weapon.effect1 == EFF_NO:
        return res

    a1, b1, c1, d1_ = combat_armor_effectiveness(
        worn, weapon.effect1, weapon.mode, dice)
    if weapon.effect2 != EFF_NO:
        a2, b2, c2, d2_ = combat_armor_effectiveness(
            worn, weapon.effect2, weapon.mode, dice)
    else:
        a2 = b2 = c2 = d2_ = 0.0

    if _roll(dice, 1, 100) > CRIT_ROLL_THRESHOLD:
        res.critical = 1
        m = CRIT_ARMOR_MULTIPLIER
        a1, b1, c1, d1_ = a1 * m, b1 * m, c1 * m, d1_ * m
        if weapon.effect2 != EFF_NO:
            if _roll(dice, 1, 100) > CRIT_ROLL_THRESHOLD:
                res.critical = 2
                a2, b2, c2, d2_ = a2 * m, b2 * m, c2 * m, d2_ * m

    if weapon.pierce1:
        p = weapon.pierce1 * BLOCK_SCALE
        b1, d1_ = max(0.0, b1 - p), max(0.0, d1_ - p)
    if weapon.strike1:
        s = weapon.strike1 * ABSORB_SCALE
        a1, c1 = max(0.0, a1 - s), max(0.0, c1 - s)
    if weapon.effect2 != EFF_NO:
        if weapon.pierce2:
            p = weapon.pierce2 * BLOCK_SCALE
            b2, d2_ = max(0.0, b2 - p), max(0.0, d2_ - p)
        if weapon.strike2:
            s = weapon.strike2 * ABSORB_SCALE
            a2, c2 = max(0.0, a2 - s), max(0.0, c2 - s)

    roll1 = max(0, _roll(dice, 1, weapon.damage1, weapon.modifier1)
                if weapon.damage1 > 0 else 0)
    roll2 = max(0, _roll(dice, 1, weapon.damage2, weapon.modifier2)
                if weapon.effect2 != EFF_NO and weapon.damage2 > 0 else 0)

    (res.absorbed1, res.blocked1, res.damage1) = _stage(roll1, a1, b1, c1, d1_)
    (res.absorbed2, res.blocked2, res.damage2) = _stage(roll2, a2, b2, c2, d2_)
    return res


def _stage(rolled, absorb_a, block_a, absorb_b, block_b):
    absorbed = math.ceil(rolled * block_a + absorb_a)
    if absorbed >= rolled:
        return (rolled, 0, 0)
    blocked = math.ceil(rolled * block_b + absorb_b)
    if absorbed + blocked >= rolled:
        return (absorbed, rolled - absorbed, 0)
    return (absorbed, blocked, rolled - absorbed - blocked)


def conditions_from_result(result, weapon, quality=0, existing=None,
                           attacker=0, dice=None, strain=0, dna=None):
    if result is None or weapon is None:
        return []
    incendiary = EFF_BURNING in (weapon.effect1, weapon.effect2)
    return _cx.conditions_from_hit(
        weapon.effect1, result.damage1, weapon.effect2, result.damage2,
        quality, existing=existing, incendiary=incendiary, attacker=attacker,
        dice=dice, strain=strain, dna=dna)


