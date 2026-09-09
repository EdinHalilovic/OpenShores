
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.gameplay.dacity_frame import build_scene_dacity
from openshores.network.broadcast import _broadcast_to_peers
from openshores.network.city_keepalive import _city_keepalive
from openshores.network.town_square_design import serve_to_all_peers

logger = get_logger(__name__)


async def spawn_city_atom(city_auid: int, parent_world_auid: int, xyz, buildings,
                          name: str = "", rot=(0.0, 0.0, 0.0), roads=None,
                          empire: int = 0, is_capital: bool = False,
                          habitable_capital: bool = False, *,
                          conn,
                          _live_avatars: dict, _SPAWNED_CITIES: dict,
                          _DYNAMIC_SCENE_AUIDS: set,
                          _CITY_KEEPALIVE_TASKS: dict):
    cauid = int(city_auid) & 0xFFFFFFFF
    parent = int(parent_world_auid) & 0xFFFFFFFF
    if not xyz:
        logger.warning("City 0x%08x has no position; DaCity not spawned.", cauid)
        return None
    try:
        pkt = await build_scene_dacity(conn, cauid, parent, xyz, buildings,
                                       name=name, rot=rot,
                                       roads=roads, identity_auid=empire,
                                       is_capital=is_capital,
                                       habitable_capital=habitable_capital)
    except Exception as exc:
        logger.error("DaCity 0x%08x packet build failed: %r. Not spawned.",
                     cauid, exc)
        return None
    _SPAWNED_CITIES[cauid] = {
        "parent": parent, "xyz": tuple(float(v) for v in xyz),
        "buildings": [dict(b) for b in (buildings or [])],
        "roads": (None if roads is None else [dict(r) for r in roads]),
        "name": name, "rot": tuple(float(v) for v in rot),
        "empire": int(empire) & 0xFFFFFFFF,
        "is_capital": bool(is_capital),
        "habitable_capital": bool(habitable_capital),
    }
    _DYNAMIC_SCENE_AUIDS.add(cauid)
    if any(int(b.get("design_id", 0) or b.get("word", 0) or 0) == 1 for b in (buildings or [])):
        try:
            _np = await serve_to_all_peers(live_avatars=_live_avatars)
            if _np:
                logger.debug("Town-square design pushed to %d peer(s) before "
                             "atom 0x%08x.", _np, cauid)
                await asyncio.sleep(0.25)
        except Exception as _tse:
            logger.warning("Town-square push before DaCity 0x%08x failed: %r",
                           cauid, _tse)
    try:
        sent = await _broadcast_to_peers(
            pkt, _live_avatars, parent_auid=parent,
            label=f"DaCity 0x{cauid:08x} spawn")
        logger.debug("DaCity 0x%08x '%s' at %s parent=0x%08x buildings=%d "
                     "(%dB) -> %d peer(s).", cauid, name,
                     tuple(round(float(v), 1) for v in xyz), parent,
                     len(buildings or []), len(pkt), sent)
    except Exception as exc:
        logger.warning("DaCity 0x%08x spawn broadcast failed: %r", cauid, exc)
    _old = _CITY_KEEPALIVE_TASKS.get(cauid)
    if _old is None or _old.done():
        _CITY_KEEPALIVE_TASKS[cauid] = asyncio.create_task(
            _city_keepalive(cauid, conn=conn, _live_avatars=_live_avatars,
                            _SPAWNED_CITIES=_SPAWNED_CITIES))
    return cauid
