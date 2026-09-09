
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import city_model as _cm

logger = get_logger(__name__)


TOWN_SQUARE_CPID = 1

_WORK_BUTTON_SUBS = (0x65, 0x66)


def _is_work_button_frame(body: bytes) -> bool:
    return len(body) == 5 and body[0] in _WORK_BUTTON_SUBS


_DEMOLISH_BD_MATCH_M = 5.0
CAPITOL_INDUSTRY = 0x7B

_DEMOLISH_REFUSE_CPIDS = {0x7B, TOWN_SQUARE_CPID}


def _demolish_refuse_cpids():
    out = set(_DEMOLISH_REFUSE_CPIDS)
    try:
        out.add(int(_cm.industry_to_cpid_safe(CAPITOL_INDUSTRY,
                                              default_cpid=67)))
    except Exception:
        logger.warning("[demolish] Capitol cpid unresolved from GD; "
                       "refusing the 67 default", exc_info=True)
        out.add(67)
    return out


def _find_development_by_bauid(devs, bauid):
    b = int(bauid) & 0xFFFFFFFF
    if not b:
        return None, None
    for i, dev in enumerate(devs):
        if isinstance(dev, dict) and (int(dev.get("bauid") or 0) & 0xFFFFFFFF) == b:
            return i, dev
    return None, None


def _spawned_building_near(near_xyz, keep_id=0, *, _SPAWNED_BUILDINGS):
    if not near_xyz:
        return 0
    try:
        x, y, z = (float(v) for v in near_xyz)
    except Exception:
        logger.debug("[demolish] near_xyz is not three floats: %r",
                     near_xyz, exc_info=True)
        return 0
    m = _DEMOLISH_BD_MATCH_M
    keep = int(keep_id) & 0xFFFFFFFF
    best, best_d = 0, None
    for bauid, info in list(_SPAWNED_BUILDINGS.items()):
        if (int(bauid) & 0xFFFFFFFF) == keep:
            continue
        p = info.get("xyz")
        if not p:
            continue
        try:
            d = ((float(p[0]) - x) ** 2 + (float(p[1]) - y) ** 2
                 + (float(p[2]) - z) ** 2) ** 0.5
        except Exception:
            logger.debug("[demolish] spawned building 0x%08x has an "
                         "unusable xyz %r", int(bauid) & 0xFFFFFFFF, p,
                         exc_info=True)
            continue
        if d <= m and (best_d is None or d < best_d):
            best, best_d = int(bauid) & 0xFFFFFFFF, d
    return best
