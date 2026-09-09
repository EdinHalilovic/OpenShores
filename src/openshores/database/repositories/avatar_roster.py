
from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger

logger = get_logger(__name__)


async def _persons_that_exist(conn: asyncpg.Connection, auids) -> set:
    want = [int(a) & 0xFFFFFFFF for a in auids]
    if not want:
        return set()
    try:
        q = ",".join(f"${i}" for i in range(1, len(want) + 1))
        return {int(r[0]) for r in await conn.fetch(
            f'SELECT "id" FROM "a_Person" WHERE "id" IN ({q})', *want)}
    except Exception as exc:
        logger.warning(f"[picker] a_Person existence check failed: {exc!r}")
        return set(want)


async def _selfie_stored_len(conn: asyncpg.Connection, actor_auid: int):
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'a_Person'""")}
    if "selfie" not in cols:
        return None
    row = await conn.fetchrow(
        'SELECT length("selfie") FROM "a_Person" WHERE "id" = $1',
        int(actor_auid) & 0xFFFFFFFF)
    return None if not row else row[0]
