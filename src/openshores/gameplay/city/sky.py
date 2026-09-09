
from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.city_site import city_and_globe
from openshores.database.repositories.city_world import (
    star_by_id,
    star_children,
    system_for_star,
)
from openshores.database.repositories.world import _globe_star_and_seed
from openshores.gameplay.worldgen import world_chain as _wch
from openshores.world.sim_time import _current_sim_time_ms

logger = get_logger(__name__)

_SKY_CACHE = {}


async def _city_sky(conn: asyncpg.Connection, cauid: int, *, _CITY_SIM: dict):
    if cauid in _SKY_CACHE:
        return _SKY_CACHE[cauid]
    result = None
    try:
        _city, globe = await city_and_globe(conn, cauid)
        star = None
        if globe is not None and globe["idp"]:
            star, _seed_unused, _parent_unused = await _globe_star_and_seed(
                conn, globe)
        if star is not None:
            prim = star
            sysrow = await system_for_star(conn, star["idp"])
            if sysrow is None:
                prim = await star_by_id(conn, star["idp"]) or star
                sysrow = await system_for_star(conn, prim["idp"])
            star_rows = [dict(prim)]
            star_rows += [dict(r) for r in await star_children(conn, prim["id"])]
            n_stars = len(star_rows)
            seed = sysrow["genSeed"] if sysrow else None
            snap = (_CITY_SIM.get(cauid) or {}).get("sim_snapshot") or {}
            chain = _wch.body_chain(
                dict(globe), None, seed,
                breathable=not bool(snap.get("enclosure_needed", False)),
                star_count=int(n_stars or 0))
            sub = _wch.spectral_subclass(dict(star))
            if chain is not None and sub is not None and seed:
                bodies, radius = chain
                result = (bodies, radius,
                          _wch.star_descriptors(star_rows, int(seed)))
            elif chain is not None:
                logger.warning(f"[city-prod] star data for city 0x{int(cauid) & 4294967295:08x} is not in client semantics (habZone={star['habZone']!r}).")
    except Exception as exc:
        logger.warning(f"[city-prod] sky lookup failed "
                       f"0x{int(cauid) & 0xFFFFFFFF:08x}: {exc!r}")
    if result is None:
        logger.warning(f'[city-prod] darkness gate OFF for city 0x{int(cauid) & 4294967295:08x} (no usable star/seed data).')
    _SKY_CACHE[cauid] = result
    return result


async def _make_is_dark(conn: asyncpg.Connection, cauid: int, *,
                        _CITY_SIM: dict, anchor_full: int):
    sky = await _city_sky(conn, cauid, _CITY_SIM=_CITY_SIM)
    if sky is None:
        return None
    bodies, radius, stars = sky

    def is_dark(b):
        return _wch.is_dark_at_multi(bodies, radius,
                                     float(_current_sim_time_ms(
                                         anchor_full=anchor_full)),
                                     float(getattr(b, "lat", 0.0) or 0.0),
                                     float(getattr(b, "lon", 0.0) or 0.0),
                                     stars)
    return is_dark
