
from __future__ import annotations

import logging
import math
from typing import Sequence

logger = logging.getLogger(__name__)

__all__ = ["AuDice", "AuNoise"]


class AuDice:

    MULT = 0x41C64E6D
    INC = 0x00003039
    MASK = 0xFFFFFFFF
    _POW32 = 1 << 32

    __slots__ = ("state",)

    def __init__(self, seed: int = 1) -> None:
        self.state = seed & self.MASK

    def seed(self, s: int) -> None:
        self.state = s & self.MASK

    def time_seed(self, fake_time: int | None = None) -> None:
        import time as _t
        self.state = (int(_t.time()) if fake_time is None else fake_time) & self.MASK

    def random(self) -> int:
        self.state = (self.state * self.MULT + self.INC) & self.MASK
        return self.state

    def roll(self, n: int, sides: int, mod: int = 0) -> int:
        if n == 0:
            return 0
        accum = 0
        for _ in range(n):
            r = (self.state * self.MULT + self.INC) & self.MASK
            self.state = r
            if sides > 1:
                accum += 1 + (r * sides) // self._POW32
        if sides == 0:
            return mod
        if sides == 1:
            return n + mod
        return accum + mod

    def advance(self, k: int) -> None:
        if k < 0:
            raise ValueError("Advance: k must be >= 0")
        a, c = 1, 0
        ba, bc = self.MULT, self.INC
        while k:
            if k & 1:
                a, c = (ba * a) & self.MASK, (ba * c + bc) & self.MASK
            ba, bc = (ba * ba) & self.MASK, (ba * bc + bc) & self.MASK
            k >>= 1
        self.state = (a * self.state + c) & self.MASK

    def random_range(self, lo: int, hi: int) -> int:
        if lo == hi:
            return lo
        a, b = (lo, hi) if lo < hi else (hi, lo)
        span = b - a + 1
        r = self.random()
        return a + ((r * span) // self._POW32)

    def random_choice(self, a: int, b: int) -> int:
        return a if (self.random() & 1) == 0 else b

    def random_min_max(self, lo: float, hi: float, scale: float = float(1 << 32)) -> float:
        r = self.random()
        return lo + (r / scale) * (hi - lo)


class AuNoise:

    CONST_1 = 1.0
    CONST_2 = 1.0 / (1 << 30)
    _MASK32 = 0xFFFFFFFF

    TABLE_A: Sequence[int] = (
        13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59,
    )
    TABLE_B: Sequence[int] = (
        15629, 15641, 15643, 15647, 15649, 15661,
        15667, 15671, 15679, 15683, 15727, 15731,
    )
    TABLE_C: Sequence[int] = (
        754907, 754921, 754931, 754937, 754939, 754967,
        754969, 754973, 754979, 754981, 754991, 789221,
    )
    TABLE_D: Sequence[int] = (
        1372950023, 1372950043, 1372950049, 1372950071,
        1372950077, 1372950101, 1372950133, 1372950169,
        1372950191, 1372950193, 1372950221, 1372950233,
    )

    @classmethod
    def _core(cls, s: int, h: int) -> float:
        m32 = cls._MASK32
        r = (cls.TABLE_B[s] * h * h + cls.TABLE_C[s]) & m32
        r = (r * h + cls.TABLE_D[s]) & m32
        r &= 0x7FFFFFFF
        return cls.CONST_1 - r * cls.CONST_2

    @classmethod
    def integer_noise1(cls, seed: int, x: int) -> float:
        s = seed % 12
        x &= cls._MASK32
        h = (x ^ ((x << 13) & cls._MASK32)) & cls._MASK32
        return cls._core(s, h)

    @classmethod
    def integer_noise(cls, seed: int, x: int, y: int) -> float:
        s = seed % 12
        m32 = cls._MASK32
        pre = (cls.TABLE_A[s] * y + x) & m32
        h = (pre ^ ((pre << 13) & m32)) & m32
        return cls._core(s, h)

    @classmethod
    def integer_noise3(cls, seed: int, x: int, y: int) -> float:
        return cls.integer_noise(seed, x, y)

    @staticmethod
    def linear_interpolate(a: float, b: float, t: float) -> float:
        return (1.0 - t) * a + t * b

    @staticmethod
    def cosine_interpolate(a: float, b: float, t: float) -> float:
        f = (1.0 - math.cos(t * math.pi)) * 0.5
        return (1.0 - f) * a + f * b


    _SCURVE_K = 3.0
    _LACUNARITY = 2.0

    @classmethod
    def cubic_scurve(cls, t: float) -> float:
        return t * t * cls._SCURVE_K - 2.0 * (t ** cls._SCURVE_K)

    @classmethod
    def cubic_coherent_noise(cls, seed: int, x: float, y: float) -> float:
        ix = math.floor(x)
        iy = math.floor(y)
        fx = x - ix
        fy = y - iy
        ix = int(ix)
        iy = int(iy)

        v00 = cls.integer_noise(seed, ix, iy)
        v10 = cls.integer_noise(seed, ix + 1, iy)
        v01 = cls.integer_noise(seed, ix, iy + 1)
        v11 = cls.integer_noise(seed, ix + 1, iy + 1)

        sx = (1.0 - math.cos(cls.cubic_scurve(fx) * math.pi)) * 0.5
        sy = (1.0 - math.cos(cls.cubic_scurve(fy) * math.pi)) * 0.5

        top = v10 * sx + v00 * (1.0 - sx)
        bottom = v01 * (1.0 - sx) + v11 * sx
        return top * (1.0 - sy) + bottom * sy

    @classmethod
    def cubic_perlin_noise(cls, octaves: int, persistence: float,
                           x: float, y: float) -> float:
        total = 0.0
        for i in range(int(octaves)):
            freq = cls._LACUNARITY ** i
            amp = persistence ** i
            total += cls.cubic_coherent_noise(i, freq * x, freq * y) * amp
        return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("AuDice smoke-test")
    d = AuDice()
    seq = [d.random() for _ in range(5)]
    logger.info("First 5 Random() after seed=1: %s",
                [f"0x{s:08x}" for s in seq])
    assert seq[0] == 0x41C67EA6, f"seq[0] = 0x{seq[0]:08x}"

    d.seed(0)
    logger.info("First Random() after seed=0: %s", f"0x{d.random():08x}")
    assert d.state == 0x3039

    d.seed(0xDEADBEEF)
    logger.info("Roll(6, 6) with seed=0xDEADBEEF: %s", d.roll(6, 6))

    logger.info("AuNoise smoke-test")
    for s in range(12):
        v = AuNoise.integer_noise(s, 0, 0)
        assert -1.0 < v <= 1.0, f"Out of range: seed={s} v={v}"
    logger.info("All 12 seeds at (0,0) are in (-1, 1] OK")

    a = AuNoise.integer_noise(7, 123456, -987654)
    b = AuNoise.integer_noise(7, 123456, -987654)
    assert a == b
    logger.info("Determinism OK; integer_noise(7, 123456, -987654) = %s", a)

    c = AuNoise.integer_noise(7, 123456, -987653)
    logger.info("Neighbour at y+1 = %s (should look uncorrelated)", c)
