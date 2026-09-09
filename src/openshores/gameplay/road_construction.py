
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import empire_for_avatar
from openshores.gameplay import construction_labor, gear_wear
from openshores.gameplay.city_sim import ItemStock
from openshores.gameplay.construction_process import construction_is_complete
from openshores.gameplay.gear_entry import _gear_cid_of
from openshores.gameplay.jurisdiction import load_planet_cities
from openshores.gameplay.roads import _ROAD_STRIP_TOOLS

logger = get_logger(__name__)


_ROAD_OPTYPES = {0x0a, 0x0b, 0x0c, 0x0d}


GD_ROAD_CONSTRUCTION_COMPONENTS = {
    5: [(2, 0, 2, 0), (3, 0, 2, 1), (82, 0, 2, 0), (114, 0, 2, 0)],
    2: [(2, 0, 2, 0), (3, 0, 2, 1), (82, 0, 2, 0), (114, 0, 2, 0)],
    3: [(2, 0, 2, 0), (3, 0, 2, 1), (23, 0, 5, 1), (82, 0, 2, 0),
        (114, 0, 2, 0)],
    4: [(2, 0, 2, 0), (3, 0, 2, 1), (76, 0, 5, 1), (82, 0, 2, 0),
        (114, 0, 2, 0)],
}
ROAD_CONSTRUCTION_LABOR = 10
_ROAD_COMPEFFECT_MATERIAL = 5


def build_road_construction_demand(optype, cpid, p1, p2, width):
    if int(optype) & 0xFF not in _ROAD_OPTYPES:
        return None
    gd_rows = GD_ROAD_CONSTRUCTION_COMPONENTS.get(int(cpid) & 0x7F, [])
    try:
        length = sum((float(p1[i]) - float(p2[i])) ** 2 for i in range(3)) ** 0.5
    except Exception:
        length = 0.0
    area = max(1.0, length * float(width or 8.0))
    factor = 0.01
    strip = _ROAD_STRIP_TOOLS
    comps = []
    for (gcid, b2, eff, gqty) in gd_rows:
        if eff == _ROAD_COMPEFFECT_MATERIAL:
            cid = gcid
            req = max(1, min(9999, int(max(1, gqty) * area * factor + 0.5)))
            comps.append([cid, b2, eff, req, 0])
        elif not strip:
            comps.append([gcid, b2, eff, int(gqty), 0])
    return {"flags": 0, "procId": int(cpid) & 0x7F,
            "labor": ROAD_CONSTRUCTION_LABOR,
            "components": comps,
            "f28": 0, "f2a": 0, "flags2": 0, "designId": 0}


def build_area_construction_demand(optype):
    return {"flags": 0, "procId": int(optype) & 0x7F,
            "labor": ROAD_CONSTRUCTION_LABOR,
            "components": [],
            "f28": 0, "f2a": 0, "flags2": 0, "designId": 0}


_ROAD_INSTANT_BUILD = False


async def _iter_road_construction_jobs(*, conn, _SAVE,
                                       city_buildings_blob_io):
    wld = int(_SAVE.planet_auid) & 0xFFFFFFFF
    try:
        cities = await load_planet_cities(conn, wld)
    except Exception as exc:
        logger.error('Planet 0x%08x city read failed: %r.', wld, exc)
        cities = []
    for c in cities:
        cid = int(c["id"]) & 0xFFFFFFFF
        for dev in await city_buildings_blob_io(conn, cid):
            if dev.get("kind") in ("road", "area_op") and dev.get("cstate") \
                    and dev.get("under_construction"):
                yield (cid, c, dev)


async def _find_road_construction_job(actor_auid, *, conn, _SAVE,
                                      city_buildings_blob_io,
                                      _CITIZEN_EMPIRE_OVERRIDE):
    try:
        emp = int(await empire_for_avatar(
            conn, actor_auid,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    except Exception:
        emp = 0
    wld = int(_SAVE.planet_auid) & 0xFFFFFFFF
    cities = await load_planet_cities(conn, wld)
    for c in cities:
        if emp and (int(c.get("empire", 0)) & 0xFFFFFFFF) != emp:
            continue
        cid = int(c["id"]) & 0xFFFFFFFF
        for dev in await city_buildings_blob_io(conn, cid):
            if dev.get("kind") in ("road", "area_op") and dev.get("cstate") \
                    and dev.get("under_construction"):
                return (cid, c, dev)
    return None


async def _road_job_complete_and_reemit(cid, dev, *, conn,
                                        city_buildings_blob_io):
    rid = dev.get("rid")
    st = dev.get("cstate")
    done = bool(st) and construction_is_complete(st)

    def _mut(lst):
        for it in lst:
            if it.get("rid") == rid:
                it["cstate"] = st
                if done:
                    it.pop("under_construction", None)
                    it.pop("cstate", None)
        return lst
    await city_buildings_blob_io(conn, cid, mutate=_mut)
    return done


def make_labor_accessors(actor_auid, city_id, *, _get_augear, _CITY_SIM,
                         _push_gear_refresh):
    actor_i = int(actor_auid) & 0xFFFFFFFF
    cid_i = int(city_id) & 0xFFFFFFFF

    def _player_has(commodity):
        try:
            gear = _get_augear(actor_i)
        except Exception:
            return False
        return gear_wear.find_ready_index(gear, commodity, _gear_cid_of) >= 0

    def _player_use(commodity):
        try:
            gear = _get_augear(actor_i)
        except Exception:
            return False
        idx = gear_wear.find_ready_index(gear, commodity, _gear_cid_of)
        if idx < 0:
            return False
        code, destroyed, before, after = gear_wear.use_gear_item(gear, idx)
        if destroyed:
            logger.info("0x%08x cid 0x%x broke (condition %s -> spent); item removed", actor_i, int(commodity), before)
            _push_gear_refresh(actor_i)
        elif after != before:
            logger.debug("0x%08x cid 0x%x condition %s->%s",
                         actor_i, int(commodity), before, after)
            _push_gear_refresh(actor_i)
        return True

    def _city_has(commodity):
        try:
            info = _CITY_SIM.get(cid_i) or {}
            snap = info.get("sim_snapshot") or {}
            return int(ItemStock.from_json(snap.get("stock")).get(int(commodity)) or 0) > 0
        except Exception:
            return False

    return (_player_has, _player_use, _city_has, _city_has,
            _city_has(construction_labor.ELECTRICITY_CID))
