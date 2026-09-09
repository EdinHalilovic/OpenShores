from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


_LCG_MUL = 0x41C64E6D
_LCG_ADD = 0x3039
_U32 = 0xFFFFFFFF


class AuDice:

    __slots__ = ("seed",)

    def __init__(self, seed: int = 1) -> None:
        self.seed = seed & _U32

    def _step(self) -> int:
        self.seed = (self.seed * _LCG_MUL + _LCG_ADD) & _U32
        return self.seed


    def roll(self, dice: int, sides: int, mod: int = 0) -> int:
        if dice == 0:
            return 0
        total = 0
        for _ in range(dice):
            s = self._step()
            if sides > 1:
                total += 1 + ((s * sides) >> 32)
        if sides == 0:
            return mod
        if sides == 1:
            return dice + mod
        return total + mod

    def random_range(self, lo: int, hi: int) -> int:
        if hi < lo:
            lo, hi = hi, lo
        rng = hi - lo + 1
        s = self._step()
        return lo + ((s * rng) >> 32)


BIT_FIELDS: list[tuple[int, int, int]] = [
    (0,  0, 4), (0,  4, 4), (0,  8, 2), (0, 10, 2), (0, 12, 4),
    (0, 16, 3), (0, 19, 5), (0, 24, 3), (0, 27, 5),
    (1,  0, 2), (1,  2, 2), (1,  4, 2), (1,  6, 2),
    (1,  8, 1), (1,  9, 1), (1, 10, 1), (1, 11, 1),
    (1, 12, 1), (1, 13, 1), (1, 14, 1), (1, 15, 1),
    (1, 16, 3), (1, 19, 5), (1, 24, 2), (1, 26, 2),
    (1, 28, 2), (1, 30, 2),
    (2,  0, 3), (2,  3, 5), (2,  8, 4), (2, 12, 4),
    (2, 16, 5), (2, 21, 3), (2, 24, 5), (2, 29, 3),
    (3,  0, 2), (3,  2, 2), (3,  4, 2), (3,  6, 2),
    (3,  8, 3), (3, 11, 5), (3, 16, 2), (3, 18, 2),
    (3, 20, 2), (3, 22, 2), (3, 24, 3), (3, 27, 5),
    (4,  0, 3), (4,  3, 5), (4,  8, 4), (4, 12, 4),
    (4, 16, 2), (4, 18, 2), (4, 20, 2), (4, 22, 2),
    (4, 24, 3), (4, 27, 5),
    (5,  0, 5), (5,  5, 3), (5,  8, 5), (5, 13, 3),
    (5, 16, 5), (5, 21, 3),
]
assert len(BIT_FIELDS) == 63, "DhDNA bit-field table must be exactly 63 slices"

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUV"
ALPHABET_INDEX = {c: i for i, c in enumerate(ALPHABET)}
DHDNA_STRING_LEN = 63
DHDNA_BYTES_LEN = 24


@dataclass
class DhDNA:

    w: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 0])


    @classmethod
    def from_bytes(cls, data: bytes) -> "DhDNA":
        if len(data) != DHDNA_BYTES_LEN:
            raise ValueError(
                f"DhDNA must be {DHDNA_BYTES_LEN} bytes, got {len(data)}")
        return cls(w=list(struct.unpack("<6I", data)))

    def to_bytes(self) -> bytes:
        return struct.pack("<6I", *self.w)

    @classmethod
    def from_string(cls, s: str) -> "DhDNA":
        if len(s) != DHDNA_STRING_LEN:
            raise ValueError(
                f"DhDNA string must be {DHDNA_STRING_LEN} chars, got {len(s)}")
        d = cls()
        for i, (word, shift, bits) in enumerate(BIT_FIELDS):
            ch = s[i]
            try:
                v = ALPHABET_INDEX[ch]
            except KeyError as e:
                raise ValueError(
                    f"DhDNA char {i} {ch!r} not in alphabet") from e
            mask = (1 << bits) - 1
            d.w[word] = (d.w[word] & ~(mask << shift) & _U32) \
                        | ((v & mask) << shift)
        return d

    def to_string(self) -> str:
        chars = []
        for word, shift, bits in BIT_FIELDS:
            mask = (1 << bits) - 1
            v = (self.w[word] >> shift) & mask
            chars.append(ALPHABET[v])
        return "".join(chars)

    def __repr__(self) -> str:
        return (
            f"DhDNA(w={[f'0x{x:08x}' for x in self.w]} "
            f"str={self.to_string()!r})")


    @classmethod
    def default_human(cls) -> "DhDNA":
        d = cls()
        d.w[0] = 0x92800d65
        d.w[1] = 0x16711080
        d.w[5] = (d.w[5] & 0xff141456 & _U32) | 0x141456
        d.w[2] = 0x6a587782
        d.w[3] = 0x82054654
        d.w[4] = 0x72c254a2
        return d


    def can_fly(self) -> bool:
        return (
            (self.w[1] & 0x400) != 0
            and (self.w[0] & 0x300) != 0
            and (self.w[0] & 0x60000) != 0
        )

    def is_sentient(self) -> bool:
        return (self.w[3] & 0xf800) != 0

    def is_water(self) -> bool:
        return (self.w[1] & 0x1000) != 0

    def is_burrow(self) -> bool:
        return (self.w[1] & 0x2000) != 0

    _ECO_NAMES  = ['Carnivorous', 'Herbivorous', 'Omnivorous', 'Scavenging']
    _PHYLA      = ['Insectoid', 'Reptilian', 'Glabrian', 'Avian',
                   'Furrian', 'Crustacean', 'Aquarian', 'Amphibian']
    _EXOSKELETAL_PHYLA = frozenset({0, 5})

    def eco_role(self) -> int:
        return (self.w[1] >> 6) & 3

    def eco_role_name(self) -> str:
        idx = self.eco_role()
        return self._ECO_NAMES[idx] if idx < len(self._ECO_NAMES) else f'Eco{idx}'

    def phylum(self) -> int:
        return self.w[4] & 7

    def phylum_name(self) -> str:
        idx = self.phylum()
        return self._PHYLA[idx] if idx < len(self._PHYLA) else f'Phylum{idx}'

    def is_exoskeletal(self) -> bool:
        return self.phylum() in self._EXOSKELETAL_PHYLA

    def spot_description(self) -> str:
        w0, w1 = self.w[0], self.w[1]

        b10 = bool((w1 >> 10) & 1)
        b11 = bool(w1 & 0x800)
        b12 = bool((w1 >> 12) & 1)
        has_legs  = bool(w0 & 0x0300)
        has_wings = bool(w0 & 0x60000)

        if b11 and b10 and has_legs and has_wings and b12:
            loco = 'Triphibious '
        elif (w1 & 0x1800) == 0x1800:
            loco = 'Amphibious '
        elif b11 and b10 and has_legs and has_wings:
            loco = 'Aquaerial '
        elif b10 and has_legs and has_wings:
            loco = 'Aerial '
        elif b11:
            loco = 'Aquatic '
        else:
            loco = ''

        prefix = 'Subterranean ' if (w1 & 0x2000) else ''
        return prefix + loco + self.eco_role_name() + ' ' + self.phylum_name()

    def sight_range_m(self) -> float:
        base = (((self.w[1] >> 26) & 3) + 1) * 90.0
        if self.can_fly():
            base *= 2.0
        return base

    def hearing_range_m(self) -> float:
        bucket = (self.w[1] >> 4) & 3
        return 50.0 + bucket * 25.0

    def smell_range_m(self) -> float:
        bucket = (self.w[1] >> 2) & 3
        return 30.0 + bucket * 20.0

    def bit_sum(self) -> int:
        return sum(
            (self.w[word] >> shift) & ((1 << bits) - 1)
            for word, shift, bits in BIT_FIELDS
        )


    def randomize(
        self,
        dice: AuDice,
        phylum: int = 0,
        sentient: bool = False,
        tod: int = 0,
        randomize_w4_low3: bool = False,
    ) -> None:
        self.w = [0, 0, 0, 0, 0, 0]
        if phylum <= 0:
            phylum = dice.roll(1, 25, -1)
        phylum_idx = max(0, min(0x18, phylum))

        sent_limit = 8 if sentient else 2
        sent_class = dice.roll(1, sent_limit) - 1 if sent_limit > 1 else 0

        bit9 = 1 if dice.roll(1, 100) >= 0x60 else 0
        bit13 = 1 if dice.roll(1, 6) == 1 else 0

        lut = [0, 0, 0, 0, 2, 3, 0, 0, 0, 0]
        w3_2021 = lut[(dice.roll(1, 10) - 1) % len(lut)]

        w4_1415 = tod & 3

        def roll_bits(bits: int) -> int:
            sides = 1 << bits
            if sides <= 1:
                return 0
            return dice.random_range(0, sides - 1)

        for i, (word, shift, bits) in enumerate(BIT_FIELDS):
            if i == 5:
                v = sent_class & ((1 << bits) - 1)
            elif i in (6, 22, 28, 33, 40, 46, 48, 56, 57, 59, 61):
                v = dice.roll(1, 8, phylum_idx - 1) & ((1 << bits) - 1)
            elif i == 14:
                v = bit9
            elif i == 18:
                v = bit13
            elif i == 43:
                v = w3_2021 & ((1 << bits) - 1)
            elif i == 47 and not randomize_w4_low3:
                v = 0
            elif i == 50:
                low = roll_bits(4) & 0xF
                v = low
            elif i == 51:
                v = w4_1415 & 3
            else:
                v = roll_bits(bits)
            mask = (1 << bits) - 1
            self.w[word] = (self.w[word] & ~(mask << shift) & _U32) \
                           | ((v & mask) << shift)

        if sentient and (self.w[3] & 0xf800) == 0:
            self.w[3] |= 1 << 11
        elif (not sentient) and (self.w[3] & 0xf800) != 0:
            self.w[3] &= ~0xf800 & _U32

    def combine(self, mate: "DhDNA", dice: AuDice) -> "DhDNA":
        child = DhDNA()
        for word, shift, bits in BIT_FIELDS:
            mask = (1 << bits) - 1
            src = self if dice.roll(1, 2) == 1 else mate
            v = (src.w[word] >> shift) & mask
            child.w[word] = (child.w[word] & ~(mask << shift) & _U32) \
                            | (v << shift)
        return child


def _self_test() -> None:
    logger.info("DhDNA codec self-test")

    h = DhDNA.default_human()
    s = h.to_string()
    logger.info("Default human DhDNA = %s (len %d)", s, len(s))
    assert len(s) == DHDNA_STRING_LEN, "String length must be 63"
    h2 = DhDNA.from_string(s)
    logger.info("Round-trip equal = %s", h.w == h2.w)
    assert h.w == h2.w, "Round-trip failed"

    logger.info("  is_sentient         = %s", h.is_sentient())
    logger.info("  can_fly             = %s", h.can_fly())
    logger.info("  eco_role            = %s", h.eco_role())
    logger.info("  sight_range_m       = %s", h.sight_range_m())
    logger.info("  hearing_range_m     = %s", h.hearing_range_m())
    logger.info("  bit_sum             = %s", h.bit_sum())

    a = AuDice(seed=1)
    rolls = [a.roll(1, 6) for _ in range(8)]
    logger.info("AuDice(1) 8x d6       = %s", rolls)
    a2 = AuDice(seed=1)
    rolls2 = [a2.roll(1, 6) for _ in range(8)]
    assert rolls == rolls2, "AuDice not deterministic"

    logger.info("5 random sentients (seed=42)")
    dice = AuDice(seed=42)
    for i in range(5):
        d = DhDNA()
        d.randomize(dice, phylum=0, sentient=True, tod=0, randomize_w4_low3=True)
        s = d.to_string()
        rt = DhDNA.from_string(s)
        assert d.w == rt.w, "Random DhDNA failed round-trip"
        logger.info("  [%d] %s  sentient=%s fly=%s role=%s",
                    i, s, d.is_sentient(), d.can_fly(), d.eco_role())

    logger.info("5 random fauna (planet seed = 0xdeadbeef)")
    dice = AuDice(seed=0xDEADBEEF)
    for i in range(5):
        d = DhDNA()
        d.randomize(dice, phylum=0, sentient=False, tod=1)
        s = d.to_string()
        rt = DhDNA.from_string(s)
        assert d.w == rt.w
        logger.info("  [%d] %s  fly=%s water=%s burrow=%s role=%s  "
                    "sight=%sm  hear=%sm",
                    i, s, d.can_fly(), d.is_water(), d.is_burrow(),
                    d.eco_role(), d.sight_range_m(), d.hearing_range_m())

    logger.info("Combine two parents")
    a = DhDNA(); a.randomize(AuDice(1), phylum=0, sentient=False, tod=0)
    b = DhDNA(); b.randomize(AuDice(2), phylum=0, sentient=False, tod=0)
    logger.info("Parent A: %s", a.to_string())
    logger.info("Parent B: %s", b.to_string())
    child = a.combine(b, AuDice(99))
    logger.info("Child : %s", child.to_string())

    logger.info("ALL OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _self_test()
