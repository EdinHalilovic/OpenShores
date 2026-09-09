from __future__ import annotations

import datetime as _dt
import struct

DEFAULT_MAIL_PORT = 16760


def mail_port(port: int = DEFAULT_MAIL_PORT) -> int:
    v = int(port or DEFAULT_MAIL_PORT)
    return v if 0 < v < 65536 else DEFAULT_MAIL_PORT

NO_GALAXY = 0x14
MAIL_FORMAT_VERSION = 6

MSGTYPE_QUEUE_BIT = 0x10
MSGTYPE_PERSIST_BIT = 0x02
MSGTYPE_ALT_BIT = 0x800


def _qstring(s):
    if s is None:
        return struct.pack(">I", 0xFFFFFFFF)
    raw = s.encode("utf-16-be")
    return struct.pack(">I", len(raw)) + raw


def _read_qstring(buf, off):
    (n,) = struct.unpack_from(">I", buf, off); off += 4
    if n == 0xFFFFFFFF:
        return None, off
    s = buf[off:off + n].decode("utf-16-be"); off += n
    return s, off


def julian_day(y, m, d):
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def encode_qdatetime_v7(unix_ms: int) -> bytes:
    t = _dt.datetime.fromtimestamp(int(unix_ms) / 1000.0, tz=_dt.timezone.utc)
    jd = julian_day(t.year, t.month, t.day)
    ms = ((t.hour * 60 + t.minute) * 60 + t.second) * 1000 + (t.microsecond // 1000)
    return struct.pack(">IIb", jd & 0xFFFFFFFF, ms & 0xFFFFFFFF, 1)


def encode_aumailmsg(*, subject: str, body: str, sender_id: int, recipient_id: int,
                     timestamp_ms: int, status: int = 0, flags_byte: int = 0,
                     title: str = "", bool_flag: int = 0,
                     system_id: int = 0, system_name: str = "",
                     world_id: int = 0, world_name: str = "",
                     galaxy: int = NO_GALAXY, loc=(0.0, 0.0, 0.0)) -> bytes:
    b = bytearray()
    b += struct.pack(">i", int(status))
    b += encode_qdatetime_v7(timestamp_ms)
    b += _qstring(subject)
    b += struct.pack(">I", int(sender_id) & 0xFFFFFFFF)
    b += struct.pack(">I", int(recipient_id) & 0xFFFFFFFF)
    flags = int(flags_byte) & 0xFF
    if int(system_id) != 0:
        flags |= 0x100
    if int(world_id) != 0:
        flags |= 0x200
    if (int(galaxy) & 0xFF) != NO_GALAXY:
        flags |= 0x400
    b += struct.pack(">H", flags & 0xFFFF)
    b += _qstring(title)
    b += _qstring(body)
    b += struct.pack(">B", int(bool_flag) & 0xFF)
    if flags & 0x100:
        b += struct.pack(">I", int(system_id) & 0xFFFFFFFF)
        b += _qstring(system_name)
    if flags & 0x200:
        b += struct.pack(">I", int(world_id) & 0xFFFFFFFF)
        b += _qstring(world_name)
    if flags & 0x400:
        b += struct.pack(">b", int(galaxy) & 0xFF if int(galaxy) < 128 else int(galaxy) - 256)
        b += struct.pack(">fff", float(loc[0]), float(loc[1]), float(loc[2]))
    return bytes(b)


def decode_aumailmsg(buf: bytes, off: int = 0):
    d = {}
    (d["status"],) = struct.unpack_from(">i", buf, off); off += 4
    (jd, ms, spec) = struct.unpack_from(">IIb", buf, off); off += 9
    d["julian_day"] = jd; d["ms_since_midnight"] = ms; d["time_spec"] = spec
    d["subject"], off = _read_qstring(buf, off)
    (d["sender_id"],) = struct.unpack_from(">I", buf, off); off += 4
    (d["recipient_id"],) = struct.unpack_from(">I", buf, off); off += 4
    (flags,) = struct.unpack_from(">H", buf, off); off += 2
    d["flags"] = flags
    d["title"], off = _read_qstring(buf, off)
    d["body"], off = _read_qstring(buf, off)
    (d["bool_flag"],) = struct.unpack_from(">B", buf, off); off += 1
    if flags & 0x100:
        (d["system_id"],) = struct.unpack_from(">I", buf, off); off += 4
        d["system_name"], off = _read_qstring(buf, off)
    if flags & 0x200:
        (d["world_id"],) = struct.unpack_from(">I", buf, off); off += 4
        d["world_name"], off = _read_qstring(buf, off)
    if flags & 0x400:
        (d["galaxy"],) = struct.unpack_from(">b", buf, off); off += 1
        d["loc"] = struct.unpack_from(">fff", buf, off); off += 12
    return d, off


def encode_mail_packet(*, login_version: str, sender_empire: int, msg_type: int,
                       mail_body: bytes) -> bytes:
    p = bytearray()
    p += struct.pack(">B", MAIL_FORMAT_VERSION)
    p += _qstring(login_version)
    p += struct.pack(">i", int(sender_empire) & 0xFFFFFFFF)
    p += struct.pack(">i", int(msg_type) & 0xFFFFFFFF)
    p += bytes(mail_body)
    return bytes(p)


def msgtype_will_queue(msg_type: int) -> bool:
    t = int(msg_type)
    return bool((t & MSGTYPE_QUEUE_BIT) and
                ((t & MSGTYPE_PERSIST_BIT) or ((t >> 11) & 1)) and t < 0x989681)


def _mail_write_packet_size(n: int) -> bytes:
    n = int(n)
    if n < 0x40:
        return bytes([n])
    if n < 0x4000:
        return bytes([0x40 | (n >> 8), n & 0xFF])
    if n < 0x400000:
        return bytes([0x80 | (n >> 16), (n >> 8) & 0xFF, n & 0xFF])
    return bytes([0xC0 | (n >> 24), (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])


MAIL_OPCODE_END = 4


def _mail_terminator() -> bytes:
    return _mail_write_packet_size(1) + bytes([MAIL_OPCODE_END])
