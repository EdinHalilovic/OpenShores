
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple

Vec3 = Tuple[float, float, float]

IS_DARK_THRESHOLD = 0.30000001192092896

_BRIGHTNESS_SCALE = 2400000.0
_BRIGHTNESS_PER_SUBCLASS = 0.25
_BRIGHTNESS_NEGATIVE_SUBCLASS = 0.125
_DEPTH_EXTINCTION = 820.20997375328
_BINARY_HALVING = 0.5
_DISTANCE_EXPONENT = 2.0


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _length(v: Vec3) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def gravity_dir(lat_rad: float, lon_rad: float) -> Vec3:
    r = -1.0
    return (r * math.cos(lat_rad) * math.cos(lon_rad),
            r * math.cos(lat_rad) * math.sin(lon_rad),
            r * math.sin(lat_rad))


def up_dir(lat_rad: float, lon_rad: float) -> Vec3:
    d = gravity_dir(lat_rad, lon_rad)
    return (-d[0], -d[1], -d[2])


def light_attenuation(spectral_subclass: int, depth: float = 0.0,
                      binary: bool = False) -> float:
    sub = int(spectral_subclass)
    if sub > 127:
        sub -= 256
    brightness = (_BRIGHTNESS_NEGATIVE_SUBCLASS if sub < 0
                  else (sub + 1.0) * _BRIGHTNESS_PER_SUBCLASS)
    b = brightness * _BRIGHTNESS_SCALE
    if depth > 0.0:
        scale = 1.0 - depth / _DEPTH_EXTINCTION
        if scale <= 0.0:
            return 0.0
        b *= scale
    if binary:
        b *= _BINARY_HALVING
    if b == 0.0:
        raise ZeroDivisionError(
            "light_attenuation: zero brightness for subclass %r" % (sub,))
    return 1.0 / (b * b)


def compute_sun_light(surface_point: Vec3, star_point: Vec3,
                      attenuation: float, star_radius: float,
                      up: Vec3) -> float:
    delta = _sub(star_point, surface_point)
    dist = _length(delta)
    if dist == 0.0:
        return 0.0
    d = (delta[0] / dist, delta[1] / dist, delta[2] / dist)
    dot = _dot(up, d)

    ang_radius = math.atan2(star_radius, dist)
    theta = math.acos(max(-1.0, min(1.0, dot)))

    term = max(math.cos(theta - ang_radius),
               max(math.cos(theta + ang_radius), dot))
    if term <= 0.0:
        return 0.0
    if attenuation == 0.0:
        return 0.0
    return term / (math.pow(dist, _DISTANCE_EXPONENT) * attenuation)


@dataclass
class Star:

    position: Vec3
    radius: float
    spectral_subclass: int
    binary: bool = False
    star_type: int = 0


SKIPPED_STAR_TYPE = 7


def query_sunlight(surface_point: Vec3, lat_rad: float, lon_rad: float,
                   stars: Iterable[Star], *, depth: float = 0.0) -> float:
    up = up_dir(lat_rad, lon_rad)
    total = 0.0
    for s in stars:
        if s.star_type == SKIPPED_STAR_TYPE:
            continue
        att = light_attenuation(s.spectral_subclass, depth, s.binary)
        if att == 0.0:
            continue
        total += compute_sun_light(surface_point, s.position, att,
                                   s.radius, up)
    return total


def is_dark(sunlight: float) -> bool:
    return sunlight < IS_DARK_THRESHOLD


def sunlight_available(sunlight: float) -> bool:
    return not is_dark(sunlight)
