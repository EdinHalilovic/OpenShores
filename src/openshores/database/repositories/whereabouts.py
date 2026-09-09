
from __future__ import annotations

import asyncpg


async def globe_name_for_person(conn: asyncpg.Connection,
                                person_auid: int) -> str | None:
    return await conn.fetchval(
        'SELECT "g"."name" FROM "a_Person" "p" '
        'JOIN "a_WorldGlobe" "g" ON "g"."id" = "p"."idp" '
        'WHERE "p"."id" = $1', int(person_auid))
