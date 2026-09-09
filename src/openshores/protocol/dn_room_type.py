
from __future__ import annotations

from openshores.protocol.stream import QDS


def build_scene_dn_room_type_0x30(
        type_id: int,
        sc_header: str,
        sc_subtitle: str,
        bd_header: str,
        bd_subtitle: str) -> bytes:
    s = QDS()
    s.write_u8(0x30)
    s.write_i32(int(type_id) & 0xFFFFFFFF)
    s.write_qstring(sc_header)
    s.write_qstring(sc_subtitle)
    s.write_qstring(bd_header)
    s.write_qstring(bd_subtitle)
    return s.getvalue()
