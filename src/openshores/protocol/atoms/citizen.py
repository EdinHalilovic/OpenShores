
from __future__ import annotations

from openshores.protocol.atoms.office import (
    _write_auoffice_empty,
    _write_auoffice_emperor,
    _write_auoffice_titled,
)
from openshores.protocol.stream import QDS


def _write_aucitizen(s: QDS, citizen_auid: int, name: str,
                     is_emperor: bool = False,
                     title: str | None = None,
                     rights1: int = -1, rights2: int = -1) -> None:
    s.write_u32(int(citizen_auid) & 0xFFFFFFFF)
    s.write_qstring(name or "")
    s.write_u8(0x80 | 0x08)
    if is_emperor:
        _write_auoffice_emperor(s, citizen_auid)
    elif title:
        _write_auoffice_titled(s, int(citizen_auid) & 0xFFFFFFFF, title,
                               flags1=rights1, flags2=rights2)
    else:
        _write_auoffice_empty(s, role_id=int(citizen_auid) & 0xFFFFFFFF)
