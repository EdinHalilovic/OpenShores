
from __future__ import annotations

import enum
import math
import random
import threading
import warnings
from dataclasses import dataclass, field, InitVar
from typing import Optional, Callable

from openshores.core.logging import get_logger

from .persistence import Vehicle
from .vehicle_constants import (
    CRIT_ARMOR_MULTIPLIER, CRIT_ROLL_THRESHOLD,
)

logger = get_logger(__name__)


class WEAPONMODE(enum.IntEnum):
    NOT        = 0
    AREA       = 1
    CONTACT    = 2
    DETONATOR  = 3
    FUSE       = 4
    PROJECTILE = 5
    PSIONIC    = 6


WEAPONMODE_HULL = 7

MODE_ARMOR_SLOT: dict[int, int] = {
    WEAPONMODE.AREA: 0, WEAPONMODE.DETONATOR: 0, WEAPONMODE.FUSE: 0,
    WEAPONMODE.CONTACT: 1,
    WEAPONMODE.PROJECTILE: 2,
    WEAPONMODE.PSIONIC: 3,
}


class WEAPONEFFECT(enum.IntEnum):
    NO          = 0
    ACID        = 1
    SUFFOCATION = 2
    STUN        = 3
    POISON      = 4
    RADIATION   = 5
    DISEASE     = 6
    ELECTRICAL  = 7
    BLUDGEON    = 8
    FREEZING    = 9
    CRUSHING    = 10
    SONIC       = 11
    BURNING     = 12
    PIERCING    = 13
    IMPLANT     = 14
    SLASHING    = 15
    ENERGY      = 16
    KINETIC     = 17
    BLEEDING    = 18
    STARVATION  = 19
    CORROSION   = 20


class WeaponMode(enum.IntEnum):
    NONE     = 0
    CONTACT  = 1
    AREA     = 2
    CRUSH    = 3
    BLUDGEON = 4
    ELECTRIC = 5
    FREEZE   = 6
    HULL     = 7


class WeaponEffect(enum.IntEnum):
    NONE          = 0
    KINETIC       = 1
    EXPLOSIVE     = 2
    LASER         = 3
    PLASMA        = 4
    INCENDIARY    = 5
    ELECTRIC      = 6
    ACID          = 7
    POISON        = 8
    FREEZE        = 9


LEGACY_MODE_TO_MODE: dict[int, int] = {
    WeaponMode.NONE:     WEAPONMODE.NOT,
    WeaponMode.CONTACT:  WEAPONMODE.CONTACT,
    WeaponMode.AREA:     WEAPONMODE.AREA,
    WeaponMode.CRUSH:    WEAPONMODE.CONTACT,
    WeaponMode.BLUDGEON: WEAPONMODE.CONTACT,
    WeaponMode.ELECTRIC: WEAPONMODE.CONTACT,
    WeaponMode.FREEZE:   WEAPONMODE.CONTACT,
    WeaponMode.HULL:     WEAPONMODE_HULL,
}

LEGACY_MODE_TO_EFFECT: dict[int, int] = {
    WeaponMode.CRUSH:    WEAPONEFFECT.CRUSHING,
    WeaponMode.BLUDGEON: WEAPONEFFECT.BLUDGEON,
    WeaponMode.ELECTRIC: WEAPONEFFECT.ELECTRICAL,
    WeaponMode.FREEZE:   WEAPONEFFECT.FREEZING,
    WeaponMode.HULL:     WEAPONEFFECT.CRUSHING,
}

LEGACY_EFFECT_TO_EFFECT: dict[int, int] = {
    WeaponEffect.NONE:       WEAPONEFFECT.NO,
    WeaponEffect.KINETIC:    WEAPONEFFECT.KINETIC,
    WeaponEffect.EXPLOSIVE:  WEAPONEFFECT.BLUDGEON,
    WeaponEffect.LASER:      WEAPONEFFECT.ENERGY,
    WeaponEffect.PLASMA:     WEAPONEFFECT.BURNING,
    WeaponEffect.INCENDIARY: WEAPONEFFECT.BURNING,
    WeaponEffect.ELECTRIC:   WEAPONEFFECT.ELECTRICAL,
    WeaponEffect.ACID:       WEAPONEFFECT.ACID,
    WeaponEffect.POISON:     WEAPONEFFECT.POISON,
    WeaponEffect.FREEZE:     WEAPONEFFECT.FREEZING,
}

INCENDIARY_EFFECTS = frozenset({WEAPONEFFECT.BURNING})


@dataclass
class AuCombatWeapon:
    weapon_id: int = 0
    mode: int = WEAPONMODE.NOT
    field_08: int = 0
    active: int = 1
    effect1: int = WEAPONEFFECT.NO
    dice_count_1: int = 0
    dice_bonus_1: int = 0
    radius_1: int = 0
    pierce_block_1: float = 0.0
    pierce_absorb_1: float = 0.0
    effect2: int = WEAPONEFFECT.NO
    dice_count_2: int = 0
    dice_bonus_2: int = 0
    radius_2: int = 0
    pierce_block_2: float = 0.0
    pierce_absorb_2: float = 0.0

    effect: InitVar[Optional[int]] = None
    mode1: InitVar[Optional[int]] = None
    mode2: InitVar[Optional[int]] = None

    def __post_init__(self, effect, mode1, mode2) -> None:
        if effect is None and mode1 is None and mode2 is None:
            return
        warnings.warn(
            "AuCombatWeapon(effect=/mode1=/mode2=) is the legacy shape; the "
            "engine has one mode (+0x04) and two effects (+0x10/+0x28). "
            "Pass mode=/effect1=/effect2= instead.",
            DeprecationWarning, stacklevel=3,
        )
        if mode1 is not None:
            self.mode = LEGACY_MODE_TO_MODE.get(int(mode1), WEAPONMODE.NOT)
            if effect is None and int(mode1) in LEGACY_MODE_TO_EFFECT:
                self.effect1 = LEGACY_MODE_TO_EFFECT[int(mode1)]
        if effect is not None:
            self.effect1 = LEGACY_EFFECT_TO_EFFECT.get(
                int(effect), WEAPONEFFECT.NO)
        if mode2 is not None:
            self.effect2 = LEGACY_MODE_TO_EFFECT.get(
                int(mode2), WEAPONEFFECT.NO)

    @classmethod
    def from_mode(cls, mode: int,
                  effect: int = WEAPONEFFECT.NO) -> "AuCombatWeapon":
        w = cls()
        w.mode = int(mode)
        w.effect1 = int(effect)
        w.active = 1
        return w


for _legacy_attr in ("effect", "mode1", "mode2"):
    delattr(AuCombatWeapon, _legacy_attr)
del _legacy_attr


@dataclass
class AuCombatResult:
    primary_absorbed: int = 0
    secondary_absorbed: int = 0
    primary_blocked: int = 0
    secondary_blocked: int = 0
    primary_damage: int = 0
    secondary_damage: int = 0
    critical_flag: int = 0
    kill_confirmed: bool = False

    def total_damage(self) -> int:
        return self.primary_damage + self.secondary_damage


@dataclass
class DbCommodityArmor:
    absorb_area_blast: float = 0.0
    absorb_area_contact: float = 0.0
    absorb_area_ranged: float = 0.0
    absorb_area_psionic: float = 0.0
    block_area_blast: float = 0.0
    block_area_contact: float = 0.0
    block_area_ranged: float = 0.0
    block_area_psionic: float = 0.0

    def slot(self, index: int) -> tuple[float, float]:
        return (
            (self.absorb_area_blast, self.block_area_blast),
            (self.absorb_area_contact, self.block_area_contact),
            (self.absorb_area_ranged, self.block_area_ranged),
            (self.absorb_area_psionic, self.block_area_psionic),
        )[index] if 0 <= int(index) <= 3 else (0.0, 0.0)


def _uniform_armor(absorb: float, block: float,
                   psionic_absorb: float = 0.0,
                   psionic_block: float = 0.0) -> DbCommodityArmor:
    return DbCommodityArmor(
        absorb_area_blast=absorb, absorb_area_contact=absorb,
        absorb_area_ranged=absorb, absorb_area_psionic=psionic_absorb,
        block_area_blast=block, block_area_contact=block,
        block_area_ranged=block, block_area_psionic=psionic_block,
    )


_DEFAULT_ARMOR: dict[int, DbCommodityArmor] = {
    0x06: _uniform_armor(0.10, 0.10),
    0x07: _uniform_armor(0.15, 0.15),
    0x08: _uniform_armor(0.20, 0.10),
    0x09: _uniform_armor(0.10, 0.05),
    0x1C: _uniform_armor(0.50, 0.40),
    0x4D: _uniform_armor(0.20, 0.20),
    0x52: _uniform_armor(0.40, 0.30),
    0x68: _uniform_armor(0.45, 0.35),
    0x84: _uniform_armor(0.15, 0.10),
    0x85: _uniform_armor(0.60, 0.50),
    0xE7: _uniform_armor(0.25, 0.15),
}


_armor_lock = threading.Lock()


def set_db_commodity_armor(commodity_id: int, profile: DbCommodityArmor) -> None:
    with _armor_lock:
        _DEFAULT_ARMOR[int(commodity_id)] = profile


def get_db_commodity_armor(commodity_id: int) -> DbCommodityArmor:
    with _armor_lock:
        return _DEFAULT_ARMOR.get(int(commodity_id), DbCommodityArmor())


def reset_armor_registry() -> None:
    pass


def combat_armor_effectiveness(
    target: Vehicle, weapon_effect: int, weapon_mode: int,
    hit_point=None, exit_point=None,
) -> tuple[float, float, float, float]:
    armor = get_db_commodity_armor(target.cid)

    slot = MODE_ARMOR_SLOT.get(int(weapon_mode))
    if slot is None:
        absorb_area, block_area = 0.0, 0.0
    else:
        absorb_area, block_area = armor.slot(slot)

    quality_mult = max(0.0, min(1.0, target.qual / 255.0))
    block_area *= quality_mult

    return (absorb_area, 0.0, block_area, 0.0)


DiceRoller = Callable[[int, int, int], int]


def default_dice_roller(num_dice: int, sides: int, bonus: int) -> int:
    total = bonus
    for _ in range(num_dice):
        total += random.randint(1, max(1, sides))
    return total


_global_dice_roller: DiceRoller = default_dice_roller


def set_dice_roller(roller: DiceRoller) -> None:
    global _global_dice_roller
    _global_dice_roller = roller


def reset_dice_roller() -> None:
    global _global_dice_roller
    _global_dice_roller = default_dice_roller


def _roll(num_dice: int, sides: int, bonus: int = 0) -> int:
    return _global_dice_roller(num_dice, sides, bonus)


def target_attacked(
    target: Vehicle,
    weapon: AuCombatWeapon,
    hit_point=None,
    exit_point=None,
    dice_roller: Optional[DiceRoller] = None,
) -> AuCombatResult:
    result = AuCombatResult()

    if weapon.effect1 == WEAPONEFFECT.NO:
        return result

    roll = dice_roller if dice_roller is not None else _global_dice_roller

    abs_area_P, abs_pt_P, blk_area_P, blk_pt_P = combat_armor_effectiveness(
        target, weapon.effect1, weapon.mode, hit_point, exit_point,
    )
    if weapon.effect2 != WEAPONEFFECT.NO:
        abs_area_S, abs_pt_S, blk_area_S, blk_pt_S = combat_armor_effectiveness(
            target, weapon.effect2, weapon.mode, hit_point, exit_point,
        )
    else:
        abs_area_S = abs_pt_S = blk_area_S = blk_pt_S = 0.0

    r1 = roll(1, 100, 0)
    if r1 > CRIT_ROLL_THRESHOLD:
        result.critical_flag = 1
        abs_area_P *= CRIT_ARMOR_MULTIPLIER
        abs_pt_P *= CRIT_ARMOR_MULTIPLIER
        blk_area_P *= CRIT_ARMOR_MULTIPLIER
        blk_pt_P *= CRIT_ARMOR_MULTIPLIER
        if weapon.effect2 != WEAPONEFFECT.NO:
            r2 = roll(1, 100, 0)
            if r2 > CRIT_ROLL_THRESHOLD:
                result.critical_flag = 2
                abs_area_S *= CRIT_ARMOR_MULTIPLIER
                abs_pt_S *= CRIT_ARMOR_MULTIPLIER
                blk_area_S *= CRIT_ARMOR_MULTIPLIER
                blk_pt_S *= CRIT_ARMOR_MULTIPLIER

    if weapon.pierce_block_1 > 0:
        blk_area_P = max(0.0, blk_area_P - weapon.pierce_block_1)
        blk_pt_P = max(0.0, blk_pt_P - weapon.pierce_block_1)
    if weapon.pierce_absorb_1 > 0:
        abs_area_P = max(0.0, abs_area_P - weapon.pierce_absorb_1)
        abs_pt_P = max(0.0, abs_pt_P - weapon.pierce_absorb_1)
    if weapon.effect2 != WEAPONEFFECT.NO:
        if weapon.pierce_block_2 > 0:
            blk_area_S = max(0.0, blk_area_S - weapon.pierce_block_2)
            blk_pt_S = max(0.0, blk_pt_S - weapon.pierce_block_2)
        if weapon.pierce_absorb_2 > 0:
            abs_area_S = max(0.0, abs_area_S - weapon.pierce_absorb_2)
            abs_pt_S = max(0.0, abs_pt_S - weapon.pierce_absorb_2)

    d1 = max(0, roll(1, weapon.dice_count_1, weapon.dice_bonus_1)
              if weapon.dice_count_1 > 0 else 0)
    d2 = (max(0, roll(1, weapon.dice_count_2, weapon.dice_bonus_2))
          if weapon.effect2 != WEAPONEFFECT.NO and weapon.dice_count_2 > 0
          else 0)

    absorbed = math.ceil(d1 * blk_pt_P + abs_pt_P)
    if absorbed >= d1:
        result.primary_absorbed = d1
        result.primary_blocked = 0
        result.primary_damage = 0
    else:
        blocked = math.ceil(d1 * blk_area_P + abs_area_P)
        if absorbed + blocked >= d1:
            result.primary_absorbed = absorbed
            result.primary_blocked = d1 - absorbed
            result.primary_damage = 0
        else:
            result.primary_absorbed = absorbed
            result.primary_blocked = blocked
            result.primary_damage = d1 - absorbed - blocked

    absorbed_s = math.ceil(d2 * blk_pt_S + abs_pt_S)
    if absorbed_s >= d2:
        result.secondary_absorbed = d2
        result.secondary_blocked = 0
        result.secondary_damage = 0
    else:
        blocked_s = math.ceil(d2 * blk_area_S + abs_area_S)
        if absorbed_s + blocked_s >= d2:
            result.secondary_absorbed = absorbed_s
            result.secondary_blocked = d2 - absorbed_s
            result.secondary_damage = 0
        else:
            result.secondary_absorbed = absorbed_s
            result.secondary_blocked = blocked_s
            result.secondary_damage = d2 - absorbed_s - blocked_s

    return result


_HP_ELIGIBLE_EFFECTS_MASK = 0x13ffa2

_VEH_LAST_DAMAGE_MS: dict[int, int] = {}


def get_last_damage_ms(vehicle_id: int) -> int:
    return int(_VEH_LAST_DAMAGE_MS.get(int(vehicle_id) & 0xFFFFFFFF, 0))


def clear_last_damage_ms(vehicle_id: int) -> None:
    _VEH_LAST_DAMAGE_MS.pop(int(vehicle_id) & 0xFFFFFFFF, None)


COND_BURNING   = 0x01
COND_PARALYZED = 0x02
COND_ACID      = 0x04


def _get_cond_flags(target: Vehicle) -> int:
    return int(getattr(target, "_condition_flags", 0)) & 0xFF


def _set_cond_flag(target: Vehicle, bit: int) -> None:
    flags = _get_cond_flags(target) | (int(bit) & 0xFF)
    setattr(target, "_condition_flags", flags)


def has_condition(target: Vehicle, bit: int) -> bool:
    return bool(_get_cond_flags(target) & (int(bit) & 0xFF))


def clear_conditions(target: Vehicle) -> None:
    setattr(target, "_condition_flags", 0)


_VEH_MASS_KG: dict[int, float] = {
    0x06: 1200.0, 0x07: 800.0, 0x08: 2500.0, 0x09: 600.0,
    0x1C: 18000.0, 0x68: 14000.0, 0x52: 9000.0, 0x85: 25000.0,
    0x4D: 3500.0, 0x84: 2000.0, 0xE7: 8000.0,
}
_VEH_MASS_DEFAULT = 1500.0

_VEH_MAX_HP: dict[int, int] = {
    0x06: 32767, 0x07: 32767, 0x08: 32767, 0x09: 32767,
    0x1C: 32767, 0x68: 32767, 0x52: 32767, 0x85: 32767,
    0x4D: 32767, 0x84: 32767, 0xE7: 32767,
}
_VEH_MAX_HP_DEFAULT = 32767

LOW_HP_BURNING_FRACTION: float = 0.25

INCENDIARY_ROLL_PCT: int = 10

KNOCKBACK_SCALE: float = 0.5


def _knockback(target: Vehicle, hit_point, normal, dmg_total: float,
               *, mass: float) -> None:
    if hit_point is None or normal is None or mass <= 0 or dmg_total <= 0:
        return
    hx, hy, hz = float(hit_point[0]), float(hit_point[1]), float(hit_point[2])
    nx, ny, nz = float(normal[0]), float(normal[1]), float(normal[2])
    dx, dy, dz = hx - nx, hy - ny, hz - nz
    mag2 = dx*dx + dy*dy + dz*dz
    if mag2 <= 1e-9:
        return
    inv = (mag2 ** -0.5) * (KNOCKBACK_SCALE / mass) * dmg_total
    target.vecX = float(target.vecX) - dx * inv
    target.vecY = float(target.vecY) - dy * inv
    target.vecZ = float(target.vecZ) - dz * inv


def combat_apply_damage(
    target: Vehicle,
    attacker_id: int,
    weapon: AuCombatWeapon,
    hit_point=None,
    normal=None,
    *,
    now_ms: Optional[int] = None,
    dice_roller: Optional[DiceRoller] = None,
) -> AuCombatResult:
    from .weapons import record_damage

    result = target_attacked(target, weapon, hit_point=hit_point,
                             exit_point=normal, dice_roller=dice_roller)
    if result.primary_damage == 0 and result.secondary_damage == 0:
        return result

    if now_ms is None:
        now_ms = _now_ms_combat()

    p_eff = int(weapon.effect1) & 0x1F
    s_eff = int(weapon.effect2) & 0x1F

    p_eligible = bool((_HP_ELIGIBLE_EFFECTS_MASK >> p_eff) & 1) if p_eff < 21 else False
    s_eligible = bool((_HP_ELIGIBLE_EFFECTS_MASK >> s_eff) & 1) if s_eff < 21 else False

    _strict_effect_mask = False
    if _strict_effect_mask:
        eff_p = result.primary_damage if p_eligible else 0
        eff_s = result.secondary_damage if s_eligible else 0
    else:
        eff_p = result.primary_damage
        eff_s = result.secondary_damage

    total_to_apply = eff_p + eff_s
    _staged = AuCombatResult(
        primary_damage=eff_p, secondary_damage=eff_s,
        primary_absorbed=result.primary_absorbed,
        secondary_absorbed=result.secondary_absorbed,
        primary_blocked=result.primary_blocked,
        secondary_blocked=result.secondary_blocked,
        critical_flag=result.critical_flag,
        kill_confirmed=result.kill_confirmed,
    )
    killed = record_damage(target, attacker_id=attacker_id, weapon=weapon,
                           result=_staged, now_ms=now_ms)
    if killed:
        result.kill_confirmed = True

    _VEH_LAST_DAMAGE_MS[int(target.id) & 0xFFFFFFFF] = int(now_ms)

    weapon_cid = int(weapon.weapon_id) & 0xFFFF

    if not killed and weapon_cid != 0xFFFE2:
        max_hp = _VEH_MAX_HP.get(int(target.cid) & 0xFFFF, _VEH_MAX_HP_DEFAULT)
        if max_hp > 0 and (target.hp / float(max_hp)) <= LOW_HP_BURNING_FRACTION:
            _set_cond_flag(target, COND_BURNING)

    if (not killed
            and (p_eff == WEAPONEFFECT.ACID and eff_p > 0
                 or s_eff == WEAPONEFFECT.ACID and eff_s > 0)
            and weapon_cid != 0xFFFE3
            and not has_condition(target, COND_ACID)):
        _set_cond_flag(target, COND_ACID)

    if (not killed and (weapon.effect1 in INCENDIARY_EFFECTS
                        or weapon.effect2 in INCENDIARY_EFFECTS)):
        roll = dice_roller if dice_roller is not None else _global_dice_roller
        if roll(1, 100, 0) <= INCENDIARY_ROLL_PCT:
            _set_cond_flag(target, COND_BURNING)

    if (not killed
            and (p_eff == WEAPONEFFECT.STUN and eff_p > 0
                 or s_eff == WEAPONEFFECT.STUN and eff_s > 0)
            and not has_condition(target, COND_PARALYZED)):
        _set_cond_flag(target, COND_PARALYZED)

    if weapon_cid != 0x57 and not (0x95 <= weapon_cid <= 0x96):
        mass = _VEH_MASS_KG.get(int(target.cid) & 0xFFFF, _VEH_MASS_DEFAULT)
        _knockback(target, hit_point, normal,
                   float(eff_p + eff_s), mass=mass)

        target.switches = int(target.switches) | 0x04

    return result


def _now_ms_combat() -> int:
    import time as _t
    return int(_t.time() * 1000)


def _selftest() -> None:
    from .vehicle_constants import VehicleType


    target = Vehicle(id=1, cid=VehicleType.TANK, hp=100, qual=255)
    no_dmg = target_attacked(target, AuCombatWeapon(mode=WEAPONMODE.PROJECTILE))
    assert no_dmg.primary_damage == 0
    assert no_dmg.secondary_damage == 0
    assert no_dmg.critical_flag == 0

    assert len(_DEFAULT_ARMOR) == 11, (
        f"Expected 11 shipped armour defaults, found {len(_DEFAULT_ARMOR)}")
    for _cid, _prof in _DEFAULT_ARMOR.items():
        assert (_prof.absorb_area_blast == _prof.absorb_area_contact
                == _prof.absorb_area_ranged), (
            f"0x{_cid:x}: absorb not uniform across blast/contact/ranged")
        assert (_prof.block_area_blast == _prof.block_area_contact
                == _prof.block_area_ranged), (
            f"0x{_cid:x}: block not uniform across blast/contact/ranged")
    logger.debug("Blast-hole check: %d shipped profiles, all uniform across blast/contact/ranged", len(_DEFAULT_ARMOR))

    def no_crit_max(n, sides, bonus):
        if sides == 100:
            return 50
        return n * sides + bonus

    w_gun = AuCombatWeapon(
        weapon_id=1, mode=WEAPONMODE.PROJECTILE,
        effect1=WEAPONEFFECT.KINETIC, dice_count_1=10, dice_bonus_1=0,
    )
    res = target_attacked(target, w_gun, dice_roller=no_crit_max)
    logger.debug('Tank vs Projectile d10: absorbed=%d blocked=%d damage=%d crit=%d',
                 res.primary_absorbed, res.primary_blocked, res.primary_damage,
                 res.critical_flag)
    assert res.primary_absorbed == 0
    assert res.primary_blocked == 5
    assert res.primary_damage == 5
    assert res.critical_flag == 0

    def crit_max(n, sides, bonus):
        if sides == 100:
            return 99
        return n * sides + bonus
    res = target_attacked(target, w_gun, dice_roller=crit_max)
    logger.debug('Tank vs Projectile d10 (CRIT): absorbed=%d blocked=%d '
                 'damage=%d crit=%d', res.primary_absorbed, res.primary_blocked,
                 res.primary_damage, res.critical_flag)
    assert res.critical_flag == 1
    assert res.primary_damage == 7

    w_dual = AuCombatWeapon(
        weapon_id=2, mode=WEAPONMODE.PROJECTILE,
        effect1=WEAPONEFFECT.KINETIC, dice_count_1=10, dice_bonus_1=0,
        effect2=WEAPONEFFECT.ELECTRICAL, dice_count_2=5, dice_bonus_2=0,
    )
    res = target_attacked(target, w_dual, dice_roller=no_crit_max)
    logger.debug('Tank vs Dual-effect: P_dmg=%d S_dmg=%d',
                 res.primary_damage, res.secondary_damage)
    assert res.primary_damage == 5
    assert res.secondary_damage == 2

    w_pierce = AuCombatWeapon(
        weapon_id=3, mode=WEAPONMODE.PROJECTILE,
        effect1=WEAPONEFFECT.KINETIC, dice_count_1=10, dice_bonus_1=0,
        pierce_block_1=0.3, pierce_absorb_1=0.3,
    )
    res = target_attacked(target, w_pierce, dice_roller=no_crit_max)
    logger.debug('Tank vs Pierce: blocked=%d damage=%d',
                 res.primary_blocked, res.primary_damage)
    assert res.primary_damage == 8

    no_armor = Vehicle(id=2, cid=0xFE, hp=100, qual=255)
    res = target_attacked(no_armor, w_gun, dice_roller=no_crit_max)
    assert res.primary_damage == 10
    assert res.primary_absorbed == 0
    assert res.primary_blocked == 0

    w_blast = AuCombatWeapon(
        weapon_id=4, mode=WEAPONMODE.AREA,
        effect1=WEAPONEFFECT.BLUDGEON, dice_count_1=10, dice_bonus_1=0,
    )
    res = target_attacked(target, w_blast, dice_roller=no_crit_max)
    logger.debug('Tank vs Area d10: blocked=%d damage=%d',
                 res.primary_blocked, res.primary_damage)
    assert res.primary_blocked == 5
    assert res.primary_damage == 5

    set_db_commodity_armor(0xFD, DbCommodityArmor(
        absorb_area_ranged=0.50, block_area_ranged=0.40,
    ))
    lopsided = Vehicle(id=3, cid=0xFD, hp=100, qual=255)
    res_area = target_attacked(lopsided, w_blast, dice_roller=no_crit_max)
    res_proj = target_attacked(lopsided, w_gun, dice_roller=no_crit_max)
    logger.debug('Lopsided(blast=0,ranged=.50/.40): AREA dmg=%d PROJECTILE dmg=%d',
                 res_area.primary_damage, res_proj.primary_damage)
    assert res_area.primary_damage == 10, "AREA must draw the empty blast slot"
    assert res_proj.primary_damage == 5, "PROJECTILE must draw the ranged slot"
    set_db_commodity_armor(0xFD, DbCommodityArmor())


    w7 = AuCombatWeapon.from_mode(WEAPONMODE_HULL, WEAPONEFFECT.CRUSHING)
    assert w7.mode == WEAPONMODE_HULL
    assert w7.effect1 == WEAPONEFFECT.CRUSHING
    assert w7.active == 1
    assert w7.dice_count_1 == 0
    assert target_attacked(
        target, AuCombatWeapon.from_mode(WEAPONMODE_HULL),
        dice_roller=no_crit_max).primary_damage == 0
    w7.dice_count_1 = 10
    res = target_attacked(target, w7, dice_roller=no_crit_max)
    logger.debug('Tank vs Hull(7) d10: blocked=%d damage=%d',
                 res.primary_blocked, res.primary_damage)
    assert res.primary_blocked == 0
    assert res.primary_damage == 10

    set_db_commodity_armor(0xFE, DbCommodityArmor(
        absorb_area_ranged=1.0, block_area_ranged=0.0,
    ))
    res = target_attacked(no_armor, w_gun, dice_roller=no_crit_max)
    logger.debug('Custom-armor unknown: blocked=%d damage=%d',
                 res.primary_blocked, res.primary_damage)
    assert res.primary_blocked == 1
    assert res.primary_damage == 9
    set_db_commodity_armor(0xFE, DbCommodityArmor())

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        w_legacy = AuCombatWeapon(
            weapon_id=5, effect=WeaponEffect.LASER,
            mode1=WeaponMode.CONTACT, dice_count_1=10, dice_bonus_1=0,
        )
        assert w_legacy.mode == WEAPONMODE.CONTACT
        assert w_legacy.effect1 == WEAPONEFFECT.ENERGY
        assert w_legacy.effect2 == WEAPONEFFECT.NO
        res = target_attacked(target, w_legacy, dice_roller=no_crit_max)
        assert res.primary_damage == 5, res
        w_leg2 = AuCombatWeapon(mode1=WeaponMode.FREEZE, dice_count_1=4)
        assert w_leg2.mode == WEAPONMODE.CONTACT
        assert w_leg2.effect1 == WEAPONEFFECT.FREEZING
        for gone in ("mode1", "mode2", "effect"):
            assert not hasattr(w_legacy, gone), f"{gone} should not survive"

    from .weapons import _WEAPON_BY_AMMO
    for _cid, _w in _WEAPON_BY_AMMO.items():
        assert _w.effect1 != WEAPONEFFECT.ACID, (
            f"Ammo 0x{_cid:x} is Acid; nothing shipped should be")
        victim = Vehicle(id=100 + _cid, cid=VehicleType.TANK, hp=10_000,
                         qual=255)
        combat_apply_damage(victim, attacker_id=0xABCD, weapon=_w,
                            hit_point=(1.0, 0.0, 0.0), normal=(0.0, 0.0, 0.0),
                            now_ms=1_000, dice_roller=no_crit_max)
        assert not has_condition(victim, COND_ACID), (
            f"Ammo 0x{_cid:x} inflicted acid.")
    logger.debug("Acid check: %d shipped weapons, none inflict acid",
                 len(_WEAPON_BY_AMMO))

    w_acid = AuCombatWeapon(
        weapon_id=6, mode=WEAPONMODE.PROJECTILE,
        effect1=WEAPONEFFECT.ACID, dice_count_1=50, dice_bonus_1=0,
    )
    acid_victim = Vehicle(id=99, cid=VehicleType.TANK, hp=10_000, qual=255)
    combat_apply_damage(acid_victim, attacker_id=0xABCD, weapon=w_acid,
                        hit_point=(1.0, 0.0, 0.0), normal=(0.0, 0.0, 0.0),
                        now_ms=1_000, dice_roller=no_crit_max)
    assert has_condition(acid_victim, COND_ACID), "Acid must still inflict acid"
    logger.debug("Acid check: an Acid weapon still inflicts COND_ACID")

    for _eff in (WEAPONEFFECT.KINETIC, WEAPONEFFECT.ENERGY,
                 WEAPONEFFECT.BURNING, WEAPONEFFECT.BLUDGEON,
                 WEAPONEFFECT.CRUSHING):
        assert (_HP_ELIGIBLE_EFFECTS_MASK >> int(_eff)) & 1, _eff
    for _eff in (WEAPONEFFECT.NO, WEAPONEFFECT.STUN, WEAPONEFFECT.POISON,
                 WEAPONEFFECT.DISEASE, WEAPONEFFECT.SUFFOCATION):
        assert not (_HP_ELIGIBLE_EFFECTS_MASK >> int(_eff)) & 1, _eff


if __name__ == "__main__":
    logger.info("vehicles.combat self-test starting")
    _selftest()
    logger.info("vehicles.combat self-test passed")
