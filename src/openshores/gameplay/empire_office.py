
from __future__ import annotations


import struct
from typing import List

from openshores.core.logging import get_logger
from openshores.gameplay.empire_read import _empire_for, _office_tail
from openshores.protocol.empire_chat_parse import _read_qstring

logger = get_logger(__name__)


def classify_unhandled(op: int, body_after_opcode: bytes) -> str:
    b = body_after_opcode
    n = len(b)
    hints: List[str] = []
    if 0xB0 <= op <= 0xBF or op in (0x4A, 0x98, 0x14, 0xAF):
        hints.append("opcode in empire/admin band")
    if n == 64:
        ints = [struct.unpack_from(">i", b, i * 4)[0] for i in range(16)]
        hints.append(f"64B = 16xqint32 -> looks like SetEmpireRewards "
                     f"(set HZ_OP_EMPIRE_REWARDS=0x{op:02X}); values={ints}")
    if n == 2:
        hints.append(f"2B [u8 {b[0]}][u8 {b[1]}] -> policy-toggle(0xB1)/"
                     f"contrail(0x98)-shaped")
    if n == 3:
        u16 = struct.unpack_from(">H", b, 0)[0]
        hints.append(f"3B -> taxes(0xAF)/role(0xBA)-shaped "
                     f"([u16 {u16}][u8 {b[2]}] or [u8][u8][u8])")
    if n >= 4:
        try:
            slen = struct.unpack_from(">I", b, 0)[0]
            if slen != 0xFFFFFFFF and 4 + slen == n:
                txt = b[4:4 + slen].decode("utf-16-be", "replace")
                hints.append(f"QString({slen}B) -> announcement/name-shaped: "
                             f"{txt!r}")
        except Exception:
            logger.debug('classify_unhandled: 0x%02X body of %dB does not read as a QString.', op, n)
    return " | ".join(hints) if hints else f"{n}B body, no empire-shape match"


def _serialize_theme(colors) -> bytes:
    out = bytearray([6])
    src = (list(colors) + [(255, 0, 0, 0)] * 6)[:6]
    for (a, r, g, b) in src:
        out += bytes([1])
        out += struct.pack(">5H", (a * 257) & 0xFFFF, (r * 257) & 0xFFFF,
                           (g * 257) & 0xFFFF, (b * 257) & 0xFFFF, 0)
    return bytes(out)


def _make_capture_handler(opcode: int, label: str, *,
                          conn,
                          _CITIZEN_EMPIRE_OVERRIDE):
    async def _handler(payload: bytes, actor: int) -> None:
        eid = await _empire_for(
            conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
        logger.warning("[empire-mut] 0x%02X %s capture (handled, persistence pending): empire=%s actor=0x%08x body=%s",
                       opcode, label, eid, int(actor),
                       bytes(payload[1:64]).hex())
    return _handler


def parse_assign_office(body: bytes):
    if len(body) < 8:
        return None
    citizen = struct.unpack_from(">I", body, 0)[0]
    _name, p = _read_qstring(body, 4)
    try:
        flags1 = struct.unpack_from(">i", body, p)[0]; p += 4
        flags2 = struct.unpack_from(">i", body, p)[0]; p += 4
        place_count = struct.unpack_from(">h", body, p)[0]; p += 2
        if place_count == 0:
            role_id = struct.unpack_from(">I", body, p)[0]; p += 4
            title, p = _read_qstring(body, p)
        else:
            role_id, title = _office_tail(body)
    except struct.error:
        return None
    if title is None:
        return None
    return citizen, title, flags1 & 0xFFFFFFFF, flags2 & 0xFFFFFFFF, \
        (role_id or citizen) & 0xFFFFFFFF
