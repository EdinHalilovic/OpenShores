
from __future__ import annotations

import asyncpg

from openshores.database.repositories.spawn import globe_row


def _city_id_variants(cauid: int):
    u = int(cauid) & 0xFFFFFFFF
    sgn = u if u < 0x80000000 else u - 0x100000000
    return (u, sgn)


async def city_and_globe(conn: asyncpg.Connection, cauid: int):
    u, sgn = _city_id_variants(int(cauid))
    city = await conn.fetchrow(
        'SELECT "idp", "locX", "locY", "locZ" FROM "a_City" '
        'WHERE "id" IN ($1, $2)', u, sgn)
    globe = None
    if city is not None and city["idp"]:
        globe = await globe_row(conn, city["idp"])
    return city, globe
