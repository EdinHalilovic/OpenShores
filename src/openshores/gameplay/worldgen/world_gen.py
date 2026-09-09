
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from openshores.protocol.rng import AuDice

from . import fauna as fa
from . import galaxy as gg

HAB_RANDOM = 0
HAB_SYSTEM = 1
HAB_HOMEWORLD = 2
HAB_RINGWORLD = 3

DEFAULT_GEN_HAB = HAB_SYSTEM

AU_PER_ORBIT = 0.25

AU_IN_UNITS = 2400000.0

UNITS_PER_SIZE = 1000.0 / 1.609344 * 5.0

TERRAIN_REF_RADIUS = 24854.84765625

MOON_GAP = 40000.0
MOON_STEP = 42500.0
MOON_LIMIT = 278750.0

MIN_SECTION_LENGTH = 761317.1173472044

ATM_TYPE_TABLE = (4, 3, 2, 1, 0, 0, 0, 1, 2, 3, 4)

BLACK_HOLE_TYPE_TABLE = (0, 0, 0, 1, 6, 1, 6, 1, 6, 1, 6, 1, 6, 1, 4, 6)
BLACK_HOLE_SIZE_TABLE = (0, 0, 0, 8, 8, 7, 7, 6, 6, 5, 5, 4, 4, 3, 3, 2)

BLACK_HOLE_GALAXY_SCALE = -9.0
BLACK_HOLE_REFERENCE_GALAXY = 3

COMPANION_TYPE_TABLE = (0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 6, 6, 6)
COMPANION_SIZE_TABLE = (0, 1, 2, 3, 4, 7, 7, 5, 5, 6, 7, 7, 7)

RELIEF_DIV = 111.11100006103516
DETAIL_BIAS = 0.69897


def _f32(v: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(v)))[0]


def globe_radius_units(size: int) -> float:
    return (int(size) & 0xFF) * UNITS_PER_SIZE


def radius_km(size: int) -> float:
    return (int(size) & 0xFF) * 1000.0


def _sc(v: int) -> int:
    v &= 0xFF
    return v - 256 if v >= 128 else v


AUFLORA_DNA_STEPS = 36

DNA_PER_TERRAIN_FLORA = 18

FLORA_STEPS_PER_ZONE = 3 * DNA_PER_TERRAIN_FLORA * AUFLORA_DNA_STEPS

DHDNA_RANDOMIZE_STEPS = fa.DHDNA_RANDOMIZE_STEPS

FAUNA_RECORD_STEPS = DHDNA_RANDOMIZE_STEPS + 2

FAUNA_ELEV_BANDS = fa.FAUNA_ELEV_BANDS
FAUNA_SUBZONES = fa.FAUNA_TIMES_OF_DAY
FAUNA_KINDS = fa.FAUNA_SLOTS
FAUNA_RECORDS = fa.FAUNA_RECORDS_PER_ZONE

fauna_steps = fa.fauna_steps


@dataclass
class Star:

    index: int
    star_type: int = -1
    subclass: int = -1
    size: int = -1
    type_roll: int = -1
    size_roll: int = -1
    companion_orbit: int = -1
    orbits_available: float = 0.0
    zones: List[int] = field(default_factory=lambda: [0] * 16)
    hab_orbit: int = -1
    min_orbit: int = -1
    companions: List["Star"] = field(default_factory=list)
    worlds: List["World"] = field(default_factory=list)

    @property
    def is_primary(self) -> bool:
        return self.companion_orbit < 0

    @property
    def has_planets(self) -> bool:
        return self.star_type != gg.STAR_TYPE_NO_PLANETS

    def zone_at(self, i: int) -> int:
        if 0 <= i < 16:
            return self.zones[i]
        if i == 16:
            return self.size & 0xFF
        return 0

    def init_zones(self) -> None:
        zones, hab, mn = gg.init_zones(self.size, self.star_type, self.subclass)
        self.zones = list(zones)
        self.hab_orbit = hab
        self.min_orbit = mn


@dataclass
class World:

    kind: str
    orbit: int
    orbit_zone: int
    orbit_radius: float
    name: str = ""
    habitability: int = HAB_RANDOM
    is_satellite: bool = False
    size: int = 0
    atm_density: int = 0
    atm_type: int = 0
    water: int = 0
    terrain: Optional[tuple] = None
    sections: int = 0
    ring_sections: List = field(default_factory=list)
    moons: List["World"] = field(default_factory=list)

    @property
    def radius_km(self) -> float:
        return radius_km(self.size)

    def has_breathable_atmosphere(self) -> bool:
        return ((self.atm_type & 0xFF) < 2
                and ((_sc(self.atm_density) - 15) & 0xFF) < 0x47
                and ((self.orbit_zone - 1) & 0xFF) < 3)

    def can_have_fauna(self) -> bool:
        size = self.size & 0xFF
        if size == 2:
            if self.is_satellite:
                return False
        elif ((size - 2) & 0xFF) > 10:
            return False
        return self.has_breathable_atmosphere()

    def is_suitable_home_planet(self) -> bool:
        if self.orbit_zone != 2:
            return False
        size = self.size & 0xFF
        if size == 2:
            if self.is_satellite:
                return False
        elif ((size - 2) & 0xFF) > 10:
            return False
        return ((self.atm_type & 0xFF) == 0
                and ((_sc(self.atm_density) - 15) & 0xFF) < 0x47
                and ((_sc(self.water) - 15) & 0xFF) < 0x47)

    def is_habitable(self, hab: int) -> bool:
        size = self.size & 0xFF
        if hab == HAB_RANDOM:
            if self.orbit_zone != 2:
                return False
            if size == 2:
                return not self.is_satellite
            return ((size - 2) & 0xFF) < 11
        if hab == HAB_SYSTEM:
            return self.orbit_zone == 2 and self.has_breathable_atmosphere()
        if hab == HAB_HOMEWORLD:
            return self.is_suitable_home_planet()
        return False

    def resource_zones(self) -> int:
        return 3 if (self.size & 0xFF) > 2 else 1

    def walk(self):
        yield self
        for m in self.moons:
            yield from m.walk()


def gen_primary_type(star: Star, dice: AuDice) -> int:
    idx = dice.roll(1, 13, -1)
    star.star_type = gg.PRIMARY_TYPE_TABLE[idx]
    if star.star_type == 1:
        if gg.PRIMARY_TYPE_TABLE[dice.roll(1, 13) - 1] == 1:
            star.star_type = 0
    while True:
        sub = dice.roll(1, 10, -1)
        star.subclass = sub
        if star.star_type != 0 or sub >= 5:
            break
    return idx


def gen_primary_size(star: Star, dice: AuDice) -> int:
    idx = dice.roll(1, 13, -1)
    size = gg.PRIMARY_SIZE_TABLE[idx]
    if size == 4:
        size = 5 if star.star_type > 4 else 4
    if size == 6 and (star.star_type < 3
                      or (star.star_type == 3 and star.subclass < 5)):
        size = 5
    star.size = size
    return idx


def gen_companion_orbit(primary: Star, dice: AuDice, which: int) -> int:
    roll = dice.roll(2, 6)
    if which != 0:
        roll += 4
    if roll >= 12:
        orbit = 15
    elif roll <= 3:
        orbit = 0
    elif roll == 4:
        orbit = 1
    elif roll == 5:
        orbit = 2
    elif roll == 6:
        orbit = 3
    else:
        orbit = dice.roll(1, 6, {7: 4, 8: 5, 9: 6, 10: 7, 11: 8}[roll])
    while 0 <= orbit < 16 and primary.zones[orbit] < 2:
        orbit += 1
    return 0 if orbit > 15 else orbit


def min_orbit_available_from(primary: Star, orbit: int) -> int:
    lo = hi = int(orbit)
    while lo > 0 and primary.zone_at(lo - 1) >= 2 \
            and (hi > 15 or primary.zone_at(hi + 1) >= 2):
        lo -= 1
        hi += 1
    return lo


def gen_companion_type(star: Star, dice: AuDice, primary_type_roll: int) -> None:
    idx = dice.roll(1, 6, int(primary_type_roll / 2) - 1)
    idx = 0 if idx < 0 else (12 if idx > 12 else idx)
    star.star_type = COMPANION_TYPE_TABLE[idx]
    while True:
        sub = dice.roll(1, 10, -1)
        star.subclass = sub
        if star.star_type != 0 or sub >= 5:
            break


def gen_companion_size(star: Star, dice: AuDice, primary_size_roll: int) -> None:
    idx = dice.roll(1, 6, int(primary_size_roll / 2) - 1)
    idx = 0 if idx < 0 else (12 if idx > 12 else idx)
    size = COMPANION_SIZE_TABLE[idx]
    if size == 4:
        size = 5 if 0 <= star.star_type - 5 <= 1 else 4
    if size == 6 and (star.star_type < 3
                      or (star.star_type == 3 and star.subclass < 5)):
        size = 5
    star.size = size


def reserve_zones(primary: Star, lo: int, hi: int) -> None:
    i = int(lo)
    while i <= int(hi) and i < 16:
        if primary.zones[i] >= 2:
            primary.zones[i] = 1
        i += 1


def _black_hole_galaxy_index(galaxy_index: int) -> int:
    ratio = (gg.GALAXIES[int(galaxy_index)].radius
             / gg.GALAXIES[BLACK_HOLE_REFERENCE_GALAXY].radius)
    v = ~int(ratio * BLACK_HOLE_GALAXY_SCALE)
    if v < -1:
        return -1
    return 8 if v > 8 else v


def _black_hole_zone_edge(idx: int) -> int:
    k = int(idx * 3 / 2) if idx >= 0 else -(int(abs(idx * 3) / 2))
    return k + 1 if k == idx else k


def gen_black_hole(star: Star, dice: AuDice, galaxy_index: int):
    star.star_type = 7
    star.subclass = dice.roll(1, 10, -1)
    star.size = 0
    idx = _black_hole_galaxy_index(galaxy_index)
    slot = 15 - _black_hole_zone_edge(idx)
    star.type_roll = BLACK_HOLE_TYPE_TABLE[slot]
    star.size_roll = BLACK_HOLE_SIZE_TABLE[slot]
    return star.type_roll, star.size_roll


def init_black_hole_zones(star: Star, galaxy_index: int) -> None:
    star.hab_orbit = 16
    v = _black_hole_galaxy_index(galaxy_index)
    star.min_orbit = v
    k = _black_hole_zone_edge(v)
    star.zones = [(0 if o <= star.min_orbit else (1 if o <= k else 6))
                  for o in range(16)]


def star_count(dice: AuDice, core_black_hole: bool = False) -> int:
    roll = dice.roll(2, 6, 6 if core_black_hole else 0)
    if roll >= 12:
        return 3
    return 2 if roll >= 8 else 1


def create_stars(dice: AuDice, core_black_hole: bool = False,
                 galaxy_index: int = 15) -> Star:
    n = star_count(dice, core_black_hole)

    primary = Star(index=0)
    if core_black_hole:
        gen_black_hole(primary, dice, galaxy_index)
        init_black_hole_zones(primary, galaxy_index)
    else:
        primary.type_roll = gen_primary_type(primary, dice)
        primary.size_roll = gen_primary_size(primary, dice)
        primary.init_zones()

    for i in range(1, n):
        comp = Star(index=i)
        orbit = gen_companion_orbit(primary, dice, i - 1)
        comp.companion_orbit = orbit
        min_avail = min_orbit_available_from(primary, orbit)
        span = _sc(orbit - min_avail)
        half = int(orbit / 2)
        if span > half:
            span = half
            min_avail = _sc(orbit - span)
        comp.orbits_available = float(span)
        while True:
            gen_companion_type(comp, dice, primary.type_roll)
            gen_companion_size(comp, dice, primary.size_roll)
            comp.init_zones()
            if comp.min_orbit <= span:
                break
        reserve_zones(primary, min_avail, orbit + span)
        primary.companions.append(comp)
    return primary


def init_max_orbits(star: Star, dice: AuDice) -> None:
    adj = 0
    if star.star_type == 5:
        adj = -2
    elif star.star_type == 6:
        adj = -4
    elif star.star_type == 7:
        return
    if star.size >= 0:
        if star.size < 3:
            adj += 8
        elif star.size == 3:
            adj += 4
    max_orbits = dice.roll(2, 6, adj)
    if star.companion_orbit >= 0:
        avail = star.orbits_available
        star.orbits_available = 0.0
        max_orbits = min(max_orbits, int(avail))
    lo = max_orbits if max_orbits > 0 else 0
    for o in range(lo, 16):
        star.zones[o] = 1


def get_habitable_world(star: Star, hab: int) -> Optional[World]:
    for w in star.worlds:
        if w.kind in ("globe", "gasgiant") and w.is_habitable(hab):
            return w
        if w.orbit_zone == 2:
            for m in w.moons:
                if m.kind == "globe" and m.is_habitable(hab):
                    return m
    for comp in star.companions:
        found = get_habitable_world(comp, hab)
        if found is not None:
            return found
    return None


def create_planet(star: Star, orbit: int, hab: int, dice: AuDice) -> None:
    if orbit >= 16:
        raise ValueError(f"CreatePlanet: orbit {orbit} exceeds 15")
    radius = _f32((float(orbit) + 1.0) * AU_PER_ORBIT) if orbit >= 0 else 0.125
    zone_value = star.zones[orbit]
    w = create_world(star, hab, 0, radius, zone_value - 2, dice, orbit=orbit)
    star.worlds.append(w)
    star.zones[orbit] = 1


def create_ringworld(star: Star, orbit: int, dice: AuDice) -> None:
    if orbit < 0:
        return
    radius = _f32((float(orbit) + 1.0) * AU_PER_ORBIT)
    zone_value = star.zones[orbit]
    w = create_world(star, HAB_RINGWORLD, 0, radius, zone_value - 2, dice,
                     orbit=orbit)
    star.worlds.append(w)
    for i in range(orbit + 1):
        if star.zones[i] != 0:
            star.zones[i] = 1


def create_planets(star: Star, hab: int, dice: AuDice) -> int:
    if star.star_type == 7:
        return _recurse_companions(star, hab, dice)

    init_max_orbits(star, dice)
    eligible = sum(1 for o in range(16) if star.zones[o] >= 2)
    n = min(dice.roll(2, 6), eligible)

    hab_orbit = star.hab_orbit
    has_hab = (hab_orbit & 0xFF) <= 15 and star.zones[hab_orbit] == 4

    fill = True
    if has_hab:
        if hab == HAB_HOMEWORLD or hab_orbit >= 4:
            create_planet(star, hab_orbit, hab, dice)
            n -= 1
        else:
            forced = False
            if star.is_primary:
                for comp in star.companions:
                    if comp.companion_orbit < hab_orbit:
                        forced = True
                        break
            if forced or dice.roll(1, 100) > gg.RINGWORLD_CHANCE:
                create_planet(star, hab_orbit, hab, dice)
                n -= 1
            else:
                create_ringworld(star, hab_orbit, dice)
                fill = False

    if fill:
        while n > 0:
            while True:
                o = dice.roll(1, 16, -1)
                if star.zones[o] >= 2:
                    break
            create_planet(star, o, HAB_RANDOM, dice)
            n -= 1

    if hab != HAB_RANDOM and get_habitable_world(star, hab) is not None:
        hab = 1 if hab == 3 else hab - 1
    star.init_zones()
    return _recurse_companions(star, hab, dice)


def _recurse_companions(star: Star, hab: int, dice: AuDice) -> int:
    if not star.is_primary:
        return hab
    for comp in star.companions:
        hab = create_planets(comp, hab, dice)
        if hab != HAB_RANDOM and get_habitable_world(comp, hab) is not None:
            hab -= 1
    return hab


def create_world(star: Star, hab: int, moon_flag: int, orbit_radius: float,
                 zone: int, dice: AuDice, orbit: int = -1) -> World:
    if hab == HAB_RINGWORLD:
        return _create_ringworld_body(orbit, zone, orbit_radius, dice)

    if moon_flag != 0:
        w = _globe_create(moon_flag - 1, hab, dice, orbit_radius, zone,
                          orbit=orbit, satellite=True)
        return w

    if dice.roll(2, 6) < 9:
        w = _globe_create(1, hab, dice, orbit_radius, zone, orbit=orbit)
        moon_count = _globe_moon_count(w, dice)
        big_moon = False
    else:
        w = _gas_giant_create(dice, orbit_radius, zone, orbit=orbit)
        moon_count = _gas_giant_moon_count(w, dice)
        big_moon = True
        if zone != 2 and dice.roll(1, 10) < 8:
            big_moon = False

    if moon_count > 0:
        _create_moons(w, hab, zone, moon_count, big_moon, dice)
    return w


def _create_ringworld_body(orbit: int, zone: int, orbit_radius: float,
                           dice: AuDice) -> World:
    from . import ringworld as rwg

    circumference = (orbit_radius * AU_IN_UNITS
                     + orbit_radius * AU_IN_UNITS) * math.pi
    sections = int(math.ceil(circumference / MIN_SECTION_LENGTH))
    w = World(kind="ringworld", orbit=orbit, orbit_zone=zone,
              orbit_radius=orbit_radius, habitability=HAB_RINGWORLD,
              sections=sections)
    w.ring_sections = rwg.create_ringworld(dice, orbit_radius, zone)
    assert len(w.ring_sections) == sections
    return w


def _globe_moon_count(w: World, dice: AuDice) -> int:
    n = dice.roll(2, 3, (w.size & 0xFF) // 10 - 3)
    return 0 if n < 0 else n


def _gas_giant_moon_count(w: World, dice: AuDice) -> int:
    n = dice.roll(2, 3, (w.size & 0xFF) // 10 - 3)
    if n < 1 and w.orbit_zone == 2:
        return 1
    return 0 if n < 0 else n


def _moon_slots(parent: World) -> List[float]:
    slots = []
    d = globe_radius_units(parent.size) + MOON_GAP
    while d <= MOON_LIMIT:
        slots.append(d)
        d += MOON_STEP
    return slots


def _create_moons(parent: World, hab: int, zone: int, count: int,
                  big_moon: bool, dice: AuDice) -> None:
    slots = _moon_slots(parent)
    for k in range(count):
        if not slots:
            break
        if k == 0 and big_moon:
            idx = dice.roll(1, len(slots) - 2, 0)
            dist = slots[idx] / AU_IN_UNITS
            del slots[idx - 1:idx + 2]
            child = _globe_create(1, hab, dice, dist, zone, satellite=True)
            parent.moons.append(child)
            continue
        idx = dice.roll(1, len(slots), -1) if len(slots) > 1 else 0
        dist = slots[idx] / AU_IN_UNITS
        del slots[idx]
        if dice.roll(2, 6) > 3:
            child = _globe_create(0, hab, dice, dist, zone, satellite=True)
        else:
            child = World(kind="ring", orbit=-1, orbit_zone=zone,
                          orbit_radius=dist, is_satellite=True)
        parent.moons.append(child)


def _globe_create(is_planet: int, hab: int, dice: AuDice, orbit_radius: float,
                  zone: int, orbit: int = -1, satellite: bool = False) -> World:
    w = World(kind="globe", orbit=orbit, orbit_zone=zone,
              orbit_radius=orbit_radius, habitability=hab,
              is_satellite=satellite)
    if is_planet == 0:
        _globe_create_moon(w, dice)
    else:
        _globe_create_planet(w, hab, dice)
    return w


def _globe_create_moon(w: World, dice: AuDice) -> None:
    w.size = 2 if dice.roll(2, 6) < 9 else 1
    w.atm_density = 0
    w.atm_type = 0
    w.water = 0
    create_terrain_data(w, dice)
    _consume_flora(w, dice)


def _globe_create_planet(w: World, hab: int, dice: AuDice) -> None:
    if hab == HAB_RANDOM:
        w.size = dice.roll(2, 6)
        dens_lo, dens_hi, water_lo, water_hi = 0, 100, 0, 100
    elif hab == HAB_SYSTEM:
        w.size = dice.roll(2, 6)
        dens_lo, dens_hi, water_lo, water_hi = 15, 85, 10, 90
    elif hab == HAB_HOMEWORLD:
        while True:
            w.size = dice.roll(2, 6)
            if 7 <= w.size <= 9:
                break
        dens_lo, dens_hi, water_lo, water_hi = 40, 70, 20, 80
    else:
        raise ValueError(f"CreatePlanet: unexpected habitability {hab}")

    while True:
        base = _sc(dice.roll(2, 6, w.size - 8))
        v = _sc(dice.roll(1, 10, -1) + base * 10)
        if dens_lo <= v <= dens_hi:
            w.atm_density = v
            break

    if hab == HAB_HOMEWORLD:
        w.atm_type = 0
    elif hab == HAB_SYSTEM:
        w.atm_type = 1 if dice.roll(2, 6) > 8 else 0
    else:
        w.atm_type = ATM_TYPE_TABLE[dice.roll(2, 6, -2)]

    while True:
        base = _sc(dice.roll(2, 6, w.size - 7))
        if w.atm_density < 21 or (hab == HAB_RANDOM and w.atm_type > 2):
            base = _sc(base - 4)
        v = _sc(dice.roll(1, 10, -1) + base * 10)
        if water_lo <= v <= water_hi:
            w.water = v
            break

    create_terrain_data(w, dice)
    _consume_flora(w, dice)
    if w.can_have_fauna():
        dice.advance(w.resource_zones() * fauna_steps(w.size, w.water))


def _gas_giant_create(dice: AuDice, orbit_radius: float, zone: int,
                      orbit: int = -1) -> World:
    w = World(kind="gasgiant", orbit=orbit, orbit_zone=zone,
              orbit_radius=orbit_radius)
    w.size = _sc((dice.roll(2, 6) + 8) * 2)
    w.atm_density = _sc(dice.roll(2, 6) + 88)
    r = dice.roll(2, 6)
    w.atm_type = 2 if r < 5 else (3 + (1 if r > 8 else 0))

    private = AuDice(dice.state)
    _gas_giant_init_core_radius(w, private)
    create_terrain_data(w, private)
    return w


def _gas_giant_init_core_radius(w: World, dice: AuDice) -> None:
    size = w.size & 0xFF
    hi = size // 6
    lo = size // 13
    zone = w.orbit_zone
    if zone == 0:
        adj = -2
    elif zone == 1:
        adj = -1
    elif zone == 4:
        adj = 1
    else:
        adj = 0
    if lo != hi:
        adj += dice.roll(1, (hi - lo) + 1, -1)
    v = adj + lo
    w.water = 1 if v < 2 else _sc(v)


def create_terrain_data(w: World, dice: AuDice) -> tuple:
    n1 = dice.roll(1, 100000, -1)
    n2 = dice.roll(1, 100)
    noise_x = _f32(_f32(n2) / 100.0 + _f32(n1))

    n1 = dice.roll(1, 100000, -1)
    n2 = dice.roll(1, 100)
    noise_y = _f32(_f32(n2) / 100.0 + _f32(n1))

    size = w.size & 0xFF
    amp = _f32(dice.roll(1, size * 10000, 10000) / 10000.0)
    amp = _f32(_f32(globe_radius_units(size) / TERRAIN_REF_RADIUS) * amp)
    zones = w.resource_zones()
    if amp < zones:
        amp = float(zones)

    x = _f32(dice.roll(1, 40, 45) / 100.0)
    detail = _f32(x ** 3 + x * x + (x + 1.0) + x ** 4 + x ** 5 + x ** 6)
    detail = _f32(_f32(dice.roll(1, 261) / 1000.0 + DETAIL_BIAS) * detail)

    r = _f32(_f32(_sc(w.water) / RELIEF_DIV) - 0.5)
    r = _f32(r + r)
    relief = _f32(r * r)
    if r < 0.0:
        relief = -relief

    w.terrain = (amp, detail, x, noise_x, noise_y, relief)
    return w.terrain


def deplanetflora_init(size: int, dice: AuDice):
    from .real import auflora_dna_init

    lat_mod = 12 - int(size)
    bands = []
    for zone in range(3):
        slots = [None] * DNA_PER_TERRAIN_FLORA
        slots[0] = auflora_dna_init(dice, zone, lat_mod)
        for i in range(12, 18):
            slots[i] = auflora_dna_init(dice, zone, lat_mod)
        for i in range(1, 12):
            slots[i] = auflora_dna_init(dice, zone, lat_mod)
        bands.append(slots)
    return bands


FLORA_SLOT_ORDER = (0,) + tuple(range(12, 18)) + tuple(range(1, 12))
FLORA_DNA_BYTES = 12
FLORA_TRAILER = b"\x00" * 8


def encode_flora(zones) -> bytes:
    out = bytearray()
    for bands in zones:
        for band in bands:
            for slot in FLORA_SLOT_ORDER:
                out += struct.pack(">i", FLORA_DNA_BYTES)
                out += struct.pack("<III", *(v & 0xFFFFFFFF for v in band[slot]))
    out += FLORA_TRAILER
    return bytes(out)


def decode_flora(blob: bytes):
    if not blob:
        return []
    off = 0
    recs = []
    while off + 4 <= len(blob) - len(FLORA_TRAILER):
        (ln,) = struct.unpack_from(">i", blob, off)
        if ln != FLORA_DNA_BYTES:
            break
        off += 4
        recs.append(struct.unpack_from("<III", blob, off))
        off += ln
    per_zone = 3 * DNA_PER_TERRAIN_FLORA
    zones = []
    for z in range(len(recs) // per_zone):
        bands = []
        for b in range(3):
            base = z * per_zone + b * DNA_PER_TERRAIN_FLORA
            band = [None] * DNA_PER_TERRAIN_FLORA
            for i, slot in enumerate(FLORA_SLOT_ORDER):
                band[slot] = recs[base + i]
            bands.append(band)
        zones.append(bands)
    return zones


def world_flora_blob(w: World, dice: AuDice) -> bytes:
    return encode_flora([deplanetflora_init(w.size, dice)
                         for _ in range(w.resource_zones())])


def _consume_flora(w: World, dice: AuDice) -> None:
    dice.advance(w.resource_zones() * FLORA_STEPS_PER_ZONE)


def finalize_contents(gen_seed: int, gen_hab: int = DEFAULT_GEN_HAB,
                      core_black_hole: bool = False,
                      galaxy_index: int = 15) -> Star:
    dice = AuDice(int(gen_seed) & 0xFFFFFFFF)
    primary = create_stars(dice, core_black_hole, galaxy_index)
    if not (1 <= (int(gen_hab) & 0xFF) <= 2):
        gen_hab = HAB_SYSTEM
    create_planets(primary, int(gen_hab) & 0xFF, dice)
    return primary


STARTUP_RESOURCE_MIN = 10

ZR_STARTUP_MINERALS = 0x14
ZR_STARTUP_ORGANICS = 0x2C


def _world_resources(w: "World", seed_obj, star: Star) -> Tuple[int, int]:
    from . import zone_resources as zr

    minerals = organics = 0
    if w.kind == "globe":
        props = zr.GlobeProperties(
            climate_class=w.orbit_zone & 0xFF,
            size_class=w.size & 0xFF,
            star_type=star.star_type,
            atmosphere_type=w.atm_type & 0xFF,
            hydrographics=w.water & 0xFF,
            msl_atmosphere_density=w.atm_density & 0xFF,
            average_foliage=0,
            is_satellite=w.is_satellite,
        )
        props.average_foliage = zr.average_foliage(props)
        seed = seed_obj.gen_seed()
        for zone in range(w.resource_zones()):
            rec = zr.query_natural_resources(props, zone, seed)
            minerals += rec.u8(ZR_STARTUP_MINERALS)
            organics += rec.u8(ZR_STARTUP_ORGANICS)
    for moon in w.moons:
        if moon.kind != "globe":
            continue
        m, o = _world_resources(moon, _world_seed(moon, seed_obj), star)
        minerals += m
        organics += o
    return minerals, organics


def _star_seed(system_seed: int, star_index: int):
    from . import procgen as hp
    return hp.Star(
        parent_solar_system=hp.SolarSystem(cached_seed=int(system_seed)),
        star_number=int(star_index))


def _world_seed(w: "World", parent_seed_obj):
    from . import procgen as hp
    return hp.World(parent_star=parent_seed_obj,
                    orbit_index=w.orbit_zone & 0xFF,
                    orbit_radius=float(w.orbit_radius))


def find_startup_resources(star: Star, system_seed: int) -> Tuple[int, int]:
    minerals = organics = 0
    seed_obj = _star_seed(system_seed, star.index)
    for w in star.worlds:
        if w.kind == "ringworld":
            continue
        m, o = _world_resources(w, _world_seed(w, seed_obj), star)
        minerals += m
        organics += o
    for comp in star.companions:
        m, o = find_startup_resources(comp, system_seed)
        minerals += m
        organics += o
    return minerals, organics


@dataclass
class HomeWorld:
    gen_seed: int
    attempts: int
    primary: Star
    world: Optional["World"]
    minerals: int
    organics: int
    gen_hab: int = HAB_HOMEWORLD


ORBIT_ZONE_NAMES = ("Inferno", "Inner", "Habitable", "Outer", "Frigid")

HOME_REQUIRED_ZONES = frozenset({0, 1, 2, 3, 4})

HOME_REQUIRE_MOON = True


def system_zone_coverage(primary: Star) -> set:
    return {w.orbit_zone & 0xFF for s in walk_stars(primary) for w in s.worlds}


def system_has_moon(primary: Star) -> bool:
    return any(w.moons for s in walk_stars(primary) for w in s.worlds)


def system_has_ringworld(primary: Star) -> bool:
    return any(w.kind == "ringworld"
               for s in walk_stars(primary) for w in s.worlds)


def create_home_world(gen_seed: int, *, galaxy_index: int = 15,
                      max_attempts: int = 4096,
                      require_zones: Optional[frozenset] = None,
                      require_moon: Optional[bool] = None,
                      require_ringworld: bool = False,
                      require_resources: bool = True,
                      require_home_planet: bool = True,
                      gen_hab: int = HAB_HOMEWORLD
                      ) -> Optional[HomeWorld]:
    want_zones = (HOME_REQUIRED_ZONES if require_zones is None
                  else frozenset(require_zones))
    want_moon = HOME_REQUIRE_MOON if require_moon is None else bool(require_moon)

    hab = int(gen_hab) & 0xFF
    seed = int(gen_seed) & 0xFFFFFFFF
    for attempt in range(1, max_attempts + 1):
        dice = AuDice(seed)
        primary = create_stars(dice, False, galaxy_index)
        create_planets(primary, hab, dice)
        home = get_habitable_world(primary, hab)
        minerals = organics = 0
        ok = ((home is not None or not require_home_planet)
              and (not require_ringworld or system_has_ringworld(primary))
              and (not want_zones
                   or want_zones <= system_zone_coverage(primary))
              and (not want_moon or system_has_moon(primary)))
        if ok:
            minerals, organics = find_startup_resources(primary, seed)
            if require_resources:
                ok = (minerals >= STARTUP_RESOURCE_MIN
                      and organics >= STARTUP_RESOURCE_MIN)
        if ok:
            return HomeWorld(seed, attempt, primary, home, minerals, organics,
                             gen_hab=hab)
        seed = gg._advance_seed(seed, seed % 12)
    return None


def create_good_home(candidates, *, galaxy_index: int = 15,
                     max_attempts: int = 4096,
                     require_zones: Optional[frozenset] = None,
                     require_moon: Optional[bool] = None,
                     require_ringworld: bool = False,
                     require_resources: bool = True,
                     require_home_planet: bool = True,
                     gen_hab: int = HAB_HOMEWORLD):
    for auid, seed, core_bh in candidates:
        if core_bh:
            continue
        hw = create_home_world(seed, galaxy_index=galaxy_index,
                               max_attempts=max_attempts,
                               require_zones=require_zones,
                               require_moon=require_moon,
                               require_ringworld=require_ringworld,
                               require_resources=require_resources,
                               require_home_planet=require_home_planet,
                               gen_hab=gen_hab)
        if hw is not None:
            return auid, hw
    return None


PLANET_NUMERALS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII",
                   "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI")
MOON_LETTERS = tuple("abcdefghijklmnop")
STAR_SUFFIXES = (" Alpha", " Beta", " Gamma")


def star_suffix(star_number: int) -> str:
    n = int(star_number)
    return STAR_SUFFIXES[n] if 0 <= n < len(STAR_SUFFIXES) else ""


def world_default_name(system_name: str, star_number: int, planet_rank: int,
                       moon_rank: Optional[int] = None) -> str:
    numeral = PLANET_NUMERALS[planet_rank] if 0 <= planet_rank < 16 else ""
    letter = ""
    if moon_rank is not None and 0 <= moon_rank < len(MOON_LETTERS):
        letter = MOON_LETTERS[moon_rank]
    return f"{system_name}{star_suffix(star_number)} {numeral}{letter}"


def name_worlds(primary: Star, system_name: str) -> None:
    for star in walk_stars(primary):
        planets = sorted((w for w in star.worlds), key=lambda w: w.orbit_radius)
        for rank, w in enumerate(planets):
            w.name = world_default_name(system_name, star.index, rank)
            moons = sorted(w.moons, key=lambda m: m.orbit_radius)
            for mrank, m in enumerate(moons):
                m.name = world_default_name(system_name, star.index, rank, mrank)


def walk_stars(primary: Star):
    yield primary
    for c in primary.companions:
        yield from walk_stars(c)


def walk_worlds(primary: Star):
    for star in walk_stars(primary):
        for w in star.worlds:
            for body in w.walk():
                yield star, body
