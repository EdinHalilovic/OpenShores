
from __future__ import annotations

from typing import Optional

import asyncpg

from openshores.database.repositories.world_loader import _walk_to_root


async def _system_of_globe(conn: asyncpg.Connection, globe_auid: int):
    globe_auid = int(globe_auid or 0) & 0xFFFFFFFF
    if not globe_auid:
        return None
    for tbl, row in await _walk_to_root(conn, globe_auid):
        if tbl == "a_SolarSystem":
            return int(row.get("id")) & 0xFFFFFFFF
    return None


async def is_walkable_globe(conn: asyncpg.Connection, globe_auid: int) -> bool:
    globe_auid = int(globe_auid) & 0xFFFFFFFF
    if not globe_auid:
        return False
    row = await conn.fetchrow(
        'SELECT "id" FROM "a_WorldGlobe" WHERE "id" = $1', globe_auid)
    if not row:
        return False
    return bool(await _walk_to_root(conn, globe_auid))


async def find_worlds(conn: asyncpg.Connection, name_like: str,
                      limit: int = 25) -> list:
    rows = await conn.fetch(
        'SELECT "g"."id", "g"."name", "sys"."name", "sec"."name" '
        'FROM "a_WorldGlobe" "g" '
        'LEFT JOIN "a_Star" "st"  ON "st"."id"  = "g"."parent_atom" '
        'LEFT JOIN "a_SolarSystem" "sys" ON "sys"."id" = "st"."parent_atom" '
        'LEFT JOIN "a_Sector" "sec" ON "sec"."id" = "sys"."parent_atom" '
        'WHERE "g"."name" LIKE $1 ORDER BY "g"."name" LIMIT $2',
        f"%{name_like}%", int(limit))
    return [(int(r[0]), r[1] or "", r[2] or "", r[3] or "") for r in rows]


async def globe_row_for_fauna(conn: asyncpg.Connection,
                              world_auid: int) -> Optional[dict]:
    row = await conn.fetchrow(
        'SELECT "id", "orbitZone", "atmType", "atmDensity", "water" '
        'FROM "a_WorldGlobe" WHERE "id" = $1', int(world_auid) & 0xFFFFFFFF)
    if not row:
        return None
    return {"id": row[0], "orbitZone": row[1], "atmType": row[2],
            "atmDensity": row[3], "water": row[4]}
