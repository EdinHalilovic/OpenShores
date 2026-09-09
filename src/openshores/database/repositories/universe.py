
from __future__ import annotations

from typing import Optional, Sequence

import asyncpg

_ATOM_TABLES = ("a_Sector", "a_SolarSystem", "a_Star", "a_WorldGlobe",
                "a_WorldGasGiant", "a_WorldRing", "a_WorldRingSection")


async def universe_row(conn: asyncpg.Connection) -> Optional[asyncpg.Record]:
    return await conn.fetchrow('SELECT * FROM "a_Universe" LIMIT 1')


async def insert_universe(conn: asyncpg.Connection, *, auid: int, name: str,
                          created_ms: int) -> None:
    await conn.execute(
        'INSERT INTO "a_Universe" ("id", "name", "timeCreate", "timeModified")'
        ' VALUES ($1, $2, $3, $3)',
        int(auid), str(name), int(created_ms))


async def insert_galaxy(conn: asyncpg.Connection, *, auid: int,
                        universe_auid: int, name: str, galaxy_number: int,
                        created: int) -> None:
    await conn.execute(
        'INSERT INTO "a_Galaxy" ("id", "idp", "parent_atom", "name",'
        ' "galaxy", "timeCreate") VALUES ($1, $2, $2, $3, $4, $5)',
        int(auid), int(universe_auid), str(name), str(int(galaxy_number)),
        int(created))


async def insert_sectors(conn: asyncpg.Connection,
                         rows: Sequence[tuple]) -> None:
    await conn.executemany(
        'INSERT INTO "a_Sector" ("id", "idp", "parent_atom", "locX", "locY",'
        ' "locZ", "name") VALUES ($1, $2, $3, $4, $5, $6, $7)', rows)


async def insert_solar_systems(conn: asyncpg.Connection,
                               rows: Sequence[tuple]) -> None:
    await conn.executemany(
        'INSERT INTO "a_SolarSystem" ("id", "idp", "parent_atom", "locX",'
        ' "locY", "locZ", "rotX", "rotY", "rotZ", "name", "genSeed",'
        ' "genHab") VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)',
        rows)


async def set_system_wormholes(conn: asyncpg.Connection,
                               rows: Sequence[tuple]) -> None:
    await conn.executemany(
        'UPDATE "a_SolarSystem" SET "wormholes" = $1 WHERE "id" = $2', rows)


async def used_atom_ids(conn: asyncpg.Connection) -> set:
    used: set = set()
    for table in _ATOM_TABLES:
        used.update(int(r[0])
                    for r in await conn.fetch(f'SELECT "id" FROM "{table}"'))
    return used


async def atom_row_counts(conn: asyncpg.Connection) -> dict:
    tables = ("a_Universe", "a_Galaxy") + _ATOM_TABLES
    return {t: int(await conn.fetchval(f'SELECT count(*) FROM "{t}"'))
            for t in tables}


__all__ = ["universe_row", "insert_universe", "insert_galaxy",
           "insert_sectors", "insert_solar_systems", "set_system_wormholes",
           "used_atom_ids", "atom_row_counts"]
