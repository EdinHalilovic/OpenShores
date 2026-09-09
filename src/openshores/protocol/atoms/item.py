
from __future__ import annotations

import struct

_QSTRING_NULL = 0xFFFFFFFF


def _skip_qstring(buf, off, what="QString"):
    if off + 4 > len(buf):
        raise ValueError("%s: truncated at length" % what)
    nlen = int.from_bytes(buf[off:off + 4], "big")
    off += 4
    if nlen == _QSTRING_NULL:
        return off
    if off + nlen > len(buf):
        raise ValueError("%s: truncated at %d payload bytes" % (what, nlen))
    return off + nlen


_QS_NULL = b"\xff\xff\xff\xff"


def _pack_qstring(s) -> bytes:
    if s is None:
        return b"\xff\xff\xff\xff"
    if not s:
        return b"\x00\x00\x00\x00"
    chars = s.encode("utf-16-be")
    return struct.pack(">I", len(chars)) + chars


def _unpack_auitem_body(typeId, buf, off):
    start = off
    if (typeId == 0x01 or typeId == 0x0E or typeId == 0x06
            or typeId == 0x0B or typeId == 0x12 or typeId == 0x07
            or typeId == 0x08 or typeId == 0x09 or typeId == 0x0C
            or typeId == 0x10 or typeId == 0x11):  # noqa: E129
        if off + 1 > len(buf):
            raise ValueError("AuItem: truncated at flag")
        flag = buf[off]; off += 1
        if off + 3 > len(buf):
            raise ValueError("AuItem: truncated at cid+byte14")
        off += 3
        if flag & 0x08:
            if off + 4 > len(buf):
                raise ValueError("AuItem: truncated at name length")
            nl = int.from_bytes(buf[off:off+4], "big"); off += 4
            if off + nl > len(buf):
                raise ValueError("AuItem: truncated at name bytes")
            off += nl
        if off + 1 > len(buf):
            raise ValueError("AuItem: truncated at quality")
        off += 1
        if typeId == 0x0E:
            if off + 12 + 1 + 1 + 4 > len(buf):
                raise ValueError("FloraDNA: truncated at head")
            off += 12
            off += 1
            flag2 = buf[off]; off += 1
            off += 4
            if flag2 & 0x80:
                if off + 1 > len(buf):
                    raise ValueError("FloraDNA: truncated at flag2 byte")
                off += 1
            if off + 2 + 4 + 4 + 4 > len(buf):
                raise ValueError("FloraDNA: truncated at tail")
            off += 2 + 4 + 4 + 4
        elif typeId == 0x06:
            if off + 1 > len(buf):
                raise ValueError("AuItemState: truncated at +0x50 byte")
            off += 1
        elif typeId == 0x07:
            pass
        elif typeId == 0x08 or typeId == 0x09 or typeId == 0x0C:
            if off + 1 > len(buf):
                raise ValueError("AuItemWeapon: truncated at weapon_flags")
            wflags = buf[off]; off += 1
            if off + 2 > len(buf):
                raise ValueError("AuItemWeapon: truncated at cooldown_ts")
            off += 2
            for sub_bit, base_off in ((0x01, 0x52), (0x02, 0x5e)):
                if wflags & sub_bit:
                    sub_len = 1 + 2 + (2 if (wflags & 0x20) else 1) + 2 + 1 + 2
                    if off + sub_len > len(buf):
                        raise ValueError(
                            f"AuItemWeapon: truncated in 0x{base_off:x} "
                            f"sub-block (need {sub_len})")
                    off += sub_len
            if wflags & 0x1c:
                if off + 2 > len(buf):
                    raise ValueError("AuItemWeapon: truncated at +0x6a")
                off += 2
                if wflags & 0x04:
                    sub_len = 1 + 2 + (2 if (wflags & 0x20) else 1) + 2 + 1 + 2
                    if off + sub_len > len(buf):
                        raise ValueError("AuItemWeapon: truncated in +0x6c block")
                    off += sub_len
                if wflags & 0x08:
                    sub_len = 1 + 2 + (2 if (wflags & 0x20) else 1) + 2 + 1 + 2
                    if off + sub_len > len(buf):
                        raise ValueError("AuItemWeapon: truncated in +0x78 block")
                    off += sub_len
            if typeId == 0x09:
                if off + 4 > len(buf):
                    raise ValueError(
                        "AuItemWeaponAmmo: truncated at ammo block")
                off += 4
            elif typeId == 0x0C:
                if off + 1 > len(buf):
                    raise ValueError(
                        "AuItemWeaponState: truncated at state byte")
                off += 1
        elif typeId == 0x12:
            if off + 3 > len(buf):
                raise ValueError(
                    "AuItemBox: truncated at capacity/magic/count")
            off += 1
            magic = buf[off]; off += 1
            if magic >= 0xF1:
                if off + 1 > len(buf):
                    raise ValueError(
                        "AuItemBox: truncated at explicit-count")
                n_nested = buf[off]; off += 1
                key_per_entry = True
            else:
                n_nested = magic
                key_per_entry = False
            for _i in range(n_nested):
                if key_per_entry:
                    if off + 1 > len(buf):
                        raise ValueError(
                            "AuItemBox: truncated at nested key")
                    off += 1
                if off + 1 > len(buf):
                    raise ValueError(
                        "AuItemBox: truncated at nested typeId")
                nested_tid = buf[off]; off += 1
                _, off = _unpack_auitem_body(nested_tid, buf, off)
        elif typeId == 0x0B:
            if off + 8 + 1 > len(buf):
                raise ValueError(
                    "AuItemContainer: truncated at QSize+count")
            off += 8
            n_nested = buf[off]; off += 1
            for _i in range(n_nested):
                if off + 3 > len(buf):
                    raise ValueError(
                        "AuItemContainer: truncated at nested "
                        f"meta {_i}/{n_nested}")
                off += 2
                nested_tid = buf[off]; off += 1
                _, off = _unpack_auitem_body(nested_tid, buf, off)
        elif typeId == 0x11:
            if off + 1 > len(buf):
                raise ValueError(
                    "AuItemStateMessage: truncated at state byte")
            off += 1
            off = _skip_qstring(buf, off, "AuItemStateMessage message")
        elif typeId == 0x10:
            off = _skip_qstring(buf, off, "AuItemPicture url")
            if off + 1 > len(buf):
                raise ValueError(
                    "AuItemPicture: truncated at packed flag byte")
            off += 1
        return bytes(buf[start:off]), off
    raise ValueError("Unknown AuItem typeId 0x%02X" % typeId)


def _extract_cid_from_auitem_body(body: bytes) -> int:
    if len(body) < 3:
        return 0
    return int.from_bytes(body[1:3], "big") & 0xFFFF
