
from __future__ import annotations

import struct

from openshores.gameplay.city_model import industry_to_cpid_safe


def build_deconstruction_process(industry_id: int, design_id: int = 0,
                                 components=None) -> bytes:
    b = b""
    cpid = int(industry_to_cpid_safe(int(industry_id), default_cpid=0)) & 0x7F
    b += struct.pack(">B", cpid | (0x80 if design_id else 0x00))
    b += struct.pack(">B", 0)
    b += struct.pack(">h", 0)
    comps = components or []
    b += struct.pack(">B", len(comps) & 0xFF)
    for cid, kind, req, applied in comps:
        b += (struct.pack(">h", cid & 0xFFFF) + struct.pack(">B", 0)
              + struct.pack(">B", kind & 0xFF) + struct.pack(">i", req)
              + struct.pack(">i", applied) + struct.pack(">B", 0))
    b += struct.pack(">B", 0)
    b += struct.pack(">h", 0)
    b += struct.pack(">B", 0)
    if design_id:
        b += struct.pack(">i", design_id & 0xFFFFFFFF)
    return b


def construction_is_complete(st: dict) -> bool:
    if int(st.get("labor", 0)) != 0:
        return False
    for cid, b2, eff, req, applied in st["components"]:
        if eff == 5:
            if req == 0:
                if applied == 0:
                    return False
            elif applied < req:
                return False
    return True


def construction_percent(st: dict) -> int:
    tot_req = 1
    tot_app = 0
    for cid, b2, eff, req, applied in st["components"]:
        if eff == 5 and req != 0:
            tot_app += applied
            tot_req += req
    return min(100, tot_app * 100 // tot_req)


def construction_step(st: dict, labor_units: int, material_frac: float) -> dict:
    st["labor"] = max(0, int(st.get("labor", 0)) - int(labor_units))
    for comp in st["components"]:
        cid, b2, eff, req, applied = comp
        if eff == 5 and req > 0 and applied < req:
            step = max(1, int(req * material_frac))
            comp[4] = min(req, applied + step)
    return st
