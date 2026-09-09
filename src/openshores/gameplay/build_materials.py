
from __future__ import annotations


MATERIAL_TIER_ORDER = [0x56, 0x30, 0x4c, 0x33, 0x92, 0x91, 0x262]
MATERIAL_NAMES = {0x56: "rough logs", 0x30: "milled lumber", 0x4c: "stone",
                  0x33: "metal", 0x92: "magmium", 0x91: "vulcium",
                  0x262: "adamantine"}

_INITBD_MATERIAL_CID = 0x30


def material_tier(cid: int) -> int:
    try:
        return MATERIAL_TIER_ORDER.index(int(cid) & 0xFFFF)
    except ValueError:
        return -1


def effective_build_material(selected: int, design_material: int) -> int:
    sel = int(selected) & 0xFFFF
    dmat = int(design_material) & 0xFFFF
    dt = material_tier(dmat)
    if dt < 0:
        return sel or dmat or _INITBD_MATERIAL_CID
    st = material_tier(sel)
    if st < dt:
        return dmat
    return sel


def retarget_construction_material(cstate: dict, selected_material_cid: int):
    sel = int(selected_material_cid) & 0xFFFF
    if not sel or sel == _INITBD_MATERIAL_CID:
        return 0, _INITBD_MATERIAL_CID
    n = 0
    for comp in cstate.get("components", []):
        if (comp[0] & 0xFFFF) == _INITBD_MATERIAL_CID:
            comp[0] = sel
            n += 1
    return n, sel
