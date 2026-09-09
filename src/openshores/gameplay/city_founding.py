from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import city_model as _cm
from openshores.gameplay import jurisdiction as _juris
from openshores.gameplay.design_requests import _select_capitol_blueprint
from openshores.gameplay.development_lookup import TOWN_SQUARE_CPID
from openshores.protocol.atoms.building import TOWN_SQUARE_DESIGN_ID

logger = get_logger(__name__)


_FOUNDED_CITY_SEQ = [0]


async def _load_capitol_blueprint_report(conn, selector=None, payload=None,
                                         design_serial=None):
    try:
        bp = await _select_capitol_blueprint(conn, selector=selector,
                                            payload=payload,
                                            design_serial=design_serial)
    except Exception as exc:
        logger.error(f"[found-city] blueprint load err: {exc!r}")
        bp = None
    if not bp:
        return None, "", 0, b"", 0
    return bp["report"], bp["name"], bp["design_id"], bp["cblob"], bp["dmat"]


_FOUNDED_BUILDING_SEQ = [0]


async def _find_city_for_building(conn, world, empire, xyz):
    cities = await _juris.load_planet_cities(conn, int(world) & 0xFFFFFFFF)
    r2 = _juris.default_radius_m() ** 2
    best = None
    best_d = None
    emp = int(empire) & 0xFFFFFFFF
    for c in cities:
        if (int(c.get("empire", 0)) & 0xFFFFFFFF) != emp:
            continue
        d = sum((float(xyz[i]) - float((c["x"], c["y"], c["z"])[i])) ** 2 for i in range(3))
        if d <= r2 and (best_d is None or d < best_d):
            best, best_d = c, d
    return best


_FOUNDING_SEQ_SYNCED = [False]


def _town_square_bld(info):
    lat, lon = _cm.xyz_to_latlon(info["xyz"])
    return {"type": _cm.DEV_BUILDING, "cpid": TOWN_SQUARE_CPID, "lat": lat,
            "lon": lon, "facing": float(info.get("yaw", 0.0) or 0.0), "levels": 1,
            "design_id": TOWN_SQUARE_DESIGN_ID,
            "xyz": tuple(float(v) for v in info["xyz"]), "style": "old"}
