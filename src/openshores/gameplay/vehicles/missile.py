
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field

import asyncpg
from typing import Optional

from openshores.core.logging import get_logger

from .persistence import Vehicle
from .spawn import get_active_vehicle, reserve_vehicle_id
from .terrain import get_terrain_query, NearbyAtom, Vec3
from .vehicle_constants import (
    MISSILE_THRUST_HEAVY, MISSILE_THRUST_LIGHT, MISSILE_DAMPING_RATE,
)
from .combat import (
    AuCombatWeapon, AuCombatResult, WEAPONMODE, WEAPONEFFECT,
    target_attacked, DiceRoller,
)
from .weapons import record_damage, get_weapon_for_ammo
from .ordnance import ORDNANCE_COOLDOWN_MS

logger = get_logger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


_HEAVY_AMMO = frozenset({0x38, 0x44, 0x12A, 0x12C, 0x12E, 0x130})
_LIGHT_AMMO = frozenset({0x43, 0x129, 0x12D, 0x37, 0x12B, 0x12F})

INITIAL_MISSILE_SPEED: float = 50.0

MAX_MISSILE_LIFETIME_MS: int = 30_000

MISSILE_IMPACT_RADIUS: float = 3.0

_MISSILE_HINT_MIN: int = 0x60_00_00
_MISSILE_HINT_MAX: int = 0x6F_FF_FF
_id_lock = threading.Lock()
_next_missile_hint: int = _MISSILE_HINT_MIN


def reserve_missile_id() -> int:
    global _next_missile_hint
    with _id_lock:
        if _next_missile_hint > _MISSILE_HINT_MAX:
            raise RuntimeError("Missile AuId range exhausted")
        hint = _next_missile_hint
        _next_missile_hint += 1
        return (hint << 8) & 0xFFFFFFFF


def _thrust_for_ammo(ammo_id: int) -> float:
    if ammo_id in _HEAVY_AMMO:
        return MISSILE_THRUST_HEAVY
    if ammo_id in _LIGHT_AMMO:
        return MISSILE_THRUST_LIGHT
    return MISSILE_THRUST_HEAVY


@dataclass
class Missile:
    id: int
    launcher_id: int
    launcher_empire: int
    parent_id: int
    ammo_commodity_id: int
    mode: int
    quality: int = 1

    locX: float = 0.0
    locY: float = 0.0
    locZ: float = 0.0
    vecX: float = 0.0
    vecY: float = 0.0
    vecZ: float = 0.0

    target_id: int = 0
    target_locX: float = 0.0
    target_locY: float = 0.0
    target_locZ: float = 0.0
    homing: bool = False

    spawn_ms: int = 0
    impacted: bool = False
    expired: bool = False
    last_tick_ms: int = 0


_missiles: dict[int, Missile] = {}
_missiles_lock = threading.Lock()


def get_active_missile(missile_id: int) -> Optional[Missile]:
    with _missiles_lock:
        return _missiles.get(int(missile_id))


def list_active_missiles() -> list[Missile]:
    with _missiles_lock:
        return list(_missiles.values())


def active_missile_count() -> int:
    with _missiles_lock:
        return len(_missiles)


def despawn_missile(missile_id: int) -> bool:
    with _missiles_lock:
        return _missiles.pop(int(missile_id), None) is not None


def clear_missile_registry() -> None:
    with _missiles_lock:
        _missiles.clear()


def spawn_missile(
    launcher: Vehicle,
    ammo_commodity_id: int,
    mode: int = WEAPONMODE.AREA,
    target_id: int = 0,
    target_pos: Optional[Vec3] = None,
    *,
    quality: int = 1,
    initial_speed: float = INITIAL_MISSILE_SPEED,
    now_ms: Optional[int] = None,
) -> Missile:
    if now_ms is None:
        now_ms = _now_ms()

    pos0 = (launcher.locX, launcher.locY, launcher.locZ)
    if target_pos is not None:
        dx = target_pos[0] - pos0[0]
        dy = target_pos[1] - pos0[1]
        dz = target_pos[2] - pos0[2]
        d_len = math.sqrt(dx*dx + dy*dy + dz*dz)
        if d_len == 0.0:
            dir_x, dir_y, dir_z = 1.0, 0.0, 0.0
        else:
            dir_x = dx / d_len
            dir_y = dy / d_len
            dir_z = dz / d_len
    else:
        dir_x, dir_y, dir_z = 1.0, 0.0, 0.0
        if target_pos is None and (launcher.rotZ != 0 or launcher.rotY != 0):
            from .physics import body_to_world
            dir_x, dir_y, dir_z = body_to_world(
                (launcher.rotX, launcher.rotY, launcher.rotZ),
                (1.0, 0.0, 0.0),
            )

    m = Missile(
        id=reserve_missile_id(),
        launcher_id=launcher.id,
        launcher_empire=launcher.allegiance,
        parent_id=launcher.idp,
        ammo_commodity_id=int(ammo_commodity_id),
        mode=int(mode),
        quality=int(quality),
        locX=pos0[0], locY=pos0[1], locZ=pos0[2],
        vecX=dir_x * initial_speed,
        vecY=dir_y * initial_speed,
        vecZ=dir_z * initial_speed,
        target_id=int(target_id),
        target_locX=target_pos[0] if target_pos else 0.0,
        target_locY=target_pos[1] if target_pos else 0.0,
        target_locZ=target_pos[2] if target_pos else 0.0,
        homing=(target_id != 0 or target_pos is not None),
        spawn_ms=now_ms,
        last_tick_ms=now_ms,
    )
    with _missiles_lock:
        _missiles[m.id] = m
    return m


@dataclass
class MissileTickResult:
    moved: bool = False
    impacted: bool = False
    expired: bool = False
    target_atom_id: int = 0
    damage_result: Optional[AuCombatResult] = None
    killed: bool = False


async def tick_missile(
    missile_id: int,
    dt_ms: int,
    *,
    conn: asyncpg.Connection,
    now_ms: Optional[int] = None,
    dice_roller: Optional[DiceRoller] = None,
) -> MissileTickResult:
    res = MissileTickResult()
    m = get_active_missile(missile_id)
    if m is None:
        return res
    if m.impacted or m.expired:
        return res
    if now_ms is None:
        now_ms = _now_ms()

    if now_ms - m.spawn_ms > MAX_MISSILE_LIFETIME_MS:
        m.expired = True
        despawn_missile(m.id)
        res.expired = True
        return res

    if dt_ms <= 0:
        return res
    dt = dt_ms / 1000.0

    terminal = _thrust_for_ammo(m.ammo_commodity_id)
    cur_speed = math.sqrt(m.vecX**2 + m.vecY**2 + m.vecZ**2)

    thrust_per_tick = terminal * dt

    if m.homing:
        if m.target_id != 0:
            target_v = get_active_vehicle(m.target_id)
            if target_v is not None:
                m.target_locX = target_v.locX
                m.target_locY = target_v.locY
                m.target_locZ = target_v.locZ
        dx_t = m.target_locX - m.locX
        dy_t = m.target_locY - m.locY
        dz_t = m.target_locZ - m.locZ
        d_len = math.sqrt(dx_t*dx_t + dy_t*dy_t + dz_t*dz_t)
        if d_len > 0.001:
            desired_x = dx_t / d_len * terminal
            desired_y = dy_t / d_len * terminal
            desired_z = dz_t / d_len * terminal
            ddx = desired_x - m.vecX
            ddy = desired_y - m.vecY
            ddz = desired_z - m.vecZ
            ddlen = math.sqrt(ddx*ddx + ddy*ddy + ddz*ddz)
            if ddlen > thrust_per_tick:
                ddx = ddx / ddlen * thrust_per_tick
                ddy = ddy / ddlen * thrust_per_tick
                ddz = ddz / ddlen * thrust_per_tick
            m.vecX += ddx; m.vecY += ddy; m.vecZ += ddz
    else:
        if cur_speed > 0:
            m.vecX += (m.vecX / cur_speed) * thrust_per_tick
            m.vecY += (m.vecY / cur_speed) * thrust_per_tick
            m.vecZ += (m.vecZ / cur_speed) * thrust_per_tick

    cur_speed = math.sqrt(m.vecX**2 + m.vecY**2 + m.vecZ**2)
    if cur_speed > terminal:
        scale = terminal / cur_speed
        m.vecX *= scale
        m.vecY *= scale
        m.vecZ *= scale

    dx = m.vecX * dt
    dy = m.vecY * dt
    dz = m.vecZ * dt
    m.locX += dx; m.locY += dy; m.locZ += dz
    res.moved = True

    q = get_terrain_query()
    pos = (m.locX, m.locY, m.locZ)
    pos_prev = (m.locX - dx, m.locY - dy, m.locZ - dz)
    motion_len = math.sqrt(dx*dx + dy*dy + dz*dz)
    query_center = (
        (pos[0] + pos_prev[0]) * 0.5,
        (pos[1] + pos_prev[1]) * 0.5,
        (pos[2] + pos_prev[2]) * 0.5,
    )
    query_r = MISSILE_IMPACT_RADIUS + motion_len
    for atom in q.iter_obstacles_near(m.parent_id, query_center, query_r):
        if atom.atom_id == m.launcher_id:
            continue
        if atom.is_da_item and atom.is_armed_by_id == m.launcher_id:
            continue
        ax = atom.world_pos[0] - pos_prev[0]
        ay = atom.world_pos[1] - pos_prev[1]
        az = atom.world_pos[2] - pos_prev[2]
        if motion_len > 0:
            seg_len_sq = motion_len * motion_len
            t = (ax * dx + ay * dy + az * dz) / seg_len_sq
            if t < 0.0:
                closest = pos_prev
            elif t > 1.0:
                closest = pos
            else:
                closest = (
                    pos_prev[0] + dx * t,
                    pos_prev[1] + dy * t,
                    pos_prev[2] + dz * t,
                )
        else:
            closest = pos_prev
        ddx = atom.world_pos[0] - closest[0]
        ddy = atom.world_pos[1] - closest[1]
        ddz = atom.world_pos[2] - closest[2]
        d2 = ddx*ddx + ddy*ddy + ddz*ddz
        r_sum = MISSILE_IMPACT_RADIUS + atom.radius
        if d2 <= r_sum * r_sum:
            res.impacted = True
            res.target_atom_id = atom.atom_id
            m.impacted = True

            target_v = get_active_vehicle(atom.atom_id)
            if target_v is not None:
                weapon = get_weapon_for_ammo(m.ammo_commodity_id)
                if weapon is None:
                    weapon = AuCombatWeapon(
                        weapon_id=m.ammo_commodity_id,
                        mode=WEAPONMODE.AREA,
                        effect1=WEAPONEFFECT.BLUDGEON,
                        dice_count_1=20, dice_bonus_1=10,
                        effect2=WEAPONEFFECT.BURNING, dice_count_2=0,
                    )
                dmg = target_attacked(target_v, weapon, hit_point=pos,
                                       dice_roller=dice_roller)
                killed = record_damage(target_v, attacker_id=m.launcher_id,
                                        weapon=weapon, result=dmg,
                                        now_ms=now_ms)
                res.damage_result = dmg
                res.killed = killed
                if killed:
                    from .spawn import despawn_vehicle
                    await despawn_vehicle(atom.atom_id, conn=conn)
            despawn_missile(m.id)
            return res

    m.last_tick_ms = now_ms
    return res


_last_missile_tick_ms: dict[int, int] = {}
_last_missile_tick_lock = threading.Lock()


async def tick_all_missiles(now_ms: Optional[int] = None, *,
                            conn: asyncpg.Connection) -> int:
    if now_ms is None:
        now_ms = _now_ms()
    snapshot = list_active_missiles()
    n = 0
    for m in snapshot:
        with _last_missile_tick_lock:
            last = _last_missile_tick_ms.get(m.id, 0)
            _last_missile_tick_ms[m.id] = now_ms
        if last == 0:
            dt_ms = 50
        else:
            dt_ms = now_ms - last
            if dt_ms <= 0 or dt_ms > 500:
                continue
        try:
            await tick_missile(m.id, dt_ms, now_ms=now_ms, conn=conn)
        except Exception as exc:
            logger.error("Missile %#x tick failed: %r. It stays in flight and "
                         "stops moving.", m.id, exc)
        if m.impacted or m.expired:
            with _last_missile_tick_lock:
                _last_missile_tick_ms.pop(m.id, None)
        n += 1
    return n


def _selftest() -> None:
    raise NotImplementedError(
        "Retired")


if __name__ == "__main__":
    logger.info("vehicles.missile self-test starting")
    _selftest()
    logger.info("vehicles.missile self-test passed")
