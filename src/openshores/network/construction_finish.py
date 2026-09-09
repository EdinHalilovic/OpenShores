
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.construction_site import _persist_completed_building
from openshores.gameplay.dabd_frame import build_scene_dabd
from openshores.network.broadcast import _broadcast_to_peers
from openshores.network.building_broadcast import _building_broadcast_task
from openshores.network.building_keepalive import _building_keepalive

logger = get_logger(__name__)


async def _construction_finish(bauid: int, info: dict, *, _live_avatars,
                               _SPAWNED_BUILDINGS, _BUILDING_KEEPALIVE_TASKS,
                               conn, _ZONE_CACHE, _CITY_SIM,
                               anchor_full) -> None:
    if info.get("cstate") is None:
        return
    info["cstate"] = None
    pkt = await build_scene_dabd(
        bauid, info["parent"], info["xyz"], info["report"],
        name=info.get("name", ""), empire=info.get("empire", 0),
        rot=info.get("rot", (0.0, 0.0, 0.0)), btype=info.get("btype", 0x7b),
        design_id=info.get("design_id", 0), under_construction=False,
        capitol_auid=info.get("capitol_auid", 0),
        city_name=info.get("city_name", ""),
        founder_auid=info.get("founder_auid", 0),
        founder_name=info.get("founder_name", ""),
        manufacturing=info.get("manproc") or [],
        mproc_cfg=info.get("mproc_cfg"),
        conn=conn, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
        _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM, anchor_full=anchor_full)
    await _broadcast_to_peers(pkt, _live_avatars)
    logger.info("0x%08x %r COMPLETE (100%%)", bauid, info.get("name", ""))
    try:
        await _persist_completed_building(conn, bauid, info)
    except Exception:
        logger.exception("Persist err for building 0x%08x", bauid)
    _building_broadcast_task(
        bauid,
        _building_keepalive(bauid, _live_avatars=_live_avatars,
                            _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS, conn=conn,
                            _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                            anchor_full=anchor_full),
        _BUILDING_KEEPALIVE_TASKS=_BUILDING_KEEPALIVE_TASKS)
