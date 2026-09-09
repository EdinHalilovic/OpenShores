
from __future__ import annotations

import asyncpg

from openshores.database.repositories.world import _table_columns


async def read_city_world_auid(conn: asyncpg.Connection, city_auid: int):
    return await conn.fetchrow(
        'SELECT "idp" FROM "a_City" WHERE "id" = $1',
        int(city_auid) & 0xFFFFFFFF)


async def planet_city_rows(conn: asyncpg.Connection, world_auid: int):
    cols = await _table_columns(conn, "a_City")
    if not {"idp", "allegiance", "locX"} <= cols:
        return []
    return await conn.fetch(
        'SELECT "id", "allegiance", "locX", "locY", "locZ" FROM "a_City" '
        'WHERE "idp" = $1',
        int(world_auid) & 0xFFFFFFFF)


async def planet_city_ids(conn: asyncpg.Connection, planet_auid: int):
    return await conn.fetch(
        'SELECT "id" FROM "a_City" WHERE "idp" = $1',
        int(planet_auid))


async def planet_city_atom_rows(conn: asyncpg.Connection, planet_auid: int):
    cols = await _table_columns(conn, "a_City")
    _cty_alg = '"allegiance"' if "allegiance" in cols else "0"
    return await conn.fetch(
        f'SELECT "id", "idp", "locX", "locY", "locZ", "name", '
        f'"developments", {_cty_alg} '
        'FROM "a_City" WHERE "idp" = $1',
        int(planet_auid))


async def planet_city_developments(conn: asyncpg.Connection, planet_auid: int):
    return await conn.fetch(
        'SELECT "developments" FROM "a_City" WHERE "idp" = $1 '
        'AND "developments" IS NOT NULL',
        int(planet_auid))
