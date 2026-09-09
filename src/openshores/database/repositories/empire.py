
from __future__ import annotations

import struct

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories.spawn import _as_byte
from openshores.database.repositories.world import _table_columns
from openshores.protocol.atoms.citizen import _write_aucitizen
from openshores.protocol.atoms.known_empire import _write_auknown_empire
from openshores.protocol.empire_chat_parse import _s32
from openshores.protocol.stream import QDS

logger = get_logger(__name__)


_EMPIRE_BY_AVATAR_CACHE: dict = {}


async def _resolve_empire_for_avatar_uncached(conn: asyncpg.Connection,
                                              avatar_auid: int) -> int:
    avatar_auid = int(avatar_auid) & 0xFFFFFFFF
    if not avatar_auid:
        return 0
    needle = struct.pack(">I", avatar_auid)
    for emp_id, _emp_name, citizens in await conn.fetch(
            'SELECT "id", "name", "citizens" FROM "g_Empire" '
            'WHERE "id" IS NOT NULL AND "citizens" IS NOT NULL'):
        if citizens and needle in bytes(citizens):
            return int(emp_id) & 0xFFFFFFFF
    return 0


async def empire_for_avatar(conn: asyncpg.Connection, avatar_auid: int, *,
                            _CITIZEN_EMPIRE_OVERRIDE: dict) -> int:
    avatar_auid = int(avatar_auid) & 0xFFFFFFFF
    _override = _CITIZEN_EMPIRE_OVERRIDE.get(avatar_auid)
    if _override:
        return int(_override) & 0xFFFFFFFF
    if avatar_auid in _EMPIRE_BY_AVATAR_CACHE:
        return _EMPIRE_BY_AVATAR_CACHE[avatar_auid]
    eid = await _resolve_empire_for_avatar_uncached(conn, avatar_auid)
    _EMPIRE_BY_AVATAR_CACHE[avatar_auid] = eid
    if eid:
        logger.debug("Avatar 0x%08x is a citizen of empire 0x%08x.",
                     avatar_auid, eid)
    else:
        logger.debug("Avatar 0x%08x is in no empire: it is in no "
                     "g_Empire.citizens BLOB.", avatar_auid)
    return eid


def invalidate_empire_membership_cache() -> None:
    _EMPIRE_BY_AVATAR_CACHE.clear()
    _EMPEROR_BY_EMPIRE_CACHE.clear()
    _FLAG_BY_EMPIRE_CACHE.clear()


_EMPEROR_BY_EMPIRE_CACHE: dict = {}


async def emperor_for_empire(conn: asyncpg.Connection, empire_id: int) -> int:
    empire_id = int(empire_id) & 0xFFFFFFFF
    if not empire_id:
        return 0
    if empire_id in _EMPEROR_BY_EMPIRE_CACHE:
        return _EMPEROR_BY_EMPIRE_CACHE[empire_id]
    eid = 0
    row = await conn.fetchrow(
        'SELECT "citizens" FROM "g_Empire" WHERE "id" = $1', empire_id)
    if row and row[0]:
        blob = bytes(row[0])
        if len(blob) >= 8:
            eid = struct.unpack(">I", blob[4:8])[0]
    _EMPEROR_BY_EMPIRE_CACHE[empire_id] = eid
    if eid:
        logger.debug("Empire 0x%08x emperor is 0x%08x.", empire_id, eid)
    else:
        logger.debug("Empire 0x%08x has no emperor: citizens blob is empty "
                     "or its first slot is 0.", empire_id)
    return eid


_FLAG_BY_EMPIRE_CACHE: dict = {}

_EMPIRE_FLAG_OVERRIDE: dict = {}


async def flag_for_empire(conn: asyncpg.Connection, empire_id: int) -> bytes:
    empire_id = int(empire_id) & 0xFFFFFFFF
    if not empire_id:
        return b""
    _override = _EMPIRE_FLAG_OVERRIDE.get(empire_id)
    if _override is not None:
        return _override
    if empire_id in _FLAG_BY_EMPIRE_CACHE:
        return _FLAG_BY_EMPIRE_CACHE[empire_id]
    flag = b""
    row = await conn.fetchrow(
        'SELECT "flag" FROM "g_Empire" WHERE "id" = $1', empire_id)
    if row and row[0]:
        blob = bytes(row[0])
        if blob != b"\xff\xff\xff\xff":
            flag = blob
    _FLAG_BY_EMPIRE_CACHE[empire_id] = flag
    if flag:
        logger.debug("Empire 0x%08x flag is a %d byte PNG, sig=%s.",
                     empire_id, len(flag), flag[:8].hex())
    else:
        logger.debug("Empire 0x%08x has no flag: column NULL or "
                     "null-sentinel.", empire_id)
    return flag


async def _read_known_empires_for(conn: asyncpg.Connection,
                                  knower_empire_id: int) -> list:
    out = []
    if not knower_empire_id:
        return out
    _has = await conn.fetchrow(
        """SELECT "table_name" FROM "information_schema"."tables"
            WHERE "table_schema" = 'public' AND "table_type" = 'BASE TABLE'
              AND "table_name" = 'g_KnownEmpire'""")
    if not _has:
        return out
    knower = int(knower_empire_id) & 0xFFFFFFFF
    _kcols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public'
              AND "table_name" = 'g_KnownEmpire'""")}
    _sel_trib = 'k."tribute"' if "tribute" in _kcols else "0"
    for kid, first_ms, last_ms, st, ename, trib in await conn.fetch(
            'SELECT k."known_empire_id", k."first_met_ms", '
            'k."last_seen_ms", k."stance", e."name", ' + _sel_trib + ' '
            'FROM "g_KnownEmpire" k '
            'JOIN "g_Empire" e ON e."id" = k."known_empire_id" '
            'WHERE k."knower_empire_id" = $1 '
            "AND e.\"name\" IS NOT NULL AND e.\"name\" != '' "
            'ORDER BY k."known_empire_id" ASC', knower):
        docs = []
        _dcols = {r[0] for r in await conn.fetch(
            """SELECT "column_name" FROM "information_schema"."columns"
                WHERE "table_schema" = 'public'
                  AND "table_name" = 'g_KnownEmpireDoc'""")}
        _sel_state = '"doc_state"' if "doc_state" in _dcols else "0"
        for dt, ts, aav, aem, ta, tb, tc, dst in await conn.fetch(
                'SELECT "doc_type", "timestamp_ms", "actor_avatar_id", '
                '"actor_empire_id", "text_a", "text_b", "text_c", '
                + _sel_state +
                ' FROM "g_KnownEmpireDoc" '
                'WHERE "knower_empire_id" = $1 AND "known_empire_id" = $2 '
                'ORDER BY "doc_idx" ASC', knower, int(kid)):
            _aname = ""
            if aav:
                _nr = await conn.fetchrow(
                    'SELECT "name" FROM "a_Person" WHERE "id" = $1',
                    int(aav) & 0xFFFFFFFF)
                _aname = str(_nr[0]) if _nr and _nr[0] else ""
            docs.append({
                'doc_type': int(dt),
                'timestamp_ms': int(ts),
                'actor_avatar_id': int(aav or 0),
                'actor_empire_id': int(aem or 0),
                'actor_name': _aname,
                'text_a': str(ta or ""),
                'text_b': str(tb or ""),
                'text_c': str(tc or ""),
                'doc_state': int(dst or 0),
            })
        out.append({
            'known_id': int(kid) & 0xFFFFFFFF,
            'first_met_ms': int(first_ms),
            'last_seen_ms': int(last_ms),
            'stance': int(st or 0),
            'tribute': int(trib or 0),
            'name': str(ename),
            'docs': docs,
        })
    return out


async def _read_war_criteria(conn: asyncpg.Connection, empire_id: int) -> bytes:
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'g_Empire'""")}
    if "war_criteria" not in cols:
        return b""
    row = await conn.fetchrow(
        'SELECT "war_criteria" FROM "g_Empire" WHERE "id" = $1',
        empire_id & 0xFFFFFFFF)
    return bytes(row[0]) if row and row[0] else b""


async def _read_founder_domain(conn: asyncpg.Connection, empire_id: int) -> int:
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'g_Empire'""")}
    if "founder_domain" not in cols:
        return 2
    row = await conn.fetchrow(
        'SELECT "founder_domain" FROM "g_Empire" WHERE "id" = $1',
        empire_id & 0xFFFFFFFF)
    v = int(row[0]) if row and row[0] is not None else 2
    return v if 1 <= v <= 6 else 2


async def _build_nested_knownempires_and_patents(conn: asyncpg.Connection,
                                                 empire_id: int = 0) -> bytes:
    s = QDS()
    known = await _read_known_empires_for(conn, int(empire_id) & 0xFFFFFFFF) if empire_id else []
    s.write_i16(len(known))
    for entry in known:
        _write_auknown_empire(
            s,
            empire_id=entry['known_id'],
            name=entry['name'],
            include_dossier=True,
            first_met_ms=entry['first_met_ms'],
            last_seen_ms=entry['last_seen_ms'],
            stance=entry['stance'],
            tribute=entry.get('tribute', 0),
            docs=entry['docs'],
        )
    _war = await _read_war_criteria(conn, int(empire_id) & 0xFFFFFFFF) if empire_id else b""
    if _war:
        _wc = _war[0]
        s.write_u8(_wc)
        for _i in range(_wc):
            _o = 1 + _i * 2
            if _o + 1 < len(_war):
                s.write_u8(_war[_o])
                s.write_u8(_war[_o + 1])
            else:
                break
    else:
        s.write_u8(0)
    s.write_i16(0)
    if known:
        _summary = [(hex(e['known_id']), e['name'], len(e['docs']))
                    for e in known]
        logger.debug("Empire 0x%08x known empires: %d packed from SQL, %s.",
                     empire_id, len(known), _summary)
    return s.getvalue()


async def _build_nested_citizens_from_sql(conn: asyncpg.Connection,
                                          empire_id: int, *,
                                          offices: dict) -> bytes:
    s = QDS()
    if not empire_id:
        s.write_i16(0)
        return s.getvalue()
    citizens: list[tuple[int, str]] = []
    row = await conn.fetchrow(
        'SELECT "citizens" FROM "g_Empire" WHERE "id" = $1',
        int(empire_id) & 0xFFFFFFFF)
    if row and row[0]:
        blob = bytes(row[0])
        if len(blob) >= 4:
            count = struct.unpack(">I", blob[:4])[0]
            stride = 16
            for i in range(count):
                off = 4 + i * stride
                if off + 4 > len(blob):
                    break
                aid = struct.unpack(">I", blob[off:off+4])[0]
                if aid == 0:
                    continue
                nrow = await conn.fetchrow(
                    'SELECT "name" FROM "a_Person" WHERE "id" = $1', aid)
                name = (nrow[0] if nrow and nrow[0] else f"0x{aid:08x}")
                citizens.append((aid, name))
    s.write_i16(len(citizens))
    _titled = []
    for i, (aid, name) in enumerate(citizens):
        off = offices.get(int(aid) & 0xFFFFFFFF)
        if off is not None and getattr(off, "role_id", 1) == 0:
            _write_aucitizen(s, aid, name, is_emperor=True)
        elif off is not None and getattr(off, "title", ""):
            _write_aucitizen(s, aid, name, is_emperor=False,
                             title=off.title, rights1=off.rights1,
                             rights2=off.rights2)
            _titled.append((aid, off.title))
        else:
            _write_aucitizen(s, aid, name, is_emperor=(i == 0))
    if citizens:
        logger.debug("Empire 0x%08x citizens: %d packed, emperor 0x%08x %r; "
                     "%d titled %s.", empire_id, len(citizens),
                     citizens[0][0], citizens[0][1], len(_titled), _titled)
    return s.getvalue()


async def _build_nested_cities_from_sql(conn: asyncpg.Connection,
                                        empire_id: int) -> bytes:
    s = QDS()
    if not empire_id:
        s.write_i16(0)
        return s.getvalue()
    rows: list[tuple[int, str]] = []
    cols = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = 'a_City'""")}
    if not cols or "id" not in cols:
        s.write_i16(0)
        return s.getvalue()
    namecol = "name" if "name" in cols else None
    sel = '"id"' + (', "name"' if namecol else "")
    if "allegiance" in cols:
        q = f'SELECT {sel} FROM "a_City" WHERE "allegiance" = $1'
        cur = await conn.fetch(q, int(empire_id) & 0xFFFFFFFF)
    else:
        cur = await conn.fetch(f'SELECT {sel} FROM "a_City"')
    for r in cur:
        cid = int(r[0]) & 0xFFFFFFFF
        if not cid:
            continue
        nm = (r[1] if namecol and len(r) > 1 and r[1] else f"City 0x{cid:08x}")
        rows.append((cid, nm))

    s.write_i16(len(rows))
    for cid, nm in rows:
        s.write_u32(0)
        s.write_u32(0)
        s.write_u32(0)
        s.write_u32(cid)
        s.write_qstring("")
        s.write_qstring("")
        s.write_qstring("")
        s.write_qstring(nm)
        s.write_u8(0x18)
        s.write_u32(0)
        s.write_u8(0)
    if rows:
        logger.debug("Empire 0x%08x city hash: %d city(ies) %s.",
                     empire_id, len(rows), [(hex(c), n) for c, n in rows])
    return s.getvalue()


async def _update_empire(conn: asyncpg.Connection, eid: int, **cols) -> bool:
    cols = {k: v for k, v in cols.items() if v is not None}
    if not cols:
        return False
    eid &= 0xFFFFFFFF
    have = {r[0] for r in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public'
              AND "table_name" = 'g_Empire'""")}
    use = {k: v for k, v in cols.items() if k in have}
    if not use:
        return False
    assigns = ", ".join(f'"{k}" = ${i + 1}' for i, k in enumerate(use))
    tag = await conn.execute(
        f'UPDATE "g_Empire" SET {assigns} WHERE "id" = ${len(use) + 1}',
        *use.values(), eid)
    return bool(int(str(tag).rsplit(" ", 1)[-1] or 0))


async def apply_announcement(conn: asyncpg.Connection, eid: int,
                             text: str) -> dict:
    ok = await _update_empire(conn, eid, announcements=str(text or ""))
    return {"ok": ok, "len": len(text or "")}


async def set_empire_taxes(conn: asyncpg.Connection, empire_id: int,
                           income: int, sales: int, subsidy: int) -> bool:
    return await _update_empire(
        conn, empire_id,
        taxIncome=bytes([int(income) & 0xFF]),
        taxSales=bytes([int(sales) & 0xFF]),
        taxSubsidy=bytes([int(subsidy) & 0xFF]))


_RENAME_TABLE = {0: "a_SolarSystem", 1: "a_WorldGlobe",
                 2: "a_Sector", 3: "a_City"}


async def set_place_name(conn: asyncpg.Connection, kind: int,
                         target_auid: int, new_name: str) -> bool:
    table = _RENAME_TABLE.get(int(kind))
    if not table or not target_auid:
        return False
    tag = await conn.execute(
        f'UPDATE "{table}" SET "name" = $1 WHERE "id" = $2',
        new_name, int(target_auid))
    return bool(int(str(tag).rsplit(" ", 1)[-1] or 0))


_FOUNDED_EMPIRE_BASE = 0x00F00000


async def found_empire(conn: asyncpg.Connection, founder_auid: int,
                       empire_name: str = "", *,
                       _CITIZEN_EMPIRE_OVERRIDE) -> int:
    founder = int(founder_auid) & 0xFFFFFFFF
    if not founder:
        logger.warning("Reject: no founder avatar")
        return 0
    name = (empire_name or "New Empire").strip()[:64] or "New Empire"
    citizens = struct.pack(">I", 1) + struct.pack(">I", founder) + b"\x00" * 12
    try:
        row = await conn.fetchrow(
            'SELECT COALESCE(MAX("id"), 0) FROM "g_Empire"')
        max_id = int(row[0] or 0) & 0xFFFFFFFF
        new_eid = max(_FOUNDED_EMPIRE_BASE, max_id + 0x10) & 0xFFFFFFFF
        while await conn.fetchrow(
                'SELECT 1 FROM "g_Empire" WHERE "id" = $1',
                new_eid) is not None:
            new_eid = (new_eid + 0x10) & 0xFFFFFFFF
        cols = {r[0] for r in await conn.fetch(
            """SELECT "column_name" FROM "information_schema"."columns"
                WHERE "table_schema" = 'public'
                  AND "table_name" = 'g_Empire'""")}
        fields = {"id": new_eid}
        if "name" in cols:
            fields["name"] = name
        if "citizens" in cols:
            fields["citizens"] = citizens
        keys = ",".join(f'"{k}"' for k in fields)
        placeholders = ",".join(f"${i + 1}" for i in range(len(fields)))
        await conn.execute(
            f'INSERT INTO "g_Empire" ({keys}) VALUES ({placeholders})',
            *fields.values())
    except Exception as exc:
        logger.warning("INSERT failed: %r", exc)
        return 0
    _CITIZEN_EMPIRE_OVERRIDE[founder] = new_eid
    invalidate_empire_membership_cache()
    logger.info("Founder 0x%08x -> new empire 0x%08x %r (emperor=founder)",
                founder, new_eid, name)
    return new_eid


async def office_table_exists(conn: asyncpg.Connection) -> bool:
    return bool(await _table_columns(conn, "g_EmpireOffice"))


async def empire_office_rows(conn: asyncpg.Connection, empire_id: int) -> list:
    return await conn.fetch(
        'SELECT "avatar_id", "title", "rights1", "rights2", "role_id", '
        '"boss_id" FROM "g_EmpireOffice" WHERE "empire_id" = $1',
        int(empire_id) & 0xFFFFFFFF)


async def upsert_empire_office(conn: asyncpg.Connection, empire_id: int,
                               avatar_id: int, title: str, rights1: int,
                               rights2: int, role_id: int,
                               boss_id: int) -> None:
    await conn.execute(
        'INSERT INTO "g_EmpireOffice" '
        '("empire_id", "avatar_id", "title", "rights1", "rights2", '
        '"role_id", "boss_id") VALUES ($1, $2, $3, $4, $5, $6, $7) '
        'ON CONFLICT ("empire_id", "avatar_id") DO UPDATE SET '
        '"title" = EXCLUDED."title", "rights1" = EXCLUDED."rights1", '
        '"rights2" = EXCLUDED."rights2", "role_id" = EXCLUDED."role_id", '
        '"boss_id" = EXCLUDED."boss_id"',
        int(empire_id) & 0xFFFFFFFF, int(avatar_id) & 0xFFFFFFFF, title,
        _s32(rights1), _s32(rights2), _s32(role_id), _s32(boss_id))


async def remove_office(conn: asyncpg.Connection, empire_id: int,
                        avatar_id: int) -> None:
    if not await office_table_exists(conn):
        return
    await conn.execute(
        'DELETE FROM "g_EmpireOffice" WHERE "empire_id" = $1 '
        'AND "avatar_id" = $2',
        int(empire_id) & 0xFFFFFFFF, int(avatar_id) & 0xFFFFFFFF)


async def read_empire_row(conn: asyncpg.Connection, empire_id: int,
                          columns) -> asyncpg.Record | None:
    have = await _table_columns(conn, "g_Empire")
    use = [c for c in columns if c in have]
    if not use:
        return None
    sel = ", ".join(f'"{c}"' for c in use)
    return await conn.fetchrow(
        f'SELECT {sel} FROM "g_Empire" WHERE "id" = $1',
        int(empire_id) & 0xFFFFFFFF)


async def read_person_names(conn: asyncpg.Connection, auids) -> dict:
    ids = sorted({int(a) & 0xFFFFFFFF for a in auids})
    if not ids:
        return {}
    rows = await conn.fetch(
        'SELECT "id", "name" FROM "a_Person" WHERE "id" = ANY($1::bigint[])',
        ids)
    return {int(r[0]) & 0xFFFFFFFF: r[1] for r in rows}


async def read_empire_name(conn: asyncpg.Connection, empire_id: int):
    return await conn.fetchrow(
        'SELECT "name" FROM "g_Empire" WHERE "id" = $1',
        int(empire_id) & 0xFFFFFFFF)


async def read_empire_taxes(conn: asyncpg.Connection, empire_id: int):
    row = await conn.fetchrow(
        'SELECT "taxIncome", "taxSales", "taxSubsidy" FROM "g_Empire" '
        'WHERE "id" = $1', int(empire_id) & 0xFFFFFFFF)
    if row is None:
        return None
    return tuple(None if v is None else _as_byte(v) for v in row)


async def named_empire_ids(conn: asyncpg.Connection) -> list[int]:
    return [int(r[0]) & 0xFFFFFFFF for r in await conn.fetch(
        'SELECT "id" FROM "g_Empire" '
        "WHERE \"name\" IS NOT NULL AND \"name\" != '' "
        'ORDER BY "id" ASC')]
