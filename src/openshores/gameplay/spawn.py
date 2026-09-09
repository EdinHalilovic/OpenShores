from __future__ import annotations

import asyncio

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.pool import LOCK_SPACE_SYSTEM, _immediate
from openshores.database.repositories import spawn as _rows
from openshores.database.repositories.spawn import (
    _as_byte,
    _orbit_radius_au,
    _struct_unpack_6f,
)

logger = get_logger(__name__)


HOMESTEAD_SECTOR_BUDGETS = (40, 120, 400)


async def _homestead_with_retry(conn: asyncpg.Connection, *, galaxy: str,
                                region, galaxy_number: int, created: int,
                                then=None, policy=None):
    from . import homestead as _hs

    _CONTENTION_TRIES = 6

    last = None
    contention = 0
    attempt = 0
    budgets = list(HOMESTEAD_SECTOR_BUDGETS)
    bi = 0
    while bi < len(budgets):
        budget = budgets[bi]
        attempt += 1
        try:
            plan = await _hs.plan_homestead(
                conn, galaxy_name=galaxy, region=region,
                galaxy_number=galaxy_number, created=created,
                max_sectors=budget, policy=policy)
            async with _immediate(conn, LOCK_SPACE_SYSTEM, plan.system_auid):
                home, pos = await _commit_and_place(conn, plan)
                return home, pos, (await then(home, pos) if then else None)
        except _hs.HomesteadExhausted as exc:
            last = exc
            bi += 1
            logger.info('Homestead attempt %s found nothing within %s sectors (%s).',
                        attempt, budget, exc)
        except _hs.HomesteadTaken as exc:
            last = exc
            contention += 1
            if contention > _CONTENTION_TRIES:
                bi += 1
                contention = 0
            logger.info("Homestead attempt %s: %s; re-planning at the "
                        "same budget.", attempt, exc)
        except asyncpg.TransactionRollbackError as exc:
            last = exc
            contention += 1
            if contention > _CONTENTION_TRIES:
                bi += 1
                contention = 0
            logger.info('Homestead attempt %s lost the commit (%s).', attempt, exc)
            await asyncio.sleep(0.1 * contention)

    raise _hs.HomesteadExhausted(
        f"No home could be built after {attempt} attempts up to {HOMESTEAD_SECTOR_BUDGETS[-1]} sectors; refusing to drop the character on the stub spawn. Last failure: {last}")


SPAWN_MAX_ABS_LAT_DEG = 35.0


def _spawn_max_abs_lat_rad() -> float:
    import math as _math
    return _math.radians(SPAWN_MAX_ABS_LAT_DEG)


def _equatorial_land(tr, terrain, size, dice, min_altitude: float,
                     max_abs_lat: float, tries: int = 64):
    last_any = None
    last_land = None
    for _ in range(tries):
        lat, lon = tr.random_land_location(terrain, size, dice,
                                           min_altitude=min_altitude)
        last_any = (lat, lon)
        if tr.terrain_altitude_msl(terrain, size, lat, lon) >= min_altitude:
            last_land = (lat, lon)
            if abs(float(lat)) <= max_abs_lat:
                return lat, lon, True
    lat, lon = last_land or last_any or tr.random_land_location(
        terrain, size, dice)
    return lat, lon, False


async def _pick_sunniest_land(conn: asyncpg.Connection, home, terrain,
                              size: int, min_altitude: float):
    import time as _time

    from openshores.protocol.rng import AuDice as _AuDice

    from .worldgen import sunlight as _sun
    from .worldgen import terrain as _tr
    from .worldgen import world_chain as _wch

    tries = 24

    globe = await _rows.globe_row(conn, home.home_globe_auid)
    if globe is None:
        return None
    grow = dict(globe)

    parent = None
    star_id = grow.get("parent_atom")
    prow = await _rows.globe_row(conn, star_id)
    if prow is not None:
        parent = dict(prow)
        star_id = parent.get("parent_atom")

    srow = await _rows.star_row(conn, star_id)
    if srow is None:
        return None
    system_id = dict(srow).get("parent_atom")
    star_rows = await _rows.stars_in_system(conn, system_id) or [srow]
    stars_raw = [dict(r) for r in star_rows]

    system_seed = await _rows.system_gen_seed(conn, system_id)
    if not system_seed:
        return None

    built = _wch.body_chain(grow, parent, system_seed, breathable=True,
                            star_count=len(stars_raw))
    if built is None:
        return None
    chain, radius = built
    stars = _wch.star_descriptors(stars_raw, system_seed)

    now_ms = _time.time() * 1000.0
    dice = _AuDice(home.home_globe_auid & 0xFFFFFFFF or 1)
    best = None
    _max_lat = _spawn_max_abs_lat_rad()
    for _ in range(tries):
        lat, lon = _tr.random_land_location(terrain, size, dice,
                                            min_altitude=min_altitude)
        if abs(float(lat)) > _max_lat:
            continue
        if _tr.terrain_altitude_msl(terrain, size, lat, lon) < min_altitude:
            continue
        light = _wch.query_sunlight_at(chain, radius, now_ms, lat, lon, stars)
        if best is None or light > best[0]:
            best = (light, lat, lon)
    if best is None or _sun.is_dark(best[0]):
        return None
    return best[1], best[2]


async def _commit_and_place(conn: asyncpg.Connection, plan):
    from . import homestead as _hs
    home = await _hs.commit_homestead(conn, plan)
    return home, await _place_on(conn, home)


async def _homestead_and_place(conn: asyncpg.Connection, *, galaxy: str,
                               region, galaxy_number: int, created: int,
                               max_sectors: int = 40):
    import struct as _struct

    from . import homestead as _hs

    home = await _hs.create_homestead(conn, galaxy_name=galaxy, region=region,
                                      galaxy_number=galaxy_number,
                                      created=created, max_sectors=max_sectors)
    return home, await _place_on(conn, home)


async def _place_on_ringworld(conn: asyncpg.Connection, home):
    import math as _math

    from openshores.protocol.rng import AuDice as _AuDice

    from .worldgen import ringworld as _rw
    from .worldgen import terrain as _tr

    row = await _rows.ring_section_row(conn, home.home_globe_auid)
    if row is None:
        return None

    orbit_radius = _orbit_radius_au(row[1])
    if orbit_radius <= 0.0:
        raise _hs_error(
            f"Ring section 0x{home.home_globe_auid:08x} has orbitRadius {row[1]!r}.")
    section = _rw.RingSection(
        index=_as_byte(row[0]),
        orbit_radius=orbit_radius,
        sections=_rw.section_count(orbit_radius),
        water=_as_byte(row[3]),
        atm_density=_as_byte(row[4]),
        atm_type=_as_byte(row[5]))

    _seed = (int(home.home_globe_auid) & 0xFFFFFFFF) or 1
    terrain = None
    if row[2] and len(bytes(row[2])) == 24:
        terrain = _struct_unpack_6f(bytes(row[2]))

    lat = lon = 0.0
    if terrain is not None:
        _margin = 50.0
        for _min_alt in (_margin, 0.0):
            lat, lon = _tr.ring_random_land_location(
                terrain, section.sections, orbit_radius, _AuDice(_seed),
                min_altitude=_min_alt)
            if _tr.ring_terrain_altitude_msl(
                    terrain, section.sections, orbit_radius,
                    lat, lon) >= _min_alt:
                break

    pos = _rw.surface_location(section, lat, lon, 0.0)
    logger.info("Ring spawn: section %s of %s at orbit %s AU, "
                "lat %.1f lon %.1f -> %s",
                section.index, section.sections, orbit_radius,
                _math.degrees(lat), _math.degrees(lon),
                tuple(round(v, 1) for v in pos))
    return pos


def _hs_error(msg: str):
    from .homestead import HomesteadError
    return HomesteadError(msg)


async def _place_on(conn: asyncpg.Connection, home):
    import struct as _struct

    from openshores.protocol.rng import AuDice as _AuDice

    from .worldgen import terrain as _tr
    from .worldgen import world_clock as _wc
    from .worldgen import world_gen as _wg

    ring = await _place_on_ringworld(conn, home)
    if ring is not None:
        return ring

    row = await _rows.globe_radius_and_terrain(conn, home.home_globe_auid)
    size = int(float(row[0] or 8))
    if row[1] and len(bytes(row[1])) == 24:
        terrain = _struct.unpack(">ffffff", bytes(row[1]))
        _margin = 50.0
        _seed = home.home_globe_auid & 0xFFFFFFFF or 1
        _max_lat = _spawn_max_abs_lat_rad()
        lat, lon, _in_band = _equatorial_land(
            _tr, terrain, size, _AuDice(_seed), _margin, _max_lat)
        if _margin > 0.0 and _tr.terrain_altitude_msl(
                terrain, size, lat, lon) < _margin:
            lat, lon, _in_band = _equatorial_land(
                _tr, terrain, size, _AuDice(_seed), 0.0, _max_lat)
        if not _in_band:
            import math as _math
            logger.info("No land within +/-%.0f deg of the equator on this "
                        "world; landing at lat %.1f deg instead (a real land "
                        "spot beats an equatorial ocean).",
                        _math.degrees(_max_lat), _math.degrees(lat))
        try:
            _sunny = await _pick_sunniest_land(conn, home, terrain, size,
                                               _margin)
            if _sunny is not None:
                lat, lon = _sunny
        except Exception as _sun_exc:
            logger.warning("Daylight preference skipped, keeping the first "
                           "land spot: %r", _sun_exc)
    else:
        lat = lon = 0.0
    return _wc.surface_point(lat, lon, _wg.globe_radius_units(size))
