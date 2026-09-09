
from __future__ import annotations

import asyncpg


async def world_atm_type(conn: asyncpg.Connection, world_auid: int):
    return await conn.fetchrow(
        'SELECT "atmType" FROM "a_WorldGlobe" WHERE "id" = $1',
        int(world_auid) & 0xFFFFFFFF)


async def system_for_star(conn: asyncpg.Connection, star_idp):
    return await conn.fetchrow(
        'SELECT "id", "genSeed" FROM "a_SolarSystem" WHERE "id" = $1',
        star_idp)


async def star_by_id(conn: asyncpg.Connection, auid):
    return await conn.fetchrow('SELECT * FROM "a_Star" WHERE "id" = $1', auid)


async def star_children(conn: asyncpg.Connection, primary_auid) -> list:
    return await conn.fetch('SELECT * FROM "a_Star" WHERE "idp" = $1',
                            primary_auid)
