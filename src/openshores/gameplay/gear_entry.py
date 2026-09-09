
from __future__ import annotations

from openshores.gameplay import gear_wear as _gw
from openshores.protocol.atoms.item import _extract_cid_from_auitem_body


def _ground_item_quality(entry) -> int:
    try:
        return int(_gw.quality(bytes(entry["body"]))) & 0xFF
    except Exception:
        return 0


def _gear_quality_of(entry) -> int:
    try:
        return int(_gw.quality(bytes(entry[3]))) & 0xFF
    except Exception:
        return 0


def _gear_cid_of(entry):
    try:
        return _extract_cid_from_auitem_body(bytes(entry[3])) & 0xFFFF
    except Exception:
        return -1


def _augear_apply_move(state: list, src_slot: int, src_sub: int,
                        dst_slot: int) -> bool:
    for i, entry in enumerate(state):
        st, sub, typeId, body = entry
        if int(st) == int(src_slot) and int(sub) == int(src_sub):
            state[i] = [int(dst_slot) & 0x0F, int(sub) & 0x0F,
                         int(typeId) & 0xFF, bytes(body)]
            return True
    return False


def _augear_pop(state: list, src_slot: int, src_sub: int):
    for i, entry in enumerate(state):
        st, sub, typeId, body = entry
        if int(st) == int(src_slot) and int(sub) == int(src_sub):
            return state.pop(i)
    return None
