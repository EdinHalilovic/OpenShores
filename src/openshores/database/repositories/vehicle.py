
from __future__ import annotations

from typing import Optional

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.pool import IntegrityError, _now_ms

logger = get_logger(__name__)


_COLUMN_NAMES: tuple[str, ...] = (
    "id",
    "idp",
    "locX", "locY", "locZ",
    "rotX", "rotY", "rotZ",
    "timeCreate",
    "timeModified",
    "timeTick",
    "timeTock",
    "timeDeath",
    "name",
    "allegiance",
    "arenaTeam",
    "conditions",
    "damageHistory",
    "cid",
    "actBits",
    "atRest",
    "vecX", "vecY", "vecZ",
    "throttle",
    "throttleLateral",
    "throttleLong",
    "throttleVertical",
    "switches",
    "fuel",
    "hp",
    "qual",
    "ord",
    "motherShip",
    "motherShipName",
)

assert len(_COLUMN_NAMES) == 35, (
    f'a_Vehicle has {len(_COLUMN_NAMES)} columns here.'
)

_SELECT_ALL_COLUMNS = ", ".join(f'"{c}"' for c in _COLUMN_NAMES)
_VALUE_PLACEHOLDERS = ", ".join(f"${i}"
                                for i in range(1, len(_COLUMN_NAMES) + 1))


async def ensure_schema(conn: asyncpg.Connection) -> bool:
    row = await conn.fetchrow(
        """SELECT "table_name" FROM "information_schema"."tables"
            WHERE "table_schema" = 'public' AND "table_type" = 'BASE TABLE'
              AND "table_name" = 'a_Vehicle'""")
    return row is not None


async def insert_vehicle(conn: asyncpg.Connection, params: tuple) -> bool:

    sql = (f'INSERT INTO "a_Vehicle" ({_SELECT_ALL_COLUMNS}) '
           f'VALUES ({_VALUE_PLACEHOLDERS})')

    try:
        await conn.execute(sql, *params)
        return True
    except IntegrityError as exc:
        logger.warning("Vehicle 0x%x was not inserted; a row already holds "
                       "that id: %s", params[0], exc)
        return False


async def update_vehicle(conn: asyncpg.Connection, params: tuple) -> bool:
    _UPDATE_COLS = tuple(
        c for c in _COLUMN_NAMES if c not in ("id", "timeCreate", "qual")
    )
    set_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in _UPDATE_COLS)

    sql = (f'INSERT INTO "a_Vehicle" ({_SELECT_ALL_COLUMNS}) '
           f'VALUES ({_VALUE_PLACEHOLDERS}) '
           f'ON CONFLICT ("id") DO UPDATE SET {set_clause}')

    values = list(params)
    values[_COLUMN_NAMES.index("timeModified")] = _now_ms()

    await conn.execute(sql, *values)
    return True


async def load_vehicle(conn: asyncpg.Connection,
                       vehicle_id: int) -> Optional[asyncpg.Record]:
    sql = f'SELECT {_SELECT_ALL_COLUMNS} FROM "a_Vehicle" WHERE "id" = $1'
    return await conn.fetchrow(sql, int(vehicle_id))


async def load_all_vehicles(conn: asyncpg.Connection) -> list:
    sql = f'SELECT {_SELECT_ALL_COLUMNS} FROM "a_Vehicle"'
    return await conn.fetch(sql)


async def load_vehicles_by_parent(conn: asyncpg.Connection,
                                  parent_id: int) -> list:
    sql = f'SELECT {_SELECT_ALL_COLUMNS} FROM "a_Vehicle" WHERE "idp" = $1'
    return await conn.fetch(sql, int(parent_id))


async def delete_vehicle(conn: asyncpg.Connection, vehicle_id: int) -> bool:
    deleted = await conn.fetchrow(
        'DELETE FROM "a_Vehicle" WHERE "id" = $1 RETURNING "id"',
        int(vehicle_id))
    return deleted is not None
