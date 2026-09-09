
from __future__ import annotations

import asyncio

from openshores.network.building_broadcast import _construction_rebroadcast


async def _construction_ticker(bauid: int, *, _live_avatars,
                               _SPAWNED_BUILDINGS, conn, _ZONE_CACHE,
                               _CITY_SIM, anchor_full):
    interval = 5.0
    while True:
        await asyncio.sleep(interval)
        info = _SPAWNED_BUILDINGS.get(bauid)
        if not info:
            return
        st = info.get("cstate")
        if st is None:
            return
        await _construction_rebroadcast(
            bauid, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
            _live_avatars=_live_avatars, conn=conn, _ZONE_CACHE=_ZONE_CACHE,
            _CITY_SIM=_CITY_SIM, anchor_full=anchor_full)
