
from __future__ import annotations

import math
import struct
import time

import asyncpg

from openshores.database.pool import Error

GAME_UNITS_PER_AU = 2_400_000.0


DDL_SIM_TIME_ANCHOR = """
CREATE TABLE IF NOT EXISTS b_SimTimeAnchor (
    id INTEGER PRIMARY KEY,
    system_auid INTEGER,
    system_name TEXT,
    anchor_ms INTEGER,
    captured_wallclock_ms INTEGER,
    total_dist_sum_au REAL,
    optimized_for_auid INTEGER,
    optimized_for_name TEXT,
    source TEXT,
    note TEXT
)
"""


async def ensure_table(conn: asyncpg.Connection) -> bool:
    row = await conn.fetchrow(
        """SELECT "table_name" FROM "information_schema"."tables"
            WHERE "table_schema" = 'public' AND "table_type" = 'BASE TABLE'
              AND "table_name" = 'b_SimTimeAnchor'""")
    return row is not None


async def upsert_anchor_row(conn, *, system_auid, system_name, anchor_ms,
                            total_dist_sum_au, optimized_for_auid,
                            optimized_for_name, wallclock_ms,
                            source="auto-optimize", note="") -> None:
    row = await conn.fetchrow(
        'SELECT "id" FROM "b_SimTimeAnchor" WHERE "system_auid" = $1 LIMIT 1',
        system_auid)
    if row is None:
        await conn.execute(
            'INSERT INTO "b_SimTimeAnchor" '
            '("system_auid", "system_name", "anchor_ms", '
            '"captured_wallclock_ms", "total_dist_sum_au", '
            '"optimized_for_auid", "optimized_for_name", '
            '"source", "note") VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)',
            system_auid, system_name, anchor_ms, wallclock_ms,
            total_dist_sum_au, optimized_for_auid, optimized_for_name,
            source, note)
    else:
        await conn.execute(
            'UPDATE "b_SimTimeAnchor" SET "anchor_ms"=$1, '
            '"captured_wallclock_ms"=$2, "total_dist_sum_au"=$3, '
            '"optimized_for_auid"=$4, "optimized_for_name"=$5, '
            '"source"=$6, "note"=$7 WHERE "id"=$8',
            anchor_ms, wallclock_ms, total_dist_sum_au,
            optimized_for_auid, optimized_for_name, source, note, row[0])


async def read_anchor_row(conn, system_auid):
    r = await conn.fetchrow(
        'SELECT "id", "system_auid", "system_name", "anchor_ms", '
        '"captured_wallclock_ms", "total_dist_sum_au", "optimized_for_auid", '
        '"optimized_for_name", "source", "note" FROM "b_SimTimeAnchor" '
        'WHERE "system_auid" = $1 LIMIT 1', system_auid)
    if r is None:
        return None
    cols = ("id", "system_auid", "system_name", "anchor_ms",
            "captured_wallclock_ms", "total_dist_sum_au",
            "optimized_for_auid", "optimized_for_name", "source", "note")
    return dict(zip(cols, r))


async def _orbit_radius_au(conn, tbl, auid):
    try:
        r = await conn.fetchrow(
            f'SELECT "orbitRadius" FROM "{tbl}" WHERE "id" = $1', auid)
    except Error:
        return 0.0
    if not r or r[0] is None:
        return 0.0
    v = r[0]
    if isinstance(v, (int, float)):
        au = float(v)
        return au if 0.05 <= au <= 1000.0 else 0.0
    if isinstance(v, (bytes, bytearray)) and len(bytes(v)) == 8:
        b = bytes(v)
        for endian in ("<d", ">d"):
            try:
                au = struct.unpack(endian, b)[0]
            except struct.error:
                continue
            if 0.05 <= au <= 1000.0:
                return au
    return 0.0


async def planets_from_sql(conn, system_auid):
    star_row = await conn.fetchrow(
        'SELECT "id" FROM "a_Star" WHERE "parent_atom" = $1 LIMIT 1',
        system_auid)
    if star_row is None:
        return
    star_auid = star_row[0]
    for tbl in ("a_WorldGlobe", "a_WorldGasGiant"):
        for row in await conn.fetch(
                f'SELECT "id", "name", "locX", "locY", "locZ", "orbitZone" '
                f'FROM "{tbl}" WHERE "parent_atom" = $1', star_auid):
            auid, name, lx, ly, lz, zone = row
            mag = math.sqrt((lx or 0) ** 2 + (ly or 0) ** 2 + (lz or 0) ** 2)
            au = mag / GAME_UNITS_PER_AU if mag > 0 else 0.0
            if au < 0.05:
                au = await _orbit_radius_au(conn, tbl, auid)
                if au < 0.05:
                    continue
            zb = 2
            if isinstance(zone, (bytes, bytearray)) and len(zone) >= 1:
                zb = zone[0]
            elif isinstance(zone, int):
                zb = zone
            elif zone is not None:
                try:
                    zb = int(zone)
                except (TypeError, ValueError):
                    zb = 2
            yield (name or f"@{auid:06x}", au, zb)


async def home_wire_position(conn: asyncpg.Connection, name: str):
    row = await conn.fetchrow(
        'SELECT "locX", "locY" FROM "a_WorldGlobe" WHERE "name" = $1 '
        'UNION ALL '
        'SELECT "locX", "locY" FROM "a_WorldGasGiant" WHERE "name" = $2 '
        'LIMIT 1',
        name, name)
    if row and row[0] is not None and row[1] is not None:
        return float(row[0]), float(row[1])
    return None


async def atom_auid_by_name(conn: asyncpg.Connection, name: str) -> int:
    row = await conn.fetchrow(
        'SELECT "id" FROM "a_WorldGlobe" WHERE "name" = $1 UNION ALL '
        'SELECT "id" FROM "a_WorldGasGiant" WHERE "name" = $2 LIMIT 1',
        name, name)
    return int(row[0]) if row else 0


async def system_row_for(conn: asyncpg.Connection, system_auid: int):
    return await conn.fetchrow(
        'SELECT "name" FROM "a_SolarSystem" WHERE "id" = $1 LIMIT 1',
        system_auid)


async def atom_name_row(conn: asyncpg.Connection, tbl: str, auid: int):
    return await conn.fetchrow(
        f'SELECT "name" FROM "{tbl}" WHERE "id" = $1', auid)


async def parent_atom_row(conn: asyncpg.Connection, tbl: str, auid: int):
    return await conn.fetchrow(
        f'SELECT "parent_atom" FROM "{tbl}" WHERE "id" = $1', auid)


async def any_system_row(conn: asyncpg.Connection):
    return await conn.fetchrow('SELECT "id" FROM "a_SolarSystem" LIMIT 1')
