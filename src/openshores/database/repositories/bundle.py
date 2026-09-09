
from __future__ import annotations

import struct
from typing import Optional, Tuple

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.world_loader import (
    apply_sql_world_to_bundle,
)

logger = get_logger(__name__)


GAME_UNITS_PER_AU = 2_400_000.0


class DbBundleError(RuntimeError):
    pass


def _as_double(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    b = bytes(v)
    return struct.unpack("<d", b)[0] if len(b) == 8 else None


def _as_byte(v) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    b = bytes(v)
    return b[0] if b else None


_ATOM_TABLES = ("a_WorldGlobe", "a_WorldGasGiant", "a_WorldRing",
                "a_WorldRingSection", "a_Star", "a_SolarSystem", "a_Sector",
                "a_Galaxy", "a_Universe")


_FIND_ATOM_TABLE_SQL = (
    'SELECT "tbl" FROM (\n'
    + '\n    UNION ALL\n'.join(
        f'    SELECT {i} AS "ord", \'{t}\' AS "tbl" FROM "{t}" WHERE "id" = $1'
        for i, t in enumerate(_ATOM_TABLES))
    + '\n) AS "hit" ORDER BY "ord" LIMIT 1')

_ATOM_PARENTS_SQL = (
    'SELECT DISTINCT ON ("id") "id", "tbl", "parent_atom", "ord" FROM (\n'
    + '\n    UNION ALL\n'.join(
        f'    SELECT "id", "parent_atom", {i} AS "ord", \'{t}\' AS "tbl" '
        f'FROM "{t}" WHERE "id" = ANY($1::bigint[])'
        for i, t in enumerate(_ATOM_TABLES))
    + '\n) AS "hit" ORDER BY "id", "ord"')


async def find_atom_table(conn: asyncpg.Connection, auid: int) -> Optional[str]:
    row = await conn.fetchrow(_FIND_ATOM_TABLE_SQL, int(auid))
    return row["tbl"] if row else None


async def _atom_parents(conn: asyncpg.Connection, auids) -> dict:
    ids = [int(a) for a in auids]
    if not ids:
        return {}
    rows = await conn.fetch(_ATOM_PARENTS_SQL, ids)
    return {int(r["id"]): (r["tbl"], r["parent_atom"]) for r in rows}


async def _ids_reaching(conn: asyncpg.Connection, auids, table: str,
                        limit: int = 10) -> set:
    reaching: set = set()
    frontier: dict = {}
    for a in auids:
        frontier.setdefault(int(a), set()).add(int(a))
    for _ in range(limit):
        if not frontier:
            break
        found = await _atom_parents(conn, list(frontier))
        nxt: dict = {}
        for cur, origins in frontier.items():
            hit = found.get(cur)
            if hit is None:
                continue
            t, parent = hit
            if t == table:
                reaching |= origins
                continue
            if not parent:
                continue
            nxt.setdefault(int(parent), set()).update(origins)
        frontier = nxt
    return reaching


def globe_position(globe_row: dict, system_seed: int, sim_time_ms: float,
                   *, is_moon: bool = False,
                   star_number: int = 0,
                   wch, wc) -> Tuple[float, float, float]:
    body = wch.make_body(globe_row, int(system_seed), breathable=False,
                         is_moon=bool(is_moon), star_number=int(star_number))
    tx, ty, tz = wc.world_transform(body, float(sim_time_ms)).translation
    return (float(tx), float(ty), float(tz))


async def fill_missing_positions(conn: asyncpg.Connection, sim_time_ms: float,
                                 star_auid: int, system_seed: int) -> int:
    n = 0
    for table in ("a_WorldGlobe", "a_WorldGasGiant"):
        rows = await conn.fetch(
            f'SELECT "id", "orbitRadius", "orbitZone", "radius", "locX" '
            f'FROM "{table}" WHERE "parent_atom" = $1', int(star_auid))
        for r in rows:
            if r["locX"] is not None:
                continue
            if _as_double(r["orbitRadius"]) is None:
                continue
            n += 1
    return n


async def pick_person(conn: asyncpg.Connection, name: Optional[str] = None):
    want = name
    if want:
        row = await conn.fetchrow(
            'SELECT * FROM "a_Person" WHERE "name" = $1 '
            'ORDER BY "timeModified" DESC LIMIT 1', want)
        if row is None:
            raise DbBundleError(
                f"{want!r} matches no a_Person row; refusing to "
                f"boot as somebody else")
        return row
    return await conn.fetchrow(
        'SELECT * FROM "a_Person" ORDER BY "timeModified" DESC LIMIT 1')


async def pick_boot_globe(conn: asyncpg.Connection) -> asyncpg.Record:
    def _habitable(row) -> bool:
        t = _as_byte(row["atmType"])
        d = _as_byte(row["atmDensity"])
        w = _as_byte(row["water"])
        return (t == 0 and d is not None and w is not None
                and 15 <= d <= 85 and 15 <= w <= 85)

    rows = await conn.fetch(
        'SELECT * FROM "a_WorldGlobe" ORDER BY "id" LIMIT 4000')

    reaching = await _ids_reaching(conn, [int(r["id"]) for r in rows], "a_Star")

    fallback = None
    for row in rows:
        if int(row["id"]) not in reaching:
            continue
        if _habitable(row):
            return row
        if fallback is None:
            fallback = row
    if fallback is not None:
        return fallback

    raise DbBundleError(
        f'a_Person is empty and no world among {len(rows)} candidates has a parent chain reaching a star, so there is nothing to anchor the bundle on.')


_STANDABLE_TABLES = ("a_WorldGlobe", "a_WorldGasGiant", "a_WorldRingSection")


async def home_globe_for(conn: asyncpg.Connection, person) -> asyncpg.Record:
    idp = int(person["idp"] or 0)
    if not idp:
        raise DbBundleError(
            f"a_Person {person['name']!r} has no idp; it is not on any world")
    for table in _STANDABLE_TABLES:
        row = await conn.fetchrow(f'SELECT * FROM "{table}" WHERE "id" = $1',
                                  idp)
        if row is not None:
            return row
    raise DbBundleError(
        f"a_Person {person['name']!r} has idp={idp} but no row in any of {', '.join(_STANDABLE_TABLES)} has that id.")


async def walk_to(conn: asyncpg.Connection, auid: int, table: str,
                  limit: int = 10) -> Optional[asyncpg.Record]:
    cur = int(auid)
    for _ in range(limit):
        t = await find_atom_table(conn, cur)
        if t is None:
            return None
        row = await conn.fetchrow(f'SELECT * FROM "{t}" WHERE "id" = $1', cur)
        if t == table:
            return row
        parent = row["parent_atom"] if "parent_atom" in row.keys() else None
        if not parent:
            return None
        cur = int(parent)
    return None


async def build_bundle(conn: asyncpg.Connection, bundle, *,
                       SiblingGlobe, gen_planet, gen_moon, HAB_RANDOM,
                       wch, wc, tr,
                       sim_time_ms: Optional[float] = None,
                       person_name: Optional[str] = None,
                       verbose: bool = True):
    b = bundle
    b.source = "hazeron.db"

    uni = await conn.fetchrow('SELECT * FROM "a_Universe" LIMIT 1')
    if uni is None:
        raise DbBundleError("a_Universe is empty")
    b.universe_auid = int(uni["id"])
    b.universe_name = _row_name(conn, "a_Universe", uni) or "Universe"

    gal = await conn.fetchrow('SELECT * FROM "a_Galaxy" LIMIT 1')
    if gal is None:
        raise DbBundleError("a_Galaxy is empty")
    b.galaxy_auid = int(gal["id"])
    b.galaxy_rotation = _rot(gal)

    person = await pick_person(conn, person_name)
    if person is not None:
        b.person_auid = int(person["id"])
        b.person_name = person["name"] or ""
        b.person_dna24 = bytes(person["dna"]) if person["dna"] else None
        b.person_time_created = int(person["timeCreate"] or 0)
        b.person_time_modified = int(person["timeModified"] or 0)
        b.person_pose = int(person["pose"] or 0)
        b.person_stamina = int(person["stamina"] or 0)
        b.person_hunger = int(person["hunger"] or 0)
        b.person_hit_points = int(person["hp"] or 0)
        b.person_position = (float(person["locX"] or 0.0),
                             float(person["locY"] or 0.0),
                             float(person["locZ"] or 0.0))
        b.person_rotation = (float(person["rotX"] or 0.0),
                             float(person["rotY"] or 0.0),
                             float(person["rotZ"] or 0.0))

    globe = (await home_globe_for(conn, person) if person is not None
             else await pick_boot_globe(conn))
    b.planet_auid = int(globe["id"])
    b.planet_name = globe["name"] or ""
    b.whereabouts_auid = int(globe["id"])
    b.whereabouts_place = b.planet_name
    b.whereabouts_display = b.planet_name

    emp = await conn.fetchrow(
        'SELECT "id", "name" FROM "g_Empire" WHERE "name" IS NOT NULL '
        'ORDER BY "id" LIMIT 1')
    if emp is not None:
        b.empire_auid = int(emp["id"])
        b.empire_name = emp["name"] or ""
        b.empire_name_short = (b.empire_name.split() or [""])[0]
        b.capital_name = b.empire_name_short

    b.name_pools = await _name_pools(conn)

    if not await apply_sql_world_to_bundle(
            conn, b, SiblingGlobe=SiblingGlobe, gen_planet=gen_planet,
            gen_moon=gen_moon, HAB_RANDOM=HAB_RANDOM, wch=wch, wc=wc, tr=tr):
        raise DbBundleError(
            f'sql_world_loader could not resolve a parent chain for globe {b.planet_auid} ({b.planet_name!r}).')

    if verbose:
        if person is None:
            logger.info('No characters yet; anchored on %r in %r / %r, %d siblings.',
                        b.planet_name, b.system_name, b.sector_name,
                        len(b.sibling_globes))
        else:
            logger.info("%r on %r in %r / %r, %d siblings, no save file read.",
                        b.person_name, b.planet_name, b.system_name,
                        b.sector_name, len(b.sibling_globes))
    return b


def _row_name(conn, table, row) -> str:
    try:
        return row["name"] or ""
    except (IndexError, KeyError):
        return ""


def _rot(row) -> Tuple[float, float, float]:
    try:
        return (float(row["rotX"] or 0.0), float(row["rotY"] or 0.0),
                float(row["rotZ"] or 0.0))
    except (IndexError, KeyError, TypeError):
        return (0.0, 0.0, 0.0)


async def _name_pools(conn) -> dict:
    pools: dict = {}
    for kind, name in await conn.fetch('SELECT "kind", "name" FROM "names"'):
        pools.setdefault(kind, []).append(name)
    return pools
