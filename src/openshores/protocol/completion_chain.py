
from __future__ import annotations

from openshores.protocol.stream import QDS


def build_scene_empire_data_complete() -> bytes:
    return bytes([0x2E])


def build_scene_scene_logged_in(scene_name: str = "",
                                 port: int = 0,
                                 flag: int = 0) -> bytes:
    s = QDS()
    s.write_u8(0x29)
    s.write_qstring(scene_name)
    s.write_u16(port & 0xFFFF)
    s.write_u8(flag & 0xFF)
    return s.getvalue()
