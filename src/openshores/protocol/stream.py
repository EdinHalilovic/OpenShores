
from __future__ import annotations

import datetime as _dt
import struct
from typing import Optional


class QDS:
    def __init__(self, buf: bytes | bytearray = b""):
        self.buf = bytearray(buf)
        self.pos = 0

    def _take(self, n: int) -> bytes:
        if self.pos + n > len(self.buf):
            raise EOFError(f"QDS underflow: want {n}, have {len(self.buf) - self.pos}")
        chunk = bytes(self.buf[self.pos:self.pos + n])
        self.pos += n
        return chunk

    def read_u8(self) -> int:  return self._take(1)[0]
    def read_i8(self) -> int:  return struct.unpack(">b", self._take(1))[0]
    def read_bool(self) -> bool: return self._take(1)[0] != 0
    def read_i16(self) -> int: return struct.unpack(">h", self._take(2))[0]
    def read_u16(self) -> int: return struct.unpack(">H", self._take(2))[0]
    def read_i32(self) -> int: return struct.unpack(">i", self._take(4))[0]
    def read_u32(self) -> int: return struct.unpack(">I", self._take(4))[0]

    def read_bytes(self) -> Optional[bytes]:
        n = self.read_u32()
        if n == 0xFFFFFFFF:
            return None
        return self._take(n)

    def read_qstring(self) -> Optional[str]:
        n = self.read_u32()
        if n == 0xFFFFFFFF:
            return None
        raw = self._take(n)
        return raw.decode("utf-16-be")

    def write_u8(self, v: int):  self.buf.append(v & 0xFF)
    def write_i8(self, v: int):  self.buf += struct.pack(">b", ((int(v) + 0x80) & 0xFF) - 0x80)
    def write_i16(self, v: int): self.buf += struct.pack(">h", v)

    def write_i16_wrapped(self, v: int):
        self.buf += struct.pack(">h", ((int(v) + 0x8000) & 0xFFFF) - 0x8000)

    def write_u8_wrapped(self, v: int):
        self.buf += struct.pack(">B", int(v) & 0xFF)
    def write_u16(self, v: int): self.buf += struct.pack(">H", v & 0xFFFF)
    def write_i32(self, v: int):
        self.buf += struct.pack(
            ">i", ((int(v) & 0xFFFFFFFF) ^ 0x80000000) - 0x80000000)
    def write_u32(self, v: int): self.buf += struct.pack(">I", v & 0xFFFFFFFF)
    def write_f64(self, v: float): self.buf += struct.pack(">d", float(v))
    def write_f32(self, v: float): self.buf += struct.pack(">f", float(v))
    def write_bool(self, v: bool): self.buf.append(1 if v else 0)

    def write_bytes(self, b: Optional[bytes]):
        if b is None:
            self.write_u32(0xFFFFFFFF)
            return
        self.write_u32(len(b))
        self.buf += b

    def write_qstring(self, s: Optional[str]):
        if s is None:
            self.write_u32(0xFFFFFFFF)
            return
        raw = s.encode("utf-16-be")
        self.write_u32(len(raw))
        self.buf += raw

    def write_qdatetime(self, unix_ms):
        t = _dt.datetime.fromtimestamp(int(unix_ms) / 1000.0, tz=_dt.timezone.utc)
        a = (14 - t.month) // 12
        y = t.year + 4800 - a
        m = t.month + 12 * a - 3
        jd = t.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
        ms = ((t.hour * 60 + t.minute) * 60 + t.second) * 1000 + t.microsecond // 1000
        self.buf += struct.pack(">IIb", jd & 0xFFFFFFFF, ms & 0xFFFFFFFF, 1)

    def write_raw(self, b: bytes):
        self.buf += b

    def getvalue(self) -> bytes:
        return bytes(self.buf)
