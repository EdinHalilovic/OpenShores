
from __future__ import annotations

import asyncpg


async def all_city_rows(conn: asyncpg.Connection) -> list:
    return await conn.fetch('SELECT * FROM "a_City"')
