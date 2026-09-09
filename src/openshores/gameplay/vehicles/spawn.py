
from __future__ import annotations

import asyncio
import threading
from typing import Optional, Iterable

import asyncpg

from openshores.core.logging import get_logger

from .persistence import (
    Vehicle, ensure_schema, insert_vehicle, update_vehicle,
    load_vehicle, load_all_vehicles, delete_vehicle,
)
from .vehicle_constants import VehicleType

logger = get_logger(__name__)


_VEHICLE_HINT_MIN: int = 0x80_00_00
_VEHICLE_HINT_MAX: int = 0x8F_FF_FF

_id_lock = asyncio.Lock()
_next_hint: int = _VEHICLE_HINT_MIN
_id_seeded: bool = False


async def _seed_from_db(*, conn: asyncpg.Connection) -> None:
    global _next_hint, _id_seeded
    if _id_seeded:
        return
    rows = await load_all_vehicles(conn)
    max_id = 0
    for v in rows:
        if v.id > max_id:
            max_id = v.id
    if max_id != 0:
        hint = (max_id >> 8) & 0xFF_FF_FF
        if hint >= _VEHICLE_HINT_MIN and hint <= _VEHICLE_HINT_MAX:
            _next_hint = hint + 1
    _id_seeded = True


async def reserve_vehicle_id(*, conn: asyncpg.Connection) -> int:
    global _next_hint
    async with _id_lock:
        if not _id_seeded:
            await _seed_from_db(conn=conn)
        if _next_hint > _VEHICLE_HINT_MAX:
            raise RuntimeError(
                f"Vehicle AuId range exhausted (hint={_next_hint:#x})"
            )
        hint = _next_hint
        _next_hint += 1
        return (hint << 8) & 0xFFFFFFFF


def peek_next_vehicle_id() -> int:
    return _next_hint


_active: dict[int, Vehicle] = {}
_active_lock = threading.Lock()


def get_active_vehicle(vehicle_id: int) -> Optional[Vehicle]:
    with _active_lock:
        return _active.get(int(vehicle_id))


def list_active_vehicles() -> list[Vehicle]:
    with _active_lock:
        return list(_active.values())


def active_vehicle_count() -> int:
    with _active_lock:
        return len(_active)


async def hydrate_from_db(*, conn: asyncpg.Connection) -> int:
    rows = await load_all_vehicles(conn)
    with _active_lock:
        for v in rows:
            _active[v.id] = v
    return len(rows)


def clear_active_registry() -> None:
    with _active_lock:
        _active.clear()


_VEHICLE_SPAWN_HP_MAX: int = 500
_DEFAULT_HP_BY_COMMODITY: dict[int, int] = {
    VehicleType.PLANE:      300,
    VehicleType.HELICOPTER: 350,
    VehicleType.JET:        400,
    VehicleType.DRONE:      200,
    VehicleType.TANK:       800,
    VehicleType.BOAT:       400,
    VehicleType.SUB_IFV:    600,
    VehicleType.APC:        700,
    VehicleType.SHUTTLE:    350,
    VehicleType.TURRET:     900,
    VehicleType.LANDER:     400,
}
_DEFAULT_HP_FALLBACK: int = _VEHICLE_SPAWN_HP_MAX


async def spawn_vehicle(
    commodity_id: int,
    parent_id: int,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    name: str = "",
    quality: int = 1,
    allegiance: int = 0,
    arena_team: int = 0,
    fuel: int = 100,
    hp: Optional[int] = None,
    mother_ship: int = 0,
    mother_ship_name: str = "",
    persist: bool = True,
    *,
    conn: asyncpg.Connection,
) -> Vehicle:
    vid = await reserve_vehicle_id(conn=conn)
    if hp is None:
        hp = _DEFAULT_HP_BY_COMMODITY.get(commodity_id, _DEFAULT_HP_FALLBACK)

    v = Vehicle(
        id=vid,
        idp=parent_id,
        locX=float(location[0]),
        locY=float(location[1]),
        locZ=float(location[2]),
        rotX=float(rotation[0]),
        rotY=float(rotation[1]),
        rotZ=float(rotation[2]),
        name=name,
        cid=commodity_id,
        allegiance=allegiance,
        arenaTeam=arena_team,
        fuel=fuel,
        hp=hp,
        qual=quality,
        motherShip=mother_ship,
        motherShipName=mother_ship_name,
    )

    if persist:
        await insert_vehicle(conn, v)
    with _active_lock:
        _active[vid] = v
    return v


async def despawn_vehicle(vehicle_id: int, delete_row: bool = True, *,
                          conn: asyncpg.Connection) -> bool:
    with _active_lock:
        present = _active.pop(int(vehicle_id), None) is not None
    if delete_row:
        await delete_vehicle(conn, int(vehicle_id))
    return present


async def commit_vehicle(vehicle_id: int, *,
                         conn: asyncpg.Connection) -> bool:
    with _active_lock:
        v = _active.get(int(vehicle_id))
    if v is None:
        return False
    return await update_vehicle(conn, v)


class SpotType:
    GROUND = 1
    ROCKET = 2
    SPACE  = 3
    WATER  = 4


def find_parking_spot(
    parent_id: int,
    spot_type: int = SpotType.GROUND,
    near_location: Optional[tuple[float, float, float]] = None,
) -> Optional[tuple[float, float, float]]:
    from .terrain import get_terrain_query
    q = get_terrain_query()
    pos = near_location if near_location is not None else (0.0, 0.0, 0.0)
    spot = q.closest_parking_spot(parent_id, pos, int(spot_type))
    if spot is None:
        return (0.0, 0.0, 0.0)
    return spot


def _selftest() -> None:
    raise NotImplementedError(
        "Retired")

if __name__ == "__main__":
    logger.info("vehicles.spawn self-test starting")
    _selftest()
    logger.info("vehicles.spawn self-test passed")
