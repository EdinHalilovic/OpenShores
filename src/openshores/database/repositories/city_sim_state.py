
from __future__ import annotations

import json as _json
import time as _time

import asyncpg

from openshores.core.logging import get_logger

logger = get_logger(__name__)


async def _load_city_sim_snapshot(conn: asyncpg.Connection, cauid: int, *,
                                  _city_id_variants):
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'a_City'""")}
    if "sim_state" not in cols:
        return None, []
    u, sgn = _city_id_variants(cauid)
    row = await conn.fetchrow(
        'SELECT "sim_state" FROM "a_City" WHERE "id" IN ($1, $2)', u, sgn)
    if not row or not row[0]:
        return None, []
    try:
        doc = _json.loads(row[0])
        return doc.get("state"), list(doc.get("reports") or [])
    except Exception as exc:
        logger.warning('City 0x%08x has unreadable sim_state: %s.',
                       int(cauid) & 0xFFFFFFFF, exc)
        return None, []


async def _load_city_founder(conn: asyncpg.Connection, cauid: int, *,
                             _city_id_variants):
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'a_City'""")}
    if "sim_state" not in cols:
        return None
    u, sgn = _city_id_variants(cauid)
    row = await conn.fetchrow(
        'SELECT "sim_state" FROM "a_City" WHERE "id" IN ($1, $2)', u, sgn)
    if not row or not row[0]:
        return None
    try:
        return (_json.loads(row[0]) or {}).get("founder")
    except Exception:
        return None


async def _persist_city_sim(conn: asyncpg.Connection, cauid: int,
                            snapshot: dict, reports: list,
                            bump_tock: bool = True, *,
                            _city_id_variants, native_ledger_values):
    now_ms = int(_time.time() * 1000)
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'a_City'""")}
    u, sgn = _city_id_variants(cauid)
    founder = None
    _r0 = await conn.fetchrow(
        'SELECT "sim_state" FROM "a_City" WHERE "id" IN ($1, $2)', u, sgn)
    if _r0 and _r0[0]:
        founder = (_json.loads(_r0[0]) or {}).get("founder")
    _doc = {"state": snapshot, "reports": reports[-50:]}
    if founder:
        _doc["founder"] = founder
    payload = _json.dumps(_doc)
    if bump_tock:
        await conn.execute(
            'UPDATE "a_City" SET "sim_state" = $1, "timeTock" = $2 '
            'WHERE "id" IN ($3, $4)', payload, now_ms, u, sgn)
    else:
        await conn.execute(
            'UPDATE "a_City" SET "sim_state" = $1 WHERE "id" IN ($2, $3)',
            payload, u, sgn)
    vals = {c: v for c, v in native_ledger_values(snapshot).items()
            if c in cols}
    if vals:
        sets = ", ".join(f'"{c}" = ${i}' for i, c in enumerate(vals, 1))
        n = len(vals)
        await conn.execute(
            f'UPDATE "a_City" SET {sets} WHERE "id" IN (${n + 1}, ${n + 2})',
            *list(vals.values()), u, sgn)


async def city_row_for_report(conn: asyncpg.Connection, req_id: int):
    req_id = int(req_id) & 0xFFFFFFFF
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'a_City'""")}
    want = ["id", "name", "idp", "allegiance", "capitol",
            "developments", "timeTock"]
    sel = [c for c in want if c in cols]
    whr = '"id" IN ($1, $2)'
    params = [req_id, req_id]
    if "capitol" in cols:
        whr = '"id" IN ($1, $2) OR "capitol" IN ($3, $4)'
        params = [req_id, req_id, req_id, req_id]
    projection = ", ".join(f'"{c}"' for c in sel)
    return await conn.fetchrow(
        f'SELECT {projection} FROM "a_City" WHERE {whr}', *params)


async def city_roster_rows(conn: asyncpg.Connection) -> list:
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'a_City'""")}
    if "id" not in cols:
        return []
    want = ["id", "name", "idp", "allegiance", "capitol",
            "developments", "timeTock"]
    sel = [c for c in want if c in cols]
    projection = ", ".join(f'"{c}"' for c in sel)
    return [dict(zip(sel, r))
            for r in await conn.fetch(f'SELECT {projection} FROM "a_City"')]
