
from __future__ import annotations

import struct as _st

from openshores.core.logging import get_logger
from openshores.database.repositories.city import planet_city_developments
from openshores.database.repositories.world import (
    read_world_geo,
    write_world_geo,
)
from openshores.gameplay import city_model as _cm
from openshores.gameplay.worldgen.planet_geo import _gen_geo_payload

logger = get_logger(__name__)


async def _get_or_init_planet_geo(conn, planet_auid: int, size: int = None,
                                  atm_density: int = None, water: int = None,
                                  terrain=None, orbit_zone: int = 2) -> bytes:
    try:
        row = await read_world_geo(conn, int(planet_auid))
        if row and row[0] and len(row[0]) >= 1:
            return bytes(row[0])
        if row and terrain is None and row[1] and len(row[1]) == 24:
            terrain = _st.unpack(">ffffff", row[1])
        if row and row[2]:
            orbit_zone = bytes(row[2])[0]
        payload = _gen_geo_payload(planet_auid, size, atm_density, water,
                                   terrain, orbit_zone)
        await write_world_geo(conn, int(planet_auid), payload)
        logger.info(f"[wg-geo] generated + persisted "
                    f"auid=0x{planet_auid:06x} ({len(payload)}B, "
                    f"{payload[0]} feature(s))")
        return payload
    except Exception as exc:
        logger.warning(f"[wg-geo] persistence error (using transient): {exc!r}")
        return _gen_geo_payload(planet_auid, size, atm_density, water,
                                terrain, orbit_zone)


async def _gather_planet_roads(conn, planet_auid: int) -> list:
    roads = []
    try:
        rows = await planet_city_developments(conn, int(planet_auid))
        for (dev,) in rows:
            for d in _cm.developments_from_blob(dev):
                if d.get("kind") == "road":
                    roads.append(d)
    except Exception as exc:
        logger.warning(f"[wg-geo] road gather err: {exc!r}")
    return roads
