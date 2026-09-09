
from __future__ import annotations

import logging
import struct
import time

import asyncpg
from typing import Optional

from openshores.gameplay.vehicles.persistence import Vehicle
from openshores.gameplay.vehicles.wire import (
    OrdnanceSlot,
    TxOptions,
    _pack_qstring,
    pack_davehicle_update,
)

logger = logging.getLogger(__name__)


OPCODE_DAVEHICLE = 0x1C

BASE_FLAG_PARENT      = 0x01
BASE_FLAG_TIME_CREATE = 0x02
BASE_FLAG_TIME_MOD    = 0x04
BASE_FLAG_TRANSFORM   = 0x08

UNIT_FLAG_NAME_EMPIRE_ROLE = 0x01
UNIT_FLAG_CONDITIONS       = 0x02
UNIT_FLAG_VELOCITY         = 0x04


def _now_ms() -> int:
    return int(time.time() * 1000)


def _pack_daunit_body(name: str, empire_id: int, arena_team: int) -> bytes:
    out = bytearray()
    out.append(UNIT_FLAG_NAME_EMPIRE_ROLE & 0xFF)
    out += _pack_qstring(name or "")
    _emp = int(empire_id) & 0xFFFFFFFF
    if _emp >= 0x80000000:
        _emp -= 0x100000000
    out += struct.pack(">i", _emp)
    out.append(int(arena_team) & 0xFF)
    return bytes(out)


def build_da_vehicle_atom(
    v: Vehicle,
    *,
    timestamp_ms: Optional[int] = None,
    time_create_ms: Optional[int] = None,
    time_modified_ms: Optional[int] = None,
    tx_options: Optional[TxOptions] = None,
) -> bytes:
    now = _now_ms()
    ts  = timestamp_ms if timestamp_ms is not None else now
    tc  = time_create_ms if time_create_ms is not None else (v.timeCreate or now)
    tm  = time_modified_ms if time_modified_ms is not None else (v.timeModified or now)

    out = bytearray()
    out.append(OPCODE_DAVEHICLE)
    out += struct.pack(">I", int(v.id) & 0xFFFFFFFF)
    out += struct.pack(">q", int(ts))

    base_flag = (BASE_FLAG_PARENT | BASE_FLAG_TIME_CREATE
                 | BASE_FLAG_TIME_MOD | BASE_FLAG_TRANSFORM)
    out.append(base_flag)
    out += struct.pack(">I", int(v.idp) & 0xFFFFFFFF)
    out += struct.pack(">q", int(tc))
    out += struct.pack(">q", int(tm))
    out += struct.pack(
        ">6f",
        float(v.locX), float(v.locY), float(v.locZ),
        float(v.rotX), float(v.rotY), float(v.rotZ),
    )

    out += _pack_daunit_body(v.name, v.allegiance, v.arenaTeam)

    if tx_options is None:
        tx_options = TxOptions(baseline_ms=0)
    out += pack_davehicle_update(v, options=tx_options)

    return bytes(out)


def _pack_davehicle_state_for_update(v) -> bytes:
    from openshores.gameplay.vehicles.wire import Flags1, _clamp_i8, encode_flags2
    flags1 = 0
    if (v.throttle or v.throttleLateral or v.throttleLong
            or v.throttleVertical):
        flags1 |= Flags1.THROTTLE
    if v.vecX != 0.0 or v.vecY != 0.0 or v.vecZ != 0.0:
        flags1 |= Flags1.VELOCITY
    flags1 |= Flags1.HP
    flags2 = encode_flags2(int(v.switches), int(v.actBits))
    out = bytearray()
    out += struct.pack(">H", flags1)
    out.append(flags2 & 0xFF)
    if flags1 & Flags1.THROTTLE:
        out += struct.pack(">b", _clamp_i8(int(v.throttle)))
        out += struct.pack(">b", _clamp_i8(int(v.throttleLateral)))
        out += struct.pack(">b", _clamp_i8(int(v.throttleLong)))
        out += struct.pack(">b", _clamp_i8(int(v.throttleVertical)))
    if flags1 & Flags1.VELOCITY:
        out += struct.pack(">fff", float(v.vecX), float(v.vecY), float(v.vecZ))
    if flags1 & Flags1.HP:
        out += struct.pack(">h", max(0, min(0x7fff, int(v.hp))))
    return bytes(out)


def build_da_vehicle_keepalive(vehicle_auid_or_v,
                               *,
                               timestamp_ms: Optional[int] = None) -> bytes:
    from openshores.gameplay.vehicles.wire import encode_flags2
    ts = timestamp_ms if timestamp_ms is not None else _now_ms()
    if hasattr(vehicle_auid_or_v, "id"):
        auid = int(vehicle_auid_or_v.id) & 0xFFFFFFFF
        flags2 = encode_flags2(int(vehicle_auid_or_v.switches),
                               int(vehicle_auid_or_v.actBits)) & 0xFF
    else:
        auid = int(vehicle_auid_or_v) & 0xFFFFFFFF
        flags2 = 0
    return (
        bytes([OPCODE_DAVEHICLE])
        + struct.pack(">I", auid)
        + struct.pack(">q", int(ts))
        + bytes([0x00])
        + bytes([0x00])
        + struct.pack(">H", 0)
        + bytes([flags2 & 0xFF])
    )


def build_da_vehicle_update(v: Vehicle,
                              *,
                              timestamp_ms: Optional[int] = None) -> bytes:
    from openshores.gameplay.vehicles.wire import Flags1, compute_flags1, encode_flags2
    ts = timestamp_ms if timestamp_ms is not None else _now_ms()
    out = bytearray()
    out.append(OPCODE_DAVEHICLE)
    out += struct.pack(">I", int(v.id) & 0xFFFFFFFF)
    out += struct.pack(">q", int(ts))
    out.append(0x08)
    out += struct.pack(
        ">6f",
        float(v.locX), float(v.locY), float(v.locZ),
        float(v.rotX), float(v.rotY), float(v.rotZ),
    )
    out.append(0x00)
    out += _pack_davehicle_state_for_update(v)
    return bytes(out)


async def build_scene_atoms(parent_id: int, *,
                           conn: asyncpg.Connection) -> list:
    from openshores.gameplay.vehicles.persistence import load_vehicles_by_parent
    out = []
    for v in await load_vehicles_by_parent(conn, int(parent_id)):
        try:
            pkt = build_da_vehicle_atom(v)
            label = f"DaVehicle/{v.name or hex(v.id)}/cid{v.cid:#x}"
            out.append((label, pkt))
        except Exception as exc:
            logger.warning(
                "Vehicle 0x%x will not appear in the scene: %r",
                v.id, exc)
    return out


def _selftest() -> None:
    from openshores.gameplay.vehicles.vehicle_constants import VehicleType

    v = Vehicle(
        id=0x70000001, idp=0xCAFEBABE,
        locX=100.0, locY=200.0, locZ=5.0,
        rotX=0.1, rotY=0.2, rotZ=0.3,
        name="Test Tank",
        allegiance=42, arenaTeam=1,
        cid=VehicleType.TANK,
        hp=150, qual=5, fuel=99,
    )
    pkt = build_da_vehicle_atom(v, timestamp_ms=1_000_000,
                                time_create_ms=900_000,
                                time_modified_ms=950_000)
    assert pkt[0] == OPCODE_DAVEHICLE
    assert pkt[1:5] == struct.pack(">I", 0x70000001)
    assert pkt[5:13] == struct.pack(">q", 1_000_000)
    assert pkt[13] == 0x0F, f"base_flag should be 0x0F, got 0x{pkt[13]:02x}"
    assert pkt[14:18] == struct.pack(">I", 0xCAFEBABE)
    assert pkt[18:26] == struct.pack(">q", 900_000)
    assert pkt[26:34] == struct.pack(">q", 950_000)
    expected_xform = struct.pack(">6f", 100.0, 200.0, 5.0, 0.1, 0.2, 0.3)
    assert pkt[34:58] == expected_xform
    assert pkt[58] == 0x01, f"unit_flag should be 0x01, got 0x{pkt[58]:02x}"
    name_len = struct.unpack(">i", pkt[59:63])[0]
    expected_name = "Test Tank".encode("utf-16-be")
    assert name_len == len(expected_name)
    assert pkt[63:63 + name_len] == expected_name
    off = 63 + name_len
    assert pkt[off:off+4] == struct.pack(">i", 42)
    off += 4
    assert pkt[off] == 1
    off += 1
    flags1 = struct.unpack(">H", pkt[off:off+2])[0]
    assert (flags1 & 0x001) != 0, f"flags1 should have TYPE_QUALITY: 0x{flags1:03x}"

    logger.info("Built DaVehicle atom: %d bytes", len(pkt))
    logger.info("flags1 = 0x%03x", flags1)

    ka = build_da_vehicle_keepalive(0x70000001, timestamp_ms=0x1122334455667788)
    assert len(ka) == 18, f"Keepalive should be 18B, got {len(ka)}"
    assert ka[0] == 0x1C
    assert ka[1:5] == struct.pack(">I", 0x70000001)
    assert ka[5:13] == bytes.fromhex("1122334455667788")
    assert ka[13:18] == bytes(5), "Keepalive trailer must be zeros"
    logger.info("Built keepalive: %d bytes (%s)", len(ka), ka.hex())


if __name__ == "__main__":
    logger.info("DaVehicle atom packet self-test")
    _selftest()
    logger.info("DaVehicle atom packet self-test passed.")
