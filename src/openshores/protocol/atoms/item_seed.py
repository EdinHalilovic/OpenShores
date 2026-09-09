
from __future__ import annotations

import struct

from openshores.protocol.atoms.weapon import (
    _pack_auitemweapon_tail,
    _pack_auitemweaponammo_tail,
)

_AUFLORADNA_PRIMEVAL_CID130 = bytes.fromhex("75 30 75 2F 36 D0 B3 45 32 AD 82 00".replace(" ", ""))


def _build_flora_dna(cid=0, family=3, trunk_num=14, branch_len=8,
                      leaf_len=5, leaf_color=5, glow_gate=1,
                      trunk_taper=4, bend=3, branchiness=2,
                      density=2, wood_color=3, tone1=2,
                      latitude=3, raw=None):
    if raw is not None:
        if len(raw) != 12:
            raise ValueError("Raw flora DNA must be 12 bytes")
        return bytes(raw)
    family = max(1, int(family) & 7)
    branch_len = max(1, int(branch_len) & 0xf)
    leaf_len = max(1, int(leaf_len) & 7)
    glow_gate = max(1, int(glow_gate) & 3)
    trunk_taper = max(1, int(trunk_taper) & 7)
    w0 = (
        ((family & 7) << 0)
        | ((int(trunk_num) & 0x1f) << 3)
        | ((int(density) & 3)      << 8)
        | ((int(wood_color) & 7)   << 10)
        | ((int(branchiness) & 3)  << 13)
        | ((int(branchiness) & 3)  << 16)
        | ((int(tone1) & 3)        << 18)
        | ((leaf_len & 7)          << 27)
        | ((1 & 3)                 << 30)
    ) & 0xFFFFFFFF
    w1 = (
        ((int(latitude) & 7) << 0)
        | ((int(leaf_color) & 7) << 3)
        | ((1 & 3)             << 6)
        | ((branch_len & 0xf)  << 8)
        | ((int(bend) & 7)     << 12)
        | ((1 & 1)             << 15)
        | ((3 & 7)             << 16)
        | ((1 & 3)             << 19)
        | ((5 & 7)             << 21)
        | ((glow_gate & 3)     << 24)
        | ((5 & 7)             << 26)
        | ((5 & 7)             << 29)
    ) & 0xFFFFFFFF
    w2 = (
        ((3 & 7) << 0)
        | ((3 & 3) << 3)
        | ((3 & 7) << 5)
        | ((3 & 7) << 8)
        | ((3 & 7) << 11)
        | ((1 & 3) << 14)
        | ((0 & 1) << 16)
        | ((1 & 3) << 17)
        | ((2 & 3) << 19)
        | ((trunk_taper & 7) << 21)
    ) & 0xFFFFFFFF
    return struct.pack('<III', w0, w1, w2)


def _pack_auitem_seed_body(typeId, cid, byte14=5, quality=0x3D, name="",
                           flora_dna=None, for_world: bool = False,
                           switched_on: int = 0,
                           weapon_spec=None):
    typeId = int(typeId) & 0xFF
    cid = int(cid) & 0xFFFF
    flag = 0x04 | (0x08 if name else 0x00)
    body = bytes([flag]) + struct.pack(">h", cid) + bytes([byte14 & 0xFF])
    if name:
        utf16 = name.encode("utf-16-be")
        body += struct.pack(">I", len(utf16)) + utf16
    body += bytes([quality & 0xFF])

    if typeId == 0x0E:
        if flora_dna is None:
            flora_dna = _build_flora_dna(cid=cid)
        if len(flora_dna) != 12:
            raise ValueError('AuFloraDNA must be exactly 12 bytes')
        flora_flag2 = 0x80 if for_world else 0x00
        body += flora_dna
        body += bytes([0x00])
        body += bytes([flora_flag2])
        body += struct.pack(">i", 0)
        if for_world:
            body += bytes([0x00])
        body += struct.pack(">h", 0)
        body += struct.pack(">i", 0)
        body += struct.pack(">i", 0)
        body += bytes([0x00, 0x01, 0x01, 0x01])
    elif typeId == 0x06:
        body += bytes([1 if switched_on else 0])
    elif typeId == 0x07:
        pass
    elif typeId == 0x08:
        body += _pack_auitemweapon_tail(weapon_spec)
    elif typeId == 0x09:
        body += _pack_auitemweaponammo_tail(weapon_spec)
    elif typeId == 0x0C:
        body += _pack_auitemweapon_tail(weapon_spec)
        body += bytes([1 if switched_on else 0])
    elif typeId == 0x12:
        body += bytes([16])
        body += bytes([0xF1])
        body += bytes([0])
    elif typeId == 0x0B:
        body += struct.pack(">ii", 4, 4)
        body += bytes([0])
    return body
