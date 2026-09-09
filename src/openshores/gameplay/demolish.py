
from __future__ import annotations

from openshores.core.geometry import _point_segment_distance
from openshores.gameplay.development_lookup import TOWN_SQUARE_CPID
from openshores.gameplay.roads import _dev_is_building, _dev_ref_points


_DEMOLISH_REFUSE_CPIDS = {0x7B, TOWN_SQUARE_CPID}


def _dev_distance(dev, pos):
    if dev.get("p1") and dev.get("p2"):
        return _point_segment_distance(pos, dev["p1"], dev["p2"])
    best = None
    for pt in _dev_ref_points(dev):
        d = sum((float(pos[j]) - pt[j]) ** 2 for j in range(3)) ** 0.5
        if best is None or d < best:
            best = d
    return best


def _nearest_development(devs, pos, buildings_only=False):
    best = (None, None, None)
    for i, dev in enumerate(devs):
        if not isinstance(dev, dict):
            continue
        if buildings_only and not _dev_is_building(dev):
            continue
        d = _dev_distance(dev, pos)
        if d is None:
            continue
        if best[2] is None or d < best[2]:
            best = (i, dev, d)
    return best
