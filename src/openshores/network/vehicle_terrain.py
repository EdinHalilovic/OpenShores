
from __future__ import annotations

import math as _vt_math

from openshores.core.logging import get_logger
from openshores.gameplay.vehicles.terrain import (
    CallbackTerrainQuery as _VehCallbackTerrain,
)
from openshores.gameplay.vehicles.terrain import (
    set_terrain_query as _veh_set_terrain,
)

logger = get_logger(__name__)

_VEH_DEFAULT_RADIUS_M = float("18700")
_VEH_PLANET_G = float("9.80665")
_VEH_SPAWN_LIFT_M = float("5")
_VEH_GROUND_TOL_M = float("1.0")
_VEH_PARENT_FLOOR: dict[int, float] = {}


def _veh_floor_radius(parent_id):
    try:
        r = _VEH_PARENT_FLOOR.get(int(parent_id) & 0xFFFFFFFF)
    except Exception:
        r = None
    return r if (r is not None and r > 1.0) else _VEH_DEFAULT_RADIUS_M


def _veh_note_ground_radius(parent_id, xyz):
    try:
        x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    except Exception:
        return
    r = _vt_math.sqrt(x*x + y*y + z*z)
    if r < 1.0:
        return
    floor = r - _VEH_SPAWN_LIFT_M
    if floor < 1.0:
        floor = r
    try:
        _VEH_PARENT_FLOOR[int(parent_id) & 0xFFFFFFFF] = floor
    except Exception:
        logger.debug(f"Ground radius not recorded: parent id {parent_id!r} "
                     f"is not a number.")


def _veh_gravity_at(_pid, _pos):
    x, y, z = _pos
    r = _vt_math.sqrt(x*x + y*y + z*z)
    if r < 1.0:
        return (0.0, 0.0, 0.0)
    if r <= _veh_floor_radius(_pid) + _VEH_GROUND_TOL_M:
        return (0.0, 0.0, 0.0)
    g = _VEH_PLANET_G
    return (-g * x / r, -g * y / r, -g * z / r)


def _veh_is_on_ground(_pid, _pos, _vehicle_radius=1.0):
    x, y, z = _pos
    r = _vt_math.sqrt(x*x + y*y + z*z)
    return r <= _veh_floor_radius(_pid) + _VEH_GROUND_TOL_M


def _veh_radial_ground(_pid, _pos, _vehicle_radius=1.0):
    x, y, z = _pos
    r = _vt_math.sqrt(x*x + y*y + z*z)
    floor = _veh_floor_radius(_pid)
    if r >= floor:
        return None
    if r < 1.0:
        return (0.0, 0.0, floor)
    s = floor / r
    return (x * s, y * s, z * s)


def install_radial_terrain() -> None:
    _veh_set_terrain(_VehCallbackTerrain(
        gravity_fn=_veh_gravity_at,
        is_on_ground_fn=_veh_is_on_ground,
        radial_ground_fn=_veh_radial_ground,
    ))
    logger.info(f'[vehicles-physics] radial terrain installed (g={_VEH_PLANET_G:.3f} toward centre; floor=sphere, default {_VEH_DEFAULT_RADIUS_M:.0f}m, per-parent from spawn).')
