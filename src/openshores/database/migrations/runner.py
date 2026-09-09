
from __future__ import annotations

from pathlib import Path

import asyncpg

from openshores.core.logging import get_logger

logger = get_logger(__name__)


MIGRATIONS_DIR = Path(__file__).parent


async def init_db(conn: asyncpg.Connection) -> int:
    await apply_migrations(conn)
    n_tables = await conn.fetchval(
        """SELECT count(*) FROM "information_schema"."tables"
            WHERE "table_schema" = 'public'
              AND "table_type" = 'BASE TABLE'""")
    logger.info("Schema ready: %d tables.", n_tables)
    return n_tables


async def apply_migrations(conn: asyncpg.Connection) -> None:
    paths = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
    if not paths:
        raise RuntimeError(f"No migrations found in {MIGRATIONS_DIR}")
    for path in paths:
        await conn.execute(path.read_text(encoding="utf-8"))
        logger.info("Applied migration %s.", path.name)


