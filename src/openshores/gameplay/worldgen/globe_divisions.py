
from __future__ import annotations


_GLOBE_DIVISIONS_LUT: dict[int, int] = {
    0: 0, 1: 20, 2: 40, 3: 60, 4: 80, 5: 100, 6: 120,
    7: 140, 8: 160, 9: 180, 10: 200, 11: 220, 12: 240,
}

_GLOBE_DIVISIONS_MAX_SIZE: int = max(_GLOBE_DIVISIONS_LUT)
