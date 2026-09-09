from __future__ import annotations

import random
from dataclasses import dataclass

from openshores.core.logging import configure, get_logger

logger = get_logger(__name__)

HAB_RANDOM    = 0
HAB_SYSTEM    = 1
HAB_HOMEWORLD = 2
HAB_RINGWORLD = 3

ATMTYPE_LUT_HAB0 = [4, 3, 2, 1, 0, 0, 0, 1, 2, 3, 4]


def _roll(rng: random.Random, n: int, sides: int, mod: int = 0) -> int:
    return sum(rng.randint(1, sides) for _ in range(n)) + mod


@dataclass
class GeneratedPlanet:
    size_code: int
    atm_type:  int
    atm_dens:  int
    water:     int


def gen_planet(auid: int, habitability: int = HAB_RANDOM) -> GeneratedPlanet:
    rng = random.Random((int(auid) & 0xFFFFFFFF) ^ (habitability * 0x9E3779B9))

    if habitability == HAB_HOMEWORLD:
        while True:
            size = _roll(rng, 2, 6)
            if 7 <= size <= 9:
                break
        while True:
            d = _roll(rng, 2, 6, size - 8)
            d = d * 10 + _roll(rng, 1, 10, -1)
            if 40 <= d <= 70:
                break
        atm_dens = d
        atm_type = 0
        while True:
            w = _roll(rng, 2, 6, size - 7)
            if size - 7 < 0x15 or atm_type > 2:
                w -= 4
            w = w * 10 + _roll(rng, 1, 10, -1)
            if 20 <= w <= 80:
                break
        water = w
        return GeneratedPlanet(size, atm_type, atm_dens, water)

    if habitability == HAB_SYSTEM:
        size = _roll(rng, 2, 6)
        while True:
            d = _roll(rng, 2, 6, size - 8)
            d = d * 10 + _roll(rng, 1, 10, -1)
            if 15 <= d <= 85:
                break
        atm_dens = d
        atm_type = 1 if _roll(rng, 2, 6) > 8 else 0
        while True:
            w = _roll(rng, 2, 6, size - 7)
            if atm_dens < 0x15:
                w -= 4
            w = w * 10 + _roll(rng, 1, 10, -1)
            if 10 <= w <= 90:
                break
        water = w
        return GeneratedPlanet(size, atm_type, atm_dens, water)

    size = _roll(rng, 2, 6)
    while True:
        d = _roll(rng, 2, 6, size - 8)
        d = d * 10 + _roll(rng, 1, 10, -1)
        if 0 <= d <= 100:
            break
    atm_dens = d
    atm_type = ATMTYPE_LUT_HAB0[_roll(rng, 2, 6, -2)]
    while True:
        w = _roll(rng, 2, 6, size - 7)
        if atm_dens < 21 or atm_type > 2:
            w -= 4
        w = w * 10 + _roll(rng, 1, 10, -1)
        if 0 <= w <= 100:
            break
    water = w
    return GeneratedPlanet(size, atm_type, atm_dens, water)


def gen_moon(auid: int) -> GeneratedPlanet:
    rng = random.Random(int(auid) & 0xFFFFFFFF)
    size = 2 if _roll(rng, 2, 6) < 9 else 1
    return GeneratedPlanet(size, 0, 0, 0)


if __name__ == "__main__":
    configure()
    logger.info("Habitability=2 (HomeWorld). Narrow band:")
    for auid in [0x16cd86, 0x516056, 0xf614c3]:
        p = gen_planet(auid, HAB_HOMEWORLD)
        logger.info("  auid=0x%08x  %s", auid, p)
    logger.info("Habitability=0 (Random). Wide spread:")
    for auid in [0x16cd86, 0x516056, 0xf614c3, 0x123456, 0xdeadbeef]:
        p = gen_planet(auid, HAB_RANDOM)
        logger.info("  auid=0x%08x  %s", auid, p)
    logger.info("Moons:")
    for auid in [0x152165, 0x38dd0a, 0xb23e3f, 0xff1c15]:
        p = gen_moon(auid)
        logger.info("  auid=0x%08x  %s", auid, p)
