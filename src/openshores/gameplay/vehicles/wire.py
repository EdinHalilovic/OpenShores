
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from typing import Callable, Optional

from .persistence import Vehicle

logger = logging.getLogger(__name__)


class Flags1:
    TYPE_QUALITY     = 0x001
    THROTTLE         = 0x002
    VELOCITY         = 0x004
    FUEL             = 0x008
    HP               = 0x010
    TURRET0          = 0x020
    TURRET1          = 0x040
    TURRET2          = 0x080
    OWNER_NAME       = 0x100
    ACTIVE_TURRET    = 0x200
    LAUNCH_STATE     = 0x400


class Flags2:
    SWITCHES_MASK    = 0x1F
    TURRET0_DIRTY    = 0x20
    TURRET1_DIRTY    = 0x40
    TURRET2_DIRTY    = 0x80


class ActBits:
    TURRET0_DIRTY    = 0x40000
    TURRET1_DIRTY    = 0x80000
    TURRET2_DIRTY    = 0x100000


def _pack_qstring(s: Optional[str]) -> bytes:
    if s is None:
        return b"\xff\xff\xff\xff"
    if not s:
        return b"\x00\x00\x00\x00"
    chars = s.encode("utf-16-be")
    return struct.pack(">I", len(chars)) + chars


def _unpack_qstring(buf: bytes, offset: int) -> tuple[Optional[str], int]:
    (length,) = struct.unpack_from(">i", buf, offset)
    offset += 4
    if length == -1:
        return None, offset
    if length == 0:
        return "", offset
    chars = buf[offset:offset + length].decode("utf-16-be")
    return chars, offset + length


def _pack_auid(value: int) -> bytes:
    return struct.pack(">I", int(value) & 0xFFFFFFFF)


def _unpack_auid(buf: bytes, offset: int) -> tuple[int, int]:
    (v,) = struct.unpack_from(">I", buf, offset)
    return v, offset + 4


_EMPTY_ORDNANCE_SLOT: bytes = b"\x00" * 24


@dataclass
class OrdnanceSlot:
    raw_bytes: Optional[bytes] = None
    item_type_id: int = 0
    ammo_commodity: int = 0
    quality: int = 0
    last_fire_ms: int = 0


def pack_ordnance_slot(slot: Optional[OrdnanceSlot]) -> bytes:
    if slot is None or slot.raw_bytes is None:
        return _EMPTY_ORDNANCE_SLOT
    raw = slot.raw_bytes
    if len(raw) != 24:
        logger.warning('Ordnance slot serialised to %d bytes, not 24.', len(raw))
        if len(raw) < 24:
            raw = raw + b"\x00" * (24 - len(raw))
        else:
            raw = raw[:24]
    return raw


def unpack_ordnance_slot(buf: bytes, offset: int) -> tuple[OrdnanceSlot, int]:
    raw = buf[offset:offset + 24]
    return OrdnanceSlot(raw_bytes=raw), offset + 24


def encode_flags2(switches: int, act_bits: int) -> int:
    f2 = switches & Flags2.SWITCHES_MASK
    if act_bits & ActBits.TURRET0_DIRTY:
        f2 |= Flags2.TURRET0_DIRTY
    if act_bits & ActBits.TURRET1_DIRTY:
        f2 |= Flags2.TURRET1_DIRTY
    if act_bits & ActBits.TURRET2_DIRTY:
        f2 |= Flags2.TURRET2_DIRTY
    return f2 & 0xFF


def decode_flags2(flags2: int) -> tuple[int, int]:
    new_switches = flags2 & Flags2.SWITCHES_MASK
    turret_mask = 0
    if flags2 & Flags2.TURRET0_DIRTY:
        turret_mask |= ActBits.TURRET0_DIRTY
    if flags2 & Flags2.TURRET1_DIRTY:
        turret_mask |= ActBits.TURRET1_DIRTY
    if flags2 & Flags2.TURRET2_DIRTY:
        turret_mask |= ActBits.TURRET2_DIRTY
    return new_switches, turret_mask


def compute_flags1(
    v: Vehicle,
    baseline_ms: int = 0,
    fuel_ts: Optional[int] = None,
    hp_ts: Optional[int] = None,
    turret_ts: tuple[int, int, int] = (0, 0, 0),
    owner_ts: int = 0,
    launch_ts: Optional[int] = None,
    has_force_transform: bool = False,
) -> int:
    flags = 0

    if baseline_ms == 0:
        flags |= Flags1.TYPE_QUALITY

    if (baseline_ms == 0 or
        v.throttle != 0 or v.throttleLateral != 0 or
        v.throttleLong != 0 or v.throttleVertical != 0):
        flags |= Flags1.THROTTLE

    if v.vecX != 0.0 or v.vecY != 0.0 or v.vecZ != 0.0:
        flags |= Flags1.VELOCITY

    def _ts_gate(ts: Optional[int]) -> bool:
        if baseline_ms == 0 or ts is None:
            return True
        return baseline_ms <= ts

    if _ts_gate(fuel_ts):
        flags |= Flags1.FUEL
    if _ts_gate(hp_ts):
        flags |= Flags1.HP
    if _ts_gate(turret_ts[0]):
        flags |= Flags1.TURRET0
    if _ts_gate(turret_ts[1]):
        flags |= Flags1.TURRET1
    if _ts_gate(turret_ts[2]):
        flags |= Flags1.TURRET2
    if _ts_gate(owner_ts):
        flags |= Flags1.OWNER_NAME

    if v.actBits & 0x200000:
        flags |= Flags1.ACTIVE_TURRET

    if has_force_transform or _ts_gate(launch_ts):
        if has_force_transform or launch_ts is not None:
            flags |= Flags1.LAUNCH_STATE

    return flags & 0x7FF


@dataclass
class TxOptions:
    baseline_ms: int = 0
    fuel_ts: Optional[int] = None
    hp_ts: Optional[int] = None
    turret_ts: tuple[int, int, int] = (0, 0, 0)
    owner_ts: int = 0
    launch_ts: Optional[int] = None
    has_force_transform: bool = False
    turret_slots: tuple[Optional[OrdnanceSlot],
                        Optional[OrdnanceSlot],
                        Optional[OrdnanceSlot]] = (None, None, None)
    launch_start_ms: int = 0
    launch_vector: tuple[float, float, float] = (0.0, 0.0, 0.0)
    launch_counter: int = 0
    launching_vessel: int = 0
    launch_progress: float = 0.0


def pack_davehicle_update(
    v: Vehicle,
    options: Optional[TxOptions] = None,
) -> bytes:
    if options is None:
        options = TxOptions()

    flags1 = compute_flags1(
        v,
        baseline_ms=options.baseline_ms,
        fuel_ts=options.fuel_ts,
        hp_ts=options.hp_ts,
        turret_ts=options.turret_ts,
        owner_ts=options.owner_ts,
        launch_ts=options.launch_ts,
        has_force_transform=options.has_force_transform,
    )
    flags2 = encode_flags2(v.switches, v.actBits)

    out = bytearray()
    out += struct.pack(">H", flags1)
    out.append(flags2)

    if flags1 & Flags1.TYPE_QUALITY:
        out += struct.pack(">h", v.cid & 0xFFFF)
        out += struct.pack(">b", _clamp_i8(v.qual))

    if flags1 & Flags1.THROTTLE:
        out += struct.pack(">b", _clamp_i8(v.throttle))
        out += struct.pack(">b", _clamp_i8(v.throttleLateral))
        out += struct.pack(">b", _clamp_i8(v.throttleLong))
        out += struct.pack(">b", _clamp_i8(v.throttleVertical))

    if flags1 & Flags1.VELOCITY:
        out += struct.pack(">fff", float(v.vecX), float(v.vecY), float(v.vecZ))

    if flags1 & Flags1.FUEL:
        out += struct.pack(">b", _clamp_i8(v.fuel))

    if flags1 & Flags1.HP:
        out += struct.pack(">h", _clamp_i16(v.hp))

    if flags1 & Flags1.TURRET0:
        out += pack_ordnance_slot(options.turret_slots[0])
    if flags1 & Flags1.TURRET1:
        out += pack_ordnance_slot(options.turret_slots[1])
    if flags1 & Flags1.TURRET2:
        out += pack_ordnance_slot(options.turret_slots[2])

    if flags1 & Flags1.OWNER_NAME:
        out += _pack_auid(v.motherShip)
        out += _pack_qstring(v.motherShipName)

    if flags1 & Flags1.LAUNCH_STATE:
        out += struct.pack(">q", int(options.launch_start_ms))
        out += struct.pack(">ddd",
                           float(options.launch_vector[0]),
                           float(options.launch_vector[1]),
                           float(options.launch_vector[2]))
        out += struct.pack(">h", _clamp_i16(options.launch_counter))
        out += _pack_auid(options.launching_vessel)
        out += struct.pack(">f", float(options.launch_progress))

    return bytes(out)


@dataclass
class RxResult:
    flags1: int
    flags2: int
    bytes_consumed: int
    has_force_transform_hint: bool
    turret_dirty_mask: int
    launch_start_ms: int = 0
    launch_vector: tuple[float, float, float] = (0.0, 0.0, 0.0)
    launch_counter: int = 0
    launching_vessel: int = 0
    launch_progress: float = 0.0
    turret_slots: tuple[Optional[OrdnanceSlot],
                        Optional[OrdnanceSlot],
                        Optional[OrdnanceSlot]] = (None, None, None)


def unpack_davehicle_update(buf: bytes, v: Vehicle, offset: int = 0) -> RxResult:
    start = offset
    (flags1,) = struct.unpack_from(">H", buf, offset)
    offset += 2
    flags2 = buf[offset]
    offset += 1

    new_switches, turret_mask = decode_flags2(flags2)
    v.switches = (v.switches & ~Flags2.SWITCHES_MASK) | new_switches
    v.actBits = v.actBits | turret_mask

    if flags1 & Flags1.TYPE_QUALITY:
        (cid,) = struct.unpack_from(">h", buf, offset)
        offset += 2
        (qual,) = struct.unpack_from(">b", buf, offset)
        offset += 1
        v.cid = cid & 0xFFFF
        v.qual = qual if qual != 0 else 1

    if flags1 & Flags1.THROTTLE:
        v.throttle         = struct.unpack_from(">b", buf, offset)[0]; offset += 1
        v.throttleLateral  = struct.unpack_from(">b", buf, offset)[0]; offset += 1
        v.throttleLong     = struct.unpack_from(">b", buf, offset)[0]; offset += 1
        v.throttleVertical = struct.unpack_from(">b", buf, offset)[0]; offset += 1

    if flags1 & Flags1.VELOCITY:
        vx, vy, vz = struct.unpack_from(">fff", buf, offset)
        offset += 12
        v.vecX, v.vecY, v.vecZ = float(vx), float(vy), float(vz)

    if flags1 & Flags1.FUEL:
        (fuel,) = struct.unpack_from(">b", buf, offset)
        offset += 1
        v.fuel = fuel & 0xFF

    if flags1 & Flags1.HP:
        (hp,) = struct.unpack_from(">h", buf, offset)
        offset += 2
        v.hp = hp & 0xFFFF

    slots: list[Optional[OrdnanceSlot]] = [None, None, None]
    for i, bit in enumerate((Flags1.TURRET0, Flags1.TURRET1, Flags1.TURRET2)):
        if flags1 & bit:
            slot, offset = unpack_ordnance_slot(buf, offset)
            slots[i] = slot

    if flags1 & Flags1.OWNER_NAME:
        v.motherShip, offset = _unpack_auid(buf, offset)
        name, offset = _unpack_qstring(buf, offset)
        v.motherShipName = name if name is not None else ""

    has_ft_hint = False
    launch_start_ms = 0
    launch_vec = (0.0, 0.0, 0.0)
    launch_counter = 0
    launching_vessel = 0
    launch_progress = 0.0
    if flags1 & Flags1.LAUNCH_STATE:
        has_ft_hint = True
        (launch_start_ms,) = struct.unpack_from(">q", buf, offset); offset += 8
        lvx, lvy, lvz = struct.unpack_from(">ddd", buf, offset); offset += 24
        launch_vec = (lvx, lvy, lvz)
        (launch_counter,) = struct.unpack_from(">h", buf, offset); offset += 2
        launching_vessel, offset = _unpack_auid(buf, offset)
        (launch_progress,) = struct.unpack_from(">f", buf, offset); offset += 4

    return RxResult(
        flags1=flags1,
        flags2=flags2,
        bytes_consumed=offset - start,
        has_force_transform_hint=has_ft_hint,
        turret_dirty_mask=turret_mask,
        launch_start_ms=launch_start_ms,
        launch_vector=launch_vec,
        launch_counter=launch_counter,
        launching_vessel=launching_vessel,
        launch_progress=launch_progress,
        turret_slots=tuple(slots),  # type: ignore[arg-type]
    )


def _clamp_i8(x) -> int:
    x = int(x)
    if x > 127: return 127
    if x < -128: return -128
    return x


def _clamp_i16(x) -> int:
    x = int(x)
    if x > 32767: return 32767
    if x < -32768: return -32768
    return x


def _selftest_roundtrip() -> None:
    from .vehicle_constants import VehicleType

    original = Vehicle(
        id=0x70_00_01_00,
        idp=0xCAFEBABE,
        locX=10.0, locY=20.0, locZ=5.0,
        rotX=0.1, rotY=0.2, rotZ=0.3,
        name="Test Tank",
        allegiance=42,
        arenaTeam=1,
        cid=VehicleType.TANK,
        actBits=ActBits.TURRET0_DIRTY | ActBits.TURRET2_DIRTY,
        atRest=False,
        vecX=1.5, vecY=-0.5, vecZ=0.0,
        throttle=5, throttleLateral=-2, throttleLong=3, throttleVertical=-1,
        switches=0x1F,
        fuel=99,
        hp=46,
        qual=7,
        motherShip=0x00ABCDEF,
        motherShipName="Big Ship",
    )

    body = pack_davehicle_update(original)
    assert isinstance(body, bytes) and len(body) > 0

    target = Vehicle(id=original.id, cid=0, hp=0)
    result = unpack_davehicle_update(body, target)
    assert result.bytes_consumed == len(body), (
        f"Consumed {result.bytes_consumed} of {len(body)}"
    )

    assert target.cid == original.cid
    assert target.qual == original.qual
    assert target.throttle == original.throttle
    assert target.throttleLateral == original.throttleLateral
    assert target.throttleLong == original.throttleLong
    assert target.throttleVertical == original.throttleVertical
    assert abs(target.vecX - original.vecX) < 1e-6
    assert abs(target.vecY - original.vecY) < 1e-6
    assert abs(target.vecZ - original.vecZ) < 1e-6
    assert target.fuel == original.fuel
    assert target.hp == original.hp
    assert target.motherShip == original.motherShip
    assert target.motherShipName == original.motherShipName
    assert (target.switches & Flags2.SWITCHES_MASK) == (original.switches & Flags2.SWITCHES_MASK)
    expected_turret_dirty = original.actBits & (
        ActBits.TURRET0_DIRTY | ActBits.TURRET1_DIRTY | ActBits.TURRET2_DIRTY
    )
    assert (target.actBits & expected_turret_dirty) == expected_turret_dirty

    quiet = Vehicle(id=0x70_00_02_00, cid=VehicleType.HELICOPTER, hp=10, qual=1,
                    name="", switches=0)
    body2 = pack_davehicle_update(quiet, TxOptions(baseline_ms=0))
    target2 = Vehicle(id=quiet.id, cid=0, hp=0,
                      vecX=999.0, vecY=999.0, vecZ=999.0,
                      throttle=99, throttleLateral=99,
                      throttleLong=99, throttleVertical=99)
    res2 = unpack_davehicle_update(body2, target2)
    assert target2.throttle == 0 and target2.throttleLateral == 0
    assert target2.throttleLong == 0 and target2.throttleVertical == 0
    assert target2.vecX == 0.0 and target2.vecY == 0.0 and target2.vecZ == 0.0
    zero_qual = Vehicle(id=0x70_00_03_00, cid=VehicleType.JET, hp=10, qual=0,
                        name="")
    body3 = pack_davehicle_update(zero_qual)
    target3 = Vehicle(id=zero_qual.id, cid=0, hp=0)
    unpack_davehicle_update(body3, target3)
    assert target3.qual == 1, f"qual=0 must be promoted to 1 by Rx, got {target3.qual}"

    with_launch = Vehicle(id=0x70_00_04_00, cid=VehicleType.SHUTTLE,
                          hp=20, qual=3, name="Launcher", motherShipName="")
    body4 = pack_davehicle_update(
        with_launch,
        TxOptions(
            launch_ts=1_000,
            has_force_transform=True,
            launch_start_ms=123456789,
            launch_vector=(1.0, 2.0, 3.0),
            launch_counter=42,
            launching_vessel=0x00ABCDEF,
            launch_progress=0.75,
        ),
    )
    target4 = Vehicle(id=with_launch.id, cid=0, hp=0)
    res4 = unpack_davehicle_update(body4, target4)
    assert res4.flags1 & Flags1.LAUNCH_STATE
    assert res4.launch_start_ms == 123456789
    assert res4.launch_vector == (1.0, 2.0, 3.0)
    assert res4.launch_counter == 42
    assert res4.launching_vessel == 0x00ABCDEF
    assert abs(res4.launch_progress - 0.75) < 1e-6

    none_name = Vehicle(id=0x70_00_05_00, cid=VehicleType.TANK,
                        hp=5, qual=1, name="", motherShipName="")
    out_none = pack_davehicle_update(none_name)
    assert b"\x00\x00\x00\x00" in out_none, (
        "Empty motherShipName should pack as length-0 QString"
    )

    raw0 = b"\x01" + b"\x00" * 23
    raw1 = b"\x02" + b"\x11" * 23
    raw2 = b"\x03" + b"\x22" * 23
    slots = (
        OrdnanceSlot(raw_bytes=raw0),
        OrdnanceSlot(raw_bytes=raw1),
        OrdnanceSlot(raw_bytes=raw2),
    )
    body5 = pack_davehicle_update(original, TxOptions(turret_slots=slots))
    target5 = Vehicle(id=original.id, cid=0, hp=0)
    res5 = unpack_davehicle_update(body5, target5)
    assert res5.turret_slots[0].raw_bytes == raw0
    assert res5.turret_slots[1].raw_bytes == raw1
    assert res5.turret_slots[2].raw_bytes == raw2


if __name__ == "__main__":
    _selftest_roundtrip()
    logger.info("DaVehicle wire self-test passed.")
