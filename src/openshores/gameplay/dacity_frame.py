
from __future__ import annotations

import struct
import time as _t

from openshores.gameplay import city_model as _cm
from openshores.protocol.stream import QDS


async def build_scene_dacity(conn, city_auid: int, parent_auid: int, xyz,
                             buildings,
                             name: str = "", rot=(0.0, 0.0, 0.0),
                             now_ms: int | None = None, base_flag: int = 0x0B,
                             identity_auid: int = 0, aux: int = 0, roads=None,
                             is_capital: bool = False,
                             habitable_capital: bool = False) -> bytes:
    if now_ms is None:
        now_ms = int(_t.time() * 1000)
    blds = []
    for b in (buildings or []):
        b = dict(b)
        _bxyz = b.get("xyz")
        if _bxyz is not None:
            b["lat"], b["lon"] = _cm.xyz_to_latlon(_bxyz)
        elif "lat" not in b or "lon" not in b:
            b["lat"], b["lon"] = _cm.xyz_to_latlon(xyz)
        blds.append(b)
    s = QDS()
    s.write_u8(0x0B)
    s.write_u32(city_auid & 0xFFFFFFFF)
    s.buf += struct.pack(">q", now_ms)
    s.write_u8(base_flag & 0xFF)
    s.write_u32(parent_auid & 0xFFFFFFFF)
    s.buf += struct.pack(">q", now_ms)
    x, y, z = (float(v) for v in xyz)
    rx, ry, rz = (float(v) for v in rot)
    s.buf += struct.pack(">6f", x, y, z, rx, ry, rz)
    s.buf += await _cm.encode_dacity_body(conn, blds, name=(name or None),
                                          identity_auid=identity_auid, aux=aux,
                                          roads=roads,
                                          is_capital=is_capital,
                                          habitable_capital=habitable_capital,
                                          world_auid=parent_auid)
    return s.getvalue()
