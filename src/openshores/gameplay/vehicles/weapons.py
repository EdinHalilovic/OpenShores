
from __future__ import annotations

import math
import time
import struct

import asyncpg
from dataclasses import dataclass, field
from typing import Optional

from openshores.core.logging import get_logger

from .persistence import Vehicle
from .spawn import get_active_vehicle, despawn_vehicle
from .input import get_runtime
from .combat import (
    AuCombatWeapon, AuCombatResult, WEAPONMODE, WEAPONEFFECT,
    target_attacked, DiceRoller,
)
from .ordnance import (
    Ordnance, TurretLoadout, get_loadout, can_fire as ordnance_can_fire,
    fired as ordnance_fired,
)
from .terrain import get_terrain_query, NearbyAtom, Vec3
from .collision import is_obstacle as _is_obstacle

logger = get_logger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


MAX_GUN_RANGE_M: float = 500.0

DAMAGE_HISTORY_MAX: int = 16


@dataclass
class DamageRecord:
    attacker_id: int
    weapon_id: int
    damage: int
    timestamp_ms: int = 0


def record_damage(
    target: Vehicle,
    attacker_id: int,
    weapon: AuCombatWeapon,
    result: AuCombatResult,
    now_ms: Optional[int] = None,
) -> bool:
    if now_ms is None:
        now_ms = _now_ms()

    total = result.total_damage()
    if total <= 0:
        return False

    was_alive = target.hp > 0
    target.hp = max(0, target.hp - total)
    killed = was_alive and target.hp == 0
    if killed:
        result.kill_confirmed = True

    history = list(_unpack_damage_history(target.damageHistory or b""))
    history.append(DamageRecord(
        attacker_id=int(attacker_id) & 0xFFFFFFFF,
        weapon_id=int(weapon.weapon_id) & 0xFFFFFFFF,
        damage=total,
        timestamp_ms=now_ms,
    ))
    if len(history) > DAMAGE_HISTORY_MAX:
        history = history[-DAMAGE_HISTORY_MAX:]
    target.damageHistory = _pack_damage_history(history)

    return killed


def _pack_damage_history(records: list[DamageRecord]) -> bytes:
    buf = struct.pack(">I", len(records))
    for r in records:
        buf += struct.pack(">IIiq",
            r.attacker_id & 0xFFFFFFFF, r.weapon_id & 0xFFFFFFFF,
            r.damage, r.timestamp_ms,
        )
    return buf


def _unpack_damage_history(buf: bytes) -> list[DamageRecord]:
    if not buf or len(buf) < 4:
        return []
    (count,) = struct.unpack_from(">I", buf, 0)
    out = []
    off = 4
    REC = 20
    for _ in range(count):
        if off + REC > len(buf):
            break
        attacker, weapon, dmg, ts = struct.unpack_from(">IIiq", buf, off)
        off += REC
        out.append(DamageRecord(attacker, weapon, dmg, ts))
    return out


def get_killer_id(target: Vehicle) -> int:
    history = _unpack_damage_history(target.damageHistory or b"")
    if not history:
        return 0
    cum: dict[int, int] = {}
    order: list[int] = []
    for r in history:
        if r.attacker_id not in cum:
            order.append(r.attacker_id)
            cum[r.attacker_id] = 0
        cum[r.attacker_id] += int(r.damage)
    best_aid = 0
    best_dmg = 0
    for aid in order:
        if cum[aid] > best_dmg:
            best_dmg = cum[aid]
            best_aid = aid
    return best_aid


def get_last_weapon_used_by(target: Vehicle, attacker_id: int) -> tuple[int, int]:
    history = _unpack_damage_history(target.damageHistory or b"")
    last = None
    for r in history:
        if r.attacker_id == int(attacker_id) & 0xFFFFFFFF:
            last = r
    if last is None:
        return (0, 0)
    return (int(last.weapon_id) & 0xFFFF, 0)


def _dist(a: Vec3, b: Vec3) -> float:
    dx = a[0] - b[0]; dy = a[1] - b[1]; dz = a[2] - b[2]
    return math.sqrt(dx*dx + dy*dy + dz*dz)


def _find_target(shooter: Vehicle, max_range_m: float) -> Optional[NearbyAtom]:
    q = get_terrain_query()
    pos = (shooter.locX, shooter.locY, shooter.locZ)
    best: Optional[NearbyAtom] = None
    best_d2: float = max_range_m * max_range_m
    for atom in q.iter_obstacles_near(shooter.idp, pos, max_range_m):
        if atom.atom_id == shooter.id:
            continue
        if not _is_obstacle(shooter, atom):
            continue
        dx = atom.world_pos[0] - pos[0]
        dy = atom.world_pos[1] - pos[1]
        dz = atom.world_pos[2] - pos[2]
        d2 = dx*dx + dy*dy + dz*dz
        if d2 < best_d2:
            best_d2 = d2
            best = atom
    return best


_WEAPON_BY_AMMO: dict[int, AuCombatWeapon] = {
    0x43:  AuCombatWeapon(weapon_id=0x43,  mode=WEAPONMODE.PROJECTILE,
                          effect1=WEAPONEFFECT.ENERGY,
                          dice_count_1=10, dice_bonus_1=5),
    0x129: AuCombatWeapon(weapon_id=0x129, mode=WEAPONMODE.PROJECTILE,
                          effect1=WEAPONEFFECT.BURNING,
                          dice_count_1=15, dice_bonus_1=5),
    0x38:  AuCombatWeapon(weapon_id=0x38,  mode=WEAPONMODE.PROJECTILE,
                          effect1=WEAPONEFFECT.KINETIC,
                          dice_count_1=20, dice_bonus_1=10,
                          pierce_block_1=0.2, pierce_absorb_1=0.2),
    0x44:  AuCombatWeapon(weapon_id=0x44,  mode=WEAPONMODE.PROJECTILE,
                          effect1=WEAPONEFFECT.KINETIC,
                          dice_count_1=15, dice_bonus_1=5),
    0x0B:  AuCombatWeapon(weapon_id=0x0B,  mode=WEAPONMODE.PROJECTILE,
                          effect1=WEAPONEFFECT.KINETIC,
                          dice_count_1=4, dice_bonus_1=1),
    0x37:  AuCombatWeapon(weapon_id=0x37,  mode=WEAPONMODE.AREA,
                          effect1=WEAPONEFFECT.BLUDGEON,
                          dice_count_1=25, dice_bonus_1=10,
                          effect2=WEAPONEFFECT.BURNING, dice_count_2=0),
    0x12F: AuCombatWeapon(weapon_id=0x12F, mode=WEAPONMODE.AREA,
                          effect1=WEAPONEFFECT.BLUDGEON,
                          dice_count_1=30, dice_bonus_1=15,
                          effect2=WEAPONEFFECT.BURNING, dice_count_2=0),
}


def set_weapon_for_ammo(ammo_commodity_id: int, weapon: AuCombatWeapon) -> None:
    _WEAPON_BY_AMMO[int(ammo_commodity_id)] = weapon


def get_weapon_for_ammo(ammo_commodity_id: int) -> Optional[AuCombatWeapon]:
    return _WEAPON_BY_AMMO.get(int(ammo_commodity_id))


@dataclass
class FireResult:
    fired: bool = False
    target_id: int = 0
    hit: bool = False
    damage_result: Optional[AuCombatResult] = None
    killed: bool = False
    reason: str = ""


async def fire_gun(
    shooter: Vehicle,
    person_id: int = 0,
    turret_idx: Optional[int] = None,
    dice_roller: Optional[DiceRoller] = None,
    now_ms: Optional[int] = None,
    *,
    conn: asyncpg.Connection,
) -> FireResult:
    result = FireResult()
    rt = get_runtime(shooter.id)
    if turret_idx is None:
        turret_idx = rt.active_turret

    lo = get_loadout(shooter.id)
    slot = lo.get(turret_idx)

    if now_ms is None:
        now_ms = _now_ms()

    if not ordnance_can_fire(slot, now_ms=now_ms):
        result.reason = "ordnance.can_fire returned False"
        return result

    weapon = get_weapon_for_ammo(slot.ammo_commodity_id)
    if weapon is None:
        result.reason = f"no weapon profile for ammo 0x{slot.ammo_commodity_id:x}"
        return result

    target_atom = _find_target(shooter, MAX_GUN_RANGE_M)
    if target_atom is None:
        result.fired = True
        result.reason = "no target in range"
        ordnance_fired(slot, now_ms=now_ms)
        return result

    result.fired = True
    result.target_id = target_atom.atom_id

    target_v = get_active_vehicle(target_atom.atom_id)
    if target_v is None:
        ordnance_fired(slot, now_ms=now_ms)
        result.hit = True
        result.reason = "hit non-vehicle atom (Phase 5 stub)"
        return result

    dmg = target_attacked(target_v, weapon,
                          hit_point=target_atom.world_pos,
                          dice_roller=dice_roller)
    killed = record_damage(target_v, attacker_id=shooter.id, weapon=weapon,
                           result=dmg, now_ms=now_ms)
    ordnance_fired(slot, now_ms=now_ms)
    result.hit = True
    result.damage_result = dmg
    result.killed = killed

    if killed:
        await despawn_vehicle(target_atom.atom_id, conn=conn)

    return result


def fire_weapon(
    shooter: Vehicle,
    person_id: int = 0,
    turret_idx: Optional[int] = None,
    dice_roller: Optional[DiceRoller] = None,
    now_ms: Optional[int] = None,
) -> FireResult:
    from .missile import spawn_missile
    result = FireResult()
    rt = get_runtime(shooter.id)
    if turret_idx is None:
        turret_idx = rt.active_turret
    lo = get_loadout(shooter.id)
    slot = lo.get(turret_idx)
    if now_ms is None:
        now_ms = _now_ms()
    if not ordnance_can_fire(slot, now_ms=now_ms):
        result.reason = "ordnance.can_fire returned False"
        return result
    weapon = get_weapon_for_ammo(slot.ammo_commodity_id)
    if weapon is None:
        result.reason = f"no weapon profile for ammo 0x{slot.ammo_commodity_id:x}"
        return result

    target_atom = _find_target(shooter, MAX_GUN_RANGE_M)
    target_id = target_atom.atom_id if target_atom else 0
    target_pos = target_atom.world_pos if target_atom else None

    spawn_missile(
        launcher=shooter,
        ammo_commodity_id=slot.ammo_commodity_id,
        mode=weapon.mode,
        target_id=target_id,
        target_pos=target_pos,
        quality=slot.quality,
        now_ms=now_ms,
    )
    ordnance_fired(slot, now_ms=now_ms)
    result.fired = True
    result.target_id = target_id
    return result


def _selftest() -> None:
    raise NotImplementedError(
        "Retired")


if __name__ == "__main__":
    logger.info("vehicles.weapons self-test starting")
    _selftest()
    logger.info("vehicles.weapons self-test passed")
