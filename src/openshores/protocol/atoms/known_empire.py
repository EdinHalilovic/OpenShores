
from __future__ import annotations

import logging

from openshores.protocol.atoms.document import (
    _write_au_doc_note,
    _write_au_doc_unit_contact,
)
from openshores.protocol.qdatetime import _write_qdatetime_now
from openshores.protocol.stream import QDS

logger = logging.getLogger(__name__)


def _write_auknown_empire(s: QDS, empire_id: int, name: str,
                          include_dossier: bool = True,
                          first_met_ms: int = None,
                          last_seen_ms: int = None,
                          stance: int = 0,
                          tribute: int = 0,
                          docs: list = None) -> None:
    flags = int(empire_id) & 0x7FFFFFFF
    if include_dossier:
        flags |= 0x80000000
    s.write_u32(flags)
    s.write_qstring(name or "")
    s.write_u8(int(stance) & 0xFF)
    s.write_u8(int(tribute) & 0xFF)
    import time as _t
    _now_ms = int(_t.time() * 1000)
    _fm = int(first_met_ms) if first_met_ms is not None else (_now_ms - 30 * 86400000)
    _ls = int(last_seen_ms) if last_seen_ms is not None else _now_ms
    _write_qdatetime_now(s, ms_offset=_fm - _now_ms)
    _write_qdatetime_now(s, ms_offset=_ls - _now_ms)
    if include_dossier:
        _docs = docs if docs is not None else [{
            'doc_type': 0x01, 'timestamp_ms': _fm,
            'actor_avatar_id': 0, 'actor_empire_id': 0,
            'text_a': "", 'text_b': "", 'text_c': "",
        }]
        s.write_i16(len(_docs))
        for _doc in _docs:
            _dt = int(_doc.get('doc_type', 0x01))
            s.write_u8(_dt & 0xFF)
            if _dt == 0x01:
                _write_au_doc_unit_contact(
                    s, ts_ms=int(_doc.get('timestamp_ms', _fm)),
                    actor_avatar_auid=int(_doc.get('actor_avatar_id', 0)),
                    actor_empire_id=int(_doc.get('actor_empire_id', 0)),
                    text_a=str(_doc.get('text_a', "")),
                    text_b=str(_doc.get('text_b', "")),
                    text_c=str(_doc.get('text_c', "")),
                    doc_state=int(_doc.get('doc_state', 0)),
                )
            elif _dt == 0x0A:
                _write_au_doc_note(
                    s, ts_ms=int(_doc.get('timestamp_ms', _fm)),
                    doc_state=int(_doc.get('doc_state', 0)),
                    actor_auid=int(_doc.get('actor_avatar_id', 0)),
                    note=str(_doc.get('actor_name', "")),
                    t28=str(_doc.get('text_a', "")),
                )
            else:
                logger.warning(
                    'Dossier doc_type 0x%02x has no writer.', _dt)
                _write_qdatetime_now(s, ms_offset=0)
                s.write_u8(0)
