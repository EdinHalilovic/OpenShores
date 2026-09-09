
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.gameplay.dacity_frame import build_scene_dacity
from openshores.network.broadcast import _broadcast_to_peers
from openshores.network.town_square_design import serve_to_all_peers

logger = get_logger(__name__)


async def _city_keepalive(cauid: int, *, conn, _live_avatars,
                          _SPAWNED_CITIES):
    interval = 30.0
    while True:
        await asyncio.sleep(interval)
        info = _SPAWNED_CITIES.get(cauid)
        if not info:
            return
        if any(int(b.get("design_id", 0) or b.get("word", 0) or 0) == 1 for b in info.get("buildings", [])):
            try:
                await serve_to_all_peers(live_avatars=_live_avatars)
            except Exception as _tse:
                logger.warning("Town-square keepalive push failed: %r", _tse)
        try:
            pkt = await build_scene_dacity(conn, cauid, info["parent"],
                                           info["xyz"],
                                           info.get("buildings", []),
                                           name=info.get("name", ""),
                                           rot=info.get("rot", (0.0, 0.0, 0.0)),
                                           roads=info.get("roads"),
                                           identity_auid=info.get("empire", 0),
                                           is_capital=info.get("is_capital", False),
                                           habitable_capital=info.get(
                                               "habitable_capital", False))
            await _broadcast_to_peers(
                pkt, _live_avatars, parent_auid=info.get("parent"),
                label=f"DaCity 0x{cauid:08x} keepalive")
        except Exception as exc:
            logger.debug("Keepalive for city 0x%08x stopped: %s", cauid, exc)
            return
