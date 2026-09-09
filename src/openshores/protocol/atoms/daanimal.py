from __future__ import annotations

import logging
import struct
import time
from typing import Optional

logger = logging.getLogger(__name__)


OPCODE_DAANIMAL = 0x01

BASE_FLAG_PARENT      = 0x01
BASE_FLAG_TIME_CREATE = 0x02
BASE_FLAG_TIME_MOD    = 0x04
BASE_FLAG_TRANSFORM   = 0x08
BASE_FLAG_EFFECTS     = 0x10
BASE_FLAG_ATOM_BIT_11 = 0x20

CR_FLAG_DNA          = 0x01
CR_FLAG_SIZE         = 0x02
CR_FLAG_HP           = 0x04
CR_FLAG_BODY_PARTS   = 0x08
CR_FLAG_CONSOLE      = 0x10
CR_FLAG_POSE         = 0x20
CR_FLAG_SPECIAL_WPN  = 0x40
CR_FLAG_TURRET       = 0x80

POSE_STANDING = 0x24
POSE_SLEEPING = 0x20
POSE_DIGGING  = 0x16
POSE_SWIMMING = 0x2A
POSE_FLYING   = 0x18

DEFAULT_BODY_PARTS = bytes([0x7F] * 10)


def _now_ms() -> int:
    return int(time.time() * 1000)


def pack_animal_spawn(
    auid: int,
    parent_planet_auid: int,
    dna_bytes: bytes,
    *,
    xyz: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    hp: int = 100,
    max_hp: int = 100,
    stamina: int = 0x7F,
    pose: int = POSE_STANDING,
    sex: int = 0,
    body_parts: Optional[bytes] = None,
    wounds: int = 0,
    head_tilt: float = 0.0,
    timestamp_ms: Optional[int] = None,
    timeCreate_ms: Optional[int] = None,
    timeModified_ms: Optional[int] = None,
    animal_extra: float = 0.0,
) -> bytes:
    if len(dna_bytes) != 24:
        raise ValueError(
            f"dna_bytes must be 24 bytes, got {len(dna_bytes)}")
    if body_parts is None:
        body_parts = DEFAULT_BODY_PARTS
    if len(body_parts) != 10:
        raise ValueError(
            f"body_parts must be 10 bytes, got {len(body_parts)}")
    now = _now_ms()
    ts   = timestamp_ms     if timestamp_ms     is not None else now
    tc   = timeCreate_ms    if timeCreate_ms    is not None else now
    tm   = timeModified_ms  if timeModified_ms  is not None else now

    out = bytearray()
    out.append(OPCODE_DAANIMAL)
    out += struct.pack(">I", auid & 0xFFFFFFFF)
    out += struct.pack(">q", ts & 0xFFFFFFFFFFFFFFFF)

    base_flag = (
        BASE_FLAG_PARENT
        | BASE_FLAG_TIME_CREATE
        | BASE_FLAG_TIME_MOD
        | BASE_FLAG_TRANSFORM
    )
    out.append(base_flag)
    out += struct.pack(">I", parent_planet_auid & 0xFFFFFFFF)
    out += struct.pack(">q", tc & 0xFFFFFFFFFFFFFFFF)
    out += struct.pack(">q", tm & 0xFFFFFFFFFFFFFFFF)
    out += struct.pack(
        ">6f",
        float(xyz[0]), float(xyz[1]), float(xyz[2]),
        float(rotation[0]), float(rotation[1]), float(rotation[2]),
    )

    out.append(0x00)

    creature_flag = (
        CR_FLAG_DNA
        | CR_FLAG_SIZE
        | CR_FLAG_HP
        | CR_FLAG_BODY_PARTS
        | CR_FLAG_POSE
    )
    out.append(creature_flag)

    out.append(0x00)
    out += struct.pack(">I", 24)
    out += dna_bytes

    out += struct.pack(">f", float(head_tilt))

    hp_clamped = max(-30, min(0x7FFF, int(hp)))
    out += struct.pack(">h", hp_clamped)

    out += bytes([pose & 0xFF]) * 10
    out += struct.pack(">i", int(wounds))

    _max_stamina = ((dna_bytes[0] >> 4) & 0x0F) << 4 | 0x0F
    out.append(min(int(stamina) & 0xFF, _max_stamina))

    out.append(0x00)

    out += struct.pack(">f", float(animal_extra))

    return bytes(out)


def pack_animal_update(
    auid: int,
    *,
    hp: Optional[int] = None,
    stamina: Optional[int] = None,
    pose: Optional[int] = None,
    xyz: Optional[tuple[float, float, float]] = None,
    rotation: Optional[tuple[float, float, float]] = None,
    timestamp_ms: Optional[int] = None,
    animal_extra: float = 0.0,
) -> bytes:
    now = _now_ms()
    ts  = timestamp_ms if timestamp_ms is not None else now

    out = bytearray()
    out.append(OPCODE_DAANIMAL)
    out += struct.pack(">I", auid & 0xFFFFFFFF)
    out += struct.pack(">q", ts & 0xFFFFFFFFFFFFFFFF)

    base_flag = 0
    if xyz is not None or rotation is not None:
        base_flag |= BASE_FLAG_TRANSFORM
    out.append(base_flag)
    if base_flag & BASE_FLAG_TRANSFORM:
        x, y, z = xyz if xyz is not None else (0.0, 0.0, 0.0)
        rx, ry, rz = (
            rotation if rotation is not None else (0.0, 0.0, 0.0))
        out += struct.pack(
            ">6f", float(x), float(y), float(z),
            float(rx), float(ry), float(rz))

    out.append(0x00)

    creature_flag = CR_FLAG_POSE
    if hp is not None:
        creature_flag |= CR_FLAG_HP
    if pose is not None:
        creature_flag |= CR_FLAG_BODY_PARTS
    out.append(creature_flag)

    if hp is not None:
        out += struct.pack(">h", max(-30, min(0x7FFF, int(hp))))

    if pose is not None:
        out += bytes([pose & 0xFF]) * 10
        out += struct.pack(">i", 0)

    out.append((stamina if stamina is not None else 0x7F) & 0xFF)

    out.append(0x00)

    out += struct.pack(">f", float(animal_extra))

    return bytes(out)


def _self_test() -> None:
    logger.info("DaAnimal writer self-test")
    from openshores.protocol.dhdna import AuDice, DhDNA  # type: ignore

    dice = AuDice(seed=1494406)
    d = DhDNA()
    d.randomize(dice, phylum=0, sentient=False, tod=2)

    pkt = pack_animal_spawn(
        auid=0xA0000001,
        parent_planet_auid=1494406,
        dna_bytes=d.to_bytes(),
        xyz=(0.0, 0.0, 6_400_000.0),
        rotation=(0.0, 0.0, 0.0),
        hp=100, max_hp=100,
        stamina=0x7F, pose=POSE_STANDING,
    )
    logger.info("Spawn packet: %d bytes", len(pkt))
    logger.info("Spawn packet hex: %s", pkt.hex())
    assert pkt[0] == OPCODE_DAANIMAL
    assert pkt[1:5] == struct.pack(">I", 0xA0000001)
    assert pkt[13] == 0x0f, f"Expected base_flag 0x0f, got 0x{pkt[13]:02x}"

    tail = pkt[-26:]
    head_tilt = struct.unpack(">f", tail[0:4])[0]
    assert head_tilt == 0.0, (
        f"+0x4c4 is DaCreature::TiltHeadTo in RADIANS, not a size. "
        f"Got {head_tilt} = {head_tilt * 57.2957795:.1f} deg of head tilt.")
    assert tail[6:16] == bytes([POSE_STANDING]) * 10, (
        f'+0x4d0 must be the 10-entry POSE array, got {tail[6:16].hex()}.')
    assert tail[16:20] == b"\x00\x00\x00\x00", "+0x45e0 pose parameter"
    assert tail[21] == 0x00, (
        f'+0x490 is the juvenile GROWTH COUNTER and must be 0 (full grown); got 0x{tail[21]:02x}.')
    assert len(pkt) == 115, (
        f"Spawn packet changed length ({len(pkt)}B, was 115B).")

    upd = pack_animal_update(
        auid=0xA0000001,
        xyz=(10.0, 0.0, 6_400_000.0),
        pose=POSE_STANDING,
        stamina=0x7F,
    )
    logger.info("Update packet: %d bytes", len(upd))
    logger.info("Update packet hex: %s", upd.hex())

    logger.info("DaAnimal writer self-test passed.")


if __name__ == "__main__":
    _self_test()
