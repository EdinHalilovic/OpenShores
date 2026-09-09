
from __future__ import annotations

import struct


_DEFAULT_KNIFE_CIDS = frozenset({
    116,
    151,
    152,
})
_DEFAULT_GUN_CIDS = frozenset({
    31,
    32,
    117,
    292,
    296,
    305,
})
_DEFAULT_AMMO_CIDS = frozenset({
    268,
    10,
    75,
    118,
})


def _weapon_cid_sets():
    knives = set(_DEFAULT_KNIFE_CIDS)
    guns = set(_DEFAULT_GUN_CIDS)
    ammo = set(_DEFAULT_AMMO_CIDS)
    return (knives, guns, ammo)


_WEAPON_MIN_INTEGRITY = 100

_EXPECTED_KNIFE_BODYLEN = 5 + 1 + 2 + 9
_EXPECTED_PISTOL_BODYLEN = 5 + 1 + 2 + 9 + 9 + 4
_EXPECTED_AMMO_BODYLEN = 5


_WEAPON_DEFAULTS_KNIFE = {
    "weapon_flags": 0x01,
    "cooldown_ts":  0x0000,
    "primary": {
        "sound":      0x00,
        "damage":     0x0000,
        "effect":     0x00,
        "cool_max":   0x0000,
        "range":      0x00,
        "flux":       0x0000,
    },
}
_FEET_PER_METER = 3.281


def _range_units(range_m: int) -> int:
    return int(round(int(range_m) * _FEET_PER_METER)) & 0xFFFF


def _make_gun_spec(range_m: int, damage_hp: int,
                    effect_glyph: int = 0x05,
                    *, third_mode: bool = False,
                    third_range_m: int = 0,
                    third_damage_hp: int = 0,
                    third_effect_glyph: int = 0x05,
                    third_damage_mod: int = 0):
    wflags = 0x01
    spec = {
        "weapon_flags": wflags,
        "cooldown_ts": _range_units(range_m),
        "primary": {
            "sound":    int(effect_glyph) & 0xFF,
            "damage":   int(damage_hp) & 0xFFFF,
            "effect":   0,
            "cool_max": 0,
            "range":    0,
            "flux":     0,
        },
        "ammo1_qty":     0x00,
        "ammo1_quality": 0x3D,
        "ammo2_qty":     0x00,
        "ammo2_quality": 0x3D,
    }
    if third_mode:
        spec["weapon_flags"] = 0x05
        spec["tertiary_base"] = _range_units(third_range_m)
        spec["tertiary_a"] = {
            "sound":    int(third_effect_glyph) & 0xFF,
            "damage":   int(third_damage_hp) & 0xFFFF,
            "effect":   int(third_damage_mod) & 0xFFFF,
            "cool_max": 0,
            "range":    0,
            "flux":     0,
        }
    return spec


_WEAPON_DEFAULTS_PISTOL = _make_gun_spec(range_m=50, damage_hp=50,
                                           effect_glyph=0x05)


_WEFF_PIERCING = 0x0D
_WEFF_BURNING  = 0x0C
_WEFF_SLASHING = 0x0F
_WEFF_BLUDGEON = 0x08
_WEFF_ENERGY   = 0x10


_WEAPON_SPECS_BY_CID = {
    31:  _make_gun_spec(range_m=50,  damage_hp=25, effect_glyph=_WEFF_PIERCING),
    32:  _make_gun_spec(range_m=75,  damage_hp=50, effect_glyph=_WEFF_PIERCING),
    117: _make_gun_spec(range_m=30,  damage_hp=80, effect_glyph=_WEFF_PIERCING),
    292: _make_gun_spec(range_m=75,  damage_hp=45, effect_glyph=_WEFF_PIERCING),
    296: _make_gun_spec(range_m=75,  damage_hp=50, effect_glyph=_WEFF_BURNING,
                         third_mode=True,
                         third_range_m=75, third_damage_hp=75,
                         third_effect_glyph=_WEFF_ENERGY),
    305: _make_gun_spec(range_m=50,  damage_hp=25, effect_glyph=_WEFF_BURNING,
                         third_mode=True,
                         third_range_m=50, third_damage_hp=50,
                         third_effect_glyph=_WEFF_ENERGY),
}


def _weapon_spec_for_cid(cid: int):
    return _WEAPON_SPECS_BY_CID.get(int(cid) & 0xFFFF, _WEAPON_DEFAULTS_PISTOL)


def _weapon_damage_for_cid_mode(cid: int, typeId: int,
                                 mode: int) -> int:
    typeId = int(typeId) & 0xFF
    mode = int(mode) & 0xFF
    if mode == 0:
        if typeId == 0x08:
            return 12
        return 8
    spec = _WEAPON_SPECS_BY_CID.get(int(cid) & 0xFFFF)
    if spec is None:
        return 25
    if mode == 2 and spec.get("tertiary"):
        return int(spec["tertiary"].get("damage", 0)) & 0xFFFF
    primary = spec.get("primary", {})
    return int(primary.get("damage", 0)) & 0xFFFF


def _weapon_range_for_cid_mode(cid: int, mode: int) -> float:
    if int(mode) == 0:
        return 15.0
    spec = _WEAPON_SPECS_BY_CID.get(int(cid) & 0xFFFF)
    if spec is None:
        return 50.0
    if int(mode) == 2:
        units = int(spec.get("tertiary_base", 0))
    else:
        units = int(spec.get("cooldown_ts", 0))
    if units <= 0:
        return 50.0
    return float(units) / _FEET_PER_METER


def _pack_auitemweapon_tail(spec=None):
    if spec is None:
        spec = _WEAPON_DEFAULTS_KNIFE
    wflags = int(spec.get("weapon_flags", 0x01)) & 0xFF
    cooldown = int(spec.get("cooldown_ts", 0)) & 0xFFFF
    out = bytearray()
    out.append(wflags)
    out += struct.pack(">h", cooldown)

    def _emit_sub(sub):
        we = sub.get("weapon_effect", sub.get("sound", 0))
        aux = sub.get("aux_int", sub.get("effect", 0))
        b = bytearray()
        b += struct.pack(">b", int(we) & 0xFF)
        b += struct.pack(">h", int(sub.get("damage", 0)) & 0xFFFF)
        if wflags & 0x20:
            b += struct.pack(">H", int(aux) & 0xFFFF)
        else:
            b += struct.pack(">B", int(aux) & 0xFF)
        b += struct.pack(">h", int(sub.get("cool_max", 0)) & 0xFFFF)
        b += struct.pack(">b", int(sub.get("range", 0)) & 0xFF)
        b += struct.pack(">h", int(sub.get("flux", 0)) & 0xFFFF)
        return bytes(b)

    if wflags & 0x01:
        out += _emit_sub(spec.get("primary", _WEAPON_DEFAULTS_KNIFE["primary"]))
    if wflags & 0x02:
        out += _emit_sub(spec.get("secondary", {}))
    if wflags & 0x1c:
        _tb_val = int(spec.get("tertiary_base", 0)) & 0xFFFF
        out += struct.pack(">h", _tb_val)
        if wflags & 0x04:
            out += _emit_sub(spec.get("tertiary_a", {}))
        if wflags & 0x08:
            out += _emit_sub(spec.get("tertiary_b", {}))
    return bytes(out)


def _pack_auitemweaponammo_tail(spec=None):
    if spec is None:
        spec = _WEAPON_DEFAULTS_PISTOL
    out = bytearray(_pack_auitemweapon_tail(spec))
    out.append(int(spec.get("ammo1_qty", 0)) & 0xFF)
    out.append(int(spec.get("ammo1_quality", 0)) & 0xFF)
    out.append(int(spec.get("ammo2_qty", 0)) & 0xFF)
    out.append(int(spec.get("ammo2_quality", 0)) & 0xFF)
    return bytes(out)
