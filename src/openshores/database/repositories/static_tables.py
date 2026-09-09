
from __future__ import annotations

import time as _t

import asyncpg


async def already_sent(conn: asyncpg.Connection, key: str) -> bool:
    return await conn.fetchval(
        'SELECT 1 FROM "z_StaticTablesSent" WHERE "client" = $1',
        str(key)) is not None


async def mark_sent(conn: asyncpg.Connection, key: str) -> None:
    await conn.execute(
        'INSERT INTO "z_StaticTablesSent" ("client", "sent_at") '
        'VALUES ($1, $2) '
        'ON CONFLICT ("client") DO UPDATE SET "sent_at" = EXCLUDED."sent_at"',
        str(key), int(_t.time()))
