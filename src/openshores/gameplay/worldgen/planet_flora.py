
from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories import world as _rows
from openshores.protocol.rng import AuDice

from . import world_chain, world_gen

logger = get_logger(__name__)


def _gen_flora_payload(planet_auid: int, zones: int, size: int = 0) -> bytes:

    _fdice = AuDice(seed=int(planet_auid) or 1)
    _size = int(size) if size else (3 if zones >= 3 else 2)
    return world_gen.encode_flora(
        [world_gen.deplanetflora_init(_size, _fdice) for _ in range(zones)])


async def _get_or_init_planet_flora(conn: asyncpg.Connection,
                                    planet_auid: int, zones: int,
                                    size: int = 0,
                                    table: str = "a_WorldGlobe") -> bytes:
    row = await _rows.read_world_flora(conn, table, int(planet_auid))
    expected = zones * 54 * 16 + 8
    if row and row[0] and len(row[0]) == expected:
        return bytes(row[0])
    if row and not size and row[1] is not None:
        size = world_chain.size_class_from_radius(row[1])
    payload = _gen_flora_payload(planet_auid, zones, size)
    await _rows.write_world_flora(conn, table, int(planet_auid), payload)
    logger.info("World 0x%06x had no stored flora; rolled and stored %d bytes.",
                planet_auid, len(payload))
    return payload
