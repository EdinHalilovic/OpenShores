from __future__ import annotations

import struct

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import (
    _EMPIRE_FLAG_OVERRIDE,
    _FLAG_BY_EMPIRE_CACHE,
    _update_empire,
)

logger = get_logger(__name__)


async def _founder_of(conn: asyncpg.Connection, eid: int) -> int:
    row = await conn.fetchrow(
        'SELECT "citizens" FROM "g_Empire" WHERE "id" = $1', eid & 0xFFFFFFFF)
    blob = bytes(row[0]) if row and row[0] is not None else b""
    return struct.unpack_from(">I", blob, 4)[0] if len(blob) >= 8 else 0


async def _store_empire_flag(conn: asyncpg.Connection, empire_id: int,
                             png: bytes) -> bool:
    eid = int(empire_id) & 0xFFFFFFFF
    if not eid or not png:
        return False
    ok = await _update_empire(conn, eid, flag=png)
    _EMPIRE_FLAG_OVERRIDE[eid] = png
    _FLAG_BY_EMPIRE_CACHE.pop(eid, None)
    return ok


async def _ensure_a_city_capitol_column(conn: asyncpg.Connection) -> None:
    raise NotImplementedError(
        "The a_City.capitol ALTER moved out of the repository.")


_FOUNDED_CITY_BASE = 0x00C10000
_FOUNDED_CAPITOL_BASE = 0x00CD0000
_FOUNDED_BUILDING_BASE = 0x00CE0000


async def _sync_founding_seqs_from_db(conn: asyncpg.Connection, *,
                                      _FOUNDING_SEQ_SYNCED: list,
                                      _FOUNDED_BUILDING_SEQ: list,
                                      _FOUNDED_CITY_SEQ: list) -> None:
    if _FOUNDING_SEQ_SYNCED[0]:
        return
    _FOUNDING_SEQ_SYNCED[0] = True
    try:
        async def _maxoff(table, base, span=0x10000):
            try:
                ids = [int(r[0]) & 0xFFFFFFFF
                       for r in await conn.fetch(f'SELECT "id" FROM "{table}"')
                       if r[0] is not None]
                offs = [i - base for i in ids if base <= i < base + span]
                return max(offs) if offs else 0
            except Exception as exc:
                logger.warning("[found] seq sync: %s read failed: %r", table, exc)
                return 0
        _b = await _maxoff("a_Bd", _FOUNDED_BUILDING_BASE)
        if _b > _FOUNDED_BUILDING_SEQ[0]:
            _FOUNDED_BUILDING_SEQ[0] = _b
        _c = max(await _maxoff("a_City", _FOUNDED_CITY_BASE),
                 await _maxoff("a_Bd", _FOUNDED_CAPITOL_BASE))
        if _c > _FOUNDED_CITY_SEQ[0]:
            _FOUNDED_CITY_SEQ[0] = _c
    except Exception as exc:
        logger.warning("[found] seq sync err: %r", exc)


async def _persist_placed_building_bd(conn: asyncpg.Connection, bauid, world,
                                      xyz, yaw, name, empire, btype,
                                      design_id, report_bytes,
                                      city_id=0, city_name="") -> None:
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'a_Bd'""")}
    if "id" not in cols:
        return
    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    vals = {"id": int(bauid) & 0xFFFFFFFF, "idp": int(world) & 0xFFFFFFFF,
            "locX": x, "locY": y, "locZ": z, "rotZ": float(yaw or 0.0),
            "name": name or "", "allegiance": int(empire) & 0xFFFFFFFF,
            "industry": int(btype) & 0xFF,
            "designId": int(design_id) & 0xFFFFFFFF,
            "designRpt": bytes(report_bytes) if report_bytes else None,
            "capitol": (int(city_id) & 0xFFFFFFFF) or None,
            "cityName": city_name or None}
    vals = {k: v for k, v in vals.items() if k in cols and v is not None}
    keys = ",".join(f'"{k}"' for k in vals)
    placeholders = ",".join(f"${i + 1}" for i in range(len(vals)))
    set_clause = ", ".join(
        f'"{c}" = EXCLUDED."{c}"' if c in vals else f'"{c}" = NULL'
        for c in sorted(cols) if c != "id")
    await conn.execute(
        f'INSERT INTO "a_Bd" ({keys}) VALUES ({placeholders}) '
        f'ON CONFLICT ("id") DO UPDATE SET {set_clause}', *vals.values())
    logger.info("[place-building] persisted a_Bd row 0x%08x "
                "(industry=0x%02x rpt=%dB)", int(bauid) & 0xFFFFFFFF,
                int(btype) & 0xFF, len(report_bytes) if report_bytes else 0)


async def _ensure_doc_state_col(conn: asyncpg.Connection) -> None:
    raise NotImplementedError(
        "The g_KnownEmpireDoc DDL moved out of the repository.")
