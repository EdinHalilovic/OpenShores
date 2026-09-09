
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import player_run as _prun
from openshores.gameplay.blueprint_lookup import (
    _mfg_industries,
    _mfg_industry_for,
)
from openshores.gameplay.city.zone import _city_zone

logger = get_logger(__name__)


_MFG_SUB_ADD = 0xF1

_MFG_SUB_TOGGLE = 0xF8

_MFG_SUB_DELETE = 0xF0
_MFG_SUB_RAISE = 0xF2
_MFG_SUB_LOWER = 0xF3

_MFG_SUBS_ADD = frozenset({_MFG_SUB_ADD, _MFG_SUB_TOGGLE})

_MFG_SUB_STOP = _MFG_SUB_DELETE

_MFG_SUBS_PRIORITY = {_MFG_SUB_RAISE: -1, _MFG_SUB_LOWER: +1}


_MFG_INDUSTRIES = _mfg_industries()


_MPROC_CFG_KEY = "mproc_cfg"


async def _mfg_resolve_target(conn, target, actor, *,
                              _bd_row_by_auid):
    if not target:
        logger.warning("Reject: command carried target AuId 0")
        return None, 0, 0
    row = await _bd_row_by_auid(conn, target)
    if row is None:
        logger.warning("Reject: target 0x%08x matches no a_Bd row",
                       target & 0xFFFFFFFF)
        return None, 0, 0
    return (row, int(row["id"]) & 0xFFFFFFFF,
            int(row.get("capitol") or 0) & 0xFFFFFFFF)


async def _mfg_set_cfg(conn, cid, bauid, mpid, key, value, *,
                       _city_buildings_blob_io, _SPAWNED_BUILDINGS):
    changed = {"ok": False, "cfg": None}

    def _mut(blds):
        for e in blds:
            if not isinstance(e, dict):
                continue
            if (int(e.get("bauid") or 0) & 0xFFFFFFFF) != bauid:
                continue
            cfg = dict(e.get(_MPROC_CFG_KEY) or {})
            one = dict(cfg.get(str(mpid)) or {})
            one[key] = int(value)
            cfg[str(mpid)] = one
            e[_MPROC_CFG_KEY] = cfg
            changed["ok"] = True
            changed["cfg"] = one
        return blds

    if cid:
        await _city_buildings_blob_io(conn, cid, mutate=_mut)
    try:
        info = _SPAWNED_BUILDINGS.get(bauid)
        if info is not None:
            cfg = dict(info.get(_MPROC_CFG_KEY) or {})
            one = dict(cfg.get(str(mpid)) or {})
            one[key] = int(value)
            cfg[str(mpid)] = one
            info[_MPROC_CFG_KEY] = cfg
            changed["cfg"] = one
    except Exception as exc:
        logger.warning("Live cfg mirror err: %r", exc)
    return changed


_MFG_RUN_TASKS: dict = {}


async def _mfg_environment_pass(conn, *, _CITY_SIM, _ZONE_CACHE,
                                _city_buildings_blob_io):
    for cid in list(_CITY_SIM):
        cid = int(cid) & 0xFFFFFFFF
        try:
            zone = await _city_zone(conn, cid, _ZONE_CACHE=_ZONE_CACHE,
                                    _CITY_SIM=_CITY_SIM)
        except Exception as exc:
            logger.debug("Zone for city 0x%08x did not resolve; "
                         "skipped. %r", cid, exc)
            continue
        if zone is None:
            continue
        devs = (await _city_buildings_blob_io(conn, cid)) or []
        for dev in devs:
            if not isinstance(dev, dict):
                continue
            mpids = dev.get("manproc") or []
            if not mpids:
                continue
            bauid = int(dev.get("bauid") or 0) & 0xFFFFFFFF
            industry = _mfg_industry_for(dev)
            cfg = dev.get(_MPROC_CFG_KEY) or {}
            for mpid in mpids:
                one = dict(cfg.get(str(mpid)) or {})
                if int(one.get("deadline") or 0):
                    continue
                before = dict(one.get("have") or {})
                after = _prun.gather(int(mpid), zone=zone, industry=industry,
                                     shops=int(one.get("shops") or 1),
                                     have=before)
                if after is None or after == before:
                    continue
                await _mfg_set_cfg_map(
                    conn, cid, bauid, int(mpid), "have", after,
                    _city_buildings_blob_io=_city_buildings_blob_io)
                if (_prun.environment_satisfied(int(mpid), after,
                                                shops=int(one.get("shops") or 1))
                        and not _prun.environment_satisfied(
                            int(mpid), before, shops=int(one.get("shops") or 1))):
                    logger.info("0x%08x mpid %s: environment satisfied (%s). The line can run now",
                                bauid, mpid, after)


async def _mfg_dev_for(conn, cid, bauid, *, _city_buildings_blob_io):
    for e in ((await _city_buildings_blob_io(conn, cid)) or []):
        if isinstance(e, dict) and (int(e.get("bauid") or 0) & 0xFFFFFFFF) == bauid:
            return e
    return None


async def _mfg_set_cfg_map(conn, cid, bauid, mpid, key, value, *,
                           _city_buildings_blob_io):
    def _mut(blds):
        for e in blds:
            if not isinstance(e, dict):
                continue
            if (int(e.get("bauid") or 0) & 0xFFFFFFFF) != bauid:
                continue
            cfg = dict(e.get(_MPROC_CFG_KEY) or {})
            one = dict(cfg.get(str(mpid)) or {})
            one[key] = value
            cfg[str(mpid)] = one
            e[_MPROC_CFG_KEY] = cfg
        return blds

    if cid:
        await _city_buildings_blob_io(conn, cid, mutate=_mut)
