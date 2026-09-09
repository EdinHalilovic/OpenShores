from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.world import _table_columns

logger = get_logger(__name__)


_DEMOLISH_BD_MATCH_M = 5.0


async def _demolish_db_lookup(conn: asyncpg.Connection, auid):
    auid = int(auid) & 0xFFFFFFFF
    try:
        async def cols(t):
            return await _table_columns(conn, t)
        ac = await cols("a_City")
        if "id" in ac and await conn.fetchrow(
                'SELECT 1 FROM "a_City" WHERE "id" = $1', auid):
            return "city", auid
        if "capitol" in ac and "id" in ac:
            row = await conn.fetchrow(
                'SELECT "id" FROM "a_City" WHERE "capitol" = $1', auid)
            if row:
                return "city", int(row[0]) & 0xFFFFFFFF
        bc = await cols("a_Bd")
        if "id" in bc:
            sel = [c for c in ("id", "locX", "locY", "locZ", "capitol",
                               "industry", "name") if c in bc]
            projection = ",".join(f'"{c}"' for c in sel)
            row = await conn.fetchrow(
                f'SELECT {projection} FROM "a_Bd" WHERE "id" = $1', auid)
            if row:
                return "building", dict(zip(sel, row))
    except Exception as exc:
        logger.error(f"[demolish] db lookup err for 0x{auid:08x}: {exc!r}")
    return None, None


async def _demolish_delete_bd_row(conn: asyncpg.Connection, bid=None,
                                  near_xyz=None, keep_id=0):
    try:
        bc = await _table_columns(conn, "a_Bd")
        if "id" not in bc:
            return 0
        if bid:
            bid = int(bid) & 0xFFFFFFFF
            if bid == int(keep_id) & 0xFFFFFFFF:
                return 0
            status = await conn.execute(
                'DELETE FROM "a_Bd" WHERE "id" = $1', bid)
            return bid if status != "DELETE 0" else 0
        if near_xyz and {"locX", "locY", "locZ"} <= bc:
            m = _DEMOLISH_BD_MATCH_M
            x, y, z = (float(v) for v in near_xyz)
            best = (0, None)
            for r in await conn.fetch(
                    'SELECT "id", "locX", "locY", "locZ" FROM "a_Bd" '
                    'WHERE "locX" BETWEEN $1 AND $2 '
                    'AND "locY" BETWEEN $3 AND $4 '
                    'AND "locZ" BETWEEN $5 AND $6',
                    x - m, x + m, y - m, y + m, z - m, z + m):
                _d = ((float(r[1]) - x) ** 2 + (float(r[2]) - y) ** 2
                      + (float(r[3]) - z) ** 2) ** 0.5
                if (int(r[0]) & 0xFFFFFFFF) == (int(keep_id) & 0xFFFFFFFF):
                    continue
                if _d <= m and (best[1] is None or _d < best[1]):
                    best = (int(r[0]) & 0xFFFFFFFF, _d)
            if best[0]:
                await conn.execute(
                    'DELETE FROM "a_Bd" WHERE "id" = $1', best[0])
            return best[0]
    except Exception as exc:
        logger.error(f"[demolish] a_Bd delete err: {exc!r}")
    return 0
