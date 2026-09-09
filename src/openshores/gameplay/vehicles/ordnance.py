
from __future__ import annotations

import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from openshores.core.logging import get_logger

from .persistence import Vehicle
from .vehicle_constants import ORDNANCE_COOLDOWN_MS
from .wire import OrdnanceSlot

logger = get_logger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class Ordnance:
    ammo_commodity_id: int = 0
    round_count: int = 0
    quality: int = 0
    last_fire_ms: int = 0
    item_type_id: int = 0


def can_fire(slot: Ordnance, now_ms: Optional[int] = None) -> bool:
    if slot.ammo_commodity_id == 0:
        return False
    if slot.round_count <= 0:
        return False
    if slot.last_fire_ms == 0:
        return True
    cooldown = ORDNANCE_COOLDOWN_MS.get(slot.ammo_commodity_id, 0)
    if cooldown == 0:
        return True
    if now_ms is None:
        now_ms = _now_ms()
    return (now_ms - slot.last_fire_ms) >= cooldown


def fired(slot: Ordnance, now_ms: Optional[int] = None) -> None:
    slot.last_fire_ms = now_ms if now_ms is not None else _now_ms()
    if slot.round_count > 0:
        slot.round_count -= 1


def reload(slot: Ordnance, ammo_commodity_id: int, count: int,
           quality: int = 1, item_type_id: int = 0x07) -> None:
    slot.ammo_commodity_id = int(ammo_commodity_id)
    slot.round_count = int(count)
    slot.quality = int(quality) & 0xFFFF
    slot.last_fire_ms = 0
    slot.item_type_id = int(item_type_id) & 0xFF


def time_until_can_fire_ms(slot: Ordnance, now_ms: Optional[int] = None) -> int:
    if slot.ammo_commodity_id == 0 or slot.round_count <= 0:
        return -1
    if slot.last_fire_ms == 0:
        return 0
    cooldown = ORDNANCE_COOLDOWN_MS.get(slot.ammo_commodity_id, 0)
    if cooldown == 0:
        return 0
    if now_ms is None:
        now_ms = _now_ms()
    elapsed = now_ms - slot.last_fire_ms
    return max(0, cooldown - elapsed)


@dataclass
class TurretLoadout:
    slot0: Ordnance = field(default_factory=Ordnance)
    slot1: Ordnance = field(default_factory=Ordnance)
    slot2: Ordnance = field(default_factory=Ordnance)

    def get(self, idx: int) -> Ordnance:
        if idx == 0: return self.slot0
        if idx == 1: return self.slot1
        if idx == 2: return self.slot2
        raise IndexError(f"Turret idx out of range: {idx}")

    def all_slots(self):
        return (self.slot0, self.slot1, self.slot2)


_loadouts: dict[int, TurretLoadout] = {}
_loadouts_lock = threading.Lock()


def get_loadout(vehicle_id: int) -> TurretLoadout:
    vid = int(vehicle_id)
    with _loadouts_lock:
        lo = _loadouts.get(vid)
        if lo is None:
            lo = TurretLoadout()
            _loadouts[vid] = lo
        return lo


def drop_loadout(vehicle_id: int) -> bool:
    with _loadouts_lock:
        return _loadouts.pop(int(vehicle_id), None) is not None


def clear_loadout_registry() -> None:
    with _loadouts_lock:
        _loadouts.clear()


def pack_ordnance(slot: Ordnance) -> OrdnanceSlot:
    if slot.ammo_commodity_id == 0:
        return OrdnanceSlot(raw_bytes=b"\x00" * 24)
    body = struct.pack(
        ">iHHIq",
        slot.item_type_id & 0xFFFFFFFF,
        slot.ammo_commodity_id & 0xFFFF,
        slot.quality & 0xFFFF,
        slot.round_count & 0xFFFFFFFF,
        slot.last_fire_ms & 0xFFFFFFFFFFFFFFFF,
    )
    body = body + b"\x00" * 4
    return OrdnanceSlot(
        raw_bytes=body,
        item_type_id=slot.item_type_id,
        ammo_commodity=slot.ammo_commodity_id,
        quality=slot.quality,
        last_fire_ms=slot.last_fire_ms,
    )


def unpack_ordnance(raw: bytes) -> Ordnance:
    if not raw or len(raw) < 20 or raw[:4] == b"\x00\x00\x00\x00":
        return Ordnance()
    type_id, commodity, quality, round_count, last_fire = struct.unpack_from(
        ">iHHIq", raw, 0,
    )
    if commodity == 0:
        return Ordnance()
    return Ordnance(
        ammo_commodity_id=commodity,
        round_count=round_count,
        quality=quality,
        last_fire_ms=last_fire,
        item_type_id=type_id,
    )


def _selftest() -> None:
    o = Ordnance()
    assert not can_fire(o)

    reload(o, ammo_commodity_id=0x44, count=10, quality=5)
    assert o.ammo_commodity_id == 0x44
    assert o.round_count == 10
    assert o.quality == 5
    assert o.last_fire_ms == 0
    assert can_fire(o, now_ms=1_000_000)

    fired(o, now_ms=1_000_000)
    assert o.round_count == 9
    assert o.last_fire_ms == 1_000_000
    assert not can_fire(o, now_ms=1_000_500)
    assert not can_fire(o, now_ms=1_000_799)
    assert can_fire(o, now_ms=1_000_800)
    assert can_fire(o, now_ms=1_001_000)

    assert time_until_can_fire_ms(o, now_ms=1_000_200) == 600
    assert time_until_can_fire_ms(o, now_ms=1_000_799) == 1
    assert time_until_can_fire_ms(o, now_ms=1_001_000) == 0

    fast = Ordnance()
    reload(fast, ammo_commodity_id=0x0B, count=5)
    fired(fast, now_ms=5_000)
    assert not can_fire(fast, now_ms=5_300)
    assert can_fire(fast, now_ms=5_332)

    heavy = Ordnance()
    reload(heavy, ammo_commodity_id=0x38, count=3)
    fired(heavy, now_ms=10_000)
    assert not can_fire(heavy, now_ms=10_999)
    assert can_fire(heavy, now_ms=11_000)

    unknown = Ordnance()
    reload(unknown, ammo_commodity_id=0xABCD, count=2)
    fired(unknown, now_ms=20_000)
    assert can_fire(unknown, now_ms=20_001)

    empty = Ordnance()
    reload(empty, ammo_commodity_id=0x44, count=1)
    fired(empty, now_ms=30_000)
    assert empty.round_count == 0
    assert not can_fire(empty, now_ms=30_999)
    assert not can_fire(empty, now_ms=999_999_999)

    clear_loadout_registry()
    lo = get_loadout(0x12345)
    assert lo is get_loadout(0x12345)
    reload(lo.slot0, 0x43, 50)
    reload(lo.slot1, 0x129, 100)
    assert lo.slot0.ammo_commodity_id == 0x43
    assert lo.slot1.round_count == 100
    assert lo.slot2.ammo_commodity_id == 0
    drop_loadout(0x12345)
    lo2 = get_loadout(0x12345)
    assert lo2.slot0.ammo_commodity_id == 0

    src = Ordnance(ammo_commodity_id=0x44, round_count=9, quality=5,
                   last_fire_ms=1_234_567_890, item_type_id=0x07)
    packed = pack_ordnance(src)
    assert len(packed.raw_bytes) == 24
    rebuilt = unpack_ordnance(packed.raw_bytes)
    assert rebuilt.ammo_commodity_id == 0x44
    assert rebuilt.round_count == 9
    assert rebuilt.quality == 5
    assert rebuilt.last_fire_ms == 1_234_567_890
    assert rebuilt.item_type_id == 0x07

    empty_packed = pack_ordnance(Ordnance())
    assert empty_packed.raw_bytes == b"\x00" * 24
    rebuilt_empty = unpack_ordnance(b"\x00" * 24)
    assert rebuilt_empty.ammo_commodity_id == 0

    clear_loadout_registry()


if __name__ == "__main__":
    logger.info("vehicles.ordnance self-test starting")
    _selftest()
    logger.info("vehicles.ordnance self-test passed")
