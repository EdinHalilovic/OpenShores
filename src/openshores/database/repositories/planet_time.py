
from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger

logger = get_logger(__name__)


async def _stable_planet_time_ms(conn: asyncpg.Connection, planet_auid: int, *,
                                 now_ms: int, planet_time_memo: dict,
                                 planet_time_pending: list) -> int:
    key = int(planet_auid)
    if key in planet_time_memo:
        return planet_time_memo[key]
    try:
        row = await conn.fetchrow(
            'SELECT "timeCreate" FROM "a_WorldGlobe" WHERE "id" = $1',
            key)
        if row and row[0]:
            planet_time_memo[key] = int(row[0])
            return int(row[0])
        planet_time_pending.append(key)
        planet_time_memo[key] = now_ms
        return now_ms
    except Exception as _exc:
        logger.warning(f"[planet-time] non-fatal: {_exc!r}")
        return now_ms


async def _flush_planet_times(conn: asyncpg.Connection, *, now_ms: int,
                              planet_time_pending: list) -> None:
    try:
        if planet_time_pending:
            await conn.executemany(
                'UPDATE "a_WorldGlobe" SET "timeCreate" = $1, '
                '"timeModified" = $2 WHERE "id" = $3',
                [(now_ms, now_ms, gid)
                 for gid in planet_time_pending])
            logger.info(f"[planet-time] pinned {len(planet_time_pending)}"
                        f" globe time(s) in one commit")
            planet_time_pending.clear()
    except Exception as _exc:
        logger.warning(f"[planet-time] flush non-fatal: {_exc!r}")
