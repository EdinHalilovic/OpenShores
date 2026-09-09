
from __future__ import annotations

from openshores.gameplay import gd_tables as _gd
from openshores.protocol.stream import QDS


def _build_dbindustry_row(row) -> bytes:
    s = QDS()
    for kind, key in _gd._INDUSTRY_ORDER:
        v = row.raw[key]
        if kind == 'u8':
            s.write_u8(int(v) & 0xFF)
        else:
            s.write_qstring(v if v else None)
    return s.getvalue()


def build_scene_db_industry_0x32(industry_id: int, row,
                                  id_prefix: bool = False) -> bytes:
    s = QDS()
    s.write_u8(0x32)
    if id_prefix:
        s.write_i32(int(industry_id) & 0xFFFFFFFF)
    return s.getvalue() + _build_dbindustry_row(row)
