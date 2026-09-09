
from __future__ import annotations

from openshores.protocol.stream import QDS


def build_login_ok_reply_for_avatars(
        active_player_unit: int,
        avatars: list[tuple[int, str, bytes]]) -> bytes:
    if len(avatars) > 6:
        raise ValueError(f"Login reply has at most 6 avatar slots, got {len(avatars)}")
    if not active_player_unit:
        active_player_unit = 1
    s = QDS()
    s.write_u8(0x03)
    s.write_i32(1)
    s.write_i32(int(active_player_unit) & 0xFFFFFFFF)
    for slot in range(6):
        if slot < len(avatars):
            rec = avatars[slot]
            auid, name, dna = rec[0], rec[1], rec[2]
            sex = int(rec[3]) if len(rec) > 3 and rec[3] is not None else 1
            lefty = bool(rec[4]) if len(rec) > 4 and rec[4] is not None else False
            dna = (bytes(dna) + bytes(24))[:24]
            s.write_u32(int(auid) & 0xFFFFFFFF)
            s.write_qstring(name)
            s.write_bytes(dna)
            s.write_u8(sex & 0xFF)
            s.write_bool(lefty)
        else:
            s.write_u32(0)
            s.write_qstring("")
            s.write_bytes(bytes(24))
            s.write_u8(0)
            s.write_bool(False)
    s.write_u8(5)
    return s.getvalue()


def _default_dna() -> bytes:
    return bytes([
        0x65, 0x0d, 0x80, 0x92,
        0x80, 0x10, 0x71, 0x16,
        0x82, 0x77, 0x58, 0x6a,
        0x54, 0x46, 0x05, 0x82,
        0xa2, 0x54, 0xc2, 0x72,
        0x56, 0x14, 0x14, 0x00,
    ])


