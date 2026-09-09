
from __future__ import annotations

import asyncpg

from openshores.protocol.deconstruction import serialize_deconstruction


async def _persist_bd_design(conn: asyncpg.Connection, bauid: int,
                             report_bytes: bytes, design_id: int):
    if not report_bytes:
        return
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'a_Bd'""")}
    sets, vals = [], []
    if "designRpt" in cols:
        sets.append(f'"designRpt" = ${len(vals) + 1}'); vals.append(bytes(report_bytes))
    if "designId" in cols and design_id:
        sets.append(f'"designId" = ${len(vals) + 1}'); vals.append(int(design_id) & 0xFFFFFFFF)
    if not sets:
        return
    u = int(bauid) & 0xFFFFFFFF
    sgn = u if u < 0x80000000 else u - 0x100000000
    vals += [u, sgn]
    await conn.execute(
        f'UPDATE "a_Bd" SET {",".join(sets)} '
        f'WHERE "id" IN (${len(vals) - 1}, ${len(vals)})', *vals)


_BD_CSTATE_COL = "cstateBlob"


async def _persist_building_cstate(conn: asyncpg.Connection, bauid: int,
                                   cstate) -> None:
    blob = serialize_deconstruction(cstate) if cstate else None
    u = int(bauid) & 0xFFFFFFFF
    sgn = u if u < 0x80000000 else u - 0x100000000
    await conn.execute(
        f'UPDATE "a_Bd" SET "{_BD_CSTATE_COL}" = $1 WHERE "id" IN ($2, $3)',
        blob, u, sgn)
