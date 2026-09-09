
from __future__ import annotations

from openshores.protocol.encryption import au_crypt, net_crypt_key
from openshores.protocol.stream import QDS


def build_scene_dn_room_empty(room_type: int = 0) -> bytes:
    assert room_type != 0x18, "Hull variant has a different, larger layout"
    s = QDS()
    s.write_u8(0x39)
    s.write_i32(0)
    s.write_i16(0)
    s.write_u8(0)
    s.write_u8(room_type)
    s.write_u8(0)
    s.write_i16(0)
    return s.getvalue()


def build_scene_dn_building_empty() -> bytes:
    s = QDS()
    s.write_u8(0x22)
    s.write_i32(0)
    s.write_i16(0)
    s.write_i32(0)
    s.write_i32(0)
    s.write_u8(0)
    s.write_i16(0)
    s.write_i32(0)
    s.write_u8(0)
    return s.getvalue()


def build_scene_accept_invite_empire(session_lo: int = 1) -> bytes:
    pt = QDS()
    pt.write_u8(0x0E)
    pt.write_u8(0x00)
    pt.write_i32(0)
    pt.write_i32(0)
    pt.write_i32(0)
    pt.write_u8(0x00)
    pt.write_i32(0)
    pt.write_i32(0)
    plaintext = pt.getvalue()

    key = net_crypt_key(session_lo)
    ciphertext = au_crypt(plaintext, key)

    out = QDS()
    out.write_u8(0x0A)
    out.write_i32(len(ciphertext))
    out.buf += ciphertext
    return out.getvalue()
