
from __future__ import annotations

from openshores.protocol.stream import QDS


def _build_dn_detail_type_frame(type_id, sc_header, sc_subtitle,
                                bd_header, bd_subtitle, tail) -> bytes:
    s = QDS()
    s.write_u8(0x2F)
    s.write_u8(int(type_id) & 0xFF)
    for q in (sc_header, sc_subtitle, bd_header, bd_subtitle):
        s.write_qstring(q if q else None)
    return s.getvalue() + bytes(tail)


def build_scene_dn_detail_type_0x2f(row) -> bytes:
    return _build_dn_detail_type_frame(
        row.type_id, row.sc_header, row.sc_subtitle,
        row.bd_header, row.bd_subtitle, row.tail)
