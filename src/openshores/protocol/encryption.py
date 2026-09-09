
from __future__ import annotations

VERSION_STRING = "13.110.60"
VERSION_BASE_KEY = 0x6E31

LOGIN_PACKET_KEY_SEED = 0x0101


def net_crypt_key(per_packet: int) -> int:
    per_packet &= 0xFFFF
    if per_packet != 0:
        r = (VERSION_BASE_KEY + per_packet) & 0xFFFF
        return r if r != 0 else per_packet
    return VERSION_BASE_KEY if VERSION_BASE_KEY != 0 else 0x6175


def au_crypt(data: bytes, key: int) -> bytes:
    if key == 0:
        return bytes(data)
    masked = key & 0x0F0F
    k = (masked >> 8) & 0xFF
    step = masked & 0xFF
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = b ^ k
        k = (k + step) & 0xFF
    return bytes(out)
