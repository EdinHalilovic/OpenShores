
from __future__ import annotations


def _extract_png(buf: bytes) -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    i = buf.find(sig)
    if i < 0:
        return b""
    j = buf.find(b"IEND", i)
    if j < 0:
        return bytes(buf[i:])
    return bytes(buf[i:j + 8])
