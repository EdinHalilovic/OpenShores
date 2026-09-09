
from __future__ import annotations

import struct as _struct
import time as _time

from openshores.core.logging import get_logger
from openshores.gameplay.empire.dg_empire import build_scene_dg_empire_0x31
from openshores.gameplay.room_types import build_scene_dn_room_type
from openshores.network import connection_state as _connection_state
from openshores.protocol.completion_chain import (
    build_scene_empire_data_complete,
)
from openshores.protocol.framing import write_framed
from openshores.protocol.scene_init import build_scene_init_succeeded

logger = get_logger(__name__)


async def push_creation_world(conn, writer, person_auid_atom: bytes, *,
                              label: str,
                              save,
                              build_scene_dn_detail_type,
                              name_long: str,
                              name_short: str,
                              capital_name: str,
                              _CITIZEN_EMPIRE_OVERRIDE: dict,
                              _EMPIRE_NAME_OVERRIDE: dict,
                              _EMPIRE_TAX_OVERRIDE: dict) -> None:
    def _auid(n: int) -> bytes:
        return (n & 0xFFFFFFFF).to_bytes(4, "big")

    AUID_UNI_A    = _auid(0x00000101)
    AUID_GAL_A    = _auid(0x00000102)
    AUID_SEC_A    = _auid(0x00000103)
    AUID_SYS_A    = _auid(0x00000104)
    AUID_STAR_A   = _auid(0x00000105)
    AUID_WORLD_A  = _auid(0x00000107)
    AUID_PERSON_A = (person_auid_atom[:4] if len(person_auid_atom) >= 4
                     else _auid(1))

    if not _connection_state._create_autime_ms:
        _connection_state._create_autime_ms = int(_time.time() * 1000)
    _autime_a = _struct.pack(">q", _connection_state._create_autime_ms)

    def _hdr(tag: int, auid: bytes) -> bytes:
        return bytes([tag]) + auid + _autime_a

    def _base_no_parent() -> bytes:
        return bytes([0x00])
    def _base_with_parent(parent: bytes) -> bytes:
        return bytes([0x01]) + parent
    def _base_parent_xform(parent: bytes,
                           tx=0.0, ty=0.0, tz=0.0,
                           rx=0.0, ry=0.0, rz=0.0) -> bytes:
        return (bytes([0x09]) + parent
                + _struct.pack(">ffffff",
                              tx, ty, tz, rx, ry, rz))

    _solarsys_body_a = (
        _struct.pack(">i", -1) + bytes([0x00])
        + _struct.pack(">i", 0) + _struct.pack(">i", 0)
        + bytes([0x00]) + _struct.pack(">i", 0))
    _wg_body = (bytes([0x00])
                + _struct.pack(">i", -1)
                + bytes([0x21])
                + bytes([10, 0x00, 0x00, 0x00])
                + _struct.pack(">ffffff",
                              1.0, 1.0, 1.0,
                              1.0, 1.0, 1.0)
                + _struct.pack(">ff", 0.0, 0.0)
                + _struct.pack(">i", 0))
    _nowhere_utf16_a = save.planet_name.encode("utf-16-be")
    _person_body_a = (
        bytes([0x00])
        + bytes([0x00, 0x00])
        + bytes([0x00])
        + bytes([0x81])
        + bytes([0x40])
        + _struct.pack(">I", int(save.system_auid) or 1)
        + _struct.pack(">I", len(_nowhere_utf16_a)) + _nowhere_utf16_a
        + _struct.pack(">ff", 0.0, 0.0)
        + _struct.pack(">I", 0)
        + bytes([0x00])
        + _struct.pack(">i", 0)
        + bytes([0x00])
    )
    chain_a = [
        ("DaUniverse",
         _hdr(0x1b, AUID_UNI_A) + _base_no_parent()),
        ("DaGalaxy",
         _hdr(0x10, AUID_GAL_A)
         + _base_with_parent(AUID_UNI_A)),
        ("DaSector",
         _hdr(0x14, AUID_SEC_A)
         + _base_with_parent(AUID_GAL_A)),
        ("DaSolarSystem",
         _hdr(0x15, AUID_SYS_A)
         + _base_with_parent(AUID_SEC_A)
         + _solarsys_body_a),
        ("DaStar",
         _hdr(0x17, AUID_STAR_A)
         + _base_with_parent(AUID_SYS_A) + bytes([0x00])),
        ("DaWorldGlobe",
         _hdr(0x1F, AUID_WORLD_A)
         + _base_with_parent(AUID_STAR_A) + _wg_body),
        ("DaPerson",
         _hdr(0x12, AUID_PERSON_A)
         + _base_parent_xform(AUID_WORLD_A,
                              tz=1.8)
         + _person_body_a),
    ]
    for name, pkt in chain_a:
        await write_framed(writer, pkt)
        logger.debug(f"[scene]   -> [{label}] atom {name} "
                     f"({len(pkt)}B): {pkt.hex()}")

    _person_auid_int = int.from_bytes(person_auid_atom[:4], "big")
    completion = [
        ("DgEmpire",    await build_scene_dg_empire_0x31(
                            conn,
                            True,
                            player_avatar_id=_person_auid_int,
                            empire_id=0,
                            name_long=name_long,
                            name_short=name_short,
                            capital_name=capital_name,
                            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
                            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
                            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)),
        ("DnDetailType0", build_scene_dn_detail_type(
            type_id=0, name="Human", description="")),
        ("DnRoomType0",   build_scene_dn_room_type(
            room_id=0, name="Hall", description="")),
        ("DataComplete", build_scene_empire_data_complete()),
        ("InitSucceeded", build_scene_init_succeeded(
                            motd=save.motd,
                            autime_usec=0)),
    ]
    for name, pkt in completion:
        await write_framed(writer, pkt)
        logger.debug(f"[scene]   -> [{label}] completion {name} "
                     f"({len(pkt)}B): {pkt[:80].hex()}"
                     f"{'...' if len(pkt) > 80 else ''}")
