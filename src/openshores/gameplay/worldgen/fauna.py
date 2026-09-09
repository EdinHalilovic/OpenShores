
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from openshores.protocol.qt_blob import qcompress, quncompress
from openshores.protocol.rng import AuDice


DHDNA_W3_TABLE = (0, 0, 0, 0, 1, 1, 1, 2, 2, 3)

DHDNA_PHYLUM_SIDES = 25

DHDNA_RANDOMIZE_STEPS = 63
DHDNA_RANDOMIZE_STEPS_NO_FLAG = 62


def _trunc_div2(v: int) -> int:
    return -((-v) >> 1) if v < 0 else v >> 1


def randomize(words: List[int], size_mod: int, sentient: bool, tod: int,
              dice: AuDice, roll_low3: bool = True) -> List[int]:
    w = words

    def put(idx: int, shift: int, bits: int, val: int) -> None:
        mask = ((1 << bits) - 1) << shift
        w[idx] = (w[idx] & ~mask & 0xFFFFFFFF) | ((val << shift) & mask)

    def r(sides: int) -> int:
        return dice.roll(1, sides, -1)

    v = dice.roll(2, 31, size_mod - 31)
    hi5 = abs(v)
    if hi5 > 31:
        hi5 = 31

    phylum = dice.roll(1, DHDNA_PHYLUM_SIDES, -1)
    pmod = phylum - 1

    def p() -> int:
        return dice.roll(1, 8, pmod)

    put(0, 0, 4, r(16))
    put(0, 4, 4, r(16))
    put(0, 8, 2, r(4))
    clamped = dice.roll(1, 4, _trunc_div2(size_mod) - 1)
    clamped = 0 if clamped < 0 else (3 if clamped > 3 else clamped)
    put(0, 10, 2, clamped)
    put(0, 12, 4, r(16))
    put(0, 16, 3, r(8 if sentient else 2))
    put(0, 19, 5, p())
    put(0, 24, 3, r(8))
    put(0, 27, 5, p())

    put(1, 0, 2, r(4))
    put(1, 2, 2, r(4))
    put(1, 4, 2, r(4))
    put(1, 6, 2, r(4))
    put(1, 8, 1, r(2))
    put(1, 9, 1, 1 if dice.roll(1, 100) > 0x5F else 0)
    put(1, 10, 1, 1 if dice.roll(1, 5) == 1 else 0)
    put(1, 12, 1, r(2))
    put(1, 11, 1, r(2))
    put(1, 13, 1, 1 if dice.roll(1, 6) == 1 else 0)
    put(1, 14, 1, r(2))
    put(1, 16, 3, r(8))
    put(1, 19, 5, p())
    put(1, 24, 2, r(4))
    put(1, 26, 2, r(4))
    put(1, 28, 2, r(4))
    put(1, 30, 2, r(4))

    put(2, 0, 3, r(8))
    put(2, 3, 5, p())
    put(2, 8, 4, r(16))
    put(2, 12, 4, r(16))
    put(2, 16, 5, p())
    put(2, 21, 3, r(8))
    put(2, 24, 5, p())
    put(2, 29, 3, r(8))

    put(3, 0, 2, r(4))
    put(3, 2, 2, r(4))
    put(3, 4, 2, r(4))
    put(3, 6, 2, r(4))
    put(3, 8, 8, ((hi5 & 0x1F) << 3) | (r(8) & 7))
    put(3, 16, 2, r(4))
    put(3, 18, 2, r(4))
    put(3, 20, 2, DHDNA_W3_TABLE[r(10)] & 3)
    put(3, 22, 2, r(4))
    put(3, 24, 3, r(8))
    put(3, 27, 5, p())

    if roll_low3:
        put(4, 0, 3, r(8))
    put(4, 3, 5, p())
    put(4, 8, 4, r(16))
    put(4, 12, 6, ((tod & 3) << 4) | (r(16) & 0xF))
    put(4, 18, 2, r(4))
    put(4, 20, 2, r(4))
    put(4, 22, 2, r(4))
    put(4, 24, 3, r(8))
    put(4, 27, 5, p())

    put(5, 0, 5, p())
    put(5, 5, 3, r(8))
    put(5, 8, 5, p())
    put(5, 13, 3, r(8))
    put(5, 16, 5, p())
    put(5, 21, 3, r(8))

    return w


@dataclass
class DqTerrain:

    atm_density: int = 0
    atm_type: int = 0
    size: int = 0
    water: int = 0
    orbit_zone: int = 0

    @classmethod
    def from_world(cls, w) -> "DqTerrain":
        return cls(atm_density=w.atm_density & 0xFF,
                   atm_type=w.atm_type & 0xFF,
                   size=w.size & 0xFF,
                   water=w.water & 0xFF,
                   orbit_zone=w.orbit_zone & 0xFF)


def size_modifier(t: DqTerrain) -> int:
    size = t.size & 0xFF
    gas = 0x14 <= size <= 0x28
    if size == 0x32:
        mod = 0
    elif gas:
        mod = 2
    else:
        mod = 8 - size
    if gas:
        mod += 8
    elif (t.orbit_zone & 0xFF) == 1:
        mod += 4
    elif (t.orbit_zone & 0xFF) == 3:
        mod += 2
    return mod


FAUNA_KIND_TABLE = (0, 3, 1, 2, 1, 0, 3)

FAUNA_ABUNDANCE_MOD = (-3, 0, -2, -4)

FAUNA_ELEV_BANDS = 10
FAUNA_TIMES_OF_DAY = 3
FAUNA_SLOTS = 7
FAUNA_RECORDS_PER_ZONE = FAUNA_ELEV_BANDS * FAUNA_TIMES_OF_DAY * FAUNA_SLOTS

FAUNA_RECORD_BYTES = 0x1C
FAUNA_ZONE_BYTES = 0x16F8


@dataclass
class FaunaRecord:

    words: Tuple[int, ...]
    abundance: int


def fauna_record(t: DqTerrain, band: int, tod: int, kind: int,
                 dice: AuDice) -> FaunaRecord:
    size = t.size & 0xFF
    gas = 0x14 <= size <= 0x28

    words = [0, 0, 0, 0, 0, 0]
    randomize(words, size_modifier(t),
              (t.atm_density & 0xFF) >= 0x32, tod, dice, True)

    words[1] = (words[1] & 0xFFFFFF3F) | ((kind & 3) << 6)
    if band == 9 or gas:
        words[1] = (words[1] & ~0x1000 & 0xFFFFFFFF) | 0x800
    elif band < 6:
        words[1] = (words[1] & ~0x800 & 0xFFFFFFFF) | 0x1000
    else:
        words[1] |= 0x1000
        if (t.water & 0xFF) >= 10:
            words[1] = ((words[1] & ~0x800 & 0xFFFFFFFF)
                        | ((dice.roll(1, 2, -1) & 1) << 11))
        else:
            words[1] &= ~0x800 & 0xFFFFFFFF

    raw = dice.roll(2, 3, FAUNA_ABUNDANCE_MOD[kind]) & 0xFF
    signed = raw - 256 if raw >= 128 else raw
    return FaunaRecord(tuple(words), 1 if signed < 1 else raw)


def deplanetfauna_init(t: DqTerrain, dice: AuDice) -> List[FaunaRecord]:
    out: List[FaunaRecord] = []
    for band in range(FAUNA_ELEV_BANDS):
        for tod in range(FAUNA_TIMES_OF_DAY):
            for kind in FAUNA_KIND_TABLE:
                out.append(fauna_record(t, band, tod, kind, dice))
    return out


def fauna_steps(size: int, water: int) -> int:
    n = FAUNA_RECORDS_PER_ZONE * (DHDNA_RANDOMIZE_STEPS + 2)
    size &= 0xFF
    if not (0x14 <= size <= 0x28) and (water & 0xFF) > 9:
        n += 3 * FAUNA_TIMES_OF_DAY * FAUNA_SLOTS
    return n


def encode_fauna_zone(records: Sequence[FaunaRecord]) -> bytes:
    out = bytearray()
    for rec in records:
        out += struct.pack("<6IB3x", *(v & 0xFFFFFFFF for v in rec.words),
                           rec.abundance & 0xFF)
    return bytes(out)


def encode_fauna(zones: Sequence[Sequence[FaunaRecord]]) -> bytes:
    return b"".join(encode_fauna_zone(z) for z in zones)


def fauna_column_blob(zones: Sequence[Sequence[FaunaRecord]]) -> bytes:
    return qcompress(encode_fauna(zones))


def decode_fauna(blob: bytes) -> List[List[FaunaRecord]]:
    if not blob:
        return []
    raw = quncompress(blob) or blob
    if len(raw) % FAUNA_ZONE_BYTES:
        raise ValueError(
            f"Fauna image is {len(raw)} bytes, not a multiple of {FAUNA_ZONE_BYTES}")
    zones: List[List[FaunaRecord]] = []
    for z in range(len(raw) // FAUNA_ZONE_BYTES):
        recs: List[FaunaRecord] = []
        base = z * FAUNA_ZONE_BYTES
        for i in range(FAUNA_RECORDS_PER_ZONE):
            off = base + i * FAUNA_RECORD_BYTES
            vals = struct.unpack_from("<6IB", raw, off)
            recs.append(FaunaRecord(tuple(vals[:6]), vals[6]))
        zones.append(recs)
    return zones


def world_fauna(w, dice: AuDice) -> List[List[FaunaRecord]]:
    t = DqTerrain.from_world(w)
    return [deplanetfauna_init(t, dice) for _ in range(w.resource_zones())]


def world_fauna_blob(w, dice: AuDice) -> bytes:
    if not w.can_have_fauna():
        raise ValueError(
            'world_fauna_blob: CanHaveFauna is false for this world.')
    return fauna_column_blob(world_fauna(w, dice))
