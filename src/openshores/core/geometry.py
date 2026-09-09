
from __future__ import annotations


def _point_segment_distance(pos, a, b):
    ax, ay, az = (float(v) for v in a)
    bx, by, bz = (float(v) for v in b)
    px, py, pz = (float(v) for v in pos)
    dx, dy, dz = bx - ax, by - ay, bz - az
    denom = dx * dx + dy * dy + dz * dz
    if denom <= 0.0:
        t = 0.0
    else:
        t = ((px - ax) * dx + (py - ay) * dy + (pz - az) * dz) / denom
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    cx, cy, cz = ax + dx * t, ay + dy * t, az + dz * t
    return ((px - cx) ** 2 + (py - cy) ** 2 + (pz - cz) ** 2) ** 0.5
