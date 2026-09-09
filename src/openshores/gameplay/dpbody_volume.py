from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

import numpy as np

_f32 = np.float32


def _F(x) -> np.float32:
    return _f32(x)


K_0625 = _F(0.0625)
K_025  = _F(0.25)
K_1    = _F(1.0)
K_05   = _F(0.5)
K_3    = _F(3.0)
K_15   = _F(1.5)
K_125  = _F(1.25)
K_075  = _F(0.75)
K_PI   = _F(struct.unpack("<f", bytes.fromhex("db0f4940"))[0])

D_13   = 1.3
D_05   = 0.5
D_11   = 1.1
D_25   = 2.5
D_3    = 3.0

MAX_HP_SCALE = _F(struct.unpack("<f", bytes.fromhex("eb86ec41"))[0])

HEAD5 = np.array(
    list(struct.unpack("<4f", bytes.fromhex("0000803fcdcc4c3f3333333f9a99193f"))) + [0.5],
    dtype=np.float32,
)

HEADWT5 = np.array(
    list(struct.unpack("<4f", bytes.fromhex("0000803f6666663fcdcc4c3f3333333f"))) + [0.6],
    dtype=np.float32,
)

_SPECIES_HEX = (
    "59dc9f3e919bb93ec79dd23ee203eb3e"
    "c075013f47380d3f80d6183fdd5c243f"
    "5ed72f3fdf513b3f3cd8463f7576523ffc385e3fcb2c6a3fd95f763f5070813f"
    "37e0873f7b888e3fef72953fb4ab9c3f923fa43fee3dac3fd0b8b43fd6c5bd3f"
    "e97dc73fd200d23feb73dd3fb806ea3f"
    "dcf4f73f2ec5034096950c40acad1640"
)
SPECIES_SCALE = np.frombuffer(bytes.fromhex(_SPECIES_HEX), dtype="<f4")
assert SPECIES_SCALE.shape == (32,), "Species scale table must hold 32 floats"


def _dna_words(dna: bytes) -> tuple[int, ...]:
    b = bytes(dna)
    if len(b) < 24:
        b = b + b"\x00" * (24 - len(b))
    return struct.unpack("<6I", b[:24])


HAND_LENGTH = {
    0: (0.997774600982666, 0.854196809232235, 0.616704910993576, 0.8561990857124329, 0.6444480717182159, 0.5634760856628418, 1.4868378639221191, 0.7623367309570312),
    1: (0.997774600982666, 0.854196809232235, 0.8715319633483887, 0.8502543270587921, 0.42629361152648926, 0.5634760856628418, 1.4868378639221191, 0.7623367309570312),
    2: (0.997774600982666, 1.297520637512207, 0.8715319633483887, 0.8502543270587921, 0.42629361152648926, 0.5634760856628418, 1.4868378639221191, 0.7623367309570312),
    3: (0.997774600982666, 0.854196809232235, 0.8715319633483887, 0.8502543270587921, 0.42629361152648926, 0.5634760856628418, 1.4868378639221191, 0.8872754573822021),
    4: (0.5634760856628418, 0.854196809232235, 0.8715319633483887, 0.8502543270587921, 0.42629361152648926, 0.926297664642334, 1.4868378639221191, 0.8876054286956787),
    5: (0.997774600982666, 0.854196809232235, 0.616704910993576, 1.4868378639221191, 0.42629361152648926, 0.5634760856628418, 0.8936326652765274, 0.8561990857124329),
    6: (0.997774600982666, 1.297520637512207, 0.854196809232235, 0.850254237651825, 0.42629361152648926, 0.8876054286956787, 1.4868378639221191, 0.7623367309570312),
    7: (0.997774600982666, 1.297520637512207, 0.854196809232235, 0.850254237651825, 0.6444480717182159, 0.8876054286956787, 1.4868378639221191, 0.7623367309570312),
    "PA": (0.47485683858394623,),
}

FOOT_LENGTH = {
    0: (0.4742814004421234, 1.2115673422813416, 0.616704910993576, 0.8554724454879761, 0.6444480717182159, 0.5634760856628418, 0.6473076641559601, 0.5603641271591187),
    1: (1.0632967948913574, 1.2115673422813416, 0.5988831520080566, 0.8057765960693359, 0.42629361152648926, 0.5634760856628418, 0.5545871257781982, 0.5603641271591187),
    2: (1.0632967948913574, 1.268211841583252, 0.5988831520080566, 0.8057765960693359, 0.42629361152648926, 0.5634760856628418, 0.5545871257781982, 0.5603641271591187),
    3: (0.5988831520080566, 1.2115673422813416, 1.0632967948913574, 0.8057765960693359, 0.42629361152648926, 0.5634760856628418, 0.5545871257781982, 0.8263485431671143),
    4: (0.5634760856628418, 1.2115673422813416, 0.765303373336792, 0.8057765960693359, 0.42629361152648926, 0.5988831520080566, 0.5545871257781982, 0.8263485431671143),
    5: (0.6796450018882751, 1.2115673422813416, 0.6614266633987427, 0.8554724752902985, 0.8061773180961609, 0.5634760856628418, 0.6473076343536377, 0.5603641271591187),
    6: (1.0968698114156723, 1.268211841583252, 1.0632967948913574, 0.8057765364646912, 0.6472795009613037, 0.6706467270851135, 0.5545871257781982, 0.8263485431671143),
    7: (1.0632967948913574, 1.268211841583252, 1.2115673422813416, 0.8057765960693359, 0.6444480717182159, 0.6706467270851135, 0.5545871257781982, 0.8263485431671143),
    "PA": (0.6444480717182159, 0.7417032718658447),
}

OVERALL_SCALE_DIV = _F(struct.unpack("<f", bytes.fromhex("3d0a573f"))[0])
D_15 = 1.5


def has_ankle_bend(dna: bytes) -> bool:
    return ((_dna_words(dna)[2] >> 21) & 7) not in (4, 6)


@dataclass(frozen=True)
class LimbEnds:

    hand: Optional[float]
    foot: Optional[float]

    @classmethod
    def omit(cls) -> "LimbEnds":
        return cls(hand=None, foot=None)

    @classmethod
    def of(cls, hand: float, foot: float) -> "LimbEnds":
        return cls(hand=float(hand), foot=float(foot))

    @classmethod
    def from_dna(cls, dna: bytes, *, power_armour: bool = False) -> "LimbEnds":
        w0, w1, w2, w3, w4, w5 = _dna_words(dna)
        overall = _F(SPECIES_SCALE[(w3 >> 11) & 0x1F] / OVERALL_SCALE_DIV)

        def _morph(n_len: int, n_dia: int) -> np.float32:
            a = _F(float(_F(_F(_F(n_len) * K_0625) + K_05)) / D_15)
            b = _F(_F(_F(_F(n_dia) * K_0625) + K_1) * K_025)
            return _F(a * _F(b + b))

        def _size(n: int) -> np.float32:
            t = _F(_F(_F(_F(n) * K_0625) + K_05) * K_025)
            return _F(t + t)

        prefix = w4 & 7
        if power_armour:
            hand_l = HAND_LENGTH["PA"][0]
            foot_l = FOOT_LENGTH["PA"][1 if has_ankle_bend(dna) else 0]
        else:
            hand_l = HAND_LENGTH[prefix][w2 >> 29]
            foot_l = FOOT_LENGTH[prefix][(w2 >> 21) & 7]

        hand = _F(_F(_F(overall * _morph((w1 >> 19) & 0x1F, (w2 >> 3) & 0x1F))
                      * _size((w2 >> 24) & 0x1F)) * _F(hand_l))
        foot = _F(_F(_F(overall * _morph((w0 >> 19) & 0x1F, w0 >> 27))
                     * _size((w2 >> 16) & 0x1F)) * _F(foot_l))
        return cls(hand=float(hand), foot=float(foot))

    @property
    def exact(self) -> bool:
        return self.hand is not None and self.foot is not None


@dataclass
class BodyDims:

    f4078: np.float32
    f407c: np.float32
    f4080: np.float32
    f4084: np.float32
    f4094: np.float32
    f4098: np.float32
    f40a0: np.float32
    f40a4: np.float32
    f40a8: np.float32
    f40ac: np.float32
    f40b0: np.float32


def one_time_calcs(dna: bytes) -> BodyDims:
    w0, w1, w2, w3, w4, w5 = _dna_words(dna)

    sp = SPECIES_SCALE[(w3 >> 11) & 0x1F]

    def _len13(field: int) -> np.float32:
        t = _F(_F(_F(field) * K_0625) + K_05)
        return _F(float(_F(t * sp)) * D_13)

    def _len(field: int) -> np.float32:
        return _F(_F(_F(_F(field) * K_0625) + K_05) * sp)

    def _dia(field: int, length: np.float32) -> np.float32:
        t = _F(_F(_F(field) * K_0625) + K_1)
        return _F(_F(_F(t * K_025) * length) * K_05)

    f4078 = _len13((w0 >> 19) & 0x1F)
    f407c = _dia(w0 >> 27, f4078)
    f4080 = _len((w1 >> 19) & 0x1F)
    f4084 = _dia((w2 >> 3) & 0x1F, f4080)
    f40a0 = _len(w4 >> 27)

    base = _F(_F(_F(_F(w5 & 0x1F) * K_0625) * K_025) * f40a0)
    base = _F(base + _F(f40a0 / K_3))

    f40a4 = base
    if ((w1 >> 12) & 1) and (w3 & 0xC) < 8:
        f40a4 = _F(f40a4 * K_075)

    f40a8 = base
    if w1 & 0x800:
        f40a8 = _F(f40a8 * K_075)

    f4094 = _len13(w3 >> 27)
    f4098 = _dia((w4 >> 3) & 0x1F, f4094)
    f40ac = _len((w5 >> 8) & 0x1F)
    f40b0 = _dia((w5 >> 16) & 0x1F, f40ac)

    return BodyDims(f4078, f407c, f4080, f4084, f4094, f4098,
                    f40a0, f40a4, f40a8, f40ac, f40b0)


@dataclass(frozen=True)
class PartCounts:
    torso: int
    tail: int
    heads: int
    arm_pairs: int
    leg_pairs: int

    @property
    def arms(self) -> int:
        return self.arm_pairs * 2

    @property
    def legs(self) -> int:
        return self.leg_pairs * 2


def part_counts(dna: bytes) -> PartCounts:
    w0, w1, w2, w3, w4, w5 = _dna_words(dna)
    return PartCounts(
        torso=1,
        tail=1 if (w3 & 0x300000) else 0,
        heads=1 + ((w1 >> 9) & 1),
        arm_pairs=((w0 >> 8) & 3) if (w0 & 0x300) else 0,
        leg_pairs=((w3 >> 2) & 3) if (w3 & 0xC) else 0,
    )


def _head_index(dna: bytes) -> int:
    _, w1, _, w3, _, _ = _dna_words(dna)
    return ((w1 >> 9) & 1) + ((w3 >> 16) & 3)


def head_thickness(dna: bytes, d: BodyDims) -> np.float32:
    _, w1, _, _, _, _ = _dna_words(dna)
    v = d.f40a4
    if not (w1 & 0x800) and not (w1 & 0x400) and not (w1 & 0x2000):
        v = d.f40a8 if d.f40a8 < v else v
    return _F(v * HEADWT5[_head_index(dna)])


def head_width(dna: bytes, d: BodyDims) -> np.float32:
    _, w1, _, _, _, _ = _dna_words(dna)
    v = d.f40a8
    if not (w1 & 0x800) and not (w1 & 0x400) and not (w1 & 0x2000):
        v = d.f40a4 if d.f40a4 < v else v
    return _F(v * HEADWT5[_head_index(dna)])


def torso_volume(dna: bytes, d: BodyDims) -> np.float32:
    w5 = _dna_words(dna)[5]
    n = (w5 >> 5) & 7
    if n == 0:
        return _F(0.0)
    return _F(_F(_F(_F(d.f40a8 * d.f40a4) * d.f40a0) * _F(n)) * K_3)


def tail_volume(dna: bytes, d: BodyDims) -> np.float32:
    w3 = _dna_words(dna)[3]
    n = (w3 >> 22) & 3
    if n == 0:
        return _F(0.0)
    a = _F(float(d.f40a8) * D_05)
    b = _F(float(d.f40a4) * D_05)
    length = _F((float(d.f40a0) + float(d.f40a0)) / D_3)
    return _F(_F(_F(_F(a * b) * length) * _F(n)) * K_15)


def head_volume(dna: bytes, d: BodyDims) -> np.float32:
    idx = _head_index(dna)

    biggest = d.f40a8 if d.f40a8 > d.f40a4 else d.f40a4
    scaled = _F(_F(biggest * HEAD5[idx]) * K_125)

    v = _F(_F(head_thickness(dna, d) * scaled) * head_width(dna, d))

    if idx != 0:
        neck = _F(_F(_F(_F(float(d.f40a8) * D_05) * _F(float(d.f40a4) * D_05))
                     * _F(float(d.f40a0) / D_25)) * _F(idx))
        v = _F(v + neck)

    return _F(v * K_125)


def _limb_volume(length1: np.float32, dia1: np.float32,
                 length2: np.float32, dia2: np.float32,
                 end_length: Optional[float]) -> np.float32:
    r1 = _F(dia1 * K_05)
    term1 = _F(_F(_F(r1 * r1) * K_PI) * length1)

    r2 = _F(dia2 * K_05)
    term2 = _F(_F(_F(r2 * r2) * K_PI) * length2)

    total = _F(term1 + term2)

    if end_length is not None:
        end = _F(end_length)
        girth = _F(float(end) * D_05)
        if girth > dia1:
            girth = _F(float(dia1) * D_11)
        r3 = _F(girth * K_05)
        term3 = _F(_F(_F(r3 * r3) * K_PI) * end)
        total = _F(total + term3)

    return total


def arm_volume(d: BodyDims, ends: LimbEnds) -> np.float32:
    return _limb_volume(d.f4080, d.f4084, d.f40ac, d.f40b0, ends.hand)


def leg_volume(d: BodyDims, ends: LimbEnds) -> np.float32:
    return _limb_volume(d.f4078, d.f407c, d.f4094, d.f4098, ends.foot)


def body_volume(dna: bytes, ends: Optional[LimbEnds] = None) -> np.float32:
    if ends is None:
        ends = LimbEnds.from_dna(dna)
    d = one_time_calcs(dna)
    counts = part_counts(dna)

    total = _F(0.0)
    total = _F(total + torso_volume(dna, d))

    if counts.tail:
        total = _F(total + tail_volume(dna, d))

    head = head_volume(dna, d)
    for _ in range(counts.heads):
        total = _F(total + head)

    arm = arm_volume(d, ends)
    for _ in range(counts.arms):
        total = _F(total + arm)

    leg = leg_volume(d, ends)
    for _ in range(counts.legs):
        total = _F(total + leg)

    return total


def raw_hit_points(volume: float) -> int:
    root = np.sqrt(_F(max(0.0, float(volume))))
    scaled = _F(root * MAX_HP_SCALE)
    word = int(float(scaled)) & 0xFFFF
    return 0x7FFF if word > 0x7FFF else word


def max_hit_points(dna: bytes, ends: Optional[LimbEnds] = None) -> int:
    from openshores.gameplay.dpbody_maxes import can_fly, can_jump

    raw = raw_hit_points(body_volume(dna, ends))

    if can_fly(dna):
        hp = raw >> 1
    elif can_jump(dna):
        hp = (raw * 2) // 3
    else:
        hp = raw

    return 1 if hp == 0 else hp
