
from __future__ import annotations

from openshores.protocol.qdatetime import _write_qdatetime_now
from openshores.protocol.stream import QDS


def _write_au_doc_unit_contact(s: QDS, ts_ms: int,
                                actor_avatar_auid: int = 0,
                                actor_empire_id: int = 0,
                                text_a: str = "",
                                text_b: str = "",
                                text_c: str = "",
                                doc_state: int = 0) -> None:
    _write_qdatetime_now(s, ms_offset=int(ts_ms) - int(__import__('time').time() * 1000))
    s.write_u8(int(doc_state) & 0xFF)
    s.write_u8(0)
    s.write_u8(0)
    s.write_u32(int(actor_avatar_auid) & 0xFFFFFFFF)
    s.write_qstring(text_a)
    s.write_qstring(text_b)
    s.write_qstring(text_c)
    s.write_u8(0)
    s.write_u32(int(actor_empire_id) & 0xFFFFFFFF)
    s.write_qstring("")
    s.write_qstring("")


def _write_au_doc_note(s: QDS, ts_ms: int, doc_state: int = 0,
                       actor_auid: int = 0, note: str = "",
                       t28: str = "", t30: str = "", t38: str = "",
                       t40: str = "") -> None:
    _write_qdatetime_now(s, ms_offset=int(ts_ms) - int(__import__('time').time() * 1000))
    s.write_u8(int(doc_state) & 0xFF)
    s.write_u8(0x14)
    s.write_u32(int(actor_auid) & 0xFFFFFFFF)
    s.write_qstring(note or "")
    s.write_qstring(t28 or "")
    s.write_qstring(t30 or "")
    s.write_qstring(t38 or "")
    s.write_qstring(t40 or "")
