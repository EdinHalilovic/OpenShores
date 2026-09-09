from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.world_loader import (
    apply_sql_world_to_bundle,
)

logger = get_logger(__name__)


async def _retarget_bundle_to_avatar(conn: asyncpg.Connection, bundle,
                                     person_auid: int, *,
                                     SiblingGlobe, gen_planet, gen_moon,
                                     HAB_RANDOM, wch, wc, tr) -> bool:
    person_auid = int(person_auid) & 0xFFFFFFFF
    if not person_auid:
        return False
    row = await conn.fetchrow(
        'SELECT "idp", "name" FROM "a_Person" WHERE "id" = $1', person_auid)
    if not row or not row[0]:
        return False
    want = int(row[0])
    if want == int(getattr(bundle, "whereabouts_auid", 0) or 0):
        return False
    was = bundle.planet_name
    bundle.whereabouts_auid = want
    if not await apply_sql_world_to_bundle(
            conn, bundle, SiblingGlobe=SiblingGlobe, gen_planet=gen_planet,
            gen_moon=gen_moon, HAB_RANDOM=HAB_RANDOM, wch=wch, wc=wc, tr=tr):
        logger.warning("Bundle retarget to avatar %r failed: globe 0x%08x has "
                       "no walkable parent chain; keeping %r.",
                       row[1], want, was)
        return False
    logger.info("Bundle retargeted to %r: %r -> %r in %r / %r, %d siblings.",
                row[1], was, bundle.planet_name, bundle.system_name,
                bundle.sector_name, len(bundle.sibling_globes))
    return True
