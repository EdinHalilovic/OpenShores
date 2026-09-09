
from __future__ import annotations

import struct


def _qcompress(data: bytes, level: int = -1) -> bytes:
    import zlib
    if not data:
        return b"\x00\x00\x00\x00"
    if level < 0:
        level = 6
    return struct.pack(">I", len(data)) + zlib.compress(data, level)
