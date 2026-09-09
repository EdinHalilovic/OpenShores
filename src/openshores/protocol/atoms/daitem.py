from __future__ import annotations

import logging
import struct
import time
from typing import Optional

logger = logging.getLogger(__name__)


OPCODE_DAITEM = 0x11

TYPEID_AUITEM            = 0x01
TYPEID_DESIGN_BUILDING   = 0x02
TYPEID_DESIGN_SPACECRAFT = 0x03
TYPEID_DNA               = 0x04
TYPEID_MISSION           = 0x05
TYPEID_STATE             = 0x06
TYPEID_AMMO              = 0x07
TYPEID_WEAPON            = 0x08
TYPEID_WEAPON_AMMO       = 0x09
TYPEID_GALAXY_LOC        = 0x0A
TYPEID_CONTAINER         = 0x0B
TYPEID_WEAPON_STATE      = 0x0C
TYPEID_OFFICER_LOG       = 0x0D
TYPEID_FLORA_DNA         = 0x0E
TYPEID_GENESIS_DEVICE    = 0x0F
TYPEID_PICTURE           = 0x10
TYPEID_STATE_MESSAGE     = 0x11
TYPEID_BOX               = 0x12
TYPEID_SC_DESIGN         = 0x13
TYPEID_TEU_CONTAINER     = 0x14
TYPEID_MEDIA             = 0x15
TYPEID_STORAGE_MEDIA     = 0x16
TYPEID_BD_DESIGN         = 0x17

BASE_FLAG_PARENT      = 0x01
BASE_FLAG_TIME_CREATE = 0x02
BASE_FLAG_TIME_MOD    = 0x04
BASE_FLAG_TRANSFORM   = 0x08

ITEM_FLAG_AUITEM      = 0x01
ITEM_FLAG_FUSE_BOMB   = 0x40
ITEM_FLAG_OWNED       = 0x80


def _now_ms() -> int:
    return int(time.time() * 1000)


def pack_auitem_body(commodity_id: int = 1) -> bytes:
    return (
        bytes([0x00])
        + struct.pack(">h", commodity_id & 0xFFFF)
        + bytes([0x01])
    )


def pack_floor_item(
    auid: int,
    parent_planet_auid: int,
    *,
    xyz: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    typeid: int = TYPEID_AUITEM,
    auitem_body: Optional[bytes] = None,
    timestamp_ms: Optional[int] = None,
    timeCreate_ms: Optional[int] = None,
    timeModified_ms: Optional[int] = None,
) -> bytes:
    now = _now_ms()
    ts  = timestamp_ms     if timestamp_ms     is not None else now
    tc  = timeCreate_ms    if timeCreate_ms    is not None else now
    tm  = timeModified_ms  if timeModified_ms  is not None else now

    if auitem_body is None:
        if typeid == TYPEID_AUITEM:
            auitem_body = pack_auitem_body()
        else:
            raise ValueError(
                f"Typeid 0x{typeid:02x} requires auitem_body to be passed (there is only a default body for typeid 0x01)")

    out = bytearray()
    out.append(OPCODE_DAITEM)
    out += struct.pack(">I", auid & 0xFFFFFFFF)
    out += struct.pack(">q", ts)

    base_flag = (
        BASE_FLAG_PARENT
        | BASE_FLAG_TIME_CREATE
        | BASE_FLAG_TIME_MOD
        | BASE_FLAG_TRANSFORM
    )
    out.append(base_flag)
    out += struct.pack(">I", parent_planet_auid & 0xFFFFFFFF)
    out += struct.pack(">q", tc)
    out += struct.pack(">q", tm)
    out += struct.pack(
        ">6f",
        float(xyz[0]), float(xyz[1]), float(xyz[2]),
        float(rotation[0]), float(rotation[1]), float(rotation[2]))

    out.append(ITEM_FLAG_AUITEM)
    out.append(typeid & 0xFF)
    out += auitem_body

    return bytes(out)


def _self_test() -> None:
    logger.info("DaItem writer self-test")
    pkt = pack_floor_item(
        auid=0xD0000001,
        parent_planet_auid=1494406,
        xyz=(9200.0, 11440.0, -11500.0))
    logger.info("Floor item packet: %d bytes", len(pkt))
    logger.info("Packet hex: %s", pkt.hex())
    assert pkt[0] == OPCODE_DAITEM
    assert pkt[1:5] == struct.pack(">I", 0xD0000001)
    assert pkt[13] == 0x0F, f"Expected 0x0F, got 0x{pkt[13]:02x}"
    logger.info("DaItem writer self-test passed.")


if __name__ == "__main__":
    _self_test()
