from __future__ import annotations

import struct

import time as _t

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.pool import _now_ms

logger = get_logger(__name__)


_GLOBE_PARENT_TABLES = ("a_Star", "a_WorldGlobe", "a_WorldGasGiant",
                        "a_WorldRingSection")


async def _globe_star_and_seed(conn: asyncpg.Connection, globe):
    star = parent = None
    seed = None
    node = globe
    for _ in range(4):
        idp = node["idp"] if node is not None else None
        if not idp:
            break
        row = await conn.fetchrow('SELECT * FROM "a_Star" WHERE "id" = $1', idp)
        if row is not None:
            star = row
            break
        nxt = None
        for tbl in _GLOBE_PARENT_TABLES[1:]:
            nxt = await conn.fetchrow(
                f'SELECT * FROM "{tbl}" WHERE "id" = $1', idp)
            if nxt is not None:
                break
        if nxt is None:
            break
        if parent is None:
            parent = nxt
        node = nxt
    if star is not None:
        row = await conn.fetchrow(
            'SELECT "genSeed" FROM "a_SolarSystem" WHERE "id" = $1',
            star["idp"])
        if row is None:
            prim = await conn.fetchrow('SELECT * FROM "a_Star" WHERE "id" = $1',
                                       star["idp"])
            if prim is not None:
                row = await conn.fetchrow(
                    'SELECT "genSeed" FROM "a_SolarSystem" WHERE "id" = $1',
                    prim["idp"])
        seed = row["genSeed"] if row else None
    return star, seed, parent


async def _ring_section_geo(conn: asyncpg.Connection,
                            section_auid: int) -> bytes:
    row = await conn.fetchrow(
        'SELECT "geoFeatures" FROM "a_WorldRingSection" WHERE "id" = $1',
        int(section_auid))
    if row and row[0] and len(row[0]) >= 1:
        blob = bytes(row[0])
        logger.debug("Ring section 0x%08x: %d bytes, %d geological feature(s).",
                     int(section_auid), len(blob), blob[0])
        return blob
    return bytes([0x00])


async def _fauna_terrain_for_world(conn: asyncpg.Connection, world_auid, *,
                                   cache):
    key = int(world_auid) & 0xFFFFFFFF
    hit = cache.get(key)
    if hit is not None:
        return hit
    terrain, size = None, 0
    row = await conn.fetchrow(
        'SELECT "terrain", "radius" FROM "a_WorldGlobe" WHERE "id" = $1', key)
    if row and row[0] and len(row[0]) == 24:
        terrain = struct.unpack(">ffffff", row[0])
    if row and row[1]:
        size = int(row[1])
    cache[key] = (terrain, size)
    return (terrain, size)


async def read_world_flora(conn: asyncpg.Connection, table: str, auid: int):
    if table == "a_WorldGlobe":
        return await conn.fetchrow(
            'SELECT "flora", "radius" FROM "a_WorldGlobe" WHERE "id" = $1',
            int(auid))
    _r = await conn.fetchrow(
        f'SELECT "flora" FROM "{table}" WHERE "id" = $1', int(auid))
    return (_r[0], None) if _r else None


async def write_world_flora(conn: asyncpg.Connection, table: str, auid: int,
                            payload: bytes) -> None:
    await conn.execute(
        f'UPDATE "{table}" SET "flora" = $1 WHERE "id" = $2',
        payload, int(auid))


async def read_atom_globe(conn: asyncpg.Connection, auid: int):
    row = await conn.fetchrow(
        'SELECT "id", "idp", "name", "locX", "locY", "locZ", "radius" '
        'FROM "a_WorldGlobe" WHERE "id" = $1', int(auid))
    if not row:
        return None
    return {
        "id":       int(row[0]),
        "idp":      int(row[1]) if row[1] is not None else 0,
        "name":     row[2] or "",
        "locXYZ":   (float(row[3] or 0.0),
                     float(row[4] or 0.0),
                     float(row[5] or 0.0)),
        "radius":   float(row[6]) if row[6] is not None else None,
    }


async def read_atom_gasgiant(conn: asyncpg.Connection, auid: int):
    row = await conn.fetchrow(
        'SELECT "id", "idp", "name", "locX", "locY", "locZ", "radius" '
        'FROM "a_WorldGasGiant" WHERE "id" = $1', int(auid))
    if not row:
        return None
    return {
        "id":       int(row[0]),
        "idp":      int(row[1]) if row[1] is not None else 0,
        "name":     row[2] or "",
        "locXYZ":   (float(row[3] or 0.0),
                     float(row[4] or 0.0),
                     float(row[5] or 0.0)),
        "radius":   float(row[6]) if row[6] is not None else None,
    }


async def update_atom(conn: asyncpg.Connection, table: str, auid: int,
                      **fields) -> bool:
    if not fields or not table:
        return False
    found = await conn.fetchrow(
        """SELECT "table_name" FROM "information_schema"."tables"
            WHERE "table_schema" = 'public' AND "table_type" = 'BASE TABLE'
              AND "table_name" = $1""", table)
    if not found:
        return False
    valid = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = $1""", table)}
    clean = {k: v for k, v in fields.items() if k in valid}
    if not clean:
        return False
    if "timeModified" in valid:
        clean.setdefault("timeModified", _now_ms())
    parts = ", ".join(f'"{k}" = ${i}' for i, k in enumerate(clean, 1))
    vals = list(clean.values()) + [int(auid) & 0xFFFFFFFF]
    updated = await conn.fetchrow(
        f'UPDATE "{table}" SET {parts} '
        f'WHERE "id" = ${len(clean) + 1} RETURNING "id"', *vals)
    return updated is not None


async def dropped_item_insert(conn: asyncpg.Connection, auid: int,
                              parent_auid: int,
                              xyz: tuple, rotation: tuple,
                              type_id: int, body: bytes,
                              time_created_ms: int) -> bool:
    row = await conn.fetchrow(
        """SELECT "table_name" FROM "information_schema"."tables"
            WHERE "table_schema" = 'public' AND "table_type" = 'BASE TABLE'
              AND "table_name" = 'a_Item'""")
    if not row:
        return False
    item_blob = bytes([int(type_id) & 0xFF]) + bytes(body)
    await conn.execute(
        'INSERT INTO "a_Item" '
        '("id", "idp", "locX", "locY", "locZ", "rotX", "rotY", "rotZ", '
        ' "timeCreate", "timeModified", "item", "atRest") '
        'VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 1) '
        'ON CONFLICT ("id") DO UPDATE SET '
        '"idp" = EXCLUDED."idp", '
        '"locX" = EXCLUDED."locX", '
        '"locY" = EXCLUDED."locY", '
        '"locZ" = EXCLUDED."locZ", '
        '"rotX" = EXCLUDED."rotX", '
        '"rotY" = EXCLUDED."rotY", '
        '"rotZ" = EXCLUDED."rotZ", '
        '"timeCreate" = EXCLUDED."timeCreate", '
        '"timeModified" = EXCLUDED."timeModified", '
        '"item" = EXCLUDED."item", '
        '"atRest" = EXCLUDED."atRest"',
        int(auid) & 0xFFFFFFFF,
        int(parent_auid) & 0xFFFFFFFF,
        float(xyz[0]), float(xyz[1]), float(xyz[2]),
        float(rotation[0]), float(rotation[1]), float(rotation[2]),
        int(time_created_ms),
        _now_ms(),
        item_blob,
    )
    return True

async def dropped_item_delete(conn: asyncpg.Connection, auid: int) -> bool:
    row = await conn.fetchrow(
        """SELECT "table_name" FROM "information_schema"."tables"
            WHERE "table_schema" = 'public' AND "table_type" = 'BASE TABLE'
              AND "table_name" = 'a_Item'""")
    if not row:
        return False
    deleted = await conn.fetchrow(
        'DELETE FROM "a_Item" WHERE "id" = $1 RETURNING "id"',
        int(auid) & 0xFFFFFFFF)
    return deleted is not None


_ROBERT_EMPIRE_ID = 370624


async def add_citizen_to_empire(conn: asyncpg.Connection, avatar_id: int,
                                empire_db_id: int = _ROBERT_EMPIRE_ID) -> bool:
    import struct as _struct
    row = await conn.fetchrow(
        'SELECT "citizens" FROM "g_Empire" WHERE "id" = $1',
        int(empire_db_id))
    if row is None:
        logger.warning("Empire %s not found; citizenship not recorded.",
                       empire_db_id)
        return False
    blob = bytes(row[0]) if row[0] else b""
    if len(blob) >= 4:
        count = _struct.unpack(">I", blob[:4])[0]
    else:
        count = 0
        blob = b""
    needle = _struct.pack(">I", int(avatar_id) & 0xFFFFFFFF)
    if needle in blob:
        logger.debug("0x%08x is already a citizen of empire %s.",
                     int(avatar_id), empire_db_id)
        return True
    new_entry = needle + bytes(12)
    if count == 0:
        new_blob = _struct.pack(">I", 1) + new_entry
    else:
        new_blob = _struct.pack(">I", count + 1) + blob[4:] + new_entry
    await conn.execute(
        'UPDATE "g_Empire" SET "citizens" = $1 WHERE "id" = $2',
        new_blob, int(empire_db_id))
    logger.info("0x%08x joined empire %s, which now has %d citizens.",
                int(avatar_id), empire_db_id, count + 1)
    return True


async def dropped_items_load_all(conn: asyncpg.Connection,
                                 min_id: int = 0x70000000) -> list:
    row = await conn.fetchrow(
        """SELECT "table_name" FROM "information_schema"."tables"
            WHERE "table_schema" = 'public' AND "table_type" = 'BASE TABLE'
              AND "table_name" = 'a_Item'""")
    if not row:
        return []
    rows = await conn.fetch(
        'SELECT "id", "idp", "locX", "locY", "locZ", "rotX", "rotY", "rotZ",'
        ' "item", "timeCreate"'
        ' FROM "a_Item" WHERE "id" >= $1',
        int(min_id))
    out = []
    for r in rows:
        blob = bytes(r[8] or b"")
        if not blob:
            continue
        type_id = blob[0]
        body = blob[1:]
        out.append({
            "auid": int(r[0]),
            "parent_auid": int(r[1]) if r[1] is not None else 0,
            "xyz": (float(r[2] or 0.0),
                    float(r[3] or 0.0),
                    float(r[4] or 0.0)),
            "rotation": (float(r[5] or 0.0),
                         float(r[6] or 0.0),
                         float(r[7] or 0.0)),
            "type_id": int(type_id),
            "body": body,
            "time_created_ms": int(r[9]) if r[9] is not None else 0,
        })
    return out


_CLAIM_TABLES = ("a_WorldGlobe", "a_WorldGasGiant", "a_WorldRingSection")


async def _table_columns(conn: asyncpg.Connection, table: str) -> set:
    return {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = $1""", table)}


async def world_claim_state(conn: asyncpg.Connection, world_auid: int):
    w = int(world_auid) & 0xFFFFFFFF
    if not w:
        return (0, 0)
    for tbl in _CLAIM_TABLES:
        cols = await _table_columns(conn, tbl)
        if "claimedBy" not in cols:
            continue
        second = "claimId" if "claimId" in cols else "claimedBy"
        row = await conn.fetchrow(
            f'SELECT "claimedBy", "{second}" FROM "{tbl}" WHERE "id" = $1', w)
        if row is not None:
            cb = int(row[0] or 0) & 0xFFFFFFFF
            ci = int(row[1] or 0) & 0xFFFFFFFF
            return (cb, ci)
    return (0, 0)


async def world_exists(conn: asyncpg.Connection, world_auid: int) -> bool:
    w = int(world_auid) & 0xFFFFFFFF
    if not w:
        return False
    for tbl in _CLAIM_TABLES:
        if not await _table_columns(conn, tbl):
            continue
        if await conn.fetchrow(
                f'SELECT 1 FROM "{tbl}" WHERE "id" = $1', w) is not None:
            return True
    return False


async def claim_world(conn: asyncpg.Connection, person_auid: int,
                      empire_id: int, world_auid: int, lon: float = 0.0,
                      lat: float = 0.0, empire_name: str = "") -> bool:
    person = int(person_auid) & 0xFFFFFFFF
    empire = int(empire_id) & 0xFFFFFFFF
    w = int(world_auid) & 0xFFFFFFFF
    if not (person and empire and w):
        logger.warning("Reject: person=0x%08x empire=0x%08x world=0x%08x (need all three)", person, empire, w)
        return False
    now_ms = int(_t.time() * 1000)
    for tbl in _CLAIM_TABLES:
        cols = await _table_columns(conn, tbl)
        if "claimedBy" not in cols:
            continue
        if await conn.fetchrow(
                f'SELECT 1 FROM "{tbl}" WHERE "id" = $1', w) is None:
            continue
        sets, vals = [], []

        def _put(c, v):
            if c in cols:
                sets.append(f'"{c}" = ${len(vals) + 1}')
                vals.append(v)

        _put("claimedBy", person)
        _put("claimId", empire)
        _put("claimName", empire_name or "")
        _put("claimLon", float(lon))
        _put("claimLat", float(lat))
        _put("claimTime", now_ms)
        if not sets:
            return False
        vals.append(w)
        tag = await conn.execute(
            f'UPDATE "{tbl}" SET {",".join(sets)} WHERE "id" = ${len(vals)}',
            *vals)
        ok = int(str(tag).rsplit(" ", 1)[-1] or 0) > 0
        logger.info("%s: world 0x%08x (%s) claimedBy=0x%08x empire=0x%08x "
                    "lon=%.2f lat=%.2f",
                    "APPLY" if ok else "NOOP", w, tbl, person, empire, lon, lat)
        return ok
    logger.info("World 0x%08x not found in any world table", w)
    return False


async def read_world_geo(conn: asyncpg.Connection, auid: int):
    return await conn.fetchrow(
        'SELECT "geoFeatures", "terrain", "orbitZone" '
        'FROM "a_WorldGlobe" WHERE "id" = $1',
        int(auid))


async def write_world_geo(conn: asyncpg.Connection, auid: int,
                          payload: bytes) -> None:
    await conn.execute(
        'UPDATE "a_WorldGlobe" SET "geoFeatures" = $1 WHERE "id" = $2',
        payload, int(auid))
