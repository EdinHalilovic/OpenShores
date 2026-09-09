
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.gameplay import construction_labor as _cl
from openshores.gameplay import gear_wear as _gw
from openshores.gameplay.construction_process import construction_is_complete
from openshores.gameplay.construction_site import (
    _active_construction_job,
    _city_stock_has_commodity,
)
from openshores.gameplay.gear_entry import _gear_cid_of
from openshores.network.building_broadcast import _construction_rebroadcast
from openshores.network.construction_finish import _construction_finish

logger = get_logger(__name__)


async def apply_construction_labor(actor_auid: int, units: int = 0, *,
                                   _get_augear,
                                   _push_augear_refresh_for, _live_avatars,
                                   _SPAWNED_BUILDINGS,
                                   _BUILDING_KEEPALIVE_TASKS, conn,
                                   _ZONE_CACHE, _CITY_SIM,
                                   anchor_full) -> bool:
    job = _active_construction_job(actor_auid,
                                   _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
                                   _live_avatars=_live_avatars)
    if job is None:
        return False
    bauid, info = job
    st = info["cstate"]
    comps = st.get("components") or []
    if units <= 0:
        actor_i = int(actor_auid) & 0xFFFFFFFF

        def _p_has(commodity):
            try:
                gear = _get_augear(actor_i)
            except Exception:
                return False
            return _gw.find_ready_index(gear, commodity, _gear_cid_of) >= 0

        def _p_use(commodity):
            try:
                gear = _get_augear(actor_i)
            except Exception:
                return False
            idx = _gw.find_ready_index(gear, commodity, _gear_cid_of)
            if idx < 0:
                return False
            code, destroyed, before, after = _gw.use_gear_item(gear, idx)
            if destroyed:
                logger.info(f"[gear-wear] 0x{actor_i:08x} cid 0x{int(commodity):x} broke (condition {before} -> spent).")
            elif after != before:
                logger.debug(f"[gear-wear] 0x{actor_i:08x} cid 0x{int(commodity):x} "
                             f"condition {before}->{after}")
            if destroyed or after != before:
                try:
                    asyncio.get_running_loop().create_task(
                        _push_augear_refresh_for(actor_i,
                                                 log_prefix="gear-wear"))
                except Exception as exc:
                    logger.debug(f"[gear-wear] 0x{actor_i:08x} gear refresh not "
                                 f"scheduled: {exc!r}")
            return True

        _stock = {}
        for _c in ({(int(c[0]) & 0xFFFF) for c in comps}
                   | {_cl.ELECTRICITY_CID}):
            _stock[_c] = await _city_stock_has_commodity(conn, info, _c,
                                                         _CITY_SIM=_CITY_SIM)

        def _c_has(commodity):
            return _stock.get(int(commodity) & 0xFFFF, False)

        units, blocked = _cl.labor_units_for_work(
            comps, player_has=_p_has, player_use=_p_use,
            city_has=_c_has, city_use=_c_has,
            city_power=_c_has(_cl.ELECTRICITY_CID))
        if blocked:
            logger.warning(f"[capitol-build] 0x{bauid:08x} blocked: required {[hex(b) for b in blocked]} not in worker gear or city stock. No labor applied ({_cl.describe(comps)})")
            return False
    before, after, applied = _cl.apply_labor(st, units)
    if applied <= 0:
        return False
    logger.info(f"[capitol-build] 0x{bauid:08x} labor {before}->{after} "
                f"(-{applied}) by 0x{actor_auid:08x}")
    if construction_is_complete(st):
        await _construction_finish(
            bauid, info, _live_avatars=_live_avatars,
            _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
            _BUILDING_KEEPALIVE_TASKS=_BUILDING_KEEPALIVE_TASKS,
            conn=conn, _ZONE_CACHE=_ZONE_CACHE, _CITY_SIM=_CITY_SIM,
            anchor_full=anchor_full)
    else:
        await _construction_rebroadcast(
            bauid, _SPAWNED_BUILDINGS=_SPAWNED_BUILDINGS,
            _live_avatars=_live_avatars, conn=conn, _ZONE_CACHE=_ZONE_CACHE,
            _CITY_SIM=_CITY_SIM, anchor_full=anchor_full)
    return True
