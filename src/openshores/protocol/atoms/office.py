
from __future__ import annotations

from openshores.protocol.stream import QDS


def _write_auoffice_empty(s: QDS, role_id: int = 0xFFFFFFFF) -> None:
    s.write_i32(0)
    s.write_i32(0)
    s.write_i16(0)
    s.write_u32(int(role_id) & 0xFFFFFFFF)
    s.write_u32(0xFFFFFFFF)


def _write_auoffice_emperor(s: QDS, holder_auid: int,
                            office_name: str = "Emperor",
                            flags1: int = -1,
                            flags2: int = -1) -> None:
    s.write_i32(flags1)
    s.write_i32(flags2)
    s.write_i16(0)
    s.write_i32(0)
    s.write_qstring(office_name)
    _ = holder_auid


def _build_nested_offices_empty() -> bytes:
    s = QDS(); s.write_i16(0); return s.getvalue()


def _build_nested_cityhash_empty() -> bytes:
    s = QDS(); s.write_i16(0); return s.getvalue()


def _write_auoffice_titled(s: QDS, role_id: int, title: str,
                           flags1: int = -1, flags2: int = -1) -> None:
    s.write_i32(flags1)
    s.write_i32(flags2)
    s.write_i16(0)
    s.write_i32(int(role_id) & 0xFFFFFFFF)
    s.write_qstring(title or "")
