from __future__ import annotations

import asyncpg

_KE_DOC_SCHEMA = """
CREATE TABLE IF NOT EXISTS g_KnownEmpireDoc (
    knower_empire_id INTEGER, known_empire_id INTEGER, doc_idx INTEGER,
    doc_type INTEGER, timestamp_ms INTEGER, actor_avatar_id INTEGER,
    actor_empire_id INTEGER, text_a TEXT, text_b TEXT, text_c TEXT,
    doc_state INTEGER DEFAULT 0)"""

DOC_UNIT_CONTACT = 0x01
DOC_NOTE = 0x0A


def _rowcount(tag) -> int:
    return int(str(tag).rsplit(" ", 1)[-1] or 0)


async def _add_dossier_doc(conn: asyncpg.Connection, knower: int, known: int,
                           doc_type: int, ts_ms: int,
                           actor_avatar: int, actor_empire: int,
                           text_a: str = "", text_b: str = "",
                           text_c: str = "", doc_state: int = 0) -> int:
    row = await conn.fetchrow(
        'SELECT COALESCE(MAX("doc_idx"),-1)+1 FROM "g_KnownEmpireDoc" '
        'WHERE "knower_empire_id"=$1 AND "known_empire_id"=$2',
        knower & 0xFFFFFFFF, known & 0xFFFFFFFF)
    idx = int(row[0]) if row else 0
    await conn.execute(
        'INSERT INTO "g_KnownEmpireDoc" ("knower_empire_id","known_empire_id",'
        '"doc_idx","doc_type","timestamp_ms","actor_avatar_id",'
        '"actor_empire_id","text_a","text_b","text_c","doc_state") '
        'VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)',
        knower & 0xFFFFFFFF, known & 0xFFFFFFFF, idx, doc_type, int(ts_ms),
        actor_avatar & 0xFFFFFFFF, actor_empire & 0xFFFFFFFF,
        text_a, text_b, text_c, int(doc_state))
    return idx


async def set_dossier_doc_state(conn: asyncpg.Connection, knower: int,
                                known: int, au_time: int, state: int) -> int:
    return _rowcount(await conn.execute(
        'UPDATE "g_KnownEmpireDoc" SET "doc_state"=$1 WHERE '
        '"knower_empire_id"=$2 AND "known_empire_id"=$3 AND "timestamp_ms"=$4',
        int(state), knower & 0xFFFFFFFF, known & 0xFFFFFFFF, int(au_time)))


async def set_known_empire_stance(conn: asyncpg.Connection, knower: int,
                                  known: int, stance: int,
                                  tribute: int) -> int:
    return _rowcount(await conn.execute(
        'UPDATE "g_KnownEmpire" SET "stance"=$1, "tribute"=$2 WHERE '
        '"knower_empire_id"=$3 AND "known_empire_id"=$4',
        int(stance), int(tribute), knower & 0xFFFFFFFF, known & 0xFFFFFFFF))


async def set_war_criteria(conn: asyncpg.Connection, eid: int,
                           blob: bytes) -> int:
    return _rowcount(await conn.execute(
        'UPDATE "g_Empire" SET "war_criteria"=$1 WHERE "id"=$2',
        blob, eid & 0xFFFFFFFF))


async def set_founder_domain(conn: asyncpg.Connection, eid: int,
                             domain: int) -> int:
    return _rowcount(await conn.execute(
        'UPDATE "g_Empire" SET "founder_domain"=$1 WHERE "id"=$2',
        int(domain), eid & 0xFFFFFFFF))
