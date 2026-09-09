
from __future__ import annotations

from openshores.gameplay.gear_commodity import (
    _bits_wear_for_cid,
    _pack_volume_for_cid,
)
from openshores.gameplay.gear_entry import _gear_cid_of

SLOT_CAPS = {
    1: 2,
    2: 1,
    3: 1,
    4: 1,
    5: 1,
    6: 2,
    7: 4,
    8: 4,
    9: 4,
}
SLOT_NAMES = {
    0: 'Invalid', 1: 'Hand', 2: 'Head', 3: 'Face', 4: 'Neck',
    5: 'Body', 6: 'Wear', 7: 'Limb', 8: 'Digit', 9: 'Waist',
}
SLOT_UNIVERSAL = frozenset({1, 5, 9})


def _slot_count(augear, slottype):
    st = int(slottype) & 0x0F
    return sum(1 for e in augear if int(e[0]) == st)


def _next_sub_index(augear, slottype):
    st = int(slottype) & 0x0F
    used = {int(e[1]) & 0x0F for e in augear if int(e[0]) == st}
    cap = SLOT_CAPS.get(st, 0)
    for sub in range(cap):
        if sub not in used:
            return sub
    return None


_SLOT_FIT_MASKS = {
    2: 0x00000410,
    3: 0x00000202,
    4: 0x00080000,
    6: 0x000039ED,
    7: 0x3000C000,
    8: 0x00F00000,
}


WAIST_MAX_PACK_UNITS = 16


def _can_hold_item(slottype, typeId, body):
    st = int(slottype) & 0x0F
    if st not in SLOT_CAPS:
        return False, 'slottype out of range 1..9'
    if st == 9:
        _wcid = _gear_cid_of([0, 0, typeId, body]) if body else -1
        if _wcid < 0:
            return True, None
        vol = _pack_volume_for_cid(_wcid)
        if vol is None or vol < WAIST_MAX_PACK_UNITS:
            return True, None
        reason = ('cid %d is %d pack units; the Waist slot takes under %d'
                  % (_wcid, vol, WAIST_MAX_PACK_UNITS))
        return False, reason
    mask = _SLOT_FIT_MASKS.get(st)
    if mask is None:
        return True, None
    cid = _gear_cid_of([0, 0, typeId, body]) if body else -1
    if cid < 0:
        return True, None
    bw = _bits_wear_for_cid(cid)
    if bw is None:
        return True, None
    if bw & mask:
        return True, None
    reason = ('cid %d bitsWear 0x%08x does not fit slot %d (%s), mask 0x%08x'
              % (cid, bw, st, SLOT_NAMES.get(st, '?'), mask))
    return False, reason


def _add_gear_item(augear, typeId, body):
    for slottype in (5, 1, 9):
        cap = SLOT_CAPS.get(slottype, 0)
        if _slot_count(augear, slottype) < cap:
            sub = _next_sub_index(augear, slottype)
            if sub is None:
                continue
            augear.append([slottype, sub, int(typeId) & 0xFF, bytes(body)])
            return slottype, sub
    return None, None
