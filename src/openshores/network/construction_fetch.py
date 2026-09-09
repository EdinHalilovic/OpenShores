
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.bd_design import _persist_building_cstate
from openshores.gameplay.construction_process import construction_is_complete
from openshores.gameplay.construction_site import (
    _COMPEFFECT_DECREASES_TIME,
    _active_construction_job,
    _city_stock_has_commodity,
    _cname,
    _zone_supplies_commodity,
)
from openshores.gameplay.gear_entry import _gear_cid_of
from openshores.network.building_broadcast import _construction_rebroadcast
from openshores.network.construction_finish import _construction_finish

logger = get_logger(__name__)


async def fetch_construction_materials(actor_auid: int, *, _get_augear,
                                       _push_augear_refresh_for,
                                       _live_avatars, _SPAWNED_BUILDINGS,
                                       _BUILDING_KEEPALIVE_TASKS,
                                       conn, _CITY_SIM,
                                       _ZONE_CACHE,
                                       anchor_full) -> bool:
    job = _active_construction_job(actor_auid,
                                   _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                                   _live_avatars=_live_avatars)
    if job is None:
        logger.debug("Fetch: no active construction job for 0x%08x",
                     actor_auid & 0xFFFFFFFF)
        return False
    bauid, info = job
    st = info["cstate"]
    gear = _get_augear(actor_auid)
    _gcids = sorted({(_gear_cid_of(e) & 0xFFFF) for e in gear if _gear_cid_of(e) >= 0})
    logger.debug("Fetch: job 0x%08x demand=%s inv_cids=%s", bauid,
                 [(hex(c[0] & 0xFFFF), "eff" + str(c[2]),
                   str(c[4]) + "/" + str(c[3])) for c in st["components"]],
                 [hex(c) for c in _gcids])
    moved = 0
    for comp in st["components"]:
        cid, b2, eff, req, applied = comp
        if eff == 5 and req > 0:
            if applied >= req:
                continue
            need = req - applied
            avail = [e for e in gear if int(e[2]) == 0x01 and _gear_cid_of(e) == cid]
            take = min(need, len(avail))
            if take > 0:
                drop = {id(e) for e in avail[:take]}
                gear[:] = [e for e in gear if id(e) not in drop]
                comp[4] = applied + take
                moved += take
                logger.info("0x%08x fetched %dx cid%s (%s/%s) from 0x%08x gear",
                            bauid, take, cid, comp[4], req, actor_auid)
        else:
            reqn = max(int(req), 1)
            if applied >= reqn:
                continue
            where = None
            if any(_gear_cid_of(e) == cid for e in gear):
                where = "inventory"
            elif await _city_stock_has_commodity(conn, info, cid,
                                                 _CITY_SIM=_CITY_SIM):
                where = "city-stock"
            elif await _zone_supplies_commodity(info, cid, conn,
                                                _ZONE_CACHE=_ZONE_CACHE,
                                                _CITY_SIM=_CITY_SIM):
                where = "zone"
            if where:
                comp[4] = reqn
                moved += 1
                logger.debug("0x%08x tool %s (eff%s) satisfied by presence in "
                             "%s (not consumed)", bauid, _cname(cid), eff, where)
            elif int(eff) == _COMPEFFECT_DECREASES_TIME:
                logger.debug('0x%08x boost %s (eff%s) unavailable.',
                             bauid, _cname(cid), eff)
            else:
                logger.warning("0x%08x tool %s (eff%s) not found in inventory, city-stock or zone", bauid, _cname(cid), eff)
    if moved:
        try:
            await _push_augear_refresh_for(actor_auid, log_prefix="construct-fetch")
        except Exception:
            logger.exception("Gear refresh err for 0x%08x", actor_auid)
        if construction_is_complete(st):
            await _construction_finish(
                bauid, info, _live_avatars=_live_avatars,
                _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                _BUILDING_KEEPALIVE_TASKS=_BUILDING_KEEPALIVE_TASKS,
                conn=conn, _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                anchor_full=anchor_full)
        else:
            await _persist_building_cstate(conn, bauid, st)
            await _construction_rebroadcast(
                bauid, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                _live_avatars=_live_avatars, conn=conn,
                _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
                anchor_full=anchor_full)
    return bool(moved)
