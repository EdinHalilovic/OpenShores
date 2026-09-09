
from __future__ import annotations

import asyncio

from openshores.gameplay.dabd_frame import build_scene_dabd
from openshores.core.logging import get_logger
from openshores.network.broadcast import _broadcast_to_peers
from openshores.protocol.deconstruction import serialize_deconstruction

logger = get_logger(__name__)


def _building_broadcast_stop(bauid: int, *, _BUILDING_KEEPALIVE_TASKS) -> None:
    t = _BUILDING_KEEPALIVE_TASKS.pop(int(bauid) & 0xFFFFFFFF, None)
    if t is not None and not t.done():
        t.cancel()


async def _construction_rebroadcast(bauid: int, *, _SPAWNED_BUILDINGS,
                                    _live_avatars, conn,
                                    _ZONE_CACHE, _CITY_SIM,
                                    anchor_full) -> None:
    info = _SPAWNED_BUILDINGS.get(bauid)
    if not info:
        return
    st = info.get("cstate")
    try:
        pkt = await build_scene_dabd(
            bauid, info["parent"], info["xyz"], info["report"],
            name=info.get("name", ""), empire=info.get("empire", 0),
            rot=info.get("rot", (0.0, 0.0, 0.0)),
            btype=info.get("btype", 0x7b), design_id=info.get("design_id", 0),
            under_construction=(st is not None),
            construction_blob=(serialize_deconstruction(st) if st else None),
            capitol_auid=info.get("capitol_auid", 0),
            city_name=info.get("city_name", ""),
            founder_auid=info.get("founder_auid", 0),
            founder_name=info.get("founder_name", ""),
            manufacturing=info.get("manproc") or [],
            mproc_cfg=info.get("mproc_cfg"),
            conn=conn, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
            _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
            anchor_full=anchor_full)
        await _broadcast_to_peers(pkt, _live_avatars)
    except Exception as exc:
        logger.warning('Construction site 0x%08x was not re-broadcast: %s.',
                       int(bauid) & 0xFFFFFFFF, exc)


def _building_broadcast_task(bauid: int, coro, *,
                             _BUILDING_KEEPALIVE_TASKS) -> None:
    bauid = int(bauid) & 0xFFFFFFFF
    try:
        cur = asyncio.current_task()
    except Exception:
        cur = None
    old = _BUILDING_KEEPALIVE_TASKS.get(bauid)
    if old is not None and old is not cur and not old.done():
        old.cancel()
    try:
        _BUILDING_KEEPALIVE_TASKS[bauid] = asyncio.create_task(coro)
    except Exception:
        coro.close()
