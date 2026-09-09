
from __future__ import annotations

import math
from typing import Optional, Iterable

from openshores.core.logging import get_logger

from .persistence import Vehicle
from .input import get_runtime
from .terrain import get_terrain_query, NearbyAtom, Vec3

logger = get_logger(__name__)


def _dist_sq(a: Vec3, b: Vec3) -> float:
    dx = a[0] - b[0]; dy = a[1] - b[1]; dz = a[2] - b[2]
    return dx*dx + dy*dy + dz*dz


def _vehicle_radius(v: Vehicle) -> float:
    from .vehicle_constants import CROSS_SECTIONAL_AREA
    dims = CROSS_SECTIONAL_AREA.get(v.cid)
    if dims is None:
        return 1.0
    return max(dims.x, dims.y, dims.z) * 0.5


def is_obstacle(v: Vehicle, other: NearbyAtom) -> bool:
    if other.atom_id == v.id:
        return False
    if other.is_da_item and other.is_armed_by_id == v.id:
        return False
    return True


def check_collision_against_launcher(v: Vehicle, target_atom_id: int) -> bool:
    rt = get_runtime(v.id)
    if rt.launch_counter == 0:
        return False
    return target_atom_id == rt.launching_vessel


def movement_blocked(v: Vehicle,
                     desired_dx: float, desired_dy: float, desired_dz: float
                     ) -> Optional[Vec3]:
    if (desired_dx, desired_dy, desired_dz) == (0.0, 0.0, 0.0):
        v.vecX = v.vecY = v.vecZ = 0.0
        return (0.0, 0.0, 0.0)
    return None


def move(v: Vehicle,
         dx: float, dy: float, dz: float,
         dt_ms: int) -> tuple[float, float, float, bool]:
    q = get_terrain_query()

    pos0 = (v.locX, v.locY, v.locZ)
    motion_len = math.sqrt(dx*dx + dy*dy + dz*dz)
    if motion_len == 0.0:
        return (0.0, 0.0, 0.0, False)

    vr = _vehicle_radius(v)
    proposed = (pos0[0] + dx, pos0[1] + dy, pos0[2] + dz)

    obstacles = q.iter_obstacles_near(v.idp, proposed, vr + motion_len)

    blockers: list[NearbyAtom] = []
    for o in obstacles:
        if o.atom_id == v.id:
            continue
        if check_collision_against_launcher(v, o.atom_id):
            continue
        if not is_obstacle(v, o):
            continue
        d2 = _dist_sq(proposed, o.world_pos)
        r_sum = vr + o.radius
        if d2 <= r_sum * r_sum:
            blockers.append(o)

    blocked = False
    if blockers:
        candidates = [
            (dx, dy, 0.0),
            (dx, 0.0, dz),
            (0.0, dy, dz),
            (dx, 0.0, 0.0),
            (0.0, dy, 0.0),
            (0.0, 0.0, dz),
            (0.0, 0.0, 0.0),
        ]
        for tdx, tdy, tdz in candidates:
            tpos = (pos0[0] + tdx, pos0[1] + tdy, pos0[2] + tdz)
            hits = False
            for o in blockers:
                if _dist_sq(tpos, o.world_pos) <= (vr + o.radius) ** 2:
                    hits = True
                    break
            if not hits:
                dx, dy, dz = tdx, tdy, tdz
                blocked = True
                break
        else:
            dx = dy = dz = 0.0
            blocked = True

    new_pos = (pos0[0] + dx, pos0[1] + dy, pos0[2] + dz)

    rg = None
    try:
        rg = q.radial_ground(v.idp, new_pos, vr)
    except Exception:
        rg = None
    if rg is not None:
        rx, ry, rz = rg
        rlen = math.sqrt(rx*rx + ry*ry + rz*rz)
        if rlen > 1e-9:
            nx, ny, nz = rx/rlen, ry/rlen, rz/rlen
            vdot = v.vecX*nx + v.vecY*ny + v.vecZ*nz
            if vdot < 0.0:
                v.vecX -= vdot*nx
                v.vecY -= vdot*ny
                v.vecZ -= vdot*nz
        new_pos = (rx, ry, rz)
        dx = new_pos[0] - pos0[0]
        dy = new_pos[1] - pos0[1]
        dz = new_pos[2] - pos0[2]
        blocked = True
    else:
        gh = q.ground_height_xy(v.idp, new_pos[0], new_pos[1])
        if gh is not None:
            floor_z = gh + 0.01
            if new_pos[2] < floor_z:
                dz = floor_z - pos0[2]
                new_pos = (new_pos[0], new_pos[1], floor_z)
                if v.vecZ < 0:
                    v.vecZ = 0.0
                blocked = True

    v.locX, v.locY, v.locZ = new_pos
    return (dx, dy, dz, blocked)


def _selftest() -> None:
    raise NotImplementedError(
        "Retired")


if __name__ == "__main__":
    logger.info("vehicles.collision self-test starting")
    _selftest()
    logger.info("vehicles.collision self-test passed")
