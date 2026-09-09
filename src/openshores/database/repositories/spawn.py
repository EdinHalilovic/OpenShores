from __future__ import annotations

import asyncpg

from openshores.database.pool import Error


class StubSpawnUnavailable(RuntimeError):
    pass


async def _stub_spawn(conn: asyncpg.Connection):
    from openshores.database.repositories.person import (
        PLACEHOLDER_AVATAR_NAME,
        _SPAWN_LOC_X,
        _SPAWN_LOC_Y,
        _SPAWN_LOC_Z,
        _SPAWN_PLANET_ID,
    )

    row = await conn.fetchrow(
        'SELECT 1 FROM "a_WorldGlobe" WHERE "id" = $1 LIMIT 1',
        _SPAWN_PLANET_ID)
    if row:
        return (_SPAWN_PLANET_ID, _SPAWN_LOC_X, _SPAWN_LOC_Y, _SPAWN_LOC_Z)

    row = await conn.fetchrow(
        'SELECT "p"."idp", "p"."locX", "p"."locY", "p"."locZ" '
        'FROM "a_Person" "p" '
        'JOIN "a_WorldGlobe" "g" ON "g"."id" = "p"."idp" '
        'WHERE "p"."locX" IS NOT NULL AND "p"."name" <> $1 '
        'ORDER BY "p"."id" LIMIT 1', PLACEHOLDER_AVATAR_NAME)
    if row:
        return (int(row[0]), float(row[1]), float(row[2]), float(row[3]))

    raise StubSpawnUnavailable(
        f"World {_SPAWN_PLANET_ID} is gone and no existing character has a world to borrow, so there is nowhere to stub-spawn.")


async def globe_row(conn: asyncpg.Connection, auid):
    return await conn.fetchrow('SELECT * FROM "a_WorldGlobe" WHERE "id" = $1',
                               auid)


async def star_row(conn: asyncpg.Connection, auid):
    return await conn.fetchrow('SELECT * FROM "a_Star" WHERE "id" = $1', auid)


async def stars_in_system(conn: asyncpg.Connection, system_auid):
    return await conn.fetch('SELECT * FROM "a_Star" WHERE "parent_atom" = $1',
                            system_auid)


async def system_gen_seed(conn: asyncpg.Connection, system_auid):
    row = await conn.fetchrow(
        'SELECT "genSeed" FROM "a_SolarSystem" WHERE "id" = $1', system_auid)
    return int(row[0]) if row and row[0] else None


async def ring_section_row(conn: asyncpg.Connection, auid):
    try:
        return await conn.fetchrow(
            'SELECT "sectionIndex", "orbitRadius", "terrain", "water", '
            '"atmDensity", "atmType" FROM "a_WorldRingSection" WHERE "id" = $1',
            auid)
    except Error:
        return None


async def globe_radius_and_terrain(conn: asyncpg.Connection, auid):
    return await conn.fetchrow(
        'SELECT "radius", "terrain" FROM "a_WorldGlobe" WHERE "id" = $1', auid)


def _as_byte(v) -> int:
    if isinstance(v, (bytes, bytearray, memoryview)):
        b = bytes(v)
        return b[0] if b else 0
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _struct_unpack_6f(blob: bytes):
    import struct as _s
    return _s.unpack(">ffffff", blob)


def _orbit_radius_au(v) -> float:
    if isinstance(v, (bytes, bytearray, memoryview)):
        b = bytes(v)
        if len(b) == 8:
            import struct as _s
            return float(_s.unpack("<d", b)[0])
        return 0.0
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0
