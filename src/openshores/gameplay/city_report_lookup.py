
from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.city_sim_state import city_row_for_report

logger = get_logger(__name__)


async def _lookup_city_for_report(conn: asyncpg.Connection, req_id: int, *,
                                  _CITY_SIM, _city_info_from_row):
    req_id = int(req_id) & 0xFFFFFFFF
    if req_id in _CITY_SIM:
        return req_id, _CITY_SIM[req_id]
    for cid, inf in _CITY_SIM.items():
        if int(inf.get("capitol", 0)) & 0xFFFFFFFF == req_id:
            return cid, inf
    if len(_CITY_SIM) == 1:
        return next(iter(_CITY_SIM.items()))
    try:
        r = await city_row_for_report(conn, req_id)
        if r:
            info = await _city_info_from_row(conn, dict(r))
            return int(dict(r).get("id") or req_id) & 0xFFFFFFFF, info
    except Exception as exc:
        logger.warning('City 0x%08x could not be read for its report: %s.',
                       req_id, exc)
    return None, None
