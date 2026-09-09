
from __future__ import annotations

from openshores.protocol.stream import QDS


def _write_qdatetime_null(s: QDS) -> None:
    s.write_u32(0)
    s.write_u32(0xFFFFFFFF)
    s.write_u8(0)


def _write_qdatetime_now(s: QDS, ms_offset: int = 0) -> None:
    import time as _t
    ms = int(_t.time() * 1000) + int(ms_offset)
    jd = (ms // 86400000) + 2440588
    mds = ms % 86400000
    s.write_u32(jd & 0xFFFFFFFF)
    s.write_u32(mds & 0xFFFFFFFF)
    s.write_u8(1)
