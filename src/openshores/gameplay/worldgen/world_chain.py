
from __future__ import annotations

import math
import struct
from typing import List, Optional, Tuple

from . import world_clock as wc

GAME_UNITS_PER_AU = 2_400_000.0


def as_double(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    b = bytes(v)
    return struct.unpack("<d", b)[0] if len(b) == 8 else None


def as_byte(v) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    b = bytes(v)
    return b[0] if b else None


def synthetic_system_seed(system_id: int) -> int:
    from . import procgen as hp
    from openshores.protocol.rng import AuNoise

    K = 2147483647.0
    s = hp._u32(int(system_id)) or 1
    for _ in range(2):
        n = AuNoise.integer_noise1(s & 0xFF, hp._i32(s))
        s = hp._u32(s + hp._trunc_to_i32(n * K))
        if s == 0:
            s = 1
    return s


def world_gen_seed(system_seed: int, orbit_zone: int, orbit_radius_au: float,
                   *, star_number: int = 0) -> int:
    from . import procgen as hp

    star = hp.Star(parent_solar_system=hp.SolarSystem(cached_seed=int(system_seed)),
                   star_number=int(star_number))
    return hp.World(parent_star=star,
                    orbit_index=int(orbit_zone) & 0xFF,
                    orbit_radius=float(orbit_radius_au)).gen_seed()


def make_body(globe_row: dict, system_seed: int, *, breathable: bool,
              is_moon: bool = False, star_number: int = 0) -> wc.Body:
    au = as_double(globe_row.get("orbitRadius"))
    zone = as_byte(globe_row.get("orbitZone")) or 0
    if au is None:
        raise ValueError("a_WorldGlobe.orbitRadius is not a double")
    wid = int(globe_row.get("id") or 0) & 0xFFFFFFFF
    return wc.Body(
        world_id=wid,
        gen_seed=world_gen_seed(system_seed, zone, au, star_number=star_number),
        orbit_radius=au,
        orbit_zone=zone,
        is_moon=bool(is_moon),
        breathable=bool(breathable),
    )


def body_chain(globe_row: dict, parent_globe_row: Optional[dict],
               system_seed: Optional[int], *, breathable: bool,
               star_count: int = 1) -> Optional[Tuple[List[wc.Body], float]]:
    if not system_seed:
        return None
    radius = globe_row.get("radius")
    if not radius:
        return None
    try:
        if parent_globe_row is not None:
            planet = make_body(parent_globe_row, system_seed, breathable=False)
            moon = make_body(globe_row, system_seed, breathable=breathable,
                             is_moon=True)
            return [planet, moon], float(radius)
        return [make_body(globe_row, system_seed, breathable=breathable)], \
            float(radius)
    except (ValueError, TypeError, KeyError):
        return None


SIZE_CLASS_KM_PER_STEP = 1000.0
SIZE_CLASS_MAX = 255


def size_class_from_radius(radius) -> int:
    try:
        v = float(radius)
    except (TypeError, ValueError):
        return 0
    if v <= SIZE_CLASS_MAX:
        return max(0, int(round(v)))
    return max(0, min(SIZE_CLASS_MAX,
                      int(round(v / SIZE_CLASS_KM_PER_STEP))))


def spectral_subclass(star_row: dict) -> Optional[int]:
    if not star_row:
        return None
    v = star_row.get("habZone")
    if v is None:
        return None
    if isinstance(v, float) and v != int(v):
        return None
    if isinstance(v, (bytes, bytearray)):
        v = as_byte(v)
    try:
        iv = int(v)
    except (TypeError, ValueError):
        return None
    return iv if 0 <= iv <= 255 else None


habitable_orbit = spectral_subclass


def hydrographics(globe_row: dict) -> int:
    v = globe_row.get("water")
    if isinstance(v, (bytes, bytearray)) and len(bytes(v)) != 1:
        return 0
    return as_byte(v) or 0


def globe_properties(globe_row: dict, star_row: Optional[dict] = None, *,
                     size_class: Optional[int] = None,
                     is_satellite: bool = False,
                     breathable: bool = False,
                     average_foliage: Optional[int] = None):
    from . import zone_resources as zr

    if size_class is None:
        size_class = size_class_from_radius(globe_row.get("radius"))
    gp = zr.GlobeProperties(
        climate_class=as_byte(globe_row.get("orbitZone")) or 0,
        size_class=int(size_class),
        star_type=(as_byte(star_row.get("specType")) if star_row else 0) or 0,
        atmosphere_type=as_byte(globe_row.get("atmType")) or 0,
        hydrographics=hydrographics(globe_row),
        msl_atmosphere_density=as_byte(globe_row.get("atmDensity")) or 0,
        average_foliage=0,
        is_satellite=bool(is_satellite),
    )
    gp.average_foliage = (zr.average_foliage(gp) if average_foliage is None
                          else int(average_foliage))
    gp.can_have_fauna = bool(breathable) and gp.habitable_size()
    return gp


def city_zone(globe_row: dict, star_row: Optional[dict], system_seed: int,
              longitude_rad: float, *, size_class: Optional[int] = None,
              is_satellite: bool = False, breathable: bool = False,
              average_foliage: Optional[int] = None):
    from . import zone_resources as zr

    gp = globe_properties(globe_row, star_row, size_class=size_class,
                          is_satellite=is_satellite, breathable=breathable,
                          average_foliage=average_foliage)
    seed = world_gen_seed(system_seed,
                          as_byte(globe_row.get("orbitZone")) or 0,
                          as_double(globe_row.get("orbitRadius")) or 0.0)
    n = zr.resource_zones(gp.size_class)
    return zr.query_natural_resources(gp, zr.resource_zone(longitude_rad, n), seed)


def is_dark_at(chain: List[wc.Body], radius: float, coordinated_time_ms: float,
               lat_rad: float, lon_rad: float, *,
               spectral_subclass: int, star_radius: float) -> bool:
    return wc.is_dark(chain, coordinated_time_ms, float(lat_rad), float(lon_rad),
                      float(radius), spectral_subclass=int(spectral_subclass),
                      star_radius=float(star_radius))


STAR_ORBIT_STEP_AU = 0.25
STAR_FALLBACK_ORBIT_AU = 0.125
STAR_RADIUS_SHRINK_AU = 0.01


def star_radius(min_orbit: int, zone0: int = 0) -> float:
    mo = as_signed_byte(min_orbit)
    r = (STAR_FALLBACK_ORBIT_AU if mo < 0
         else (float(mo) + 1.0) * STAR_ORBIT_STEP_AU)
    if mo < 1:
        r -= float((int(zone0) & 0xFF) - 1) * STAR_RADIUS_SHRINK_AU
    return r * wc.GAME_UNITS_PER_AU


def as_signed_byte(v) -> int:
    b = as_byte(v)
    if b is None:
        return -1
    return b - 256 if b >= 128 else b


def star_descriptors(star_rows: List[dict], system_seed: int) -> List[dict]:
    out: List[dict] = []
    primaries = [r for r in star_rows if as_signed_byte(r.get("orbit")) < 0]
    companions = [r for r in star_rows if as_signed_byte(r.get("orbit")) >= 0]
    for n, row in enumerate(primaries + companions):
        orbit = as_signed_byte(row.get("orbit"))
        gen_seed = star_gen_seed(system_seed, star_number=n)
        out.append({
            "spectral_subclass": as_byte(row.get("habZone")) or 0,
            "star_radius": star_radius(row.get("radius"),
                                       _zone0(row.get("orbitZones"))),
            "star_type": as_byte(row.get("specType")) or 0,
            "binary": len(star_rows) > 1,
            "companion": wc.CompanionStar(gen_seed=gen_seed,
                                          companion_orbit=orbit),
        })
    return out


def _zone0(orbit_zones) -> int:
    if not orbit_zones:
        return 0
    b = bytes(orbit_zones) if not isinstance(orbit_zones, (int, float)) else b""
    return b[0] if b else 0


def star_gen_seed(system_seed: int, *, star_number: int = 0) -> int:
    from . import procgen as hp

    return hp.Star(
        parent_solar_system=hp.SolarSystem(cached_seed=int(system_seed)),
        star_number=int(star_number)).gen_seed()


def query_sunlight_at(chain: List[wc.Body], radius: float,
                      coordinated_time_ms: float, lat_rad: float,
                      lon_rad: float, stars: List[dict]) -> float:
    return wc.query_sunlight_multi(chain, coordinated_time_ms, float(lat_rad),
                                   float(lon_rad), float(radius), stars)


def is_dark_at_multi(chain: List[wc.Body], radius: float,
                     coordinated_time_ms: float, lat_rad: float,
                     lon_rad: float, stars: List[dict]) -> bool:
    from . import sunlight as _sunlight

    return _sunlight.is_dark(query_sunlight_at(
        chain, radius, coordinated_time_ms, lat_rad, lon_rad, stars))
