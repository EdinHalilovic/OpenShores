
from __future__ import annotations

import struct


def _build_sector_atom_rename_pkt(sector_auid: int, new_name: str,
                                    time_ms: int = None) -> bytes:
    import time as _t
    _wall_ms = int(time_ms) if time_ms is not None else int(_t.time() * 1000)
    _name_raw = (new_name or "").encode("utf-16-be")
    return (
        bytes([0x14])
        + struct.pack(">I", int(sector_auid) & 0xFFFFFFFF)
        + struct.pack(">q", _wall_ms)
        + bytes([0x00])
        + struct.pack(">I", len(_name_raw))
        + _name_raw
    )


def _build_system_atom_rename_pkt(system_auid: int, new_name: str,
                                    time_ms: int = None) -> bytes:
    import time as _t
    _wall_ms = int(time_ms) if time_ms is not None else int(_t.time() * 1000)
    _name_raw = (new_name or "").encode("utf-16-be")
    return (
        bytes([0x15])
        + struct.pack(">I", int(system_auid) & 0xFFFFFFFF)
        + struct.pack(">q", _wall_ms)
        + bytes([0x00])
        + struct.pack(">I", len(_name_raw))
        + _name_raw
        + bytes([0x00])
        + struct.pack(">i", 0)
        + struct.pack(">i", 0)
        + bytes([0x00])
        + struct.pack(">i", 0)
    )


def _build_world_atom_rename_pkt(world_auid: int, new_name: str,
                                   time_ms: int = None) -> bytes:
    import time as _t
    _wall_ms = int(time_ms) if time_ms is not None else int(_t.time() * 1000)
    _name_raw = (new_name or "").encode("utf-16-be")
    return (
        bytes([0x1F])
        + struct.pack(">I", int(world_auid) & 0xFFFFFFFF)
        + struct.pack(">q", _wall_ms)
        + bytes([0x00])
        + bytes([0x00])
        + struct.pack(">I", len(_name_raw))
        + _name_raw
        + bytes([0x00])
    )
