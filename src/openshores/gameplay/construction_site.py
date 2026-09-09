
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.bd_design import _persist_building_cstate
from openshores.gameplay import jurisdiction as _juris
from openshores.gameplay.city import zone as _czone
from openshores.gameplay.city_sim import ItemStock
from openshores.gameplay.worldgen import zone_resources as _zr
from openshores.gameplay.gd_tables import commodity_name

logger = get_logger(__name__)


_COMPEFFECT_DECREASES_TIME = 2


async def _city_stock_has_commodity(conn, bld_info, cid, *, _CITY_SIM) -> bool:
    try:
        xyz = bld_info.get("xyz")
        world = int(bld_info.get("parent", 0)) & 0xFFFFFFFF
        if not xyz or not world:
            return False
        r2 = _juris.default_radius_m() ** 2
        best = None
        for c in await _juris.load_planet_cities(conn, world):
            d = sum((float(xyz[i]) - float((c["x"], c["y"], c["z"])[i])) ** 2 for i in range(3))
            if d <= r2:
                best = c
                break
        if not best:
            return False
        info = _CITY_SIM.get(int(best["id"]) & 0xFFFFFFFF) or {}
        snap = info.get("sim_snapshot") or {}
        return int(ItemStock.from_json(snap.get("stock")).get(int(cid) & 0xFFFF) or 0) > 0
    except Exception:
        return False


def _active_construction_job(actor_auid: int = 0, *, _SPAWNED_BUILDINGS,
                             _live_avatars):
    cands = [(b, i) for b, i in _SPAWNED_BUILDINGS.items()
             if i.get("cstate") is not None]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    ref = (_live_avatars.get(int(actor_auid) & 0xFFFFFFFF) or {}).get("xyz")
    if not ref:
        logger.warning('%d live construction sites and no position for actor 0x%08x.',
                       len(cands), int(actor_auid) & 0xFFFFFFFF)
        return cands[0]

    def _d2(item):
        xyz = item[1].get("xyz") or (0.0, 0.0, 0.0)
        return sum((float(xyz[i]) - float(ref[i])) ** 2 for i in range(3))

    return min(cands, key=_d2)


def _cname(cid) -> str:
    return f"{commodity_name(cid)} (cid 0x{int(cid) & 0xFFFF:x})"


async def _city_auid_for_building(conn, bld_info):
    try:
        xyz = bld_info.get("xyz")
        world = int(bld_info.get("parent", 0)) & 0xFFFFFFFF
        if not xyz or not world:
            return 0
        r2 = _juris.default_radius_m() ** 2
        for c in await _juris.load_planet_cities(conn, world):
            d = sum((float(xyz[i]) - float((c["x"], c["y"], c["z"])[i])) ** 2
                    for i in range(3))
            if d <= r2:
                return int(c["id"]) & 0xFFFFFFFF
    except Exception as exc:                            # noqa: BLE001
        logger.debug("No jurisdiction for building %r: %r",
                     bld_info.get("auid", bld_info.get("parent")), exc)
    return 0


async def _zone_supplies_commodity(bld_info, cid, conn, *,
                                   _ZONE_CACHE: dict,
                                   _CITY_SIM: dict) -> bool:
    try:
        cauid = await _city_auid_for_building(conn, bld_info)
        if not cauid:
            return False
        zone = await _czone._city_zone(conn, cauid,
                                       _ZONE_CACHE=_ZONE_CACHE,
                                       _CITY_SIM=_CITY_SIM)
        if zone is None:
            return False
        if zone is None:
            return False
        return int(_zr.fetch_probability(zone, int(cid) & 0xFFFF) or 0) > 0
    except Exception as exc:                            # noqa: BLE001
        logger.warning("Zone probe failed for cid 0x%04x: %r",
                       int(cid) & 0xFFFF, exc)
        return False


async def _persist_completed_building(conn, bauid: int, info: dict) -> None:
    info["completed"] = True
    await _persist_building_cstate(conn, bauid, None)
