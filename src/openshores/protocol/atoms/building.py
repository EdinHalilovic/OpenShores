
from __future__ import annotations

import struct
import zlib

from openshores.protocol.stream import QDS


TOWN_SQUARE_DESIGN_ID = 1

DETAIL_FLAGPOLE = 0x64
DETAIL_LIGHTPOLE = 0x8E


def _qds():
    return QDS()


def encode_grid_coord(col: int, row: int) -> int:
    return ((col & 0xFF) << 8) | (row & 0xFF)


def encode_dndetail(design_id: int, *, det_type: int = DETAIL_FLAGPOLE,
                    level: int = 0, pos=(0.0, 0.0, 0.0), detail_id: int = 1,
                    f28: int = 0, flag: int = 0) -> bytes:
    s = _qds()
    s.write_i32(design_id)
    s.write_i32(detail_id)
    s.write_i16(f28)
    s.write_u8(level & 0xFF)
    s.write_u8(det_type & 0xFF)
    s.buf += struct.pack(">ddd", float(pos[0]), float(pos[1]), float(pos[2]))
    s.write_u8(flag & 0xFF)
    return s.getvalue()


def encode_dnroom(design_id: int, *, verts, level: int = 0, room_type: int = 6,
                  field8: int = 0, room_idx: int = 1) -> bytes:
    if room_type == 0x18:
        raise ValueError("Special case")
    s = _qds()
    s.write_i32(design_id)
    s.write_i16(room_idx)
    s.write_u8(level & 0xFF)
    s.write_u8(room_type & 0xFF)
    s.write_u8(field8 & 0xFF)
    raw = b"".join(struct.pack("<H", encode_grid_coord(c, r)) for (c, r) in verts)
    payload = struct.pack(">I", len(raw)) + zlib.compress(raw)
    s.write_bytes(payload)
    return s.getvalue()


def encode_dnbuilding(design_id: int, *, name: str = "Town Square",
                      owner_id: int = 0, name2: str = "", flag1: int = 0,
                      flag2: int = 0, flag3: int = 1, empire_ids=None) -> bytes:
    s = _qds()
    s.write_i32(design_id)
    s.write_qstring(name)
    s.write_u32(owner_id & 0xFFFFFFFF)
    s.write_qstring(name2 or "")
    s.write_u8(flag1 & 0xFF)
    s.write_i16(flag2)
    s.write_u8(flag3 & 0xFF)
    ids = list(empire_ids or [])
    s.write_i32(len(ids))
    for eid in ids:
        s.write_i32(eid)
    return s.getvalue()


def build_town_square_design(design_id: int = TOWN_SQUARE_DESIGN_ID):
    detail = encode_dndetail(design_id, det_type=DETAIL_FLAGPOLE,
                             pos=(0.0, 0.0, 0.0), detail_id=1)
    verts = [(-8, -8), (8, -8), (8, 8), (-8, 8)]
    room = encode_dnroom(design_id, verts=verts, level=0, room_type=6, room_idx=1)
    header = encode_dnbuilding(design_id, name="Town Square")
    return detail, room, header
