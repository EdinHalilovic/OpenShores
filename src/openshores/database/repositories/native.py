
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.pool import _now_ms
from openshores.database.repositories.person import _rows_affected

logger = get_logger(__name__)


NATIVE_AUID_BASE = 0x7B000000
NATIVE_AUID_LIMIT = 0x7C000000
NATIVE_BLOCK_SIZE = 64


NATIVE_COLUMNS: Tuple[Tuple[str, str, str], ...] = (
    ("id",              "INTEGER", "+0x14 AuId; toUInt"),
    ("idp",             "INTEGER", "DaAtom::ParentId(); LoadSubatoms WHERE key"),
    ("locX",            "REAL",    "Location().x; toDouble"),
    ("locY",            "REAL",    "Location().y; toDouble"),
    ("locZ",            "REAL",    "Location().z; toDouble"),
    ("rotX",            "REAL",    "Rotation().x; toDouble"),
    ("rotY",            "REAL",    "Rotation().y; toDouble"),
    ("rotZ",            "REAL",    "Rotation().z; toDouble -- the heading"),
    ("timeCreate",      "INTEGER", "+0x20 AuTime; epoch-ms here (deviation 1)"),
    ("timeModified",    "INTEGER", "+0x1a0 AuTime"),
    ("timeTick",        "INTEGER", "+0x1e8 AuTime"),
    ("timeTock",        "INTEGER", "+0x1f8 AuTime"),
    ("timeDeath",       "INTEGER", "+0x50 AuTime"),
    ("name",            "TEXT",    "DaUnit::AssignedName(); toString"),
    ("allegiance",      "INTEGER", "+0x3b8; toUInt"),
    ("arenaTeam",       "INTEGER", "+0x3a8 u8; toUInt"),
    ("conditions",      "BLOB",    "AuConditionList QDataStream v7 (deviation 2)"),
    ("damageHistory",   "BLOB",    "i32 count + N*(AuId,rec) v7 (deviation 2)"),
    ("hunger",          "INTEGER", "+0x4610 u16; toInt, <1 clamps to 0"),
    ("seatIndex",       "INTEGER", "+0x491 u8; toInt"),
    ("hp",              "INTEGER", "+0x4cc i16; toInt -> SetHitPoints"),
    ("sex",             "INTEGER", "+0x4f8 u8; toInt.  UPDATE never touches it"),
    ("dna",             "BLOB",    "24 raw bytes from +0x4ac.  Write-once"),
    ("islefty",         "INTEGER", "+0x4ce; toBool.  Write-once"),
    ("pose",            "INTEGER", "+0x4dc general pose; toInt -> SetGeneralPose"),
    ("whichConsole",    "INTEGER", "+0x494 i16; toInt"),
    ("atRest",          "INTEGER", "+0x11; toBool.  base-flag bit 5 on the wire"),
    ("vecX",            "REAL",    "+0x370 velocity; toDouble"),
    ("vecY",            "REAL",    "+0x378; toDouble"),
    ("vecZ",            "REAL",    "+0x380; toDouble"),
    ("stamina",         "INTEGER", "+0x492 u8; toInt"),
    ("minsToFullGrown", "INTEGER", "+0x490 u8; toUInt"),
    ("lineage",         "INTEGER", "+0x4770 u8; toUInt"),
    ("ship",            "INTEGER", "+0x4774 AuId; toUInt.  schema.sql BLOB is wrong"),
    ("orders",          "BLOB",    "order list v7 blob.  schema.sql INTEGER is wrong"),
    ("posture",         "INTEGER", "+0x4690 CITIZEN_POSTURE.  schema.sql BLOB is wrong"),
    ("inv",             "BLOB",    "AuGear v7 blob (deviation 2)"),
    ("homeworld",       "INTEGER", "+0x47a0 AuId; toUInt"),
    ("interlocutor",    "INTEGER", "+0x4728 AuId; toUInt (DaSentient::Interlocutor)"),
    ("role",            "INTEGER", "+0x47a4 INDI_ROLE u8; toUInt"),
)

NATIVE_COLUMN_NAMES: Tuple[str, ...] = tuple(c for c, _, _ in NATIVE_COLUMNS)

NATIVE_WRITE_ONCE: frozenset = frozenset(
    ("id", "timeCreate", "sex", "dna", "islefty"))


def _u32(v: Any) -> int:
    return int(v or 0) & 0xFFFFFFFF


async def _table_exists(conn: asyncpg.Connection, name: str) -> bool:
    return await conn.fetchval(
        'SELECT 1 FROM "information_schema"."tables" '
        "WHERE \"table_schema\" = 'public' AND \"table_name\" = $1",
        name) is not None


async def _declared_types(conn: asyncpg.Connection,
                          table: str) -> Dict[str, str]:
    return {row[0]: (row[1] or "").upper()
            for row in await conn.fetch(
                'SELECT "column_name", "data_type" '
                'FROM "information_schema"."columns" '
                "WHERE \"table_schema\" = 'public' AND \"table_name\" = $1",
                table)}


async def allocate_block(conn: asyncpg.Connection,
                         world_auid: int) -> Optional[int]:
    w = _u32(world_auid)
    row = await conn.fetchrow('SELECT "auid_block" FROM "hz_native_village" '
                              'WHERE "world_auid" = $1', w)
    if row is not None:
        block = int(row[0])
    else:
        row = await conn.fetchrow(
            'SELECT COALESCE(MAX("auid_block"), -1) FROM "hz_native_village"')
        block = int(row[0]) + 1
        await conn.execute(
            'INSERT INTO "hz_native_village" '
            '("world_auid", "auid_block", "timeCreate", "timeModified") '
            'VALUES ($1, $2, $3, $4)',
            w, block, _now_ms(), _now_ms())
    base = NATIVE_AUID_BASE + block * NATIVE_BLOCK_SIZE
    if base + NATIVE_BLOCK_SIZE > NATIVE_AUID_LIMIT:
        raise ValueError(
            "Native AuId space exhausted: block %d would run past 0x%08X" % (block, NATIVE_AUID_LIMIT))
    return base


def _row_out(cur_row: Sequence[Any]) -> Dict[str, Any]:
    d = dict(zip(NATIVE_COLUMN_NAMES, cur_row))
    for k in ("dna", "conditions", "damageHistory", "orders", "inv"):
        if d.get(k) is not None:
            d[k] = bytes(d[k])
    return d


async def save_village(conn: asyncpg.Connection, world_auid: int,
                       rows: Sequence[Dict[str, Any]], *,
                       seed: Optional[int] = None,
                       dna: Optional[bytes] = None,
                       centre_xyz: Optional[Sequence[float]] = None,
                       homes: Optional[Dict[int, Dict[str, Any]]] = None,
                       replace: bool = True) -> int:
    w = _u32(world_auid)
    now = _now_ms()
    cols = list(NATIVE_COLUMN_NAMES)
    collist = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
    set_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"'
                           for c in cols if c != "id")
    stmt = (f'INSERT INTO "a_CitIndigenous" ({collist}) '
            f'VALUES ({placeholders}) '
            f'ON CONFLICT ("id") DO UPDATE SET {set_clause}')
    keep: List[int] = []
    for r in rows:
        r = dict(r)
        r.setdefault("idp", w)
        r["idp"] = _u32(r["idp"])
        r["timeModified"] = now
        keep.append(_u32(r["id"]))
        await conn.execute(stmt, *[r.get(c) for c in cols])

        h = (homes or {}).get(_u32(r["id"]))
        if h is None:
            home = (r["locX"], r["locY"], r["locZ"])
            heading = float(r.get("rotZ") or 0.0)
            label = str(r.get("name") or "")
            tilt = 0.0
        else:
            home = h.get("home", (r["locX"], r["locY"], r["locZ"]))
            heading = float(h.get("heading", r.get("rotZ") or 0.0))
            label = str(h.get("label") or r.get("name") or "")
            tilt = float(h.get("tilt") or 0.0)
        await conn.execute(
            'INSERT INTO "hz_native_home" '
            '("id", "world_auid", "label", "homeX", "homeY", "homeZ", '
            '"heading", "tilt") '
            'VALUES ($1, $2, $3, $4, $5, $6, $7, $8) '
            'ON CONFLICT ("id") DO UPDATE SET '
            '"world_auid" = EXCLUDED."world_auid", '
            '"label" = EXCLUDED."label", "homeX" = EXCLUDED."homeX", '
            '"homeY" = EXCLUDED."homeY", "homeZ" = EXCLUDED."homeZ", '
            '"heading" = EXCLUDED."heading", "tilt" = EXCLUDED."tilt"',
            _u32(r["id"]), w, label,
            float(home[0]), float(home[1]), float(home[2]), heading,
            tilt)

    if replace and keep:
        await conn.execute('DELETE FROM "a_CitIndigenous" WHERE "idp" = $1 '
                           'AND "id" <> ALL($2::bigint[])', w, keep)
        await conn.execute('DELETE FROM "hz_native_home" '
                           'WHERE "world_auid" = $1 '
                           'AND "id" <> ALL($2::bigint[])', w, keep)

    base = await allocate_block(conn, w)
    await conn.execute(
        'UPDATE "hz_native_village" SET "seed" = COALESCE($1, "seed"), '
        '"pop" = $2, "dna" = COALESCE($3, "dna"), '
        '"centreX" = COALESCE($4, "centreX"), '
        '"centreY" = COALESCE($5, "centreY"), '
        '"centreZ" = COALESCE($6, "centreZ"), "timeModified" = $7 '
        'WHERE "world_auid" = $8',
        None if seed is None else int(seed),
        len(keep),
        None if dna is None else bytes(dna),
        None if centre_xyz is None else float(centre_xyz[0]),
        None if centre_xyz is None else float(centre_xyz[1]),
        None if centre_xyz is None else float(centre_xyz[2]),
        now, w)
    logger.info("Saved %d villager(s) for world 0x%08X, AuId base 0x%08X.",
                len(keep), w, base or 0)
    return len(keep)


async def load_village(conn: asyncpg.Connection,
                       world_auid: int) -> Optional[Dict[str, Any]]:
    if not await _table_exists(conn, "a_CitIndigenous"):
        return None
    have = set(await _declared_types(conn, "a_CitIndigenous"))
    if not set(NATIVE_COLUMN_NAMES).issubset(have):
        logger.warning(
            'a_CitIndigenous is missing %d column(s).',
            len(set(NATIVE_COLUMN_NAMES) - have))
        return None
    w = _u32(world_auid)
    collist = ", ".join(f'"{c}"' for c in NATIVE_COLUMN_NAMES)
    cur = await conn.fetch(
        f'SELECT {collist} FROM "a_CitIndigenous" '
        f'WHERE "idp" = $1 ORDER BY "id"', w)
    rows = [_row_out(r) for r in cur]
    if not rows:
        return None

    homes: Dict[int, Dict[str, Any]] = {}
    if await _table_exists(conn, "hz_native_home"):
        _has_tilt = "tilt" in await _declared_types(conn, "hz_native_home")
        _tilt_col = '"tilt"' if _has_tilt else "0.0"
        for r in await conn.fetch(
                f'SELECT "id", "label", "homeX", "homeY", "homeZ", "heading", '
                f'{_tilt_col} FROM "hz_native_home" WHERE "world_auid" = $1',
                w):
            homes[int(r[0])] = {
                "label": r[1] or "",
                "home": (float(r[2] or 0.0), float(r[3] or 0.0),
                         float(r[4] or 0.0)),
                "heading": float(r[5] or 0.0),
                "tilt": float(r[6] or 0.0),
            }
    meta = (None if not await _table_exists(conn, "hz_native_village") else
            await conn.fetchrow('SELECT "auid_block", "seed", "pop", "dna", '
                                '"centreX", "centreY", "centreZ" '
                                'FROM "hz_native_village" '
                                'WHERE "world_auid" = $1', w))
    if meta is None:
        block, seed, pop, vdna, cx, cy, cz = 0, None, len(rows), None, \
            None, None, None
    else:
        block, seed, pop, vdna, cx, cy, cz = meta
    return {
        "world_auid": w,
        "auid_base": NATIVE_AUID_BASE + int(block or 0) * NATIVE_BLOCK_SIZE,
        "seed": None if seed is None else int(seed),
        "pop": int(pop or len(rows)),
        "dna": None if vdna is None else bytes(vdna),
        "centre_xyz": (None if cx is None
                       else (float(cx), float(cy), float(cz))),
        "rows": rows,
        "homes": homes,
    }


async def delete_village(conn: asyncpg.Connection, world_auid: int) -> int:
    w = _u32(world_auid)
    n = 0
    if await _table_exists(conn, "a_CitIndigenous"):
        status = await conn.execute(
            'DELETE FROM "a_CitIndigenous" WHERE "idp" = $1', w)
        n = _rows_affected(status)
    if await _table_exists(conn, "hz_native_home"):
        await conn.execute('DELETE FROM "hz_native_home" '
                           'WHERE "world_auid" = $1', w)
    return n


async def update_native(conn: asyncpg.Connection, auid: int, **fields) -> bool:
    if not fields:
        return False
    if not await _table_exists(conn, "a_CitIndigenous"):
        return False
    valid = set(await _declared_types(conn, "a_CitIndigenous"))
    clean = {k: v for k, v in fields.items()
             if k in valid and k not in NATIVE_WRITE_ONCE}
    if not clean:
        return False
    clean.setdefault("timeModified", _now_ms())
    parts = ", ".join(f'"{k}" = ${i}' for i, k in enumerate(clean, 1))
    vals = list(clean.values()) + [_u32(auid)]
    status = await conn.execute(
        f'UPDATE "a_CitIndigenous" SET {parts} WHERE "id" = ${len(vals)}',
        *vals)
    return _rows_affected(status) > 0


async def set_interlocutor(conn: asyncpg.Connection, native_auid: int,
                           target_auid: int) -> bool:
    return await update_native(conn, native_auid,
                               interlocutor=_u32(target_auid))


async def world_native_ids(conn: asyncpg.Connection, world_auid: int) -> set:
    return {int(r[0]) for r in await conn.fetch(
        'SELECT "id" FROM "a_CitIndigenous" WHERE "idp" = $1',
        _u32(world_auid))}


async def store_interlocutors(conn: asyncpg.Connection,
                              pairs: Sequence[Tuple[int, int]]) -> int:
    now = _now_ms()
    n_nat = 0
    for aid, who in pairs:
        await conn.execute('UPDATE "a_CitIndigenous" SET "interlocutor" = $1, '
                           '"timeModified" = $2 WHERE "id" = $3',
                           _u32(who), now, _u32(aid))
        n_nat += 1
    return n_nat


async def store_reputations(conn: asyncpg.Connection, world_auid: int,
                            items: Sequence[Tuple[int, int]]) -> int:
    if not await _table_exists(conn, "hz_native_reputation"):
        return 0
    w = _u32(world_auid)
    now = _now_ms()
    n_rep = 0
    for player, rep in items:
        await conn.execute(
            'INSERT INTO "hz_native_reputation" '
            '("world_auid", "player_auid", "rep", "timeModified") '
            'VALUES ($1, $2, $3, $4) '
            'ON CONFLICT ("world_auid", "player_auid") DO UPDATE SET '
            '"rep" = EXCLUDED."rep", '
            '"timeModified" = EXCLUDED."timeModified"',
            w, _u32(player), int(rep), now)
        n_rep += 1
    return n_rep


async def stored_interlocutors(conn: asyncpg.Connection, world_auid: int):
    if not await _table_exists(conn, "a_CitIndigenous"):
        return []
    return await conn.fetch(
        'SELECT "id", "interlocutor" FROM "a_CitIndigenous" '
        'WHERE "idp" = $1 AND "interlocutor" IS NOT NULL '
        'AND "interlocutor" != 0', _u32(world_auid))


async def stored_reputations(conn: asyncpg.Connection, world_auid: int):
    if not await _table_exists(conn, "hz_native_reputation"):
        return []
    return await conn.fetch(
        'SELECT "player_auid", "rep" FROM "hz_native_reputation" '
        'WHERE "world_auid" = $1', _u32(world_auid))


async def save_drift_rows(conn: asyncpg.Connection,
                          moved: Sequence[Sequence[Any]]) -> int:
    if not moved:
        return 0
    if not await _table_exists(conn, "a_CitIndigenous"):
        return 0
    has_home = await _table_exists(conn, "hz_native_home")
    has_tilt = has_home and "tilt" in await _declared_types(
        conn, "hz_native_home")
    now = _now_ms()
    n = 0
    for rec in moved:
        auid, xyz, rot = rec[0], rec[1], rec[2]
        tilt = float(rec[3]) if len(rec) > 3 else None
        await conn.execute(
            'UPDATE "a_CitIndigenous" SET "locX" = $1, "locY" = $2, '
            '"locZ" = $3, "rotX" = $4, "rotY" = $5, "rotZ" = $6, '
            '"timeModified" = $7 WHERE "id" = $8',
            float(xyz[0]), float(xyz[1]), float(xyz[2]),
            float(rot[0]), float(rot[1]), float(rot[2]),
            now, _u32(auid))
        if tilt is not None and has_tilt:
            await conn.execute('UPDATE "hz_native_home" SET "tilt" = $1 '
                               'WHERE "id" = $2', tilt, _u32(auid))
        n += 1
    return n


async def save_growth(conn: asyncpg.Connection,
                      grown: Sequence[Sequence[Any]]) -> int:
    pairs = [(_u32(a), max(0, min(255, int(m)))) for a, m in grown]
    if not pairs:
        return 0
    if not await _table_exists(conn, "a_CitIndigenous"):
        return 0
    now = _now_ms()
    await conn.executemany(
        'UPDATE "a_CitIndigenous" SET "minsToFullGrown" = $1, '
        '"timeModified" = $2 WHERE "id" = $3',
        [(m, now, a) for a, m in pairs])
    return len(pairs)


__all__ = [
    "NATIVE_AUID_BASE", "NATIVE_AUID_LIMIT", "NATIVE_BLOCK_SIZE",
    "NATIVE_COLUMNS", "NATIVE_COLUMN_NAMES", "NATIVE_WRITE_ONCE",
    "allocate_block",
    "save_village", "load_village", "delete_village",
    "update_native", "set_interlocutor", "save_growth", "save_drift_rows",
    "world_native_ids", "store_interlocutors", "store_reputations",
    "stored_interlocutors", "stored_reputations",
]
