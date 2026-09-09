
from __future__ import annotations

import struct

import asyncpg


def _u8_blob(value) -> bytes:
    return bytes([int(value) & 0xFF])


def _f64_blob(value) -> bytes:
    return struct.pack("<d", float(value))


async def _row_exists(conn: asyncpg.Connection, table: str,
                      auid: int) -> bool:
    row = await conn.fetchrow(
        f'SELECT 1 FROM "{table}" WHERE "id" = $1', int(auid))
    return row is not None


async def sector_set(conn: asyncpg.Connection, *, auid: int, name: str,
                     loc_x: float, loc_y: float, loc_z: float,
                     now: int) -> bool:
    async with conn.transaction():
        created = not await _row_exists(conn, "a_Sector", auid)
        await conn.execute(
            'INSERT INTO "a_Sector" '
            '("id", "name", "locX", "locY", "locZ", '
            '"timeCreate", "timeModified") '
            'VALUES ($1, $2, $3, $4, $5, $6, $6) '
            'ON CONFLICT ("id") DO UPDATE SET '
            '"name" = EXCLUDED."name", '
            '"locX" = EXCLUDED."locX", '
            '"locY" = EXCLUDED."locY", '
            '"locZ" = EXCLUDED."locZ", '
            '"timeModified" = EXCLUDED."timeModified"',
            int(auid), str(name), float(loc_x), float(loc_y), float(loc_z),
            int(now))
    return created


async def system_set(conn: asyncpg.Connection, *, auid: int, name: str,
                     loc_x: float, loc_y: float, loc_z: float,
                     parent_atom: int, now: int) -> bool:
    async with conn.transaction():
        created = not await _row_exists(conn, "a_SolarSystem", auid)
        await conn.execute(
            'INSERT INTO "a_SolarSystem" '
            '("id", "name", "locX", "locY", "locZ", "parent_atom", '
            '"timeCreate", "timeModified") '
            'VALUES ($1, $2, $3, $4, $5, $6, $7, $7) '
            'ON CONFLICT ("id") DO UPDATE SET '
            '"name" = EXCLUDED."name", '
            '"locX" = EXCLUDED."locX", '
            '"locY" = EXCLUDED."locY", '
            '"locZ" = EXCLUDED."locZ", '
            '"parent_atom" = EXCLUDED."parent_atom", '
            '"timeModified" = EXCLUDED."timeModified"',
            int(auid), str(name), float(loc_x), float(loc_y), float(loc_z),
            int(parent_atom), int(now))
    return created


async def world_set(conn: asyncpg.Connection, *, auid: int, name: str,
                    parent_atom: int, orbit_zone: int, orbit_radius: float,
                    atm_type: int, atm_density: int, water: int,
                    radius: float, now: int) -> bool:
    async with conn.transaction():
        created = not await _row_exists(conn, "a_WorldGlobe", auid)
        await conn.execute(
            'INSERT INTO "a_WorldGlobe" '
            '("id", "name", "parent_atom", "orbitZone", "orbitRadius", '
            '"atmType", "atmDensity", "water", "radius", '
            '"timeCreate", "timeModified") '
            'VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10) '
            'ON CONFLICT ("id") DO UPDATE SET '
            '"name" = EXCLUDED."name", '
            '"parent_atom" = EXCLUDED."parent_atom", '
            '"orbitZone" = EXCLUDED."orbitZone", '
            '"orbitRadius" = EXCLUDED."orbitRadius", '
            '"atmType" = EXCLUDED."atmType", '
            '"atmDensity" = EXCLUDED."atmDensity", '
            '"water" = EXCLUDED."water", '
            '"radius" = EXCLUDED."radius", '
            '"timeModified" = EXCLUDED."timeModified"',
            int(auid), str(name), int(parent_atom),
            _u8_blob(orbit_zone), _f64_blob(orbit_radius),
            _u8_blob(atm_type), _u8_blob(atm_density), _u8_blob(water),
            float(radius), int(now))
    return created


__all__ = ["sector_set", "system_set", "world_set"]
