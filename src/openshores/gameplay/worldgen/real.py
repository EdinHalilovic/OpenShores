from __future__ import annotations

import struct
from typing import List, Tuple

from openshores.core.logging import get_logger
from openshores.protocol.rng import AuDice

logger = get_logger(__name__)

HAB_RANDOM = 0
HAB_SYSTEM = 1
HAB_HOMEWORLD = 2

ATMTYPE_TABLE = (4, 3, 2, 1, 0, 0, 0, 1, 2, 3, 4)

_TERRAIN_BASE_RADIUS_KM = 24854.85
_RELIEF_DIVISOR = 111.1106
_DETAIL_BIAS = 0.69897


def create_planet_physical(dice: AuDice, habitability: int) -> Tuple[int, int, int, int]:
    if habitability == HAB_HOMEWORLD:
        while True:
            size = dice.roll(2, 6)
            if 7 <= size <= 9:
                break
        dens_lo, dens_hi = 40, 70
        water_lo, water_hi = 20, 80
    elif habitability == HAB_SYSTEM:
        size = dice.roll(2, 6)
        dens_lo, dens_hi = 15, 85
        water_lo, water_hi = 10, 90
    else:
        size = dice.roll(2, 6)
        dens_lo, dens_hi = 0, 100
        water_lo, water_hi = 0, 100

    while True:
        density = dice.roll(2, 6, size - 8) * 10 + dice.roll(1, 10, -1)
        if dens_lo <= density <= dens_hi:
            break

    if habitability == HAB_HOMEWORLD:
        atm_type = 0
    elif habitability == HAB_SYSTEM:
        atm_type = 1 if dice.roll(2, 6) > 8 else 0
    else:
        atm_type = ATMTYPE_TABLE[dice.roll(2, 6, -2)]

    while True:
        base = dice.roll(2, 6, size - 7)
        if density < 21 or (habitability == HAB_RANDOM and atm_type > 2):
            base -= 4
        water = base * 10 + dice.roll(1, 10, -1)
        if water_lo <= water <= water_hi:
            break

    return size & 0xFF, density & 0xFF, atm_type & 0xFF, water & 0xFF


def roll_atm_water(dice: AuDice, size: int, habitability: int) -> Tuple[int, int, int]:
    if habitability == HAB_HOMEWORLD:
        dens_lo, dens_hi, water_lo, water_hi = 40, 70, 20, 80
    elif habitability == HAB_SYSTEM:
        dens_lo, dens_hi, water_lo, water_hi = 15, 85, 10, 90
    else:
        dens_lo, dens_hi, water_lo, water_hi = 0, 100, 0, 100
    _MAX_TRIES = 256
    density = None
    for _ in range(_MAX_TRIES):
        density = dice.roll(2, 6, size - 8) * 10 + dice.roll(1, 10, -1)
        if dens_lo <= density <= dens_hi:
            break
    else:
        density = max(dens_lo, min(dens_hi, density if density is not None
                                   else dens_lo))
        logger.warning('No atmosphere density in %d..%d is reachable for size=%d hab=%d (2d6+%d scaled by ten starts at %d); clamped to %d.',
                       dens_lo, dens_hi, size, habitability, size - 8,
                       10 * (size - 6), density)
    if habitability == HAB_HOMEWORLD:
        atm_type = 0
    elif habitability == HAB_SYSTEM:
        atm_type = 1 if dice.roll(2, 6) > 8 else 0
    else:
        atm_type = ATMTYPE_TABLE[dice.roll(2, 6, -2)]
    water = None
    for _ in range(_MAX_TRIES):
        base = dice.roll(2, 6, size - 7)
        if density < 21 or (habitability == HAB_RANDOM and atm_type > 2):
            base -= 4
        water = base * 10 + dice.roll(1, 10, -1)
        if water_lo <= water <= water_hi:
            break
    else:
        water = max(water_lo, min(water_hi, water if water is not None
                                  else water_lo))
        logger.warning("No hydrographics in %d..%d is reachable for size=%d "
                       "hab=%d; clamped to %d.",
                       water_lo, water_hi, size, habitability, water)
    return density & 0xFF, atm_type & 0xFF, water & 0xFF


_UNITS_PER_SIZE = 1000.0 / 1.609344 * 5.0


def create_terrain_data(dice: AuDice, size_byte: int, sea_byte: int,
                        zone_count: int = 1) -> Tuple[float, float, float, float, float, float]:
    n1 = dice.roll(1, 100000, -1)
    n2 = dice.roll(1, 100)
    noise_x = n2 / 100.0 + n1
    n1 = dice.roll(1, 100000, -1)
    n2 = dice.roll(1, 100)
    noise_y = n2 / 100.0 + n1

    size = max(1, int(size_byte) & 0xFF)
    amp = dice.roll(1, size * 10000, 10000) / 10000.0
    amp = ((size * _UNITS_PER_SIZE) / _TERRAIN_BASE_RADIUS_KM) * amp
    if amp < zone_count:
        amp = float(zone_count)

    x = dice.roll(1, 40, 45) / 100.0
    poly = x**3 + x*x + (x + 1.0) + x**4 + x**5 + x**6
    detail = (dice.roll(1, 261) / 1000.0 + _DETAIL_BIAS) * poly

    sea = int(sea_byte) & 0xFF
    if sea >= 128:
        sea -= 256
    r = (sea / _RELIEF_DIVISOR - 0.5) * 2.0
    relief = r * r
    if r < 0:
        relief = -relief

    f32 = lambda v: struct.unpack("<f", struct.pack("<f", v))[0]
    return (f32(amp), f32(detail), f32(x), f32(noise_x), f32(noise_y), f32(relief))


def auflora_dna_init(dice: AuDice, zone: int, lat_mod: int = 0) -> Tuple[int, int, int]:
    M = 0xFFFFFFFF
    w0 = w1 = w2 = 0

    w0 |= dice.roll(1, 8) & 7
    v = dice.roll(2, 30, lat_mod) // 2
    v = 0 if v < 0 else (31 if v > 31 else v)
    w0 |= (v & 0x1f) << 3
    w0 |= (dice.roll(1, 4) & 3) << 8
    w0 |= (dice.roll(1, 8) & 7) << 10
    w0 |= (dice.roll(1, 4) & 3) << 13
    w0 |= (dice.roll(1, 2) & 1) << 15
    w0 |= (dice.roll(1, 4) & 3) << 16
    w0 |= (dice.roll(1, 4) & 3) << 18
    w0 |= (dice.roll(1, 4) & 3) << 20
    w0 |= (dice.roll(1, 4) & 3) << 22

    zmod = (-1 if zone == 0 else (1 if zone >= 2 else 0)) - 1

    w0 |= (dice.roll(1, 8) & 7) << 24
    leaf = dice.roll(1, 8, zmod)
    if leaf < 0:
        pass
    elif leaf < 8:
        w0 |= (leaf & 7) << 27
    else:
        w0 |= 0x38000000
    w0 = (w0 | (dice.roll(1, 4) << 30)) & M

    branch = dice.roll(1, 8, zmod)
    if branch < 0:
        pass
    elif branch < 8:
        w1 |= branch & 7
    else:
        w1 |= 7
    w1 |= (dice.roll(1, 8) & 7) << 3
    w1 |= (dice.roll(1, 4) & 3) << 6
    w1 |= (dice.roll(1, 16) & 0xf) << 8
    w1 |= (dice.roll(1, 8) & 7) << 12
    w1 |= (dice.roll(1, 2) & 1) << 15
    w1 |= (dice.roll(1, 8) & 7) << 16
    w1 |= (dice.roll(1, 4) & 3) << 19
    w1 |= (dice.roll(1, 8) & 7) << 21
    w1 |= (dice.roll(1, 4) & 3) << 24
    w1 |= (dice.roll(1, 8) & 7) << 26
    w1 = (w1 | (dice.roll(1, 8) << 29)) & M

    w2 |= dice.roll(1, 8) & 7
    w2 |= (dice.roll(1, 4) & 3) << 3
    w2 |= (dice.roll(1, 8) & 7) << 5
    w2 |= (dice.roll(1, 8) & 7) << 8
    w2 |= (dice.roll(1, 8) & 7) << 11
    w2 |= (dice.roll(1, 4) & 3) << 14
    w2 |= (dice.roll(1, 2) & 1) << 16
    w2 |= (dice.roll(1, 4) & 3) << 17
    w2 |= (dice.roll(1, 4) & 3) << 19
    w2 |= (dice.roll(1, 8) & 7) << 21

    return w0 & M, w1 & M, w2 & M


_GEO_TINY = (6, 2, 2, 2, 2, 2, 1, 9)
_GEO_BIOME0 = (6, 6, 2, 2, 3, 1, 1, 4, 4, 4, 4, 4, 9, 9, 8, 8)
_GEO_BIOME1_DRY = (6, 6, 2, 2, 3, 1, 1, 4, 4, 4, 4, 9, 8)
_GEO_BIOME1_WET = (6, 6, 2, 2, 3, 5, 5, 5, 5, 5, 1, 1, 4, 4, 4, 4, 8)
_GEO_BIOME2_DRY = (6, 6, 2, 3, 3, 1, 1, 4, 4, 9, 8)
_GEO_BIOME2_WET = (6, 6, 2, 3, 3, 5, 5, 5, 5, 5, 1, 1, 4, 4, 4, 8)
_GEO_BIOME3_DRY = (6, 6, 6, 2, 3, 3, 1, 4, 9, 8)
_GEO_BIOME3_WET = (6, 6, 6, 2, 3, 3, 5, 5, 5, 5, 5, 1, 1, 4, 4)
_GEO_BIOME4 = (6, 6, 6, 6, 6, 2, 2, 3, 3, 3, 1, 1, 4, 9, 8)


def geology_pool(size: int, atm_density: int, water_pct: int, biome: int) -> Tuple[int, int]:
    if size < 3:
        return None, _GEO_TINY
    dry = water_pct < 20 or water_pct > 80
    if biome <= 0:
        pool = _GEO_BIOME0
    elif biome == 1:
        pool = _GEO_BIOME1_DRY if dry else _GEO_BIOME1_WET
    elif biome == 2:
        pool = _GEO_BIOME2_DRY if dry else _GEO_BIOME2_WET
    elif biome == 3:
        pool = _GEO_BIOME3_DRY if dry else _GEO_BIOME3_WET
    else:
        pool = _GEO_BIOME4
    return None, pool


def geology_feature_count(dice: AuDice, size: int, atm_density: int,
                          water_pct: int = 0) -> int:
    if size < 3:
        return dice.roll(2, 6, 4)
    mod = (((size // 3) - (atm_density // 20) - (water_pct // 20)) + 3) // 3
    return dice.roll(2, 4, mod)


def generate_globe(seed: int, habitability: int = HAB_HOMEWORLD,
                   biome: int = 2, flora_records_per_zone: int = 54):
    dice = AuDice(seed=(seed & 0xFFFFFFFF) or 1)

    size, density, atm_type, water = create_planet_physical(dice, habitability)
    zone_count = 1 if size <= 2 else 3
    terrain = create_terrain_data(dice, size, water, zone_count=zone_count)

    flora_zones: List[List[Tuple[int, int, int]]] = []
    for z in range(zone_count):
        band = 0 if z == 0 else (2 if z == zone_count - 1 else 1)
        recs = [auflora_dna_init(dice, band, lat_mod=0)
                for _ in range(flora_records_per_zone)]
        flora_zones.append(recs)

    geo_count = geology_feature_count(dice, size, density, water)
    _, geo_pool = geology_pool(size, density, water, biome)
    geo_types = [geo_pool[dice.roll(1, len(geo_pool), -1) % len(geo_pool)]
                 for _ in range(max(0, geo_count))]

    return {
        "size": size, "atm_density": density, "atm_type": atm_type,
        "water": water, "zone_count": zone_count,
        "terrain": terrain, "flora_zones": flora_zones,
        "geo_count": geo_count, "geo_types": geo_types,
    }


if __name__ == "__main__":
    g = generate_globe(0x5a3e9, HAB_HOMEWORLD, biome=2)
    logger.info("Homeworld: %s", {k: v for k, v in g.items()
                                  if k not in ("flora_zones", "terrain")})
    logger.info("Terrain floats: %s", [round(f, 4) for f in g["terrain"]])
    logger.info("Flora zones: %d x %d records", len(g["flora_zones"]),
                len(g["flora_zones"][0]))
    w0, w1, w2 = g["flora_zones"][0][0]
    logger.info("Sample tree DNA: %08x %08x %08x family=%d trunk=%d leaf=%d",
                w0, w1, w2, w0 & 7, (w0 >> 3) & 0x1f, (w0 >> 27) & 7)
