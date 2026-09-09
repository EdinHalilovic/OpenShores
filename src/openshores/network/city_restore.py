
from __future__ import annotations

from typing import Any, Callable

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.city_restore import persisted_city_rows
from openshores.gameplay.city_snapshot import _split_developments
from openshores.network.city_atom import spawn_city_atom

logger = get_logger(__name__)

async def _restore_persisted_cities(*, conn: asyncpg.Connection,
                                    ensure_road_construction_ticker: Callable[[], Any],
                                    _live_avatars: dict, _SPAWNED_CITIES: dict,
                                    _DYNAMIC_SCENE_AUIDS: set,
                                    _CITY_KEEPALIVE_TASKS: dict):
    rows = []
    try:
        rows = await persisted_city_rows(conn)
    except Exception as exc:
        logger.error("City restore read failed: %r. No persisted cities restored.",
                     exc)
        return
    n = 0
    _uc_roadlike = 0
    for (cid, idp, x, y, z, name, dev, allegiance) in rows:
        try:
            blds, _roads, _area_ops = _split_developments(dev)
            _alldev = blds + _roads + _area_ops
            _uc_roadlike += sum(
                1 for d in _alldev
                if d.get("kind") in ("road", "area_op")
                and d.get("under_construction") and d.get("cstate"))
            if not blds and not _roads:
                continue
            await spawn_city_atom(int(cid) & 0xFFFFFFFF, int(idp or 0) & 0xFFFFFFFF,
                                  (x or 0.0, y or 0.0, z or 0.0), blds,
                                  conn=conn,
                                  name=name or "", roads=(_roads or None),
                                  empire=int(allegiance or 0) & 0xFFFFFFFF,
                                  is_capital=True, habitable_capital=True,
                                  _live_avatars=_live_avatars,
                                  _SPAWNED_CITIES=_SPAWNED_CITIES,
                                  _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                                  _CITY_KEEPALIVE_TASKS=_CITY_KEEPALIVE_TASKS)
            n += 1
        except Exception as exc:
            logger.error("City 0x%08x not restored: %r", int(cid) & 0xFFFFFFFF, exc)
    if n:
        logger.info("Restored %d persisted %s from a_City.", n,
                    "city" if n == 1 else "cities")
    if _uc_roadlike:
        try:
            ensure_road_construction_ticker()
            logger.info('%d under-construction road/area job(s) restored.', _uc_roadlike)
        except Exception as exc:
            logger.error('Road construction ticker restart failed: %r.', exc)
