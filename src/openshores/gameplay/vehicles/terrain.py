
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Protocol, Iterable, Callable

from openshores.core.logging import get_logger

logger = get_logger(__name__)


Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class NearbyAtom:
    atom_id: int
    world_pos: Vec3
    radius: float = 1.0
    flag_bits: int = 0
    is_da_item: bool = False
    is_armed_by_id: int = 0


class TerrainQuery(Protocol):

    def is_on_ground(self, parent_id: int, pos: Vec3,
                     vehicle_radius: float = 1.0) -> bool: ...
    def is_in_water(self, parent_id: int, pos: Vec3) -> bool: ...
    def ground_height_xy(self, parent_id: int,
                         x: float, y: float) -> Optional[float]: ...
    def radial_ground(self, parent_id: int, pos: Vec3,
                      vehicle_radius: float = 1.0) -> Optional[Vec3]: ...
    def gravity_at(self, parent_id: int, pos: Vec3) -> Vec3: ...
    def air_density_at(self, parent_id: int, pos: Vec3) -> float: ...
    def is_atmosphere(self, parent_id: int) -> bool: ...
    def latlon_to_xyz(self, parent_id: int,
                      latitude_deg: float, longitude_deg: float) -> Vec3: ...
    def iter_obstacles_near(self, parent_id: int, pos: Vec3,
                            radius: float) -> Iterable[NearbyAtom]: ...
    def closest_parking_spot(self, parent_id: int, pos: Vec3,
                             spot_type: int) -> Optional[Vec3]: ...
    def carrier_motion(self, parent_id: int) -> Optional[tuple[Vec3, float]]:
        ...


class NullTerrainQuery:

    def is_on_ground(self, parent_id, pos, vehicle_radius=1.0):
        return False

    def is_in_water(self, parent_id, pos):
        return False

    def ground_height_xy(self, parent_id, x, y):
        return None

    def radial_ground(self, parent_id, pos, vehicle_radius=1.0):
        return None

    def gravity_at(self, parent_id, pos):
        return (0.0, 0.0, -9.80665)

    def air_density_at(self, parent_id, pos):
        return 1.225

    def is_atmosphere(self, parent_id):
        return True

    def latlon_to_xyz(self, parent_id, lat_deg, lon_deg):
        return (0.0, 0.0, 0.0)

    def iter_obstacles_near(self, parent_id, pos, radius):
        return ()

    def closest_parking_spot(self, parent_id, pos, spot_type):
        return None

    def carrier_motion(self, parent_id):
        return None


@dataclass
class CallbackTerrainQuery:

    is_on_ground_fn: Optional[Callable[[int, Vec3, float], bool]] = None
    is_in_water_fn: Optional[Callable[[int, Vec3], bool]] = None
    ground_height_fn: Optional[Callable[[int, float, float], Optional[float]]] = None
    radial_ground_fn: Optional[Callable[[int, Vec3, float], Optional[Vec3]]] = None
    gravity_fn: Optional[Callable[[int, Vec3], Vec3]] = None
    air_density_fn: Optional[Callable[[int, Vec3], float]] = None
    is_atmosphere_fn: Optional[Callable[[int], bool]] = None
    latlon_to_xyz_fn: Optional[Callable[[int, float, float], Vec3]] = None
    iter_obstacles_fn: Optional[Callable[[int, Vec3, float],
                                         Iterable[NearbyAtom]]] = None
    closest_parking_spot_fn: Optional[Callable[[int, Vec3, int],
                                               Optional[Vec3]]] = None
    carrier_motion_fn: Optional[Callable[[int],
                                         Optional[tuple[Vec3, float]]]] = None

    _null: NullTerrainQuery = None

    def __post_init__(self):
        object.__setattr__(self, "_null", NullTerrainQuery())

    def is_on_ground(self, parent_id, pos, vehicle_radius=1.0):
        if self.is_on_ground_fn:
            return self.is_on_ground_fn(parent_id, pos, vehicle_radius)
        return self._null.is_on_ground(parent_id, pos, vehicle_radius)

    def is_in_water(self, parent_id, pos):
        if self.is_in_water_fn:
            return self.is_in_water_fn(parent_id, pos)
        return self._null.is_in_water(parent_id, pos)

    def ground_height_xy(self, parent_id, x, y):
        if self.ground_height_fn:
            return self.ground_height_fn(parent_id, x, y)
        return self._null.ground_height_xy(parent_id, x, y)

    def radial_ground(self, parent_id, pos, vehicle_radius=1.0):
        if self.radial_ground_fn:
            return self.radial_ground_fn(parent_id, pos, vehicle_radius)
        return None

    def gravity_at(self, parent_id, pos):
        if self.gravity_fn:
            return self.gravity_fn(parent_id, pos)
        return self._null.gravity_at(parent_id, pos)

    def air_density_at(self, parent_id, pos):
        if self.air_density_fn:
            return self.air_density_fn(parent_id, pos)
        return self._null.air_density_at(parent_id, pos)

    def is_atmosphere(self, parent_id):
        if self.is_atmosphere_fn:
            return self.is_atmosphere_fn(parent_id)
        return self._null.is_atmosphere(parent_id)

    def latlon_to_xyz(self, parent_id, lat_deg, lon_deg):
        if self.latlon_to_xyz_fn:
            return self.latlon_to_xyz_fn(parent_id, lat_deg, lon_deg)
        return self._null.latlon_to_xyz(parent_id, lat_deg, lon_deg)

    def iter_obstacles_near(self, parent_id, pos, radius):
        if self.iter_obstacles_fn:
            return self.iter_obstacles_fn(parent_id, pos, radius)
        return ()

    def closest_parking_spot(self, parent_id, pos, spot_type):
        if self.closest_parking_spot_fn:
            return self.closest_parking_spot_fn(parent_id, pos, spot_type)
        return None

    def carrier_motion(self, parent_id):
        if self.carrier_motion_fn:
            return self.carrier_motion_fn(parent_id)
        return None


_active_query: TerrainQuery = NullTerrainQuery()


def set_terrain_query(query: TerrainQuery) -> None:
    global _active_query
    _active_query = query


def get_terrain_query() -> TerrainQuery:
    return _active_query


def reset_terrain_query() -> None:
    global _active_query
    _active_query = NullTerrainQuery()


def spherical_latlon_to_xyz(planet_radius_m: float,
                            lat_deg: float, lon_deg: float,
                            altitude_m: float = 0.0) -> Vec3:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    r = planet_radius_m + altitude_m
    x = r * math.cos(lat) * math.cos(lon)
    y = r * math.cos(lat) * math.sin(lon)
    z = r * math.sin(lat)
    return (x, y, z)


def _selftest() -> None:
    nq = NullTerrainQuery()
    assert nq.is_on_ground(0, (0,0,0)) is False
    assert nq.gravity_at(0, (0,0,0)) == (0.0, 0.0, -9.80665)
    assert nq.air_density_at(0, (0,0,0)) == 1.225

    reset_terrain_query()
    assert isinstance(get_terrain_query(), NullTerrainQuery)

    flat = CallbackTerrainQuery(
        is_on_ground_fn=lambda pid, pos, r: pos[2] <= 0.01,
        gravity_fn=lambda pid, pos: (0.0, 0.0, -3.7),
        latlon_to_xyz_fn=lambda pid, lat, lon: spherical_latlon_to_xyz(
            3389000.0, lat, lon
        ),
    )
    set_terrain_query(flat)
    assert get_terrain_query().is_on_ground(42, (0, 0, 0.0)) is True
    assert get_terrain_query().is_on_ground(42, (0, 0, 100.0)) is False
    assert get_terrain_query().gravity_at(42, (0,0,0)) == (0.0, 0.0, -3.7)
    pos = get_terrain_query().latlon_to_xyz(42, 0.0, 0.0)
    assert abs(pos[0] - 3389000.0) < 1.0, f"Equator lon=0 should be +X: {pos}"
    pos = get_terrain_query().latlon_to_xyz(42, 90.0, 0.0)
    assert abs(pos[2] - 3389000.0) < 1.0, f"North pole should be +Z: {pos}"

    assert flat.is_in_water(0, (0,0,0)) is False
    assert flat.air_density_at(0, (0,0,0)) == 1.225

    reset_terrain_query()


if __name__ == "__main__":
    logger.info("vehicles.terrain self-test starting")
    _selftest()
    logger.info("vehicles.terrain self-test passed")
