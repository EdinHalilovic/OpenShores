
from __future__ import annotations

import struct


def _build_daitem_keepalive_packet(item_auid_int: int,
                                    item_typeId: int,
                                    item_body: bytes) -> bytes:
    import time as _t
    now_ms = int(_t.time() * 1000)
    return (
        bytes([0x11])
        + struct.pack(">I", item_auid_int & 0xFFFFFFFF)
        + struct.pack(">q", now_ms)
        + bytes([0x00])
        + bytes([0x01])
        + bytes([int(item_typeId) & 0xFF])
        + bytes(item_body)
    )


def _build_daitem_drop_packet(item_auid_int: int,
                               parent_auid: bytes,
                               xyz: tuple,
                               item_typeId: int,
                               item_body: bytes,
                               rotation: tuple = (0.0, 0.0, 0.0),
                               time_created_ms: int | None = None) -> bytes:
    import time as _t
    now_ms = int(_t.time() * 1000)
    if len(parent_auid) != 4:
        raise ValueError("parent_auid must be 4 bytes")
    px, py, pz = float(xyz[0]), float(xyz[1]), float(xyz[2])
    rx, ry, rz = (float(rotation[0]), float(rotation[1]),
                  float(rotation[2]))
    tc_ms = int(time_created_ms) if time_created_ms is not None else now_ms
    return (
        bytes([0x11])
        + struct.pack(">I", item_auid_int & 0xFFFFFFFF)
        + struct.pack(">q", now_ms)
        + bytes([0x0B])
        + parent_auid
        + struct.pack(">q", tc_ms)
        + struct.pack(">ffffff", px, py, pz, rx, ry, rz)
        + bytes([0x01])
        + bytes([int(item_typeId) & 0xFF])
        + bytes(item_body)
    )
