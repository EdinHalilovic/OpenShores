
from __future__ import annotations

from typing import List

import asyncpg

from openshores.database.repositories.world import _table_columns

_ATOM_TABLES = ("a_Sector", "a_SolarSystem", "a_Star", "a_WorldGlobe",
                "a_WorldGasGiant", "a_WorldRing", "a_WorldRingSection")

_ID_TAKEN_SQL = (
    'SELECT 1 FROM (\n'
    + '\n    UNION ALL\n'.join(
        f'    SELECT 1 AS "hit" FROM "{t}" WHERE "id" = $1'
        for t in _ATOM_TABLES)
    + '\n) AS "any" LIMIT 1')


async def atom_id_taken(conn: asyncpg.Connection, auid: int) -> bool:
    return bool(await conn.fetchrow(_ID_TAKEN_SQL, int(auid)))


async def system_is_materialised(conn: asyncpg.Connection,
                                 system_auid: int) -> bool:
    return bool(await conn.fetchrow(
        'SELECT 1 FROM "a_Star" WHERE "parent_atom" = $1 LIMIT 1',
        int(system_auid)))


async def city_sector_locations(conn: asyncpg.Connection):
    return await conn.fetch(
        'SELECT DISTINCT "sec"."locX", "sec"."locY", "sec"."locZ" '
        'FROM "a_City" AS "c" '
        'JOIN "a_WorldGlobe" AS "g" ON "g"."id" = "c"."idp" '
        'JOIN "a_Star" AS "st" ON "st"."id" = "g"."parent_atom" '
        'JOIN "a_SolarSystem" AS "sy" ON "sy"."id" = "st"."parent_atom" '
        'JOIN "a_Sector" AS "sec" ON "sec"."id" = "sy"."parent_atom"')


async def name_pool(conn: asyncpg.Connection, kind: str) -> List[str]:
    return [r[0] for r in await conn.fetch(
        'SELECT "name" FROM "names" WHERE "kind" = $1 AND "name" IS NOT NULL '
        'ORDER BY "auid", "name"', kind)]


async def galaxy_row(conn: asyncpg.Connection):
    return await conn.fetchrow(
        'SELECT "id", "galaxy", "timeCreate" FROM "a_Galaxy" LIMIT 1')


async def sector_row(conn: asyncpg.Connection, sector_auid: int):
    return await conn.fetchrow(
        'SELECT "id" FROM "a_Sector" WHERE "id" = $1', int(sector_auid))


def _replace_set_clause(cols: set, named) -> str:
    every = sorted((cols or set()) | set(named))
    return ", ".join(
        f'"{c}" = EXCLUDED."{c}"' if c in named else f'"{c}" = NULL'
        for c in every if c != "id")


_SECTOR_COLUMNS = ("id", "idp", "parent_atom", "locX", "locY", "locZ", "name")


async def insert_sector(conn: asyncpg.Connection, sector_auid: int,
                        gal_id: int, sx: float, sy: float, sz: float,
                        name: str) -> None:
    set_clause = _replace_set_clause(
        await _table_columns(conn, "a_Sector"), _SECTOR_COLUMNS)
    await conn.execute(
        'INSERT INTO "a_Sector" '
        '("id", "idp", "parent_atom", "locX", "locY", "locZ", "name") '
        'VALUES ($1, $2, $3, $4, $5, $6, $7) '
        f'ON CONFLICT ("id") DO UPDATE SET {set_clause}',
        int(sector_auid), int(gal_id), int(gal_id),
        float(sx), float(sy), float(sz), name)


async def rename_sector(conn: asyncpg.Connection, sector_auid: int,
                        name: str) -> None:
    await conn.execute(
        'UPDATE "a_Sector" SET "name" = $1 WHERE "id" = $2',
        name, int(sector_auid))


_SOLAR_SYSTEM_COLUMNS = ("id", "idp", "parent_atom", "locX", "locY", "locZ",
                         "rotX", "rotY", "rotZ", "name", "genSeed", "genHab")


async def insert_solar_system(conn: asyncpg.Connection, system_auid: int,
                              sector_auid: int, x: float, y: float, z: float,
                              rot_x_deg: float, rot_y_deg: float,
                              rot_z_deg: float, name: str, gen_seed: int,
                              gen_hab: int) -> None:
    set_clause = _replace_set_clause(
        await _table_columns(conn, "a_SolarSystem"), _SOLAR_SYSTEM_COLUMNS)
    await conn.execute(
        'INSERT INTO "a_SolarSystem" '
        '("id", "idp", "parent_atom", "locX", "locY", "locZ", '
        '"rotX", "rotY", "rotZ", "name", "genSeed", "genHab") '
        'VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) '
        f'ON CONFLICT ("id") DO UPDATE SET {set_clause}',
        int(system_auid), int(sector_auid), int(sector_auid),
        float(x), float(y), float(z),
        float(rot_x_deg), float(rot_y_deg), float(rot_z_deg), name,
        int(gen_seed), int(gen_hab))
