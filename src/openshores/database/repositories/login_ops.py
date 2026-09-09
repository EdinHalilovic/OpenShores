
from __future__ import annotations

import struct

import asyncpg

from openshores.database.pool import Error
from openshores.database.repositories.person import _rows_affected


async def person_names(conn: asyncpg.Connection, auids) -> dict:
    out: dict = {}
    for rid, name in await conn.fetch(
            'SELECT "id", "name" FROM "a_Person" WHERE "id" = ANY($1::bigint[])',
            [int(a) for a in auids]):
        rid = int(rid)
        out[rid] = (str(name) if name is not None else "") or ("Avatar 0x%08x" % rid)
    return out


async def select_person_name(conn: asyncpg.Connection, auid: int):
    return await conn.fetchrow('SELECT "name" FROM "a_Person" WHERE "id" = $1',
                               int(auid) & 0xFFFFFFFF)


async def delete_person(conn: asyncpg.Connection, auid: int) -> None:
    await conn.execute('DELETE FROM "a_Person" WHERE "id" = $1',
                       int(auid) & 0xFFFFFFFF)


async def _strip_from_empire_citizens(conn: asyncpg.Connection,
                                      auid: int) -> list:
    touched = []
    rows = await conn.fetch(
        'SELECT "id", "name", "citizens" FROM "g_Empire" '
        'WHERE "citizens" IS NOT NULL')
    for eid, ename, blob in rows:
        raw = bytes(blob or b"")
        if len(raw) < 4:
            continue
        count = struct.unpack_from(">I", raw, 0)[0]
        entries, dropped = [], 0
        for i in range(count):
            off = 4 + i * 16
            if off + 16 > len(raw):
                break
            entry = raw[off:off + 16]
            if struct.unpack_from(">I", entry, 0)[0] == auid:
                dropped += 1
            else:
                entries.append(entry)
        if not dropped:
            continue
        new = struct.pack(">I", len(entries)) + b"".join(entries)
        await conn.execute('UPDATE "g_Empire" SET "citizens" = $1 WHERE "id" = $2',
                           new, eid)
        touched.append((int(eid), ename, dropped))
    return touched


async def _update_person(conn: asyncpg.Connection, auid: int,
                         column: str, value) -> tuple:
    try:
        status = await conn.execute(
            f'UPDATE "a_Person" SET "{column}" = $1 WHERE "id" = $2',
            value, int(auid) & 0xFFFFFFFF)
    except Error as exc:
        return False, f"update failed ({exc!r})"
    if _rows_affected(status) == 0:
        return False, f"no a_Person row 0x{int(auid) & 0xFFFFFFFF:08x}"
    return True, ""


async def update_person_identity(conn: asyncpg.Connection, auid: int,
                                 name: str, dna: bytes, sex: int,
                                 lefty: bool) -> bool:
    auid = int(auid) & 0xFFFFFFFF
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'a_Person'""")}
    if not await conn.fetchrow('SELECT 1 FROM "a_Person" WHERE "id" = $1', auid):
        return False
    sets, vals = ['"name" = $1', '"dna" = $2'], [name, bytes(dna)]
    if "sex" in cols:
        sets.append(f'"sex" = ${len(vals) + 1}'); vals.append(int(sex) & 0xFF)
    if "islefty" in cols:
        sets.append(f'"islefty" = ${len(vals) + 1}'); vals.append(1 if lefty else 0)
    vals.append(auid)
    await conn.execute(
        f'UPDATE "a_Person" SET {", ".join(sets)} WHERE "id" = ${len(vals)}',
        *vals)
    return True
