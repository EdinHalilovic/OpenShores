
from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.city_site import city_and_globe
from openshores.database.repositories.world import _globe_star_and_seed
from openshores.gameplay.city_model import xyz_to_latlon as _llf
from openshores.gameplay.worldgen import world_chain as _wch

logger = get_logger(__name__)


async def _city_zone(conn: asyncpg.Connection, cauid: int, *,
                     _ZONE_CACHE: dict,
                     _CITY_SIM: dict):
    if cauid in _ZONE_CACHE:
        return _ZONE_CACHE[cauid]
    zone = None
    try:
        city, globe = await city_and_globe(conn, cauid)
        star = None
        seed = None
        parent = None
        if globe is not None and globe["idp"]:
            star, seed, parent = await _globe_star_and_seed(conn, globe)
        if globe is not None and seed:
            _lat, lon = _llf((city["locX"], city["locY"], city["locZ"]))
            snap = (_CITY_SIM.get(cauid) or {}).get("sim_snapshot") or {}
            zone = _wch.city_zone(dict(globe),
                                  dict(star) if star is not None else None,
                                  int(seed), lon,
                                  is_satellite=(parent is not None),
                                  breathable=not bool(
                                      snap.get("enclosure_needed", False)))
    except Exception as exc:
        logger.warning("Resource zone for city 0x%08x could not be built: %r.",
                       int(cauid) & 0xFFFFFFFF, exc)
        zone = None
    if zone is None:
        logger.warning('City 0x%08x has NO RESOURCE ZONE: natural materials are unavailable, so most recipes cannot run.',
                       int(cauid) & 0xFFFFFFFF)
    _ZONE_CACHE[cauid] = zone
    return zone
