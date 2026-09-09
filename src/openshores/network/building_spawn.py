
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.bd_design import _persist_bd_design
from openshores.gameplay.build_materials import (
    MATERIAL_NAMES,
    _INITBD_MATERIAL_CID,
    material_tier,
    retarget_construction_material,
)
from openshores.gameplay.construction_process import construction_percent
from openshores.gameplay.dabd_frame import build_scene_dabd
from openshores.network.broadcast import _broadcast_to_peers
from openshores.network.building_broadcast import _building_broadcast_task
from openshores.network.building_keepalive import _building_keepalive
from openshores.network.construction_ticker import _construction_ticker
from openshores.protocol.deconstruction import (
    parse_deconstruction,
    serialize_deconstruction,
)

logger = get_logger(__name__)


async def spawn_city_building(building_auid: int, parent_world_auid: int, xyz,
                              report_bytes: bytes, name: str = "", empire: int = 0,
                              rot=(0.0, 0.0, 0.0), btype: int = 0x7b,
                              design_id: int = 0, construction_blob: bytes | None = None,
                              build_material: int = 0, design_material: int = 0,
                              under_construction: bool | None = None,
                              capitol_auid: int = 0, city_name: str = "",
                              founder_auid: int = 0, founder_name: str = "",
                              manproc=None, mproc_cfg=None, *,
                              conn, effective_build_material,
                              _live_avatars, _SPAWNED_BUILDINGS,
                              _BUILDING_KEEPALIVE_TASKS, _DYNAMIC_SCENE_AUIDS,
                              _ZONE_CACHE, _CITY_SIM, anchor_full):
    bauid = int(building_auid) & 0xFFFFFFFF
    parent = int(parent_world_auid) & 0xFFFFFFFF
    if not xyz or not report_bytes:
        logger.warning(f"[capitol-spawn] missing xyz/report for 0x{bauid:08x}; not spawned")
        return None
    cstate = None
    if construction_blob:
        try:
            cstate = parse_deconstruction(bytes(construction_blob))
            eff = effective_build_material(build_material or design_material,
                                           design_material)
            if eff and eff != _INITBD_MATERIAL_CID:
                n, sel = retarget_construction_material(cstate, eff)
                if n:
                    _sn = MATERIAL_NAMES.get(sel, "?")
                    _reason = ""
                    if build_material and material_tier(build_material) >= 0 \
                            and material_tier(build_material) < material_tier(design_material):
                        _reason = (f" (clamped up from 0x{build_material & 0xFFFF:x} "
                                   f"to recipe floor)")
                    logger.info(f"[capitol-build] build material 0x{sel:x} ({_sn}) "
                                f"{n} component(s) retargeted{_reason}")
        except Exception as exc:
            logger.error(f"[capitol-build] construction blob parse err: {exc!r}")
    try:
        pkt = await build_scene_dabd(bauid, parent, xyz, report_bytes, name=name,
                                     empire=empire, rot=rot, btype=btype,
                                     design_id=design_id,
                                     under_construction=(under_construction
                                                         if under_construction is not None
                                                         else (bool(cstate) or None)),
                                     construction_blob=(serialize_deconstruction(cstate)
                                                        if cstate else None),
                                     capitol_auid=capitol_auid, city_name=city_name,
                                     founder_auid=founder_auid,
                                     founder_name=founder_name,
                                     manufacturing=list(manproc or []),
                                     mproc_cfg=mproc_cfg,
                                     conn=conn,
                                     _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                                     _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                                     anchor_full=anchor_full)
    except Exception as exc:
        logger.error(f"[capitol-spawn] packet build err: {exc!r}")
        return None
    _SPAWNED_BUILDINGS[bauid] = {
        "parent": parent, "xyz": tuple(float(v) for v in xyz),
        "report": bytes(report_bytes), "name": name, "empire": int(empire),
        "rot": tuple(float(v) for v in rot), "btype": int(btype) & 0xFF,
        "design_id": int(design_id) & 0xFFFFFFFF,
        "cstate": cstate,
        "capitol_auid": int(capitol_auid) & 0xFFFFFFFF,
        "city_name": city_name or "",
        "founder_auid": int(founder_auid) & 0xFFFFFFFF,
        "founder_name": founder_name or "",
        "manproc": [int(v) for v in (manproc or [])],
        "mproc_cfg": dict(mproc_cfg or {}),
    }
    _DYNAMIC_SCENE_AUIDS.add(bauid)
    try:
        await _persist_bd_design(conn, bauid, bytes(report_bytes),
                                 int(design_id) & 0xFFFFFFFF)
    except Exception as exc:
        logger.error(f"[capitol-spawn] designRpt persist err: {exc!r}")
    try:
        sent = await _broadcast_to_peers(pkt, _live_avatars)
        _pct = construction_percent(cstate) if cstate else 100
        logger.info(f"[capitol-spawn] DaBd 0x{bauid:08x} '{name}' at "
                    f"{tuple(round(float(v), 1) for v in xyz)} parent=0x{parent:08x} "
                    f"report={len(report_bytes)}B construction={_pct}% -> {sent} peer(s)")
    except Exception as exc:
        logger.error(f"[capitol-spawn] broadcast err: {exc!r}")
    try:
        _building_broadcast_task(
            bauid,
            _construction_ticker(
                bauid, _live_avatars=_live_avatars,
                _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                conn=conn, _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                anchor_full=anchor_full)
            if cstate is not None
            else _building_keepalive(
                bauid, _live_avatars=_live_avatars,
                _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS, conn=conn,
                _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                anchor_full=anchor_full),
            _BUILDING_KEEPALIVE_TASKS=_BUILDING_KEEPALIVE_TASKS)
    except Exception as exc:
        logger.error(f"[capitol-spawn] broadcast task install err for "
                     f"0x{bauid:08x}: {exc!r}")
    return bauid
