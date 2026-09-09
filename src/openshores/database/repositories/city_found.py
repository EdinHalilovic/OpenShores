from __future__ import annotations

import asyncpg

from openshores.database.repositories.homestead import _replace_set_clause


async def replace_city_row(conn: asyncpg.Connection, vals: dict,
                           cols: set) -> None:
    vals = {k: v for k, v in vals.items() if k in cols}
    keys = ",".join(f'"{k}"' for k in vals)
    placeholders = ",".join(f"${i + 1}" for i in range(len(vals)))
    set_clause = _replace_set_clause(cols, tuple(vals))
    await conn.execute(
        f'INSERT INTO "a_City" ({keys}) VALUES ({placeholders}) '
        f'ON CONFLICT ("id") DO UPDATE SET {set_clause}', *vals.values())


async def replace_bd_row(conn: asyncpg.Connection, vals: dict,
                         cols: set) -> None:
    vals = {k: v for k, v in vals.items() if k in cols}
    keys = ",".join(f'"{k}"' for k in vals)
    placeholders = ",".join(f"${i + 1}" for i in range(len(vals)))
    set_clause = _replace_set_clause(cols, tuple(vals))
    await conn.execute(
        f'INSERT INTO "a_Bd" ({keys}) VALUES ({placeholders}) '
        f'ON CONFLICT ("id") DO UPDATE SET {set_clause}', *vals.values())


async def founder_name_and_dna(conn: asyncpg.Connection, person_auid: int):
    return await conn.fetchrow(
        'SELECT "name", "dna" FROM "a_Person" WHERE "id" IN ($1, $2)',
        person_auid & 0xFFFFFFFF, person_auid)


async def founder_name(conn: asyncpg.Connection, person_auid: int):
    return await conn.fetchrow(
        'SELECT "name" FROM "a_Person" WHERE "id" IN ($1, $2)',
        person_auid & 0xFFFFFFFF, person_auid)


async def set_city_sim_state(conn: asyncpg.Connection, doc: str,
                             city_id: int) -> None:
    await conn.execute(
        'UPDATE "a_City" SET "sim_state" = $1 WHERE "id" = $2', doc, city_id)
