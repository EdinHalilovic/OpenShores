
from __future__ import annotations

from openshores.gameplay import city_model as _cm

_ROAD_STRIP_TOOLS = False

_ROAD_UNDER_CONSTRUCTION_ENABLED = True

_ROAD_AUTO_SUPPLY_ENABLED = False


def _cm_units_fpm():
    return _cm.WIRE_FEET_PER_METER


def _dev_ref_points(dev):
    pts = []
    if dev.get("xyz"):
        pts.append(tuple(float(v) for v in dev["xyz"]))
    for k in ("p1", "p2"):
        if dev.get(k):
            pts.append(tuple(float(v) for v in dev[k]))
    if dev.get("p1") and dev.get("p2"):
        pts.append(tuple((float(dev["p1"][i]) + float(dev["p2"][i])) / 2.0
                         for i in range(3)))
    return pts


def _dev_is_building(dev):
    return dev.get("kind", "building") == "building"


_DUP_PLACEMENT_M = 2.0


def _is_duplicate_placement(blds, add, radius_m=_DUP_PLACEMENT_M):
    if not isinstance(add, dict) or not _dev_is_building(add):
        return False
    xyz = add.get("xyz")
    if not xyz:
        return False
    cpid = int(add.get("cpid") or 0)
    for d in blds:
        if not isinstance(d, dict) or not _dev_is_building(d):
            continue
        if int(d.get("cpid") or 0) != cpid or not d.get("xyz"):
            continue
        dist = sum((float(xyz[i]) - float(d["xyz"][i])) ** 2
                   for i in range(3)) ** 0.5
        if dist <= radius_m:
            return True
    return False
