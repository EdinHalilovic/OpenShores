
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

Vec3 = Tuple[float, float, float]


class AuMatrix4x4:

    __slots__ = ("m",)

    def __init__(self, values: Sequence[float] | None = None) -> None:
        if values is None:
            self.m: List[float] = [0.0] * 16
            self.load_identity()
        else:
            if len(values) != 16:
                raise ValueError("AuMatrix4x4 takes 16 values, got %d"
                                 % len(values))
            self.m = [float(v) for v in values]

    def load_identity(self) -> "AuMatrix4x4":
        self.m = [0.0] * 16
        self.m[0] = self.m[5] = self.m[10] = self.m[15] = 1.0
        return self

    def get(self, row: int, col: int) -> float:
        return self.m[col * 4 + row]

    def set(self, row: int, col: int, value: float) -> None:
        self.m[col * 4 + row] = float(value)

    @property
    def translation(self) -> Vec3:
        return (self.m[12], self.m[13], self.m[14])

    def rotate_z(self, angle: float) -> "AuMatrix4x4":
        c = math.cos(angle)
        s = math.sin(angle)
        m = self.m
        for i in range(4):
            a = m[i]
            b = m[4 + i]
            m[i] = a * c + b * s
            m[4 + i] = b * c - a * s
        return self

    def translate(self, x: float, y: float, z: float) -> "AuMatrix4x4":
        m = self.m
        for i in range(4):
            m[12 + i] += x * m[i] + y * m[4 + i] + z * m[8 + i]
        return self

    def __mul__(self, other: "AuMatrix4x4") -> "AuMatrix4x4":
        a, b = self.m, other.m
        out = [0.0] * 16
        for col in range(4):
            for row in range(4):
                out[col * 4 + row] = (
                    a[row] * b[col * 4]
                    + a[4 + row] * b[col * 4 + 1]
                    + a[8 + row] * b[col * 4 + 2]
                    + a[12 + row] * b[col * 4 + 3]
                )
        return AuMatrix4x4(out)

    def inverse(self) -> "AuMatrix4x4":
        n = 4
        a = [[self.get(r, c) for c in range(n)] for r in range(n)]
        inv = [[1.0 if r == c else 0.0 for c in range(n)] for r in range(n)]

        for col in range(n):
            pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
            if a[pivot][col] == 0.0:
                raise ZeroDivisionError(
                    "AuMatrix4x4.inverse: singular matrix (column %d)" % col)
            if pivot != col:
                a[col], a[pivot] = a[pivot], a[col]
                inv[col], inv[pivot] = inv[pivot], inv[col]
            scale = 1.0 / a[col][col]
            for c in range(n):
                a[col][c] *= scale
                inv[col][c] *= scale
            for r in range(n):
                if r == col:
                    continue
                f = a[r][col]
                if f == 0.0:
                    continue
                for c in range(n):
                    a[r][c] -= f * a[col][c]
                    inv[r][c] -= f * inv[col][c]

        out = AuMatrix4x4([0.0] * 16)
        for r in range(n):
            for c in range(n):
                out.set(r, c, inv[r][c])
        return out

    def transform_point(self, p: Vec3) -> Vec3:
        x, y, z = p
        m = self.m
        return (m[0] * x + m[4] * y + m[8] * z + m[12],
                m[1] * x + m[5] * y + m[9] * z + m[13],
                m[2] * x + m[6] * y + m[10] * z + m[14])

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AuMatrix4x4):
            return NotImplemented
        return self.m == other.m

    def __repr__(self) -> str:
        rows = ["[%s]" % ", ".join("%9.4f" % self.get(r, c) for c in range(4))
                for r in range(4)]
        return "AuMatrix4x4(\n  " + "\n  ".join(rows) + "\n)"


def identity() -> AuMatrix4x4:
    return AuMatrix4x4()
