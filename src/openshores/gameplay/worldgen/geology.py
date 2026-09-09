
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

from openshores.protocol.rng import AuDice

from . import terrain as tr

GEO_VALLEY = 1
GEO_CRATER = 2
GEO_MESA = 3
GEO_VOLCANO = 4
GEO_RIVER = 5
GEO_CHASM = 6
GEO_HENGE = 7
GEO_VENT = 8
GEO_FISSURE = 9
GEO_ROAD_GRADE = 10
GEO_ROAD_DIRT = 11
GEO_ROAD_ASPHALT = 12
GEO_ROAD_CONCRETE = 13
GEO_LANDSCAPE = 14
GEO_BOMB_CRATER = 15

GEO_NAMES = {
    GEO_VALLEY: "Valley", GEO_CRATER: "Crater", GEO_MESA: "Mesa",
    GEO_VOLCANO: "Volcano", GEO_RIVER: "River", GEO_CHASM: "Chasm",
    GEO_HENGE: "Henge", GEO_VENT: "Vent", GEO_FISSURE: "Fissure",
    GEO_ROAD_GRADE: "RoadGrade", GEO_ROAD_DIRT: "RoadDirt",
    GEO_ROAD_ASPHALT: "RoadAsphalt", GEO_ROAD_CONCRETE: "RoadConcrete",
    GEO_LANDSCAPE: "Landscape", GEO_BOMB_CRATER: "BombCrater",
}

FT_PER_M = 3.28083989501312
TEN_M_FT = 32.8083989501312
FIFTY_M_FT = 164.041994750656
HUNDRED = 100.0
HALF = 0.5
HALF_PI_F = 1.5707963705062866
NEG_HALF_PI_F = -1.5707963705062866
PI_F = 3.1415927410125732
WALK_LAT_STEP = 0.007853982038795948
WALK_LON_STEP = 0.015707964077591896
TWO = 2.0


def _f32(v: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(v)))[0]


from .real import (  # noqa: E402
    _GEO_BIOME0,
    _GEO_BIOME1_DRY,
    _GEO_BIOME1_WET,
    _GEO_BIOME2_DRY,
    _GEO_BIOME2_WET,
    _GEO_BIOME3_DRY,
    _GEO_BIOME3_WET,
    _GEO_BIOME4,
    _GEO_TINY,
    geology_feature_count,
    geology_pool,
)


@dataclass
class GeoWorld:
    terrain: Tuple[float, ...]
    size: int
    water: int = 0
    is_satellite: bool = False

    @property
    def globe_radius(self) -> float:
        from .world_gen import globe_radius_units
        return globe_radius_units(self.size)

    @property
    def sea_level_radius(self) -> float:
        return self.globe_radius

    @property
    def sea_level_altitude(self) -> float:
        return self.globe_radius

    @property
    def altitude_increment(self) -> float:
        return self.globe_radius / HUNDRED

    @property
    def terrain_scale(self) -> float:
        lo = _f32((tr.ATMOSPHERE_HEIGHT_MSL + tr.ATMOSPHERE_HEIGHT_MSL) / 10.0)
        hi = _f32((tr.ATMOSPHERE_HEIGHT_MSL * 4.0) / 10.0)
        return _f32((hi + lo) * HALF)

    def altitude(self, lat: float, lon: float) -> float:
        return tr.terrain_altitude_msl(self.terrain, self.size, lat, lon)

    def random_land(self, dice: AuDice, min_alt: float = 0.0):
        return tr.random_land_location(self.terrain, self.size, dice, min_alt)

    def random_ll(self, dice: AuDice):
        return tr.random_ll(dice)


@dataclass
class GeoFeature:
    kind: int
    lat: float = 0.0
    lon: float = 0.0
    a: float = 0.0
    b: float = 0.0
    end_lat: Optional[float] = None
    end_lon: Optional[float] = None
    c: float = 0.0
    d: float = 0.0
    flags: int = 0
    slabs: int = 0
    byte2: int = 0
    auid: int = 0

    @property
    def name(self) -> str:
        return GEO_NAMES.get(self.kind, f"type{self.kind}")


def _init_crater(f: GeoFeature, w: GeoWorld, dice: AuDice) -> None:
    f.lat, f.lon = w.random_land(dice)
    elev = _f32(w.altitude(f.lat, f.lon))
    f.a = _f32(elev - dice.roll(1, 100, 50) * FT_PER_M)
    radius = _f32(dice.roll(1, 400, 100) * FT_PER_M)
    if w.is_satellite:
        radius = _f32((radius + radius) / 3.0)
    f.c = radius
    f.b = float(dice.roll(1, int(radius / 5.0) if radius >= 5.0 else 1, 1))


def _init_mesa(f: GeoFeature, w: GeoWorld, dice: AuDice) -> None:
    f.lat, f.lon = w.random_land(dice)
    elev = _f32(w.altitude(f.lat, f.lon))
    floor = w.altitude_increment * TWO
    if elev < floor:
        elev = _f32(floor)
    f.b = _f32(dice.roll(1, 101, -51) * FT_PER_M + elev)
    f.a = _f32(dice.roll(1, 200, 300) * FT_PER_M)


def _init_volcano(f: GeoFeature, w: GeoWorld, dice: AuDice) -> None:
    f.lat, f.lon = w.random_land(dice)
    f.a = _f32(dice.roll(1, 300, 100) * FT_PER_M)
    elev = _f32(w.altitude(f.lat, f.lon))
    scale = w.terrain_scale
    f.b = _f32(_f32(scale - dice.roll(1, int(scale * HALF))) - elev)


def _init_vent(f: GeoFeature, w: GeoWorld, dice: AuDice) -> None:
    f.lat, f.lon = w.random_ll(dice)
    f.a = _f32(dice.roll(1, 20) * FT_PER_M)
    elev = _f32(w.altitude(f.lat, f.lon))
    f.b = _f32(_f32(dice.roll(2, 6) * FT_PER_M + elev) - elev)


def _wrap_over_pole(lat: float, lon: float) -> Tuple[float, float]:
    if lat > HALF_PI_F:
        return _f32(lat + HALF_PI_F), _f32(lon + PI_F)
    if lat < NEG_HALF_PI_F:
        return _f32(lat + NEG_HALF_PI_F), _f32(lon + PI_F)
    return lat, lon


def _init_valley(f: GeoFeature, w: GeoWorld, dice: AuDice) -> None:
    f.lat, f.lon = w.random_land(dice)
    lat2 = _f32(dice.roll(1, 91, -46) * tr.DEG2RAD_F32 + f.lat)
    lon2 = _f32(dice.roll(1, 181, -91) * tr.DEG2RAD_F32 + f.lon)
    lat2, lon2 = _wrap_over_pole(lat2, lon2)
    f.end_lat, f.end_lon = lat2, lon2

    elev = _f32(w.altitude(f.lat, f.lon))
    if elev > 0.0:
        cut = dice.roll(1, 100, -90)
        f.a = _f32(cut * FT_PER_M)
        if _f32(elev - _f32(cut * FT_PER_M)) < FIFTY_M_FT:
            f.a = _f32(elev - dice.roll(1, 100, 50) * FT_PER_M)
    else:
        f.a = _f32(elev - dice.roll(1, 100) * FT_PER_M)
    f.c = _f32(dice.roll(1, 400, 100) * FT_PER_M)


def _walk_to_altitude(f_lat: float, f_lon: float, w: GeoWorld, dice: AuDice,
                      ceiling: float):
    for _ in range(101):
        deg = dice.roll(1, 361, -181)
        ang = _f32(deg * tr.DEG2RAD_F32)
        cos_a = _f32(math.cos(ang))
        sin_a = _f32(math.sin(ang))
        for step in range(100):
            lat = _f32(step * sin_a * WALK_LAT_STEP + f_lat)
            lon = _f32(step * cos_a * WALK_LON_STEP + f_lon)
            lat, lon = _wrap_over_pole(lat, lon)
            if _f32(w.altitude(lat, lon)) <= _f32(ceiling):
                return lat, lon
    return None


def _init_river(f: GeoFeature, w: GeoWorld, dice: AuDice) -> None:
    f.lat, f.lon = w.random_land(dice)
    depth_frac = _f32(-dice.roll(1, 90, 10) / HUNDRED)
    f.a = _f32(w.altitude_increment * depth_frac)
    n1 = dice.roll(1, 100000, -1)
    n2 = dice.roll(1, 100)
    f.d = _f32(n2 / HUNDRED + n1)
    f.b = _f32(dice.roll(1, 19, 80) / HUNDRED)
    f.c = _f32(dice.roll(1, 900, 100) * FT_PER_M)
    src_lat, src_lon = w.random_land(dice)
    f.end_lat, f.end_lon = src_lat, src_lon
    got = _walk_to_altitude(src_lat, src_lon, w, dice, f.a)
    if got is not None:
        f.lat, f.lon = got


def _init_chasm(f: GeoFeature, w: GeoWorld, dice: AuDice) -> None:
    f.lat, f.lon = w.random_land(dice)
    depth_frac = _f32(dice.roll(1, 90, 10) / HUNDRED)
    f.a = _f32(w.altitude_increment * depth_frac)
    n1 = dice.roll(1, 100000, -1)
    n2 = dice.roll(1, 100)
    f.d = _f32(n2 / HUNDRED + n1)
    f.c = _f32(dice.roll(1, 38, 60) / HUNDRED)
    ceiling = f.a + TEN_M_FT
    f.b = _f32(dice.roll(1, 90, 10) * FT_PER_M)
    f.lat, f.lon = w.random_land(dice)
    got = _walk_to_altitude(f.lat, f.lon, w, dice, ceiling)
    if got is not None:
        f.end_lat, f.end_lon = got
    else:
        f.end_lat, f.end_lon = f.lat, f.lon


def _init_fissure(f: GeoFeature, w: GeoWorld, dice: AuDice) -> None:
    f.lat, f.lon = w.random_ll(dice)
    lead = w.sea_level_radius - w.sea_level_altitude
    roll = dice.roll(1, 81, 9)
    f.a = _f32(lead - (w.sea_level_radius * roll) / HUNDRED)
    n1 = dice.roll(1, 100000, -1)
    n2 = dice.roll(1, 100)
    f.d = _f32(n2 / HUNDRED + n1)
    f.c = _f32(dice.roll(1, 38, 50) / HUNDRED)
    f.b = _f32(dice.roll(1, 36, 4) * FT_PER_M)
    f.end_lat, f.end_lon = w.random_ll(dice)


def _init_henge(f: GeoFeature, w: GeoWorld, dice: AuDice) -> None:
    f.lat, f.lon = w.random_land(dice, FT_PER_M)


_INITS: dict = {
    GEO_VALLEY: _init_valley,
    GEO_CRATER: _init_crater,
    GEO_MESA: _init_mesa,
    GEO_VOLCANO: _init_volcano,
    GEO_RIVER: _init_river,
    GEO_CHASM: _init_chasm,
    GEO_HENGE: _init_henge,
    GEO_VENT: _init_vent,
    GEO_FISSURE: _init_fissure,
}


def random_init(kind: int, w: GeoWorld, dice: AuDice) -> GeoFeature:
    fn = _INITS.get(int(kind))
    if fn is None:
        raise NotImplementedError(
            f"Geological type {kind} ({GEO_NAMES.get(kind, '?')}) is placed by play, not by generation")
    f = GeoFeature(kind=int(kind))
    fn(f, w, dice)
    return f


def create_geological_features(w: GeoWorld, orbit_zone: int, atm_density: int,
                              dice: AuDice) -> List[GeoFeature]:
    private = AuDice(dice.state)
    size = int(w.size) & 0xFF
    water = int(w.water) & 0xFF
    n = geology_feature_count(private, size, int(atm_density) & 0xFF, water)
    _count, pool = geology_pool(size, int(atm_density) & 0xFF, water,
                                int(orbit_zone))
    out: List[GeoFeature] = []
    for _ in range(max(0, n)):
        kind = pool[private.roll(1, len(pool), -1) % len(pool)]
        try:
            out.append(random_init(kind, w, private))
        except NotImplementedError:
            continue
    return out


def _body_16(f: GeoFeature) -> bytes:
    return tr.encode_globe_llf(f.lat, f.lon) + struct.pack(">ff", f.a, f.b)


def _body_crater(f: GeoFeature) -> bytes:
    return tr.encode_globe_llf(f.lat, f.lon) + struct.pack(">fff", f.a, f.b,
                                                           f.c)


def _body_valley(f: GeoFeature) -> bytes:
    return (tr.encode_globe_llf(f.lat, f.lon) + struct.pack(">f", f.a)
            + tr.encode_globe_llf(f.end_lat or 0.0, f.end_lon or 0.0)
            + struct.pack(">f", f.c))


def _body_henge(f: GeoFeature) -> bytes:
    return (tr.encode_globe_llf(f.lat, f.lon)
            + struct.pack(">BbB", f.flags & 0xFF, f.slabs, f.byte2 & 0xFF)
            + struct.pack(">I", f.auid & 0xFFFFFFFF)
            + struct.pack(">f", f.d))


def _body_chasm(f: GeoFeature) -> bytes:
    return (tr.encode_globe_llf(f.lat, f.lon) + struct.pack(">f", f.a)
            + tr.encode_globe_llf(f.end_lat or 0.0, f.end_lon or 0.0)
            + struct.pack(">fff", f.c, f.b, f.d))


def _body_river(f: GeoFeature) -> bytes:
    return (tr.encode_globe_llf(f.lat, f.lon) + struct.pack(">ff", f.a, f.b)
            + tr.encode_globe_llf(f.end_lat or 0.0, f.end_lon or 0.0)
            + struct.pack(">ff", f.c, f.d))


_BODIES: dict = {
    GEO_VALLEY: _body_valley,
    GEO_CRATER: _body_crater,
    GEO_MESA: _body_16,
    GEO_VOLCANO: _body_16,
    GEO_RIVER: _body_river,
    GEO_CHASM: _body_chasm,
    GEO_HENGE: _body_henge,
    GEO_VENT: _body_16,
    GEO_FISSURE: _body_chasm,
}

BODY_BYTES = {GEO_VALLEY: 24, GEO_CRATER: 20, GEO_MESA: 16, GEO_VOLCANO: 16,
              GEO_RIVER: 32, GEO_CHASM: 32, GEO_HENGE: 19, GEO_VENT: 16,
              GEO_FISSURE: 32}


def encode(features: Sequence[GeoFeature]) -> bytes:
    out = bytearray(struct.pack(">b", len(features) & 0x7F))
    for f in features:
        body = _BODIES.get(f.kind)
        if body is None:
            raise ValueError(f"No serialiser for geological type {f.kind}")
        out += struct.pack(">b", f.kind)
        out += body(f)
    return bytes(out)


def decode(blob: bytes) -> List[GeoFeature]:
    if not blob:
        return []
    (count,) = struct.unpack_from(">b", blob, 0)
    off = 1
    out: List[GeoFeature] = []
    for _ in range(count):
        (kind,) = struct.unpack_from(">b", blob, off)
        off += 1
        n = BODY_BYTES.get(kind)
        if n is None:
            break
        f = GeoFeature(kind=kind)
        f.lat, f.lon = tr.decode_globe_llf(blob, off)
        if kind in (GEO_MESA, GEO_VOLCANO, GEO_VENT):
            f.a, f.b = struct.unpack_from(">ff", blob, off + 8)
        elif kind == GEO_CRATER:
            f.a, f.b, f.c = struct.unpack_from(">fff", blob, off + 8)
        elif kind == GEO_VALLEY:
            (f.a,) = struct.unpack_from(">f", blob, off + 8)
            f.end_lat, f.end_lon = tr.decode_globe_llf(blob, off + 12)
            (f.c,) = struct.unpack_from(">f", blob, off + 20)
        elif kind == GEO_HENGE:
            f.flags, f.slabs, f.byte2 = struct.unpack_from(">BbB", blob,
                                                           off + 8)
            (f.auid,) = struct.unpack_from(">I", blob, off + 11)
            (f.d,) = struct.unpack_from(">f", blob, off + 15)
        elif kind in (GEO_CHASM, GEO_FISSURE):
            (f.a,) = struct.unpack_from(">f", blob, off + 8)
            f.end_lat, f.end_lon = tr.decode_globe_llf(blob, off + 12)
            f.c, f.b, f.d = struct.unpack_from(">fff", blob, off + 20)
        elif kind == GEO_RIVER:
            f.a, f.b = struct.unpack_from(">ff", blob, off + 8)
            f.end_lat, f.end_lon = tr.decode_globe_llf(blob, off + 16)
            f.c, f.d = struct.unpack_from(">ff", blob, off + 24)
        off += n
        out.append(f)
    return out


def world_geo_blob(world, dice: AuDice) -> bytes:
    gw = GeoWorld(terrain=world.terrain, size=world.size,
                  water=world.water & 0xFF,
                  is_satellite=world.is_satellite)
    feats = create_geological_features(gw, world.orbit_zone,
                                       world.atm_density, dice)
    return encode(feats)
