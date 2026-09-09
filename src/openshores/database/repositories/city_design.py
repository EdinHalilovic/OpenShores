
from __future__ import annotations

import asyncpg


async def design_report_blobs(conn: asyncpg.Connection, bauids) -> list:
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'a_Bd'""")}
    if "designRpt" not in cols:
        return []
    marks = ",".join(f"${i + 1}" for i in range(len(bauids)))
    return await conn.fetch(
        f'SELECT "id", "designRpt" FROM "a_Bd" WHERE "id" IN ({marks})',
        *bauids)
