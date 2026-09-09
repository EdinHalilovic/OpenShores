
from __future__ import annotations

import asyncpg

BLUEPRINT_COLUMNS: tuple[str, ...] = (
    "design_id", "name", "stem", "soh_version", "blueprint_type",
    "design_state", "construction_process_id", "design_material",
    "design_blob", "file_blob", "report_bytes", "construction_blob",
    "owner_auid", "published_at",
)

_CONFLICT_KEY = "design_id"

_READ_COLUMNS = ('"design_id", "name", "stem", "design_state", '
                 '"design_material", "construction_process_id", '
                 '"design_blob", "report_bytes", "construction_blob", '
                 '"owner_auid", "published_at"')


async def published_blueprints(conn: asyncpg.Connection) -> list:
    return list(await conn.fetch(
        f'SELECT {_READ_COLUMNS} FROM "hz_blueprint" ORDER BY "stem"'))


async def blueprint_count(conn: asyncpg.Connection) -> int:
    return int(await conn.fetchval('SELECT COUNT(*) FROM "hz_blueprint"'))


async def blueprint_by_design_id(conn: asyncpg.Connection, design_id):
    return await conn.fetchrow(
        f'SELECT {_READ_COLUMNS} FROM "hz_blueprint" WHERE "design_id" = $1',
        int(design_id) & 0xFFFFFFFF)


def upsert_statement() -> str:
    cols = ", ".join(f'"{c}"' for c in BLUEPRINT_COLUMNS)
    placeholders = ", ".join(f"${i}" for i in range(1, len(BLUEPRINT_COLUMNS) + 1))
    sets = ", ".join(f'"{c}" = EXCLUDED."{c}"'
                     for c in BLUEPRINT_COLUMNS if c != _CONFLICT_KEY)
    return (f'INSERT INTO "hz_blueprint" ({cols}) VALUES ({placeholders}) '
            f'ON CONFLICT ("{_CONFLICT_KEY}") DO UPDATE SET {sets}')


async def upsert_blueprint(conn: asyncpg.Connection, *, design_id, name, stem,
                           soh_version, blueprint_type, design_state,
                           construction_process_id, design_material,
                           design_blob, file_blob, report_bytes,
                           construction_blob, owner_auid, published_at) -> None:
    await conn.execute(
        upsert_statement(),
        int(design_id) & 0xFFFFFFFF, name, stem,
        int(soh_version), int(blueprint_type), int(design_state),
        int(construction_process_id) & 0xFFFFFFFF, int(design_material) & 0xFFFF,
        design_blob, file_blob, report_bytes, construction_blob,
        (None if owner_auid is None else int(owner_auid) & 0xFFFFFFFF),
        published_at)
