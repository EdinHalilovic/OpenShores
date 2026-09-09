
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from openshores.core.logging import configure, get_logger
from openshores.protocol.rng import AuNoise

logger = get_logger(__name__)


_MASK32 = 0xFFFFFFFF


def _u32(x: int) -> int:
    return x & _MASK32


def _i32(x: int) -> int:
    x &= _MASK32
    return x - (1 << 32) if x >= (1 << 31) else x


def _trunc_noise(f: float) -> int:
    if f != f or f in (float("inf"), float("-inf")):
        v = -(1 << 63)
    else:
        v = int(f)
        if not (-(1 << 63) <= v < (1 << 63)):
            v = -(1 << 63)
    return v & _MASK32


def _trunc_to_i32(f: float) -> int:
    if f >= 0x80000000 or f <= -0x80000001 or f != f:
        return -0x80000000
    return int(f)


@dataclass
class Galaxy:
    galaxy_number: int
    creation_time_unix: int

    def gen_seed(self) -> int:
        return _u32(self.galaxy_number + self.creation_time_unix)


@dataclass
class Sector:
    galaxy: Galaxy
    location: tuple[float, float, float]

    def gen_seed(self) -> int:
        base = self.galaxy.gen_seed()
        seed_mod12 = base % 12

        K = 10.0
        lx, ly, lz = self.location
        xi = _trunc_to_i32(round(lx * K))
        yi = _trunc_to_i32(round(ly * K))
        zi = _trunc_to_i32(round(lz * K))

        n1 = AuNoise.integer_noise(seed_mod12, xi, yi)
        n2 = AuNoise.integer_noise(seed_mod12, zi, _i32(base))
        K2 = 4294967295.0
        seed = _u32(base + _trunc_noise(n1 * K2) + _trunc_noise(n2 * K2))
        if seed == 0:
            seed = 1
        return seed


@dataclass
class SolarSystem:
    cached_seed: int

    def gen_seed(self) -> int:
        return _u32(self.cached_seed)


@dataclass
class Star:
    parent_solar_system: Optional[SolarSystem]
    parent_designer_seed: Optional[int] = None
    star_number: int = 0

    def gen_seed(self) -> int:
        if self.parent_solar_system is not None:
            base = self.parent_solar_system.gen_seed()
        elif self.parent_designer_seed is not None:
            base = _u32(self.parent_designer_seed)
        else:
            base = 0

        seed = base
        if 1 <= self.star_number <= 2:
            K2 = 4294967295.0
            cur = base
            while True:
                n = AuNoise.integer_noise1(_u32(self.star_number), _i32(cur))
                cur = _u32(cur + _trunc_noise(n * K2))
                if cur != 0:
                    break
            seed = cur
        return seed


@dataclass
class World:
    parent_star: Star
    orbit_index: int
    orbit_radius: float
    _cached: Optional[int] = field(default=None, repr=False)

    def gen_seed(self) -> int:
        if self._cached:
            return _u32(self._cached)

        parent = self.parent_star.gen_seed()
        seed = parent

        GRID = 0.001
        HALF_POS = 0.0005
        HALF_NEG = -0.0005
        MULT = 2_400_000.0
        K2 = 4294967295.0

        half = HALF_POS if self.orbit_radius > 0 else HALF_NEG
        stepped = float(int((self.orbit_radius + half) / GRID)) * GRID
        contribution = _trunc_to_i32(stepped * MULT)
        seed = _u32(seed + contribution)

        while True:
            n = AuNoise.integer_noise1(_u32(self.orbit_index & 0xFF), _i32(seed))
            seed = _u32(seed + _trunc_noise(n * K2))
            if seed != 0:
                break
        self._cached = seed
        return seed


@dataclass
class Designer:
    cached_seed: int = 0
    auid: int = 0

    def gen_seed(self) -> int:
        if self.cached_seed == 0:
            return _u32(self.auid)
        return _u32(self.cached_seed)


if __name__ == "__main__":
    configure()

    g = Galaxy(galaxy_number=1, creation_time_unix=1577836800)
    logger.info("galaxy.gen_seed() = 0x%08x", g.gen_seed())

    s = Sector(galaxy=g, location=(1.2, -3.4, 5.6))
    logger.info("sector.gen_seed() = 0x%08x", s.gen_seed())

    ss = SolarSystem(cached_seed=s.gen_seed())
    logger.info("system.gen_seed() = 0x%08x", ss.gen_seed())

    star0 = Star(parent_solar_system=ss, star_number=0)
    star1 = Star(parent_solar_system=ss, star_number=1)
    logger.info("star0.gen_seed() = 0x%08x (primary)", star0.gen_seed())
    logger.info("star1.gen_seed() = 0x%08x (secondary, perturbed)",
                star1.gen_seed())

    world = World(parent_star=star0, orbit_index=3, orbit_radius=1.0)
    logger.info("world.gen_seed() = 0x%08x", world.gen_seed())
