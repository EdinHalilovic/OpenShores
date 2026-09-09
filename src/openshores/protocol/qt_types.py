
from __future__ import annotations

from openshores.protocol.stream import QDS


def _write_qimage_null(s: QDS) -> None:
    s.write_i32(0)


def _write_qimage(s: QDS, png_bytes: bytes) -> None:
    if not png_bytes:
        s.write_i32(0)
        return
    s.write_i32(1)
    s.buf += png_bytes


def _write_qcolor_null(s: QDS) -> None:
    s.write_u8(0)
    s.write_u16(0xFFFF)
    s.write_u16(0); s.write_u16(0); s.write_u16(0); s.write_u16(0)


def _write_qcolor(s: QDS, a: int = 0xFFFF, r: int = 0, g: int = 0, b: int = 0) -> None:
    s.write_u8(1)
    s.write_u16(a); s.write_u16(r); s.write_u16(g); s.write_u16(b); s.write_u16(0)
