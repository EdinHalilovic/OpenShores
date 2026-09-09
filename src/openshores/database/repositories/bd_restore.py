
from __future__ import annotations

import asyncpg

from openshores.database.repositories.city_site import _city_id_variants


async def bd_restore_rows(conn: asyncpg.Connection, sel: list) -> list:
    projection = ",".join(f'"{c}"' for c in sel)
    return list(await conn.fetch(f'SELECT {projection} FROM "a_Bd"'))


async def city_capitol_rows(conn: asyncpg.Connection, *, has_capitol: bool,
                            has_name: bool) -> list:
    csel = ('"id", ' + ('"capitol"' if has_capitol else "0")
            + (', "name"' if has_name else ", ''::text"))
    return list(await conn.fetch(f'SELECT {csel} FROM "a_City"'))


async def city_developments_by_variants(conn: asyncpg.Connection, city_id):
    u, sgn = _city_id_variants(int(city_id))
    return await conn.fetchrow(
        'SELECT "developments" FROM "a_City" WHERE "id" IN ($1, $2)', u, sgn)
