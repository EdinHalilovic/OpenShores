
from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass
from typing import Optional

from openshores.core.logging import get_logger

from .persistence import Vehicle
from .spawn import get_active_vehicle
from .input import (
    get_runtime, VehicleRuntimeState, Switches, ActBits,
)
from .vehicle_constants import (
    VehicleType,
    ACCELERATION_TABLE,
    DRAG_COEFFICIENT,
    DRAG_COEFFICIENT_DEFAULT,
    CROSS_SECTIONAL_AREA,
    DENSITY,
    DENSITY_DEFAULT,
    ORIENTATION_SPEED,
    ORIENTATION_SPEED_DEFAULT,
    JET_RUNWAY_TAKEOFF_SPEED,
)
from .terrain import get_terrain_query
from . import collision as _collision

logger = get_logger(__name__)


Vec3 = tuple[float, float, float]

DEFAULT_GRAVITY: float = 9.80665

SEA_LEVEL_AIR_DENSITY: float = 1.225

REST_TIMEOUT_MS: int = 2000

FUZZY_ZERO_EPS: float = 1e-3

MAX_TICK_MS: int = 500


_SPACE_COMMODITIES = frozenset({
})


def wrap_angle(x: float) -> float:
    while x > math.pi:
        x -= 2 * math.pi
    while x < -math.pi:
        x += 2 * math.pi
    return x


def body_to_world(rot: Vec3, body: Vec3) -> Vec3:
    rx, ry, rz = rot
    bx, by, bz = body

    cx, sx = math.cos(rx), math.sin(rx)
    y1 = by * cx - bz * sx
    z1 = by * sx + bz * cx
    x1, y1, z1 = bx, y1, z1

    cy, sy = math.cos(ry), math.sin(ry)
    x2 = x1 * cy + z1 * sy
    z2 = -x1 * sy + z1 * cy
    x2, y2, z2 = x2, y1, z2

    cz, sz = math.cos(rz), math.sin(rz)
    x3 = x2 * cz - y2 * sz
    y3 = x2 * sz + y2 * cz

    return (x3, y3, z2)


def _now_ms() -> int:
    return int(time.time() * 1000)


def compute_acceleration(v: Vehicle, rt: VehicleRuntimeState) -> Vec3:
    table = ACCELERATION_TABLE.get(v.cid)
    if table is None or table.forward is None:
        return (0.0, 0.0, 0.0)

    if not (v.switches & Switches.ENGINE_BIT):
        return (0.0, 0.0, 0.0)

    fwd = table.forward
    rev = table.reverse if table.reverse is not None else -fwd

    long_t = v.throttle / 10.0
    if long_t >= 0:
        ax_body = long_t * fwd
    else:
        ax_body = (-long_t) * rev

    fwd_mag = abs(fwd)
    lat_t = v.throttleLateral / 10.0
    vert_t = v.throttleVertical / 10.0
    strafe_t = v.throttleLong / 10.0

    ay_body = lat_t * fwd_mag * 0.5
    az_body = vert_t * fwd_mag * 0.5
    if v.cid in (VehicleType.HELICOPTER, VehicleType.SHUTTLE):
        ax_body += strafe_t * fwd_mag * 0.3

    return (ax_body, ay_body, az_body)


def compute_drag(v: Vehicle, dt: float,
                 air_density: Optional[float] = None) -> Vec3:
    cd = DRAG_COEFFICIENT.get(v.cid, DRAG_COEFFICIENT_DEFAULT)
    dims = CROSS_SECTIONAL_AREA.get(v.cid)
    if dims is None:
        Ax = Ay = Az = 1.0
    else:
        Ax = dims.y * dims.z
        Ay = dims.x * dims.z
        Az = dims.x * dims.y

    mass_scale = max(DENSITY.get(v.cid, DENSITY_DEFAULT), 1.0)

    if air_density is None:
        q = get_terrain_query()
        air_density = q.air_density_at(v.idp, (v.locX, v.locY, v.locZ))

    half_rho_cd_dt_over_m = 0.5 * air_density * cd * dt / mass_scale

    fdx = half_rho_cd_dt_over_m * Ax * abs(v.vecX) * abs(v.vecX)
    fdy = half_rho_cd_dt_over_m * Ay * abs(v.vecY) * abs(v.vecY)
    fdz = half_rho_cd_dt_over_m * Az * abs(v.vecZ) * abs(v.vecZ)

    return (fdx, fdy, fdz)


def compute_gravity(v: Vehicle) -> Vec3:
    if v.cid in _SPACE_COMMODITIES:
        return (0.0, 0.0, 0.0)
    q = get_terrain_query()
    return q.gravity_at(v.idp, (v.locX, v.locY, v.locZ))


def compute_orientation_speed(v: Vehicle) -> float:
    return ORIENTATION_SPEED.get(v.cid, ORIENTATION_SPEED_DEFAULT)


@dataclass
class TickResult:
    velocity_changed: bool = False
    transform_changed: bool = False
    became_at_rest: bool = False
    skipped: bool = False
    elapsed_ms: int = 0


def _is_fuzzy_zero(vec: Vec3) -> bool:
    return (abs(vec[0]) < FUZZY_ZERO_EPS
            and abs(vec[1]) < FUZZY_ZERO_EPS
            and abs(vec[2]) < FUZZY_ZERO_EPS)


def tick_movement_v(
    v: Vehicle,
    rt: VehicleRuntimeState,
    dt_ms: int,
    *,
    now_ms: Optional[int] = None,
    air_density: Optional[float] = None,
) -> TickResult:
    result = TickResult(elapsed_ms=dt_ms)


    if dt_ms <= 0:
        result.skipped = True
        return result
    if dt_ms > MAX_TICK_MS:
        result.skipped = True
        return result

    dt = dt_ms / 1000.0
    if now_ms is None:
        now_ms = _now_ms()

    omega_speed = compute_orientation_speed(v)
    rot_dx = 0.0
    rot_dy = 0.0
    rot_dz = 0.0
    if v.actBits & ActBits.YAW_RIGHT:
        rot_dz += omega_speed * dt * (rt.rot_yaw_strength / 127.0)
    if v.actBits & ActBits.YAW_LEFT:
        rot_dz -= omega_speed * dt * (rt.rot_yaw_strength / 127.0)
    if v.actBits & ActBits.PITCH_UP:
        rot_dy += omega_speed * dt * (rt.rot_pitch_strength / 127.0)
    if v.actBits & ActBits.PITCH_DOWN:
        rot_dy -= omega_speed * dt * (rt.rot_pitch_strength / 127.0)
    if v.actBits & ActBits.ROLL_RIGHT:
        rot_dx += omega_speed * dt * (rt.rot_roll_strength / 127.0)
    if v.actBits & ActBits.ROLL_LEFT:
        rot_dx -= omega_speed * dt * (rt.rot_roll_strength / 127.0)

    if rot_dx != 0.0 or rot_dy != 0.0 or rot_dz != 0.0:
        v.rotX = wrap_angle(v.rotX + rot_dx)
        v.rotY = wrap_angle(v.rotY + rot_dy)
        v.rotZ = wrap_angle(v.rotZ + rot_dz)
        result.transform_changed = True

    accel_body = compute_acceleration(v, rt)
    accel_world = body_to_world((v.rotX, v.rotY, v.rotZ), accel_body)

    gravity = compute_gravity(v)

    new_vx = v.vecX + (accel_world[0] + gravity[0]) * dt
    new_vy = v.vecY + (accel_world[1] + gravity[1]) * dt
    new_vz = v.vecZ + (accel_world[2] + gravity[2]) * dt

    drag_dv = compute_drag(v, dt, air_density=air_density)
    if new_vx > 0:
        new_vx -= drag_dv[0]
        if new_vx < 0:
            new_vx = 0.0
    elif new_vx < 0:
        new_vx += drag_dv[0]
        if new_vx > 0:
            new_vx = 0.0
    if new_vy > 0:
        new_vy -= drag_dv[1]
        if new_vy < 0:
            new_vy = 0.0
    elif new_vy < 0:
        new_vy += drag_dv[1]
        if new_vy > 0:
            new_vy = 0.0
    if new_vz > 0:
        new_vz -= drag_dv[2]
        if new_vz < 0:
            new_vz = 0.0
    elif new_vz < 0:
        new_vz += drag_dv[2]
        if new_vz > 0:
            new_vz = 0.0

    if new_vx != v.vecX or new_vy != v.vecY or new_vz != v.vecZ:
        result.velocity_changed = True

    q = get_terrain_query()
    carrier = q.carrier_motion(v.idp)
    if carrier is not None:
        cvel, cdt = carrier
        carrier_dt = min(dt, cdt) if cdt > 0 else dt
        v.locX += cvel[0] * carrier_dt
        v.locY += cvel[1] * carrier_dt
        v.locZ += cvel[2] * carrier_dt
        if cvel != (0.0, 0.0, 0.0):
            result.transform_changed = True

    if _is_fuzzy_zero((new_vx, new_vy, new_vz)):
        new_vx = new_vy = new_vz = 0.0
        pos_dx = pos_dy = pos_dz = 0.0
    else:
        v.vecX, v.vecY, v.vecZ = new_vx, new_vy, new_vz
        pos_dx = new_vx * dt
        pos_dy = new_vy * dt
        pos_dz = new_vz * dt
        actual_dx, actual_dy, actual_dz, was_blocked = _collision.move(
            v, pos_dx, pos_dy, pos_dz, dt_ms,
        )
        if actual_dx != pos_dx or actual_dy != pos_dy or actual_dz != pos_dz:
            if actual_dx == 0.0 and pos_dx != 0.0: new_vx = 0.0
            if actual_dy == 0.0 and pos_dy != 0.0: new_vy = 0.0
            new_vz = v.vecZ
        if was_blocked or (actual_dx, actual_dy, actual_dz) != (0.0, 0.0, 0.0):
            result.transform_changed = True

    v.vecX, v.vecY, v.vecZ = new_vx, new_vy, new_vz

    velocity_zero = (new_vx == 0.0 and new_vy == 0.0 and new_vz == 0.0)
    accel_zero = (accel_body == (0.0, 0.0, 0.0))
    if velocity_zero and accel_zero:
        rt.ts_at_rest_pending = getattr(rt, "ts_at_rest_pending", 0)
        if rt.ts_at_rest_pending == 0:
            rt.ts_at_rest_pending = now_ms
        elif (now_ms - rt.ts_at_rest_pending) >= REST_TIMEOUT_MS:
            if not v.atRest:
                v.atRest = True
                result.became_at_rest = True
    else:
        rt.ts_at_rest_pending = 0
        if v.atRest:
            v.atRest = False
            result.transform_changed = True

    if result.transform_changed and not result.became_at_rest:
        rt.ts_hp_changed = now_ms

    return result


def tick_movement(
    vehicle_id: int,
    dt_ms: int,
    *,
    now_ms: Optional[int] = None,
    air_density: Optional[float] = None,
) -> TickResult:
    v = get_active_vehicle(vehicle_id)
    if v is None:
        return TickResult(skipped=True)
    rt = get_runtime(vehicle_id)
    return tick_movement_v(v, rt, dt_ms, now_ms=now_ms, air_density=air_density)


def _selftest() -> None:
    raise NotImplementedError(
        "Retired")


if __name__ == "__main__":
    logger.info("vehicles.physics self-test starting")
    _selftest()
    logger.info("vehicles.physics self-test passed")
