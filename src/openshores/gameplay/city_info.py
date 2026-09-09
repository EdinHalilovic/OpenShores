
from __future__ import annotations

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.city_sim_state import (
    _load_city_founder,
    _load_city_sim_snapshot,
)
from openshores.database.repositories.city_site import _city_id_variants
from openshores.database.repositories.city_world import world_atm_type
from openshores.database.repositories.empire import read_empire_taxes
from openshores.gameplay.city_seed import _city_seed_defaults
from openshores.gameplay.city_snapshot import _split_developments

logger = get_logger(__name__)


async def _empire_tax_rates(conn: asyncpg.Connection, empire_id: int, *,
                            _EMPIRE_TAX_OVERRIDE: dict):
    eid = int(empire_id or 0) & 0xFFFFFFFF
    if not eid:
        return (0.0, 0.0)
    tax = _EMPIRE_TAX_OVERRIDE.get(eid)
    if tax is None:
        try:
            row = await read_empire_taxes(conn, eid)
            if row:
                tax = (int(row[0] or 0), int(row[1] or 0), int(row[2] or 0))
                _EMPIRE_TAX_OVERRIDE[eid] = tax
        except Exception as exc:
            logger.warning('Empire 0x%08x tax rates could not be read: %s.',
                           eid, exc)
            tax = None
    if not tax:
        return (0.0, 0.0)
    return (float(tax[0] or 0), float(tax[1] or 0))


async def _world_enclosure_needed(conn: asyncpg.Connection,
                                  world_auid: int) -> bool:
    if not world_auid:
        return False
    try:
        row = await world_atm_type(conn, world_auid)
        if row is None or row[0] is None:
            return False
        v = row[0]
        atm = v[0] if isinstance(v, (bytes, bytearray)) and v else int(v or 0)
        return int(atm) != 0
    except Exception as exc:
        logger.warning(f"[city-sim] enclosure probe failed for world "
                       f"0x{int(world_auid) & 0xFFFFFFFF:08x}: {exc!r}")
        return False


async def _city_info_from_row(conn: asyncpg.Connection, row: dict, *,
                              _EMPIRE_TAX_OVERRIDE: dict) -> dict:
    cid = int(row.get("id") or 0) & 0xFFFFFFFF
    snap, reports = await _load_city_sim_snapshot(
        conn, cid, _city_id_variants=_city_id_variants)
    _dead = bool(snap) and (int(snap.get("population", 0) or 0) == 0
                            and int(snap.get("housing_max", 0) or 0) == 0
                            and int(snap.get("building_levels", 0) or 0) == 0)
    if not snap:
        snap = _city_seed_defaults()
    elif _dead:
        snap = {**snap, **_city_seed_defaults()}
    snap["enclosure_needed"] = await _world_enclosure_needed(
        conn, int(row.get("idp") or 0) & 0xFFFFFFFF)
    _inc, _sal = await _empire_tax_rates(
        conn, int(row.get("allegiance") or 0) & 0xFFFFFFFF,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    snap["income_tax_pct"], snap["sales_tax_pct"] = _inc, _sal
    blds, roads, areas = _split_developments(row.get("developments"))
    return {
        "name": row.get("name") or "",
        "capitol": int(row.get("capitol") or 0) & 0xFFFFFFFF,
        "idp": int(row.get("idp") or 0) & 0xFFFFFFFF,
        "allegiance": int(row.get("allegiance") or 0) & 0xFFFFFFFF,
        "buildings": blds,
        "roads": roads,
        "area_ops": areas,
        "sim_snapshot": snap,
        "reports": reports or [],
        "last_report": (reports[-1] if reports else None),
        "last_result": None,
        "last_tock": int(row.get("timeTock") or 0),
        "founder": await _load_city_founder(
            conn, cid, _city_id_variants=_city_id_variants),
    }
