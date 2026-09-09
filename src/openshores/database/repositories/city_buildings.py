from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.world import _table_columns

logger = get_logger(__name__)


async def _city_identity(conn: asyncpg.Connection, cid):
    cap = 0
    name = ""
    alleg = 0
    cid_u = int(cid) & 0xFFFFFFFF
    try:
        cols = await _table_columns(conn, "a_City")
        sel = [c for c in ("capitol", "name", "allegiance") if c in cols]
        if sel and "id" in cols:
            projection = ",".join(f'"{c}"' for c in sel)
            row = await conn.fetchrow(
                f'SELECT {projection} FROM "a_City" WHERE "id" = $1',
                cid_u)
            if row:
                d = dict(zip(sel, row))
                cap = int(d.get("capitol") or 0) & 0xFFFFFFFF
                name = d.get("name") or ""
                alleg = int(d.get("allegiance") or 0) & 0xFFFFFFFF
        if not cap:
            bcols = await _table_columns(conn, "a_Bd")
            if {"id", "capitol", "industry"} <= bcols:
                r = await conn.fetchrow(
                    'SELECT "id" FROM "a_Bd" WHERE "capitol" = $1 '
                    'AND "industry" = $2 ORDER BY "id" LIMIT 1', cid_u, 0x7B)
                if r:
                    cap = int(r[0]) & 0xFFFFFFFF
    except Exception as exc:
        logger.error(f"[city-identity] a_City query err for 0x{cid_u:08x}: {exc!r}")
    return cap, name, alleg


async def read_city_developments(conn: asyncpg.Connection, cid):
    row = await conn.fetchrow(
        'SELECT "developments" FROM "a_City" WHERE "id" = $1', cid)
    return row[0] if row else None


async def write_city_developments(conn: asyncpg.Connection, cid, blob) -> None:
    await conn.execute(
        'UPDATE "a_City" SET "developments" = $1 WHERE "id" = $2', blob, cid)


async def bd_row_ids(conn: asyncpg.Connection) -> set:
    return {int(r[0]) & 0xFFFFFFFF
            for r in await conn.fetch('SELECT "id" FROM "a_Bd"')}


async def city_development_rows(conn: asyncpg.Connection, cid=None) -> list:
    if cid is None:
        return list(await conn.fetch(
            'SELECT "id", "developments" FROM "a_City"'))
    return list(await conn.fetch(
        'SELECT "id", "developments" FROM "a_City" WHERE "id" = $1', cid))
