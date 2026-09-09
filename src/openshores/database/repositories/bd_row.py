from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.world import _table_columns

logger = get_logger(__name__)


async def _bd_row_by_auid(conn: asyncpg.Connection, bauid):
    try:
        cols = await _table_columns(conn, "a_Bd")
        if "id" not in cols:
            return None
        want = [c for c in ("id", "capitol", "cityName", "industry",
                            "name", "allegiance", "idp") if c in cols]
        u = int(bauid) & 0xFFFFFFFF
        sgn = u if u < 0x80000000 else u - 0x100000000
        projection = ",".join(f'"{c}"' for c in want)
        row = await conn.fetchrow(
            f'SELECT {projection} FROM "a_Bd" WHERE "id" IN ($1, $2)',
            u, sgn)
        return dict(zip(want, row)) if row else None
    except Exception as exc:
        logger.error(f"[bd-mfg] a_Bd row query err 0x{int(bauid) & 0xFFFFFFFF:08x}: "
                     f"{exc!r}")
        return None


async def _bd_rows_for_empire(conn: asyncpg.Connection, empire):
    out = []
    try:
        cols = await _table_columns(conn, "a_Bd")
        if "id" not in cols:
            return out
        want = [c for c in ("id", "capitol", "cityName", "industry",
                            "name", "allegiance", "idp") if c in cols]
        projection = ",".join(f'"{c}"' for c in want)
        for row in await conn.fetch(f'SELECT {projection} FROM "a_Bd"'):
            d = dict(zip(want, row))
            if "allegiance" in d and \
                    (int(d.get("allegiance") or 0) & 0xFFFFFFFF) != \
                    (int(empire) & 0xFFFFFFFF):
                continue
            out.append(d)
    except Exception as exc:
        logger.error(f"[bd-mfg] a_Bd empire query err: {exc!r}")
    return out
