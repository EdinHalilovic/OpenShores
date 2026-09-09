
from __future__ import annotations

import os
import time
from typing import Optional, Tuple

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories import universe as _rows
from openshores.gameplay.homestead import _auid
from openshores.gameplay.worldgen import atom_writer as aw
from openshores.gameplay.worldgen import galaxy as gg
from openshores.gameplay.worldgen import world_gen as wg
from openshores.gameplay.worldgen import wormhole_gen as wh

logger = get_logger(__name__)

HOME_CELL: Tuple[int, int, int] = (1, 0, 0)

GENERATOR = "first_run"


def _seed_halves(galaxy_seed: int) -> Tuple[int, int]:
    return (int(galaxy_seed) & 0xFFFFFFFF, 0)


async def universe_exists(conn: asyncpg.Connection) -> bool:
    return await _rows.universe_row(conn) is not None


async def generate_universe(conn: asyncpg.Connection, *,
                            universe_auid: int, universe_name: str,
                            galaxy_auid: int, galaxy_name: str,
                            galaxy_seed: int, sector_radius: int,
                            maps_dir: str, created_ms: int) -> dict:
    galaxy_type = gg.GALAXY_BY_NAME.get(galaxy_name)
    if galaxy_type is None:
        raise ValueError(
            f"Unknown galaxy {galaxy_name!r}; expected one of {', '.join(sorted(gg.GALAXY_BY_NAME))}")
    galaxy_number, created = _seed_halves(galaxy_seed)

    gseed = gg.galaxy_seed(galaxy_number, created)
    logger.info("First run: generating %s, seed 0x%08x, +/-%d sectors "
                "(%d cells) of a disc that reaches +/-%d.",
                galaxy_type.name, gseed, sector_radius,
                (2 * sector_radius + 1) ** 3, gg.sector_span(galaxy_type))

    t0 = time.time()
    bounds = ((-sector_radius, sector_radius),
              (-sector_radius, sector_radius),
              (-sector_radius, sector_radius))
    _g, _gseed, plans = gg.generate(galaxy_name, galaxy_number, created,
                                    maps_dir=maps_dir, bounds=bounds)
    n_systems = sum(len(p.systems) for p in plans)
    t_gen = time.time() - t0

    await _rows.insert_universe(conn, auid=universe_auid, name=universe_name,
                                created_ms=created_ms)
    await _rows.insert_galaxy(conn, auid=galaxy_auid,
                              universe_auid=universe_auid, name=galaxy_name,
                              galaxy_number=galaxy_number, created=created)
    await gg.record_generation(conn, galaxy_name=galaxy_name,
                               galaxy_number=galaxy_number, created=created,
                               tool=GENERATOR)

    used = await _rows.used_atom_ids(conn)
    used.add(int(galaxy_auid) & 0xFFFFFFFF)
    used.add(int(universe_auid) & 0xFFFFFFFF)

    async def claim(seed: int, salt: int) -> int:
        v = _auid(seed, salt)
        while v in used:
            v = ((v + 1) & 0xFFFFFFFF) or 1
        used.add(v)
        return v

    star_names = (await _name_pool(conn, "star")
                  + await _name_pool(conn, "star_alien"))
    sector_names = await _name_pool(conn, "sector")

    home = await _create_good_home(plans, galaxy_type)

    sec_rows, sys_rows = [], []
    nodes = []
    rows = aw.SystemRows()
    t1 = time.time()
    for plan in plans:
        sid = await claim(plan.seed, 0xA1)
        sx, sy, sz = plan.location
        sec_rows.append((sid, galaxy_auid, galaxy_auid, sx, sy, sz,
                         _pick(sector_names, plan.seed, f"Sector_{sid:06x}")))
        for i, site in enumerate(plan.systems):
            yid = await claim(site.seed, 0xB2 + i)
            is_home = home == (plan, i)
            gen_hab = wg.HAB_HOMEWORLD if is_home else wg.DEFAULT_GEN_HAB
            sys_name = _pick(star_names, site.seed, f"System_{yid:06x}")
            sys_rows.append((yid, sid, sid, site.x, site.y, site.z,
                             site.rot_x_deg, site.rot_y_deg, site.rot_z_deg,
                             sys_name, site.seed, gen_hab))
            nodes.append(wh.SystemNode(yid, (plan.cx, plan.cy, plan.cz),
                                       sx + site.x, sy + site.y, sz + site.z))
            core_bh = (plan.cx == plan.cy == plan.cz == 0
                       and site.x == 0.0 and site.y == 0.0 and site.z == 0.0)
            primary = wg.finalize_contents(site.seed, gen_hab=gen_hab,
                                           core_black_hole=core_bh,
                                           galaxy_index=galaxy_type.index)
            wg.name_worlds(primary, sys_name)
            rows.extend(await aw.build_system_rows(
                primary, yid, site.seed, claim, detail=is_home))
    t_build = time.time() - t1

    t2 = time.time()
    wmap = wh.generate(nodes)
    n_pos, n_neg = wmap.counts()
    wh_rows = [(wh.encode(ws), auid)
               for auid, ws in wmap.by_system.items() if ws]
    t_worm = time.time() - t2

    logger.info("First run: %d sectors, %d systems in %.1fs; %d atom rows "
                "(%d globes, %d gas giants, %d rings, %d ringworlds / %d "
                "sections) in %.1fs; %d positive and %d negative wormholes "
                "across %d systems in %.1fs.",
                len(plans), n_systems, t_gen, rows.total, len(rows.globe),
                len(rows.gas_giant), len(rows.ring), rows.ringworlds,
                len(rows.ring_section), t_build, n_pos, n_neg, len(wh_rows),
                t_worm)

    t3 = time.time()
    await _rows.insert_sectors(conn, sec_rows)
    await _rows.insert_solar_systems(conn, sys_rows)
    await aw.write_system_rows(conn, rows)
    await _rows.set_system_wormholes(conn, wh_rows)
    counts = await _rows.atom_row_counts(conn)
    logger.info("First run: wrote %s in %.1fs.",
                "  ".join(f"{k}={v}" for k, v in counts.items()),
                time.time() - t3)
    return counts


async def _create_good_home(plans, galaxy_type):
    hx, hy, hz = HOME_CELL
    plan = next((p for p in plans if (p.cx, p.cy, p.cz) == (hx, hy, hz)), None)
    if plan is None:
        logger.warning('First run: no sector at %d,%d,%d, so this universe gets no CreateGoodHome system.', hx, hy, hz)
        return None
    t0 = time.time()
    candidates = []
    for i, site in enumerate(plan.systems):
        core_bh = ((hx, hy, hz) == (0, 0, 0)
                   and site.x == 0.0 and site.y == 0.0 and site.z == 0.0)
        candidates.append((i, site.seed, core_bh))
    got = wg.create_good_home(candidates, galaxy_index=galaxy_type.index)
    if got is None:
        logger.warning("First run: sector %d,%d,%d produced no homeworld.",
                       hx, hy, hz)
        return None
    idx, home = got
    plan.systems[idx].seed = home.gen_seed
    logger.info("First run: homeworld in sector %d,%d,%d system #%d, seed rerolled %dx to 0x%08x. Size %s, air %s%% type %s, water %s%%, %s minerals / %s organics in %.1fs.",
                hx, hy, hz, idx, home.attempts, home.gen_seed,
                home.world.size, home.world.atm_density, home.world.atm_type,
                home.world.water, home.minerals, home.organics,
                time.time() - t0)
    return (plan, idx)


async def _name_pool(conn: asyncpg.Connection, kind: str):
    from openshores.database.repositories import homestead as _hs_rows
    return await _hs_rows.name_pool(conn, kind)


def _pick(pool, seed: int, fallback: str) -> str:
    if not pool:
        return fallback
    return pool[(int(seed) & 0x7FFFFFFF) % len(pool)]


async def ensure_universe(conn: asyncpg.Connection, *,
                          universe_auid: int, universe_name: str,
                          galaxy_auid: int, galaxy_name: str,
                          galaxy_seed: int, sector_radius: int,
                          maps_dir: str,
                          created_ms: int) -> Optional[dict]:
    if await universe_exists(conn):
        return None
    if not os.path.isdir(maps_dir):
        raise FileNotFoundError(
            f'{maps_dir} does not exist, and a galaxy cannot be generated without the density map for it.')
    async with conn.transaction():
        return await generate_universe(
            conn, universe_auid=universe_auid, universe_name=universe_name,
            galaxy_auid=galaxy_auid, galaxy_name=galaxy_name,
            galaxy_seed=galaxy_seed, sector_radius=sector_radius,
            maps_dir=maps_dir, created_ms=created_ms)


__all__ = ["ensure_universe", "generate_universe", "universe_exists",
           "HOME_CELL", "GENERATOR"]
