
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from openshores.protocol.matrix import AuMatrix4x4, Vec3
from openshores.protocol.rng import AuNoise


MS_PER_REAL_DAY = 86_400_000.0
REAL_DAYS_PER_GAME_YEAR = 365.0 / 28.0
GAME_DAYS_PER_GAME_YEAR = 365.0

GAME_UNITS_PER_AU = 2_400_000.0

GAME_DAY_MS = MS_PER_REAL_DAY / GAME_DAYS_PER_GAME_YEAR * REAL_DAYS_PER_GAME_YEAR

_MOON_PERIOD_RADIUS = 7.0 / 120.0
_MOON_PERIOD_DIVISOR = 12.0
_TIDAL_LOCK_SPEED = 1.0
_SPEED_MODULUS = 1001
_SPEED_DIVISOR = 1000.0
_SPEED_EVEN_SCALE = 0.9
_SPEED_EVEN_BASE = 0.1

HOT_ORBIT_ZONE = 2

_INT32_MIN, _INT32_MAX = -(2 ** 31), 2 ** 31 - 1


def _trunc_c_int(x: float) -> float:
    if not (_INT32_MIN <= x < _INT32_MAX + 1):
        raise OverflowError(
            "world_clock: %r overflows the engine's (int) cast" % (x,))
    return float(math.trunc(x))


def _frac(x: float) -> float:
    return x - _trunc_c_int(x)


def game_years(coordinated_time_ms: float) -> float:
    return (coordinated_time_ms / MS_PER_REAL_DAY) / REAL_DAYS_PER_GAME_YEAR


def game_days(coordinated_time_ms: float) -> float:
    return game_years(coordinated_time_ms) * GAME_DAYS_PER_GAME_YEAR


@dataclass(frozen=True)
class Body:

    world_id: int
    gen_seed: int
    orbit_radius: float
    orbit_zone: int
    is_moon: bool = False
    breathable: bool = False
    rotation_angle_offset: float = 0.0
    parent_rotation_z: float = 0.0


def rotation_speed_factor(body: Body) -> float:
    if (body.orbit_zone & 0xFF) == HOT_ORBIT_ZONE and body.breathable:
        return _TIDAL_LOCK_SPEED
    uid = body.world_id & 0xFFFFFFFF
    r = uid % _SPEED_MODULUS
    if uid & 1:
        return (r + r) / _SPEED_DIVISOR + _TIDAL_LOCK_SPEED
    return (r * _SPEED_EVEN_SCALE) / _SPEED_DIVISOR + _SPEED_EVEN_BASE


def direction_of_rotation(gen_seed: int) -> int:
    return -1 if (gen_seed & 1) else 1


def calc_angle_of_rotation(body: Body, coordinated_time_ms: float) -> float:
    x = rotation_speed_factor(body) * game_days(coordinated_time_ms)
    half = _frac(x) * math.pi
    return body.rotation_angle_offset + direction_of_rotation(body.gen_seed) * (half + half)


def period(body: Body) -> float:
    r = body.orbit_radius
    if body.is_moon:
        scaled = r / _MOON_PERIOD_RADIUS
        return math.sqrt(scaled * scaled * scaled) / _MOON_PERIOD_DIVISOR
    return math.sqrt(r * r * r)


def angle_to_planet(body: Body, coordinated_time_ms: float) -> float:
    p = period(body)
    if p == 0.0:
        raise ZeroDivisionError(
            "world_clock.angle_to_planet: zero orbital period "
            "(orbit_radius=%r)" % (body.orbit_radius,))
    phase = AuNoise.integer_noise1(body.orbit_zone & 0xFF, body.gen_seed)
    half = _frac(game_years(coordinated_time_ms) / p + phase) * math.pi
    return (half + half) - body.parent_rotation_z


def world_transform(body: Body, coordinated_time_ms: float) -> AuMatrix4x4:
    a = angle_to_planet(body, coordinated_time_ms)
    m = AuMatrix4x4()
    m.rotate_z(a)
    m.translate(body.orbit_radius * GAME_UNITS_PER_AU, 0.0, 0.0)
    m.rotate_z(-a)
    m.rotate_z(calc_angle_of_rotation(body, coordinated_time_ms))
    return m


COMPANION_ORBIT_STEP_AU = 0.25
PRIMARY_FALLBACK_ORBIT_AU = 0.125


@dataclass
class CompanionStar:

    gen_seed: int
    companion_orbit: int = -1

    @property
    def is_primary(self) -> bool:
        return _sc8(self.companion_orbit) < 0

    @property
    def orbit_radius_au(self) -> float:
        o = _sc8(self.companion_orbit)
        if o < 0:
            return PRIMARY_FALLBACK_ORBIT_AU
        return (float(o) + 1.0) * COMPANION_ORBIT_STEP_AU


def _sc8(v: int) -> int:
    v = int(v) & 0xFF
    return v - 256 if v >= 128 else v


def angle_to_companion_star(star: CompanionStar,
                            coordinated_time_ms: float) -> float:
    r = star.orbit_radius_au
    p = math.sqrt(r * r * r)
    if p == 0.0:
        raise ZeroDivisionError(
            "world_clock.angle_to_companion_star: zero period")
    phase = AuNoise.integer_noise1(0, int(star.gen_seed))
    half = _frac(game_years(coordinated_time_ms) / p + phase) * math.pi
    return half + half


def companion_transform(star: CompanionStar,
                        coordinated_time_ms: float) -> AuMatrix4x4:
    m = AuMatrix4x4()
    if star.is_primary:
        return m
    a = angle_to_companion_star(star, coordinated_time_ms)
    m.rotate_z(a)
    m.translate(star.orbit_radius_au * GAME_UNITS_PER_AU, 0.0, 0.0)
    m.rotate_z(-a)
    return m


def star_position(chain: Sequence[Body], coordinated_time_ms: float,
                  star: Optional[CompanionStar] = None) -> Vec3:
    if not chain:
        raise ValueError("world_clock.star_position: empty body chain")
    combined = world_transform(chain[0], coordinated_time_ms)
    for body in chain[1:]:
        combined = combined * world_transform(body, coordinated_time_ms)
    inv = combined.inverse()
    if star is None or star.is_primary:
        return inv.translation
    return (inv * companion_transform(star, coordinated_time_ms)).translation


def surface_point(lat_rad: float, lon_rad: float, radius: float) -> Vec3:
    return (radius * math.cos(lat_rad) * math.cos(lon_rad),
            radius * math.cos(lat_rad) * math.sin(lon_rad),
            radius * math.sin(lat_rad))


def query_sunlight(chain: Sequence[Body], coordinated_time_ms: float,
                   lat_rad: float, lon_rad: float, radius: float,
                   *, spectral_subclass: int, star_radius: float,
                   binary: bool = False, star_type: int = 0,
                   depth: float = 0.0) -> float:
    from . import sunlight as _sunlight

    return _sunlight.query_sunlight(
        surface_point(lat_rad, lon_rad, radius),
        lat_rad, lon_rad,
        [_sunlight.Star(
            position=star_position(chain, coordinated_time_ms),
            radius=star_radius,
            spectral_subclass=spectral_subclass,
            binary=binary,
            star_type=star_type,
        )],
        depth=depth)


def query_sunlight_multi(chain: Sequence[Body], coordinated_time_ms: float,
                         lat_rad: float, lon_rad: float, radius: float,
                         stars: Sequence[dict], *, depth: float = 0.0) -> float:
    from . import sunlight as _sunlight

    built: List = []
    for s in stars:
        comp = s.get("companion")
        built.append(_sunlight.Star(
            position=star_position(chain, coordinated_time_ms, comp),
            radius=float(s.get("star_radius", 0.0)),
            spectral_subclass=int(s.get("spectral_subclass", 0)),
            binary=bool(s.get("binary", False)),
            star_type=int(s.get("star_type", 0)),
        ))
    return _sunlight.query_sunlight(
        surface_point(lat_rad, lon_rad, radius),
        lat_rad, lon_rad, built, depth=depth)


def is_dark(chain: Sequence[Body], coordinated_time_ms: float,
            lat_rad: float, lon_rad: float, radius: float,
            **star_kwargs) -> bool:
    from . import sunlight as _sunlight

    return _sunlight.is_dark(query_sunlight(
        chain, coordinated_time_ms, lat_rad, lon_rad, radius, **star_kwargs))
