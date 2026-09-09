
from __future__ import annotations

from typing import Dict, Optional

import asyncpg


async def record_generation(conn: asyncpg.Connection, *, galaxy_name: str,
                            galaxy_number: int, created: int,
                            tool: str) -> None:
    await conn.execute(
        'INSERT INTO "b_GalaxyGen" '
        '("id", "galaxy_name", "galaxy_number", "created", "tool") '
        'VALUES (1, $1, $2, $3, $4) '
        'ON CONFLICT ("id") DO UPDATE SET '
        '"galaxy_name" = EXCLUDED."galaxy_name", '
        '"galaxy_number" = EXCLUDED."galaxy_number", '
        '"created" = EXCLUDED."created", '
        '"tool" = EXCLUDED."tool"',
        str(galaxy_name), int(galaxy_number), int(created), str(tool))


async def read_generation(conn: asyncpg.Connection
                          ) -> Optional[Dict[str, object]]:
    row = await conn.fetchrow(
        'SELECT "galaxy_name", "galaxy_number", "created" '
        'FROM "b_GalaxyGen" WHERE "id" = 1')
    if row is None:
        return None
    return {"galaxy_name": row[0], "galaxy_number": int(row[1]),
            "created": int(row[2])}


__all__ = ["record_generation", "read_generation"]
