
from __future__ import annotations

import struct
import zlib
from typing import Optional

TYPE_LOGIN = 0x03
TYPE_LOGOUT = 0x07
TYPE_SET_PLAYER_UNIT = 0x08
TYPE_DELETE_PLAYER_UNIT = 0x0F
TYPE_REQUEST_CONTACTS = 0x11
TYPE_PLAYER_UNIT_BORN = 0x17
TYPE_PLAYER_UNIT_DIED = 0x18
TYPE_TRANSFER_PLAYER_UNIT = 0x1A
TYPE_QUERY_INACTIVE_UNITS = 0x1B
TYPE_QUERY_AVATARS = 0x1C
TYPE_LIST_PLAYER_UNITS = 0x1D
TYPE_PLAYER_UNIT_RENAMED = 0x1E
TYPE_PLAYER_UNIT_DNA_CHANGED = 0x1F

TYPE_NAMES = {
    TYPE_LOGIN: "Login",
    TYPE_LOGOUT: "Logout",
    TYPE_SET_PLAYER_UNIT: "SetPlayerUnit",
    TYPE_DELETE_PLAYER_UNIT: "DeletePlayerUnit",
    TYPE_REQUEST_CONTACTS: "RequestContacts",
    TYPE_PLAYER_UNIT_BORN: "PlayerUnitBorn",
    TYPE_PLAYER_UNIT_DIED: "PlayerUnitDied",
    TYPE_TRANSFER_PLAYER_UNIT: "TransferPlayerUnit",
    TYPE_QUERY_INACTIVE_UNITS: "QueryInactiveUnits",
    TYPE_QUERY_AVATARS: "QueryAvatars",
    TYPE_LIST_PLAYER_UNITS: "ListPlayerUnits",
    TYPE_PLAYER_UNIT_RENAMED: "PlayerUnitRenamed",
    TYPE_PLAYER_UNIT_DNA_CHANGED: "PlayerUnitDNAChanged",
}

REPLY_CONTACTS = 0x11
REPLY_LIST_PLAYER_UNITS = 0x1D

ROSTER_SLOTS = 6


def parse_delete_player_unit(payload: bytes) -> Optional[dict]:
    if len(payload) < 13 or payload[0] != TYPE_DELETE_PLAYER_UNIT:
        return None
    arg0, arg1, unit = struct.unpack_from(">III", payload, 1)
    return {"arg0": arg0, "arg1": arg1, "auid": unit & 0xFFFFFFFF}


def _read_qstring(buf: bytes, off: int):
    if off + 4 > len(buf):
        return None, off
    n = struct.unpack_from(">I", buf, off)[0]
    off += 4
    if n == 0xFFFFFFFF:
        return "", off
    if n % 2 or off + n > len(buf):
        return None, off
    try:
        return buf[off:off + n].decode("utf-16-be"), off + n
    except Exception:
        return None, off


def _read_qbytearray(buf: bytes, off: int):
    if off + 4 > len(buf):
        return None, off
    n = struct.unpack_from(">I", buf, off)[0]
    off += 4
    if n == 0xFFFFFFFF:
        return b"", off
    if off + n > len(buf):
        return None, off
    return buf[off:off + n], off + n


def parse_player_unit_died(payload: bytes) -> Optional[dict]:
    if len(payload) < 5 or payload[0] != TYPE_PLAYER_UNIT_DIED:
        return None
    (auid,) = struct.unpack_from(">I", payload, 1)
    return {"auid": auid & 0xFFFFFFFF}


def parse_player_unit_renamed(payload: bytes) -> Optional[dict]:
    if len(payload) < 9 or payload[0] != TYPE_PLAYER_UNIT_RENAMED:
        return None
    (auid,) = struct.unpack_from(">I", payload, 1)
    name, _off = _read_qstring(payload, 5)
    if name is None:
        return None
    return {"auid": auid & 0xFFFFFFFF, "name": name}


def parse_player_unit_dna_changed(payload: bytes) -> Optional[dict]:
    if len(payload) < 9 or payload[0] != TYPE_PLAYER_UNIT_DNA_CHANGED:
        return None
    (auid,) = struct.unpack_from(">I", payload, 1)
    dna, _off = _read_qbytearray(payload, 5)
    if dna is None:
        return None
    return {"auid": auid & 0xFFFFFFFF, "dna": bytes(dna)}


def parse_player_unit_born(payload: bytes) -> Optional[dict]:
    if len(payload) < 13 or payload[0] != TYPE_PLAYER_UNIT_BORN:
        return None
    auid, auid2 = struct.unpack_from(">II", payload, 1)
    name, off = _read_qstring(payload, 9)
    if name is None:
        return None
    dna, off = _read_qbytearray(payload, off)
    if dna is None or off + 2 > len(payload):
        return None
    sex = payload[off]
    lefty = bool(payload[off + 1])
    return {"auid": auid & 0xFFFFFFFF, "auid2": auid2 & 0xFFFFFFFF,
            "name": name, "dna": bytes(dna), "sex": sex, "lefty": lefty}


def parse_set_player_unit(payload: bytes) -> Optional[dict]:
    if len(payload) < 17 or payload[0] != TYPE_SET_PLAYER_UNIT:
        return None
    a, b, auid = struct.unpack_from(">III", payload, 1)
    name, off = _read_qstring(payload, 13)
    if name is None:
        return None
    dna, off = _read_qbytearray(payload, off)
    if dna is None or off + 2 > len(payload):
        return None
    return {"arg0": a, "arg1": b, "auid": auid & 0xFFFFFFFF, "name": name,
            "dna": bytes(dna), "sex": payload[off],
            "lefty": bool(payload[off + 1])}


def parse_logout(payload: bytes) -> Optional[dict]:
    if len(payload) < 9 or payload[0] != TYPE_LOGOUT:
        return None
    a, b = struct.unpack_from(">ii", payload, 1)
    return {"field264": a, "field260": b}


def _qcompress(raw: bytes) -> bytes:
    return struct.pack(">I", len(raw)) + zlib.compress(raw)


def build_contacts_reply(contacts=()) -> bytes:
    items = [tuple(c) for c in contacts]
    inner = bytearray(struct.pack(">h", len(items)))
    for c in items:
        if len(c) != 3:
            raise ValueError(f"Contact must be (auid, name, flag), got {c!r}")
        auid, name, flag = c
        inner += struct.pack(">I", int(auid) & 0xFFFFFFFF)
        inner += _qstring(str(name))
        inner += bytes([1 if flag else 0])
    blob = _qcompress(bytes(inner))
    return bytes([REPLY_CONTACTS]) + struct.pack(">I", len(blob)) + blob


def _qstring(s: str) -> bytes:
    raw = (s or "").encode("utf-16-be")
    return struct.pack(">I", len(raw)) + raw


def parse_list_player_units(payload: bytes) -> Optional[dict]:
    if len(payload) < 9 or payload[0] != TYPE_LIST_PLAYER_UNITS:
        return None
    a, b = struct.unpack_from(">II", payload, 1)
    return {"arg0": a, "arg1": b}


def build_list_player_units_reply(units=()) -> bytes:
    units = list(units)[:ROSTER_SLOTS]
    out = bytearray([REPLY_LIST_PLAYER_UNITS])
    for i in range(ROSTER_SLOTS):
        if i < len(units):
            auid, name = units[i]
            out += struct.pack(">I", int(auid) & 0xFFFFFFFF) + _qstring(name)
        else:
            out += struct.pack(">I", 0) + _qstring("")
    return bytes(out)
