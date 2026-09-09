
from __future__ import annotations

import asyncpg

INSERTS = {
    "star": (
        'INSERT INTO "a_Star" '
        '("id", "idp", "parent_atom", "name", "specType", "specDec", '
        '"specSize", "radius", "orbit", "habZone", "orbitZones") '
        'VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) '
        'ON CONFLICT ("id") DO UPDATE SET '
        '"idp" = EXCLUDED."idp", "parent_atom" = EXCLUDED."parent_atom", '
        '"name" = EXCLUDED."name", "specType" = EXCLUDED."specType", '
        '"specDec" = EXCLUDED."specDec", "specSize" = EXCLUDED."specSize", '
        '"radius" = EXCLUDED."radius", "orbit" = EXCLUDED."orbit", '
        '"habZone" = EXCLUDED."habZone", '
        '"orbitZones" = EXCLUDED."orbitZones"'),
    "globe": (
        'INSERT INTO "a_WorldGlobe" '
        '("id", "idp", "parent_atom", "name", "orbitRadius", "orbitZone", '
        '"radius", "atmDensity", "atmType", "water", "terrain", "flora", '
        '"fauna", "geoFeatures") '
        'VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14) '
        'ON CONFLICT ("id") DO UPDATE SET '
        '"idp" = EXCLUDED."idp", "parent_atom" = EXCLUDED."parent_atom", '
        '"name" = EXCLUDED."name", "orbitRadius" = EXCLUDED."orbitRadius", '
        '"orbitZone" = EXCLUDED."orbitZone", "radius" = EXCLUDED."radius", '
        '"atmDensity" = EXCLUDED."atmDensity", '
        '"atmType" = EXCLUDED."atmType", "water" = EXCLUDED."water", '
        '"terrain" = EXCLUDED."terrain", "flora" = EXCLUDED."flora", '
        '"fauna" = EXCLUDED."fauna", '
        '"geoFeatures" = EXCLUDED."geoFeatures"'),
    "gas_giant": (
        'INSERT INTO "a_WorldGasGiant" '
        '("id", "idp", "parent_atom", "name", "orbitRadius", "orbitZone", '
        '"radius", "atmDensity", "atmType", "coreRadius", "terrain") '
        'VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) '
        'ON CONFLICT ("id") DO UPDATE SET '
        '"idp" = EXCLUDED."idp", "parent_atom" = EXCLUDED."parent_atom", '
        '"name" = EXCLUDED."name", "orbitRadius" = EXCLUDED."orbitRadius", '
        '"orbitZone" = EXCLUDED."orbitZone", "radius" = EXCLUDED."radius", '
        '"atmDensity" = EXCLUDED."atmDensity", '
        '"atmType" = EXCLUDED."atmType", '
        '"coreRadius" = EXCLUDED."coreRadius", '
        '"terrain" = EXCLUDED."terrain"'),
    "ring": (
        'INSERT INTO "a_WorldRing" '
        '("id", "idp", "parent_atom", "name", "orbitRadius", "orbitZone") '
        'VALUES ($1, $2, $3, $4, $5, $6) '
        'ON CONFLICT ("id") DO UPDATE SET '
        '"idp" = EXCLUDED."idp", "parent_atom" = EXCLUDED."parent_atom", '
        '"name" = EXCLUDED."name", "orbitRadius" = EXCLUDED."orbitRadius", '
        '"orbitZone" = EXCLUDED."orbitZone"'),
    "ring_section": (
        'INSERT INTO "a_WorldRingSection" '
        '("id", "idp", "parent_atom", "name", "orbitRadius", "orbitZone", '
        '"atmDensity", "atmType", "water", "sectionIndex", "terrain", '
        '"geoFeatures") '
        'VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) '
        'ON CONFLICT ("id") DO UPDATE SET '
        '"idp" = EXCLUDED."idp", "parent_atom" = EXCLUDED."parent_atom", '
        '"name" = EXCLUDED."name", "orbitRadius" = EXCLUDED."orbitRadius", '
        '"orbitZone" = EXCLUDED."orbitZone", '
        '"atmDensity" = EXCLUDED."atmDensity", '
        '"atmType" = EXCLUDED."atmType", "water" = EXCLUDED."water", '
        '"sectionIndex" = EXCLUDED."sectionIndex", '
        '"terrain" = EXCLUDED."terrain", '
        '"geoFeatures" = EXCLUDED."geoFeatures"'),
}


async def write_system_rows(conn: asyncpg.Connection, rows) -> None:
    for key, stmt in INSERTS.items():
        batch = getattr(rows, key)
        if not batch:
            continue
        await conn.executemany(stmt, batch)


__all__ = ["INSERTS", "write_system_rows"]
