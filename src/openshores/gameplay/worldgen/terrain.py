
from __future__ import annotations

import math
import struct
from typing import Optional, Tuple

from openshores.protocol.rng import AuDice, AuNoise

TERRAIN_OCTAVES = 7

COS_SCALE_MUL = 0.999999
COS_SCALE_ADD = 1e-06

DATELINE_EPS = 1e-05
DATELINE_BLEND_FROM = 2.9670597283903604
POLE_BLEND_FROM = 1.3962634015954636
BLEND_WIDTH = 0.17453292519943295

POLE_AMP_FRACTION = 0.5

ATMOSPHERE_HEIGHT_MSL = 5000.0
_ALT_DIV = 10.0
_ALT_MUL = 4.0

DEG2RAD_F32 = 0.01745329238474369

LAND_LOCATION_TRIES = 1000

LAND_LATITUDE_LIMIT = 1.5533430576324463


def encode_globe_llf(lat: float, lon: float) -> bytes:
    return struct.pack(">ff", lon, lat)


def decode_globe_llf(blob: bytes, off: int = 0) -> Tuple[float, float]:
    lon, lat = struct.unpack_from(">ff", blob, off)
    return lat, lon


def _f32(v: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(v)))[0]


def altitude_scale(size: int) -> float:
    lo = _f32((ATMOSPHERE_HEIGHT_MSL + ATMOSPHERE_HEIGHT_MSL) / _ALT_DIV)
    if (int(size) & 0xFF) > 2:
        hi = _f32((ATMOSPHERE_HEIGHT_MSL * _ALT_MUL) / _ALT_DIV)
        return _f32((hi + lo) * 0.5)
    return lo


def _sample(lon: float, lat: float, amp: float, detail: float, bias: float,
            noise_x: float, noise_y: float, relief: float,
            cos_scale: float) -> float:
    n = AuNoise.cubic_perlin_noise(
        TERRAIN_OCTAVES, bias,
        (lon / math.pi) * cos_scale * amp + noise_x,
        (lat / math.pi) * amp + noise_y)
    return n / detail - relief


def terrain_altitude_msl(terrain: Tuple[float, ...], size: int,
                         lat: float, lon: float) -> float:
    amp, detail, bias, noise_x, noise_y, relief = (float(v) for v in terrain)
    pi = math.pi

    x = -pi if abs(lon - pi) <= DATELINE_EPS else lon

    cos_scale = math.cos(lat) * COS_SCALE_MUL + COS_SCALE_ADD
    h = _sample(x, lat, amp, detail, bias, noise_x, noise_y, relief, cos_scale)

    if x > DATELINE_BLEND_FROM:
        wrapped = _sample(x - 2.0 * pi, lat, amp, detail, bias,
                          noise_x, noise_y, relief, cos_scale)
        h = AuNoise.cosine_interpolate(wrapped, h, (pi - x) / BLEND_WIDTH)

    if lat > POLE_BLEND_FROM:
        pole = AuNoise.cubic_perlin_noise(
            TERRAIN_OCTAVES, bias, noise_x,
            amp * POLE_AMP_FRACTION + noise_y) / detail - relief
        d = pi * 0.5 - lat
        t = d / BLEND_WIDTH
        h = pole * (1.0 - t) + t * h
    elif lat < -POLE_BLEND_FROM:
        pole = AuNoise.cubic_perlin_noise(
            TERRAIN_OCTAVES, bias, noise_x,
            noise_y - amp * POLE_AMP_FRACTION) / detail - relief
        d = lat + pi * 0.5
        t = d / BLEND_WIDTH
        h = pole * (1.0 - t) + t * h

    return _f32(altitude_scale(size)) * _shape_relief(h, relief)


def random_ll(dice: AuDice) -> Tuple[float, float]:
    lon = _f32(dice.roll(1, 361, -181) * DEG2RAD_F32)
    lat = _f32(dice.roll(2, 91, -92) * DEG2RAD_F32)
    return lat, lon


def random_land_location(terrain: Tuple[float, ...], size: int, dice: AuDice,
                         min_altitude: float = 0.0
                         ) -> Tuple[float, float]:
    for _ in range(LAND_LOCATION_TRIES):
        lat, lon = random_ll(dice)
        if _f32(abs(lat)) <= LAND_LATITUDE_LIMIT:
            if terrain_altitude_msl(terrain, size, lat, lon) >= min_altitude:
                return lat, lon
    return random_ll(dice)


TWO_PI = 6.283185307179586
AU_IN_UNITS = 2400000.0
RING_WIDTH = 58562.85518055418
RING_ALTITUDE_INCREMENT = 186.41135767120016
RING_ALTITUDE_SCALE = 1500.0
RING_SEA_LEVEL_RADIUS = 0.0
RING_SEA_LEVEL_ALTITUDE = 0.0


def ring_section_angle(sections: int) -> float:
    return TWO_PI / int(sections)


def ring_section_count(orbit_radius: float) -> int:
    circumference = (orbit_radius * AU_IN_UNITS
                     + orbit_radius * AU_IN_UNITS) * math.pi
    return int(math.ceil(circumference / (RING_WIDTH * 13.0)))


def ring_aspect(sections: int, orbit_radius: float) -> float:
    arc = ring_section_angle(sections) * orbit_radius * AU_IN_UNITS
    return RING_WIDTH / arc


def _shape_relief(h: float, relief: float) -> float:
    rf = _f32(relief)
    if rf == 1.0 or (h <= 0.0 and rf != -1.0):
        h = h / (rf + 1.0)
        exponent = h + 2.0
        if exponent < 1.0:
            exponent = 1.0
        return -((-h) ** exponent)
    h = h / (1.0 - rf)
    if 0.0 < h < 1.0:
        h = h * h
    return h


def ring_terrain_altitude_msl(terrain: Tuple[float, ...], sections: int,
                              orbit_radius: float,
                              lat: float, lon: float) -> float:
    amp, detail, bias, noise_x, noise_y, relief = (float(v) for v in terrain)
    k = ring_aspect(sections, orbit_radius)
    n = AuNoise.cubic_perlin_noise(
        TERRAIN_OCTAVES, bias,
        (lon / math.pi) * amp + noise_x,
        (lat / math.pi) * amp * k + noise_y)
    return RING_ALTITUDE_SCALE * _shape_relief(n / detail - relief, relief)


def ring_random_ll(dice: AuDice) -> Tuple[float, float]:
    lon = _f32(dice.roll(1, 361, -181) * DEG2RAD_F32)
    lat = _f32(dice.roll(1, 181, -91) * DEG2RAD_F32)
    return lat, lon


def ring_random_land_location(terrain: Tuple[float, ...], sections: int,
                              orbit_radius: float, dice: AuDice,
                              min_altitude: float = 0.0
                              ) -> Tuple[float, float]:
    for _ in range(LAND_LOCATION_TRIES):
        lat, lon = ring_random_ll(dice)
        if _f32(abs(lat)) <= LAND_LATITUDE_LIMIT:
            if ring_terrain_altitude_msl(terrain, sections, orbit_radius,
                                         lat, lon) >= min_altitude:
                return lat, lon
    return ring_random_ll(dice)


def land_fraction(terrain: Tuple[float, ...], size: int, *,
                  samples: int = 24) -> float:
    land = 0
    total = 0
    for i in range(samples):
        lat = (-0.5 + (i + 0.5) / samples) * math.pi
        for j in range(samples * 2):
            lon = (-1.0 + (j + 0.5) / samples) * math.pi
            weight = math.cos(lat)
            total += weight
            if terrain_altitude_msl(terrain, size, lat, lon) > 0.0:
                land += weight
    return land / total if total else 0.0
