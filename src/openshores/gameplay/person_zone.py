
from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.spawn import globe_row
from openshores.database.repositories.world import _globe_star_and_seed
from openshores.gameplay.city_model import xyz_to_latlon as _llf
from openshores.gameplay.worldgen import world_chain as _wch
from openshores.gameplay.worldgen import zone_resources as _zr

logger = get_logger(__name__)

_PERSON_ZONE_CACHE: dict = {}
_WORLD_GP_CACHE: dict = {}


async def _world_gp_and_seed(conn: asyncpg.Connection, world_auid: int):
    world = int(world_auid) & 0xFFFFFFFF
    if world in _WORLD_GP_CACHE:
        return _WORLD_GP_CACHE[world]
    gp = seed = None
    try:
        globe = await globe_row(conn, world)
        star = parent = None
        if globe is not None and globe["idp"]:
            star, seed, parent = await _globe_star_and_seed(conn, globe)
        if globe is not None and seed:
            gp = _wch.globe_properties(
                dict(globe),
                dict(star) if star is not None else None,
                is_satellite=(parent is not None),
                breathable=False)
    except Exception as exc:
        logger.warning(f"[person-zone] globe props failed 0x{world:08x}: {exc!r}")
        gp = seed = None
    _WORLD_GP_CACHE[world] = (gp, seed)
    return gp, seed


async def _person_zone(conn: asyncpg.Connection, actor_auid: int,
                       world_auid: int = None, *,
                       _tock_state: dict, _live_avatars: dict):
    actor = int(actor_auid) & 0xFFFFFFFF
    ent = (_tock_state.get(actor) or {})
    live = (_live_avatars.get(actor) or {})
    if world_auid is None:
        for key in ("parent", "parent_auid", "parent_world", "AP", "world", "world_auid"):
            val = ent.get(key) or live.get(key)
            if val:
                try:
                    world_auid = (int.from_bytes(bytes(val), "big")
                                  if isinstance(val, (bytes, bytearray))
                                  else int(val))
                except (TypeError, ValueError):
                    continue
                break
    if not world_auid:
        return None
    world = int(world_auid) & 0xFFFFFFFF
    xyz = ent.get("xyz") or live.get("xyz")
    if not xyz:
        return None
    gp, seed = await _world_gp_and_seed(conn, world)
    if gp is None or not seed:
        return None
    try:
        _lat, lon = _llf(tuple(float(v) for v in xyz))
        n = _zr.resource_zones(gp.size_class)
        zone_idx = _zr.resource_zone(lon, n)
        key = (world, zone_idx)
        if key in _PERSON_ZONE_CACHE:
            return _PERSON_ZONE_CACHE[key]
        zone = _zr.query_natural_resources(gp, zone_idx, int(seed))
        _PERSON_ZONE_CACHE[key] = zone
        return zone
    except Exception as exc:
        logger.warning(f"[person-zone] build failed actor=0x{actor:08x} "
                       f"world=0x{world:08x}: {exc!r}")
        return None
