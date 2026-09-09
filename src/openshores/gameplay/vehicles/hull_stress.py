
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import asyncpg
from typing import Optional

from openshores.core.logging import get_logger

from .persistence import Vehicle
from .spawn import get_active_vehicle, despawn_vehicle
from .input import get_runtime
from .vehicle_constants import (
    HULL_STRESS_LOWER, HULL_STRESS_UPPER,
    HULL_STRESS_TOLERANCE, ATMO_DAMAGE_AIR_DENSITY,
    VehicleType,
)
from .terrain import get_terrain_query
from .combat import (
    AuCombatWeapon, WEAPONMODE, WEAPONEFFECT, WEAPONMODE_HULL,
    target_attacked, _roll,
)
from .weapons import record_damage


logger = get_logger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


def hull_stress(v: Vehicle) -> float:
    tolerance = HULL_STRESS_TOLERANCE.get(v.cid, 0.0)
    if tolerance == 0.0:
        return 0.0
    speed_y = abs(v.vecY)
    return speed_y / tolerance


@dataclass
class HullStressResult:
    stress_ratio: float = 0.0
    took_stress_damage: bool = False
    stress_damage: int = 0
    disintegrated: bool = False
    took_atmosphere_damage: bool = False
    atmosphere_damage: int = 0
    killed: bool = False


async def test_hull_stress(
    vehicle_id: int,
    *,
    conn: asyncpg.Connection,
    now_ms: Optional[int] = None,
    parent_flags: int = 0,
) -> HullStressResult:
    result = HullStressResult()
    v = get_active_vehicle(vehicle_id)
    if v is None:
        return result

    if now_ms is None:
        now_ms = _now_ms()

    hs = hull_stress(v)
    result.stress_ratio = hs

    if hs > HULL_STRESS_UPPER:
        result.disintegrated = True
        result.killed = True
        await despawn_vehicle(vehicle_id, conn=conn)
        return result

    if hs > HULL_STRESS_LOWER:
        max_hp = v.hp + 1
        max_for_damage = max(max_hp, 50)
        dmg_dice = max_for_damage // 5 + 1
        w = AuCombatWeapon.from_mode(WEAPONMODE_HULL, WEAPONEFFECT.CRUSHING)
        w.dice_count_1 = dmg_dice
        w.dice_bonus_1 = 0
        w.weapon_id = 0x07
        r = target_attacked(v, w)
        killed = record_damage(v, attacker_id=v.id, weapon=w,
                               result=r, now_ms=now_ms)
        result.took_stress_damage = True
        result.stress_damage = r.total_damage()
        result.killed = killed
        if killed:
            await despawn_vehicle(vehicle_id, conn=conn)
            return result

    if v.cid == VehicleType.BOAT:
        return result
    if (parent_flags & 0x240) == 0x240:
        return result

    q = get_terrain_query()
    if not q.is_atmosphere(v.idp):
        return result

    air_density = q.air_density_at(v.idp, (v.locX, v.locY, v.locZ))
    if air_density > ATMO_DAMAGE_AIR_DENSITY:
        max_for_damage = max(v.hp + 1, 50)
        dmg = max_for_damage // 10
        if dmg > 0:
            w = AuCombatWeapon.from_mode(WEAPONMODE_HULL, WEAPONEFFECT.CRUSHING)
            w.dice_count_1 = dmg
            w.dice_bonus_1 = 0
            w.weapon_id = 0x07
            r = target_attacked(v, w)
            killed = record_damage(v, attacker_id=v.id, weapon=w,
                                   result=r, now_ms=now_ms)
            result.took_atmosphere_damage = True
            result.atmosphere_damage = r.total_damage()
            result.killed = result.killed or killed
            if killed:
                await despawn_vehicle(vehicle_id, conn=conn)
    return result


def _selftest() -> None:
    raise NotImplementedError(
        "Retired")


if __name__ == "__main__":
    logger.info("vehicles.hull_stress self-test starting")
    _selftest()
    logger.info("vehicles.hull_stress self-test passed")
