
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional, Sequence, Tuple

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories import homestead as _repo

from .worldgen import galaxy as gg
from .worldgen import world_gen as wg

from .worldgen.real import HAB_SYSTEM as _HAB_SYSTEM

logger = get_logger(__name__)


class HomesteadError(RuntimeError):
    pass


class HomesteadExhausted(HomesteadError):
    pass


class HomesteadTaken(HomesteadError):
    pass


@dataclass(frozen=True)
class HomePolicy:

    require_zones: Optional[frozenset] = None
    require_moon: Optional[bool] = None
    require_ringworld: bool = False
    spawn_on_ringworld: bool = False
    require_resources: bool = True
    require_home_planet: bool = True
    gen_hab: Optional[int] = None
    max_attempts: int = 4096
    label: str = "default"

    def home_kwargs(self) -> dict:
        return dict(max_attempts=self.max_attempts,
                    require_zones=self.require_zones,
                    require_moon=self.require_moon,
                    require_ringworld=(self.require_ringworld
                                       or self.spawn_on_ringworld),
                    require_resources=self.require_resources,
                    require_home_planet=self.require_home_planet,
                    gen_hab=(wg.HAB_HOMEWORLD if self.gen_hab is None
                             else int(self.gen_hab)))


DEFAULT_POLICY = HomePolicy()

ONION_POLICY = HomePolicy(
    require_zones=frozenset(),
    require_moon=False,
    require_ringworld=True,
    require_resources=False,
    require_home_planet=False,
    spawn_on_ringworld=True,
    gen_hab=_HAB_SYSTEM,
    max_attempts=20_000,
    label="onion")

NAME_POLICIES = {
    "onion": ONION_POLICY,
}


def policy_for_name(name) -> HomePolicy:
    return NAME_POLICIES.get(str(name or "").strip().casefold(), DEFAULT_POLICY)


def describe_policy(policy: HomePolicy) -> str:
    wants = ["a habitable planet"] if policy.require_home_planet else []
    if policy.require_ringworld or policy.spawn_on_ringworld:
        wants.append("a ringworld")
    if policy.require_resources:
        wants.append(f"{wg.STARTUP_RESOURCE_MIN} startup minerals and organics")
    zones = (wg.HOME_REQUIRED_ZONES if policy.require_zones is None
             else policy.require_zones)
    if zones:
        wants.append("a planet in each of "
                     + ", ".join(wg.ORBIT_ZONE_NAMES[z] for z in sorted(zones)))
    if policy.require_moon if policy.require_moon is not None \
            else wg.HOME_REQUIRE_MOON:
        wants.append("a moon")
    if not wants:
        return "anything at all -- this policy requires nothing"
    said = (", ".join(wants[:-1]) + " and " + wants[-1]
            if len(wants) > 1 else wants[0])
    if len(wants) == 1 and policy.require_ringworld:
        said += " and nothing else"
    if policy.spawn_on_ringworld:
        said += "; the character stands on the ring"
    if policy.gen_hab is not None and policy.gen_hab != wg.HAB_HOMEWORLD:
        said += f" (generated at habitability {int(policy.gen_hab)})"
    return said


@dataclass
class HomesteadPlan:

    galaxy: gg.GalaxyType
    cell: Tuple[int, int, int]
    gal_id: int
    sector_auid: int
    sector_name: str
    created_sector: bool
    sector_loc: Tuple[float, float, float]
    system_auid: int
    system_name: str
    site: object
    home: object
    rows: object
    home_globe_auid: int
    home_globe_name: str
    region_index: int
    tier: str


@dataclass
class Homestead:

    galaxy: gg.GalaxyType
    sector_cell: Tuple[int, int, int]
    sector_auid: int
    system_auid: int
    system_name: str
    system_seed: int
    home_globe_auid: int
    home_globe_name: str
    reroll_attempts: int
    minerals: int
    organics: int
    rows_written: int
    created_sector: bool
    region_index: int = 8
    tier: str = "remote"


GALAXY_CHOICES = {15: "ShoresOfHazeron", 17: "VeilOfTargoss"}
DEFAULT_GALAXY_INDEX = 15

REGION_NAMES: Tuple[str, ...] = (
    "Eastern Cluster", "Western Cluster", "Northern Cluster", "Southern Cluster",
    "Eastern Frontier", "Western Frontier", "Northern Frontier",
    "Southern Frontier", "Remote",
)
REGION_REMOTE = 8

_REGION_BEARING = ("east", "west", "north", "south",
                   "east", "west", "north", "south", None)

_REGION_TIER = ("cluster", "cluster", "cluster", "cluster",
                "frontier", "frontier", "frontier", "frontier", "remote")


def region_index(region) -> int:
    if isinstance(region, int):
        if 0 <= region < len(REGION_NAMES):
            return region
        raise HomesteadError(
            f"Region {region} out of range; expected 0..{len(REGION_NAMES) - 1}")
    want = str(region).strip().lower()
    for i, name in enumerate(REGION_NAMES):
        if want == name.lower():
            return i
    raise HomesteadError(
        f"Unknown region {region!r}; expected one of {', '.join(REGION_NAMES)} or 0..{len(REGION_NAMES) - 1}")


def region_bearing(region) -> Optional[str]:
    return _REGION_BEARING[region_index(region)]


def region_tier(region) -> str:
    return _REGION_TIER[region_index(region)]


def bearing_matches(bearing: Optional[str], cx: int, cy: int) -> bool:
    if bearing is None:
        return True
    if cx == 0 and cy == 0:
        return False
    if abs(cx) >= abs(cy):
        return (cx > 0) if bearing == "east" else (
            (cx < 0) if bearing == "west" else False)
    return (cy > 0) if bearing == "north" else (
        (cy < 0) if bearing == "south" else False)


def candidate_cells(galaxy: gg.GalaxyType, dm: gg.DensityMap, region,
                    *, max_cells: int = 4000) -> Iterator[Tuple[int, int, int]]:
    bearing = region_bearing(region)
    seen = 0
    for radius in range(0, gg.sector_span(galaxy) + 1):
        for cy in range(-radius, radius + 1):
            for cx in range(-radius, radius + 1):
                if max(abs(cx), abs(cy)) != radius:
                    continue
                if not bearing_matches(bearing, cx, cy):
                    continue
                for cz in (0, 1, -1, 2, -2):
                    if gg.systems_in_sector(galaxy, dm, cx, cy, cz) > 0:
                        yield (cx, cy, cz)
                        seen += 1
                        if seen >= max_cells:
                            return
                        break


def _auid(seed: int, salt: int) -> int:
    v = (int(seed) ^ ((salt * 0x9E3779B1) & 0xFFFFFFFF)) & 0xFFFFFFFF
    v ^= (v >> 16)
    v = (v * 0x7FEB352D) & 0xFFFFFFFF
    v ^= (v >> 15)
    return v or 1


_ATOM_TABLES = ("a_Sector", "a_SolarSystem", "a_Star", "a_WorldGlobe",
                "a_WorldGasGiant", "a_WorldRing", "a_WorldRingSection")


async def _id_taken(con: asyncpg.Connection, auid: int) -> bool:
    return await _repo.atom_id_taken(con, auid)


def make_claimer(con: asyncpg.Connection) -> Callable[[int, int], int]:
    handed: set = set()

    async def claim(seed: int, salt: int) -> int:
        v = _auid(seed, salt)
        while v in handed or await _id_taken(con, v):
            v = ((v + 1) & 0xFFFFFFFF) or 1
        handed.add(v)
        return v

    def reserve(auid: int) -> int:
        auid = int(auid) & 0xFFFFFFFF
        handed.add(auid)
        return auid

    claim.reserve = reserve          # type: ignore[attr-defined]
    claim.handed = handed            # type: ignore[attr-defined]
    return claim


async def system_is_materialised(con: asyncpg.Connection,
                                 system_auid: int) -> bool:
    return await _repo.system_is_materialised(con, system_auid)


async def _city_sector_locations(con: asyncpg.Connection):
    return await _repo.city_sector_locations(con)


async def named_sector_cells(con: asyncpg.Connection) -> set:
    cells = set()
    rows = await _city_sector_locations(con)
    for lx, ly, lz in rows:
        cells.add((int(round((lx or 0) / gg.SECTOR_SIZE)),
                   int(round((ly or 0) / gg.SECTOR_SIZE)),
                   int(round((lz or 0) / gg.SECTOR_SIZE))))
    return cells


def _adjacent(cell, named: set) -> bool:
    cx, cy, cz = cell
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if dx == dy == dz == 0:
                    continue
                if (cx + dx, cy + dy, cz + dz) in named:
                    return True
    return False


def tier_admits(tier: str, cell, named: set) -> bool:
    if tier == "cluster":
        return True
    if cell in named:
        return False
    return _adjacent(cell, named) if tier == "frontier" else         not _adjacent(cell, named)


async def _pool(con: asyncpg.Connection, kind: str) -> List[str]:
    return await _repo.name_pool(con, kind)


async def _galaxy_row(con: asyncpg.Connection):
    return await _repo.galaxy_row(con)


async def _sector_row(con: asyncpg.Connection, sector_auid: int):
    return await _repo.sector_row(con, sector_auid)


async def _insert_sector(con: asyncpg.Connection, plan: "HomesteadPlan",
                         sx: float, sy: float, sz: float) -> None:
    await _repo.insert_sector(con, plan.sector_auid, plan.gal_id,
                              sx, sy, sz, plan.sector_name)


async def _rename_sector(con: asyncpg.Connection,
                         plan: "HomesteadPlan") -> None:
    await _repo.rename_sector(con, plan.sector_auid, plan.sector_name)


async def _insert_solar_system(con: asyncpg.Connection, plan: "HomesteadPlan",
                               site) -> None:
    await _repo.insert_solar_system(
        con, plan.system_auid, plan.sector_auid,
        site.x, site.y, site.z,
        site.rot_x_deg, site.rot_y_deg, site.rot_z_deg, plan.system_name,
        site.seed, plan.home.gen_hab)


def _pick(pool: Sequence[str], seed: int, fallback: str) -> str:
    if not pool:
        return fallback
    return pool[(int(seed) & 0x7FFFFFFF) % len(pool)]


async def plan_homestead(con: asyncpg.Connection, *,
                         galaxy_name: Optional[str] = None,
                         galaxy_index: Optional[int] = None,
                         region=REGION_REMOTE, galaxy_number: int = 1,
                         created: int = 1577836800,
                         maps_dir: Optional[str] = None,
                         max_sectors: int = 40,
                         policy: Optional[HomePolicy] = None,
                         detail: bool = True) -> HomesteadPlan:
    from .worldgen import atom_writer as aw

    policy = policy or DEFAULT_POLICY
    if galaxy_index is not None:
        galaxy_name = GALAXY_CHOICES.get(int(galaxy_index))
        if galaxy_name is None:
            raise HomesteadError(
                f"Galaxy index {galaxy_index} is not one the client offers; its Origin box has only {', '.join((f'{k} ({v})' for k, v in GALAXY_CHOICES.items()))}")
    galaxy = gg.GALAXY_BY_NAME.get(galaxy_name or "")
    if galaxy is None:
        raise HomesteadError(
            f"Unknown galaxy {galaxy_name!r}; expected one of {', '.join(sorted(gg.GALAXY_BY_NAME))}")
    ridx = region_index(region)
    tier = region_tier(ridx)
    named = await named_sector_cells(con)
    if tier == "frontier" and not named:
        logger.info("%s: no sector in this universe has a name yet.",
                    REGION_NAMES[ridx])
        tier = "remote"
    maps_dir = maps_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "galaxy_maps")
    dm = gg.DensityMap(os.path.join(maps_dir, galaxy.name + ".png"))

    gal = await _galaxy_row(con)
    if gal is None:
        raise HomesteadError("a_Galaxy is empty. Nothing to hang a sector off")
    gal_id = int(gal[0])

    if gal[1] is not None and gal[2] is not None:
        galaxy_number, created = int(gal[1]), int(gal[2])
    else:
        logger.warning('a_Galaxy has no galaxy/timeCreate; falling back to galaxy_number=%s created=%s.',
                       galaxy_number, created)

    prov = await gg.read_generation(con)
    if prov is not None and prov["galaxy_name"] != galaxy.name:
        raise HomesteadError(
            f"universe galaxy is {prov['galaxy_name']}, not {galaxy.name}.")
    if prov is None:
        logger.warning("universe predates b_GalaxyGen so its galaxy type is unrecorded. %s cannot be checked against it.", galaxy.name)

    gseed = gg.galaxy_seed(galaxy_number, created)

    claim = make_claimer(con)
    sector_names = await _pool(con, "sector")
    star_names = await _pool(con, "star") + await _pool(con, "star_alien")

    tried = 0
    skipped = 0
    wrong_tier = 0
    for cell in candidate_cells(galaxy, dm, ridx):
        if tried >= max_sectors:
            break
        if not tier_admits(tier, cell, named):
            wrong_tier += 1
            continue
        cx, cy, cz = cell
        plan = gg.create_sector(galaxy, dm, gseed, cx, cy, cz)
        if plan is None:
            continue

        sector_auid = _auid(plan.seed, 0xA1)
        sector_row = await _sector_row(con, sector_auid)
        created_sector = sector_row is None

        candidates = []
        sys_auids = []
        for i, site in enumerate(plan.systems):
            yid = _auid(site.seed, 0xB2 + i)
            sys_auids.append(yid)
            claim.reserve(yid)
            if await system_is_materialised(con, yid):
                continue
            core_bh = (cx == cy == cz == 0
                       and site.x == 0.0 and site.y == 0.0 and site.z == 0.0)
            candidates.append((i, site.seed, core_bh))
        if not candidates:
            skipped += 1
            continue

        tried += 1
        got = wg.create_good_home(candidates, galaxy_index=galaxy.index,
                                  **policy.home_kwargs())
        if got is None:
            continue
        idx, home = got
        site = plan.systems[idx]
        site.seed = home.gen_seed
        system_auid = sys_auids[idx]

        sx, sy, sz = plan.location
        system_name = _pick(star_names, site.seed, f"System_{system_auid:06x}")

        primary = wg.finalize_contents(site.seed, gen_hab=home.gen_hab,
                                       galaxy_index=galaxy.index)
        wg.name_worlds(primary, system_name)
        rows = await aw.build_system_rows(primary, system_auid, site.seed,
                                          claim, detail=detail)

        home_auid = home_name = None
        if home.world is not None:
            target = (home.world.size & 0xFF, home.world.atm_density & 0xFF,
                      home.world.atm_type & 0xFF, home.world.water & 0xFF)
            for row in rows.globe:
                if (int(row[6]), row[7][0], row[8][0], row[9][0]) == target:
                    home_auid, home_name = row[0], row[3]
                    break
            if home_auid is None:
                raise HomesteadError(
                    f"Built system {system_name!r} but could not identify the homeworld among {len(rows.globe)} globes.")
        elif not policy.spawn_on_ringworld:
            raise HomesteadError(
                f"The {policy.label!r} policy accepted system {system_name!r} with no habitable planet but does not say where to put the character.")

        if policy.spawn_on_ringworld:
            if not rows.ring_section:
                raise HomesteadError(
                    f"The {policy.label!r} policy wants the character on a ringworld, and system {system_name!r} was accepted for holding one, but no a_WorldRingSection rows were built.")
            first = min(rows.ring_section, key=lambda r: int(r[9]))
            home_auid, home_name = first[0], first[3]

        return HomesteadPlan(
            galaxy=galaxy, cell=cell, gal_id=gal_id,
            sector_auid=sector_auid,
            sector_name=system_name,
            created_sector=created_sector, sector_loc=(sx, sy, sz),
            system_auid=system_auid, system_name=system_name,
            site=site, home=home, rows=rows,
            home_globe_auid=home_auid, home_globe_name=home_name,
            region_index=ridx, tier=tier)

    raise HomesteadExhausted(
        f"No unvisited system with a habitable world found in the {REGION_NAMES[ridx]} of {galaxy.name}: {tried} of {max_sectors} sectors tried, {skipped} already fully settled, {wrong_tier} the wrong side of the {tier} rule"
        + ("" if policy is DEFAULT_POLICY else
           f" -- and this search was running the {policy.label!r} acceptance "
           f"test, which is far narrower than the default one, so read this as "
           f"'{policy.label} could not be satisfied here' rather than 'the "
           f"region is full'"))


async def commit_homestead(con: asyncpg.Connection,
                           plan: HomesteadPlan) -> Homestead:
    from .worldgen import atom_writer as aw

    if await system_is_materialised(con, plan.system_auid):
        raise HomesteadTaken(
            f"System {plan.system_name!r} (0x{plan.system_auid:08x}) was claimed while this homestead was being planned")

    sx, sy, sz = plan.sector_loc
    if plan.created_sector:
        await _insert_sector(con, plan, sx, sy, sz)
    else:
        await _rename_sector(con, plan)

    site = plan.site
    await _insert_solar_system(con, plan, site)

    await aw.write_system_rows(con, plan.rows)

    return Homestead(
        galaxy=plan.galaxy, sector_cell=plan.cell,
        sector_auid=plan.sector_auid, system_auid=plan.system_auid,
        system_name=plan.system_name, system_seed=site.seed,
        home_globe_auid=plan.home_globe_auid,
        home_globe_name=plan.home_globe_name,
        reroll_attempts=plan.home.attempts, minerals=plan.home.minerals,
        organics=plan.home.organics, rows_written=plan.rows.total,
        created_sector=plan.created_sector,
        region_index=plan.region_index, tier=plan.tier)


async def create_homestead(con: asyncpg.Connection, **kwargs) -> Homestead:
    return await commit_homestead(con,
                                  await plan_homestead(con, **kwargs))
