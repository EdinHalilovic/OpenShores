
from __future__ import annotations

import asyncpg

from openshores.database.repositories.world import _table_columns


async def persisted_city_rows(conn: asyncpg.Connection) -> list:
    cols = await _table_columns(conn, "a_City")
    if "developments" not in cols:
        return []
    _alg = '"allegiance"' if "allegiance" in cols else "0"
    return await conn.fetch(
        f'SELECT "id", "idp", "locX", "locY", "locZ", "name", "developments", {_alg} '
        'FROM "a_City" WHERE "developments" IS NOT NULL')
