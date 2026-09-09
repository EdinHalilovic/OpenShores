
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from openshores.protocol.rng import AuDice

from . import fauna as fa
from . import geology as geo
from . import terrain as tr

MIN_SECTION_LENGTH = 761317.1173472044

RING_AMP_REFERENCE = 156167.625

RING_BAND_LO = 25
RING_BAND_HI = 75

RING_FLORA_LAT_MOD = 6

RING_RESOURCE_ZONES = 2

RING_GEO_POOL = (6, 6, 6, 2, 2, 3, 3, 5, 5, 5, 5, 5, 5, 5, 1, 1)


def _f32(v: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(v)))[0]


def _trunc_div(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def section_count(orbit_radius: float) -> int:
    return tr.ring_section_count(orbit_radius)


@dataclass
class RingSection:

    index: int = 0
    orbit_radius: float = 0.0
    orbit_zone: int = 0
    sections: int = 1
    atm_density: int = 0
    atm_type: int = 0
    water: int = 0
    terrain: Optional[Tuple[float, ...]] = None
    features: List[geo.GeoFeature] = field(default_factory=list)
    name: str = ""

    size: int = 0x32

    def resource_zones(self) -> int:
        return RING_RESOURCE_ZONES

    def can_have_fauna(self) -> bool:
        return True

    def dq_terrain(self) -> fa.DqTerrain:
        return fa.DqTerrain(atm_density=self.atm_density & 0xFF,
                            atm_type=self.atm_type & 0xFF,
                            size=self.size,
                            water=self.water & 0xFF,
                            orbit_zone=self.orbit_zone & 0xFF)

    def geo_world(self) -> "RingGeoWorld":
        return RingGeoWorld(section=self)


def surface_location(s: "RingSection", lat: float, lon: float,
                     altitude: float = 0.0) -> Tuple[float, float, float]:
    R = float(s.orbit_radius) * tr.AU_IN_UNITS
    theta = -(float(lon) / float(int(s.sections) or 1))

    x = -R * math.sin(theta)
    z = -R * math.cos(theta)

    if altitude != 0.0:
        mag = math.hypot(x, z)
        if mag != 0.0:
            k = (R - float(altitude)) / mag
            x *= k
            z *= k

    y = float(lat) / (math.pi / 2.0) * tr.RING_WIDTH * 0.5
    return (x, y, z + R)


def gravity_dir(s: "RingSection",
                pos: Tuple[float, float, float]) -> Tuple[float, float, float]:
    R = float(s.orbit_radius) * tr.AU_IN_UNITS
    x, _y, z = pos
    a, b = float(x), float(z) - R
    mag = math.hypot(a, b)
    if mag == 0.0:
        return (1.0, 0.0, 0.0)
    return (a / mag, 0.0, b / mag)


@dataclass
class RingGeoWorld:

    section: RingSection

    @property
    def size(self) -> int:
        return self.section.size

    @property
    def water(self) -> int:
        return self.section.water & 0xFF

    @property
    def is_satellite(self) -> bool:
        return False

    @property
    def terrain(self) -> Tuple[float, ...]:
        return self.section.terrain

    @property
    def globe_radius(self) -> float:
        return 0.0

    @property
    def sea_level_radius(self) -> float:
        return tr.RING_SEA_LEVEL_RADIUS

    @property
    def sea_level_altitude(self) -> float:
        return tr.RING_SEA_LEVEL_ALTITUDE

    @property
    def altitude_increment(self) -> float:
        return tr.RING_ALTITUDE_INCREMENT

    @property
    def terrain_scale(self) -> float:
        return tr.RING_ALTITUDE_SCALE

    def altitude(self, lat: float, lon: float) -> float:
        return tr.ring_terrain_altitude_msl(
            self.section.terrain, self.section.sections,
            self.section.orbit_radius, lat, lon)

    def random_land(self, dice: AuDice, min_alt: float = 0.0):
        return tr.ring_random_land_location(
            self.section.terrain, self.section.sections,
            self.section.orbit_radius, dice, min_alt)

    def random_ll(self, dice: AuDice):
        return tr.ring_random_ll(dice)


def create_terrain_data(s: RingSection, dice: AuDice) -> tuple:
    n1 = dice.roll(1, 100000, -1)
    n2 = dice.roll(1, 100)
    noise_x = _f32(_f32(n2) / 100.0 + _f32(n1))

    n1 = dice.roll(1, 100000, -1)
    n2 = dice.roll(1, 100)
    noise_y = _f32(_f32(n2) / 100.0 + _f32(n1))

    arc = (tr.ring_section_angle(s.sections) * s.orbit_radius
           * tr.AU_IN_UNITS)
    amp = _f32(dice.roll(1, 80000, 10000) / 10000.0)
    amp = _f32(amp * _f32(_f32(arc) / RING_AMP_REFERENCE))
    zones = s.resource_zones()
    if amp < zones:
        amp = float(zones)

    x = _f32(dice.roll(1, 40, 45) / 100.0)
    detail = _f32(x ** 3 + x * x + (x + 1.0) + x ** 4 + x ** 5 + x ** 6)
    detail = _f32(_f32(dice.roll(1, 261) / 1000.0 + 0.69897) * detail)

    r = _f32(_f32(_sc(s.water) / 111.11100006103516) - 0.5)
    r = _f32(r + r)
    relief = _f32(r * r)
    if r < 0.0:
        relief = -relief

    s.terrain = (amp, detail, x, noise_x, noise_y, relief)
    return s.terrain


def _sc(v: int) -> int:
    v &= 0xFF
    return v - 256 if v >= 128 else v


RING_TERRAIN_STEPS = 7


def geo_feature_count(dice: AuDice, water: int, atm_density: int) -> int:
    w = _trunc_div(int(water) & 0xFF, -20)
    d = _trunc_div(_sc(int(atm_density)), 20)
    return dice.roll(2, 4, _trunc_div(w - d + 8, 3))


def create_geological_features(s: RingSection, dice: AuDice
                               ) -> List[geo.GeoFeature]:
    w = s.geo_world()
    n = geo_feature_count(dice, s.water, s.atm_density)
    out: List[geo.GeoFeature] = []
    for _ in range(max(0, n)):
        kind = RING_GEO_POOL[dice.roll(1, 16, -1) % len(RING_GEO_POOL)]
        out.append(geo.random_init(kind, w, dice))
    return out


def deplanetflora_init_ringworld(dice: AuDice):
    from .real import auflora_dna_init
    from .world_gen import DNA_PER_TERRAIN_FLORA, FLORA_SLOT_ORDER

    bands = []
    for zone in range(3):
        slots = [None] * DNA_PER_TERRAIN_FLORA
        for i in FLORA_SLOT_ORDER:
            slots[i] = auflora_dna_init(dice, zone, RING_FLORA_LAT_MOD)
        bands.append(slots)
    return bands


def _consume_flora(dice: AuDice) -> None:
    from .world_gen import FLORA_STEPS_PER_ZONE
    dice.advance(RING_RESOURCE_ZONES * FLORA_STEPS_PER_ZONE)


def _consume_fauna(s: RingSection, dice: AuDice) -> None:
    dice.advance(RING_RESOURCE_ZONES * fa.fauna_steps(s.size, s.water))


def flora_steps() -> int:
    from .world_gen import FLORA_STEPS_PER_ZONE
    return RING_RESOURCE_ZONES * FLORA_STEPS_PER_ZONE


def fauna_steps(water: int) -> int:
    return RING_RESOURCE_ZONES * fa.fauna_steps(0x32, water)


def _roll_band(dice: AuDice, penalty: bool) -> int:
    while True:
        base = _sc(dice.roll(2, 6))
        if penalty:
            base = _sc(base - 4)
        v = _sc(dice.roll(1, 10, -1) + base * 10)
        if ((v - RING_BAND_LO) & 0xFF) <= 50:
            return v


def create_first_ringworld_section(dice: AuDice, orbit_radius: float,
                                   orbit_zone: int, sections: int
                                   ) -> RingSection:
    s = RingSection(index=0, orbit_radius=orbit_radius, orbit_zone=orbit_zone,
                    sections=sections)
    s.atm_density = _roll_band(dice, penalty=False)
    s.atm_type = 1 if dice.roll(2, 6) > 8 else 0
    s.water = _roll_band(dice, penalty=s.atm_density < 21)
    create_terrain_data(s, dice)
    _consume_flora(dice)
    _consume_fauna(s, dice)
    s.features = create_geological_features(s, dice)
    return s


def create_ringworld_section(dice: AuDice, index: int,
                             first: RingSection) -> RingSection:
    s = RingSection(index=index, orbit_radius=first.orbit_radius,
                    orbit_zone=first.orbit_zone, sections=first.sections,
                    atm_density=first.atm_density, atm_type=first.atm_type)
    s.water = _roll_band(dice, penalty=s.atm_density < 21)
    create_terrain_data(s, dice)
    _consume_flora(dice)
    _consume_fauna(s, dice)
    s.features = create_geological_features(s, dice)
    return s


def create_ringworld(dice: AuDice, orbit_radius: float,
                     orbit_zone: int) -> List[RingSection]:
    n = section_count(orbit_radius)
    first = create_first_ringworld_section(dice, orbit_radius, orbit_zone, n)
    out = [first]
    for i in range(1, n):
        out.append(create_ringworld_section(dice, i, first))
    return out
