
from __future__ import annotations

from openshores.protocol.atoms.item import (
    _extract_cid_from_auitem_body,
    _unpack_auitem_body,
)


SEA_CHEST_CAPACITY = 100

_MERGE_MAX = 0x7FFFFFFE

_CHEST1_GALAXIES = frozenset({5, 6, 0x11})

CHEST_COUNT = 2


def chest_index(galaxy: int) -> int:
    return 1 if (int(galaxy) & 0xFF) in _CHEST1_GALAXIES else 0


def total_quantity(entries) -> int:
    return sum(int(e[3]) for e in entries or ())


def can_add(entries, cid: int, count: int = 1) -> tuple:
    cid = int(cid) & 0xFFFF
    count = int(count)
    if cid == 0:
        return False, "commodity id 0 is not storable"
    if count <= 0:
        return False, "non-positive count"
    used = total_quantity(entries)
    if SEA_CHEST_CAPACITY - used < count:
        return False, ("chest holds %d/%d units; %d more would overflow it"
                       % (used, SEA_CHEST_CAPACITY, count))
    for e in entries or ():
        if (int(e[0]) & 0xFFFF) == cid:
            if int(e[3]) + count > _MERGE_MAX:
                return False, "merging would overflow the i32 stack count"
            break
    return True, None


def pack(entries) -> bytes:
    items = list(entries or ())
    out = bytearray()
    out += len(items).to_bytes(4, "big", signed=True)
    for _cid, type_id, body, _count in items:
        out.append(int(type_id) & 0xFF)
        out += bytes(body)
    return bytes(out)


def unpack(blob: bytes, off: int = 0):
    blob = bytes(blob or b"")
    if off + 4 > len(blob):
        raise ValueError("AuItemHash: truncated at count")
    count = int.from_bytes(blob[off:off + 4], "big", signed=True)
    off += 4
    if count < 0:
        raise ValueError("AuItemHash: negative count %d" % count)
    entries = []
    for i in range(count):
        if off + 1 > len(blob):
            raise ValueError("AuItemHash: truncated at entry %d typeId" % i)
        type_id = blob[off]
        off += 1
        body, off = _unpack_auitem_body(type_id, blob, off)
        entries.append(
            (_extract_cid_from_auitem_body(body) & 0xFFFF,
             type_id, body, 1))
    return entries, off


def pack_column(chests) -> bytes:
    chests = list(chests or ())
    while len(chests) < CHEST_COUNT:
        chests.append([])
    return b"".join(pack(c) for c in chests[:CHEST_COUNT])


def unpack_column(blob: bytes):
    blob = bytes(blob or b"")
    if not blob:
        return [[] for _ in range(CHEST_COUNT)]
    out = []
    off = 0
    for _ in range(CHEST_COUNT):
        entries, off = unpack(blob, off)
        out.append(entries)
    return out
