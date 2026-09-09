
from __future__ import annotations

CHAT_RANGE_CLOSE_M = 1000.0
CHAT_RANGE_HAIL_M = 600000.0


def _chat_dist3(a, b):
    if not a or not b or len(a) < 3 or len(b) < 3:
        return float('inf')
    try:
        dx = float(a[0]) - float(b[0])
        dy = float(a[1]) - float(b[1])
        dz = float(a[2]) - float(b[2])
        return (dx * dx + dy * dy + dz * dz) ** 0.5
    except Exception:
        return float('inf')


def _chat_passes_range(max_range, sender_xyz, peer_xyz):
    r = int(max_range) & 0x0F
    if r == 0:
        return _chat_dist3(sender_xyz, peer_xyz) < CHAT_RANGE_CLOSE_M
    if r == 1:
        return _chat_dist3(sender_xyz, peer_xyz) < CHAT_RANGE_HAIL_M
    return True
