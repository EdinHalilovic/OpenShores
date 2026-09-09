
from __future__ import annotations

import struct
import zlib

__all__ = ["qcompress", "quncompress", "looks_qcompressed"]


def qcompress(data: bytes, level: int = -1) -> bytes:
    if not data:
        return b"\x00\x00\x00\x00"
    return struct.pack(">I", len(data)) + zlib.compress(data, level)


def quncompress(blob: bytes) -> bytes:
    if len(blob) < 4:
        return b""
    try:
        out = zlib.decompress(blob[4:])
    except zlib.error:
        return b""
    (expect,) = struct.unpack_from(">I", blob, 0)
    return out if len(out) == expect else b""


def looks_qcompressed(blob: bytes) -> bool:
    return bool(blob) and bool(quncompress(blob))
