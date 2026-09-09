
from __future__ import annotations

import struct
import time as _t

from openshores.core.logging import get_logger
from openshores.gameplay.city.zone import _city_zone
from openshores.gameplay.construction_process import build_deconstruction_process
from openshores.gameplay.construction_site import _city_auid_for_building
from openshores.gameplay.natives.village import gravity_align_euler
from openshores.world.sim_time import _current_sim_time_ms
from openshores.gameplay import manufacturing_wire as _mw
from openshores.protocol.atoms.manufacturing import encode_process_array
from openshores.protocol.stream import QDS

logger = get_logger(__name__)


async def build_scene_dabd(building_auid: int, parent_auid: int, xyz,
                           report_bytes: bytes,
                           name: str = "", empire: int = 0,
                           rot=(0.0, 0.0, 0.0),
                           btype: int = 0x00, now_ms: int | None = None,
                           design_id: int = 0,
                           under_construction: bool | None = None,
                           construction_blob: bytes | None = None,
                           capitol_auid: int = 0, city_name: str = "",
                           founder_auid: int = 0, founder_name: str = "",
                           manufacturing=None, mproc_cfg=None,
                           *, conn, _SPAWNED_BUILDINGS,
                           _ZONE_CACHE, _CITY_SIM,
                           anchor_full) -> bytes:
    if now_ms is None:
        now_ms = int(_t.time() * 1000)
    s = QDS()
    s.write_u8(0x4C)
    s.write_u32(building_auid & 0xFFFFFFFF)
    s.buf += struct.pack(">q", now_ms)
    s.write_u8(0x0B)
    s.write_u32(parent_auid & 0xFFFFFFFF)
    s.buf += struct.pack(">q", now_ms)
    x, y, z = (float(v) for v in xyz)
    rx, ry, rz = (float(v) for v in rot)
    if rx == 0.0 and ry == 0.0:
        rx, ry, rz = gravity_align_euler((x, y, z), heading_rad=rz)
    s.buf += struct.pack(">6f", x, y, z, rx, ry, rz)
    s.write_u8(0x01)
    s.write_qstring(name or "")
    s.write_u32(empire & 0xFFFFFFFF)
    s.write_u8(0x00)
    if under_construction is None:
        under_construction = True
    flags_w2 = 0x0004 if under_construction else 0x0000
    mfg_blob = None
    if manufacturing is not None:
        try:
            procs = list(manufacturing)
            if procs and not isinstance(procs[0], _mw.ManufacturingProcessState):
                _zone = None
                try:
                    _cz = await _city_auid_for_building(
                        conn, (_SPAWNED_BUILDINGS or {}).get(building_auid) or {})
                    if _cz and conn is not None:
                        _zone = await _city_zone(conn, _cz,
                                                 _ZONE_CACHE=_ZONE_CACHE,
                                                 _CITY_SIM=_CITY_SIM)
                except Exception as _zexc:                  # noqa: BLE001
                    logger.warning("Zone lookup failed for 0x%08x: %r",
                                   building_auid & 0xFFFFFFFF, _zexc)
                _sim_now = _current_sim_time_ms(anchor_full=anchor_full)
                procs = _mw.processes_from_mpids(
                    procs, cfg=mproc_cfg, auid=building_auid, zone=_zone,
                    sim_now_ms=_sim_now)
            mfg_blob = encode_process_array(procs)
            flags_w2 |= 0x0008
        except Exception as exc:                            # noqa: BLE001
            logger.warning("Manufacturing encode failed for 0x%08x: %r",
                           building_auid & 0xFFFFFFFF, exc)
            mfg_blob = None
    has_city_identity = bool(capitol_auid) or bool(city_name)
    if has_city_identity:
        flags_w2 |= 0x0040
    s.write_u16(0x0080)
    s.write_u16(flags_w2)
    s.write_u8(btype & 0xFF)
    s.write_u8(0x01)
    s.buf += bytes(report_bytes)
    s.write_u32(founder_auid & 0xFFFFFFFF)
    s.write_qstring(founder_name or "")
    if under_construction:
        if construction_blob:
            s.buf += bytes(construction_blob)
        else:
            s.buf += build_deconstruction_process(btype, design_id=design_id)
    if mfg_blob is not None:
        s.buf += bytes(mfg_blob)
    if has_city_identity:
        s.write_u32(capitol_auid & 0xFFFFFFFF)
        s.write_qstring(city_name or "")
    return s.getvalue()
