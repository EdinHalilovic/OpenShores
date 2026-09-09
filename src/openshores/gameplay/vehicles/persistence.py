
from __future__ import annotations

import sqlite3
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Iterable, Iterator, Optional

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories import vehicle as _rows

logger = get_logger(__name__)


def _default_db_path() -> Path:
    return Path(__file__).resolve().parent.parent / "recon" / "hazeron.db"


def _db_path() -> Path:
    return _default_db_path()


_wal_initialized: bool = False


def _apply_concurrency_pragmas(db: sqlite3.Connection) -> None:
    raise NotImplementedError(
        "The three sqlite concurrency pragmas have no PostgreSQL counterpart to write here, and inventing one would be new behaviour rather than a port.")


def _open(create_if_missing: bool = False) -> Optional[sqlite3.Connection]:
    raise NotImplementedError(
        "A fresh handle per call is the thing a pool exists to stop doing.")


A_VEHICLE_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS a_Vehicle (
    id                INTEGER PRIMARY KEY,
    idp               INTEGER NOT NULL,
    locX              REAL    NOT NULL DEFAULT 0,
    locY              REAL    NOT NULL DEFAULT 0,
    locZ              REAL    NOT NULL DEFAULT 0,
    rotX              REAL    NOT NULL DEFAULT 0,
    rotY              REAL    NOT NULL DEFAULT 0,
    rotZ              REAL    NOT NULL DEFAULT 0,
    timeCreate        INTEGER NOT NULL,
    timeModified      INTEGER NOT NULL,
    timeTick          INTEGER,
    timeTock          INTEGER,
    timeDeath         INTEGER,
    name              TEXT    NOT NULL DEFAULT '',
    allegiance        INTEGER NOT NULL DEFAULT 0,
    arenaTeam         INTEGER NOT NULL DEFAULT 0,
    conditions        BLOB,
    damageHistory     BLOB,
    cid               INTEGER NOT NULL,
    actBits           INTEGER NOT NULL DEFAULT 0,
    atRest            INTEGER NOT NULL DEFAULT 0,
    vecX              REAL    NOT NULL DEFAULT 0,
    vecY              REAL    NOT NULL DEFAULT 0,
    vecZ              REAL    NOT NULL DEFAULT 0,
    throttle          INTEGER NOT NULL DEFAULT 0,
    throttleLateral   INTEGER NOT NULL DEFAULT 0,
    throttleLong      INTEGER NOT NULL DEFAULT 0,
    throttleVertical  INTEGER NOT NULL DEFAULT 0,
    switches          INTEGER NOT NULL DEFAULT 0,
    fuel              INTEGER NOT NULL DEFAULT 0,
    hp                INTEGER NOT NULL,
    qual              INTEGER NOT NULL DEFAULT 1,
    ord               BLOB,
    motherShip        INTEGER NOT NULL DEFAULT 0,
    motherShipName    TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_a_Vehicle_idp        ON a_Vehicle(idp);
CREATE INDEX IF NOT EXISTS ix_a_Vehicle_cid        ON a_Vehicle(cid);
CREATE INDEX IF NOT EXISTS ix_a_Vehicle_motherShip ON a_Vehicle(motherShip);
"""


async def ensure_schema(conn: asyncpg.Connection) -> bool:
    return await _rows.ensure_schema(conn)


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class Vehicle:

    id: int = 0
    idp: int = 0
    locX: float = 0.0
    locY: float = 0.0
    locZ: float = 0.0
    rotX: float = 0.0
    rotY: float = 0.0
    rotZ: float = 0.0
    timeCreate: int = field(default_factory=_now_ms)
    timeModified: int = field(default_factory=_now_ms)
    timeTick: Optional[int] = None
    timeTock: Optional[int] = None
    timeDeath: Optional[int] = None
    name: str = ""
    allegiance: int = 0
    arenaTeam: int = 0
    conditions: Optional[bytes] = None
    damageHistory: Optional[bytes] = None
    cid: int = 0
    actBits: int = 0
    atRest: bool = False
    vecX: float = 0.0
    vecY: float = 0.0
    vecZ: float = 0.0
    throttle: int = 0
    throttleLateral: int = 0
    throttleLong: int = 0
    throttleVertical: int = 0
    switches: int = 0
    fuel: int = 0
    hp: int = 1
    qual: int = 1
    ord: Optional[bytes] = None          # noqa: A003
    motherShip: int = 0
    motherShipName: str = ""


_COLUMN_NAMES: tuple[str, ...] = tuple(f.name for f in fields(Vehicle))

assert len(_COLUMN_NAMES) == 35, (
    f'Vehicle dataclass has {len(_COLUMN_NAMES)} fields.'
)


def _vehicle_to_params(v: Vehicle) -> tuple:
    return (
        v.id,
        v.idp,
        v.locX, v.locY, v.locZ,
        v.rotX, v.rotY, v.rotZ,
        v.timeCreate,
        v.timeModified,
        v.timeTick,
        v.timeTock,
        v.timeDeath,
        v.name,
        v.allegiance,
        v.arenaTeam,
        v.conditions,
        v.damageHistory,
        v.cid,
        v.actBits,
        1 if v.atRest else 0,
        v.vecX, v.vecY, v.vecZ,
        v.throttle,
        v.throttleLateral,
        v.throttleLong,
        v.throttleVertical,
        v.switches,
        v.fuel,
        v.hp,
        v.qual,
        v.ord,
        v.motherShip,
        v.motherShipName,
    )


def _row_to_vehicle(row: tuple) -> Vehicle:
    return Vehicle(
        id=row[0],
        idp=row[1],
        locX=row[2], locY=row[3], locZ=row[4],
        rotX=row[5], rotY=row[6], rotZ=row[7],
        timeCreate=row[8],
        timeModified=row[9],
        timeTick=row[10],
        timeTock=row[11],
        timeDeath=row[12],
        name=row[13],
        allegiance=row[14],
        arenaTeam=row[15],
        conditions=bytes(row[16]) if row[16] is not None else None,
        damageHistory=bytes(row[17]) if row[17] is not None else None,
        cid=row[18],
        actBits=row[19],
        atRest=bool(row[20]),
        vecX=row[21], vecY=row[22], vecZ=row[23],
        throttle=row[24],
        throttleLateral=row[25],
        throttleLong=row[26],
        throttleVertical=row[27],
        switches=row[28],
        fuel=row[29],
        hp=row[30],
        qual=row[31],
        ord=bytes(row[32]) if row[32] is not None else None,
        motherShip=row[33],
        motherShipName=row[34],
    )


_SELECT_ALL_COLUMNS = ", ".join(_COLUMN_NAMES)


async def insert_vehicle(
    conn: asyncpg.Connection,
    v: Vehicle,
) -> bool:
    return await _rows.insert_vehicle(conn, _vehicle_to_params(v))


async def update_vehicle(
    conn: asyncpg.Connection,
    v: Vehicle,
) -> bool:
    v.timeModified = _now_ms()
    return await _rows.update_vehicle(conn, _vehicle_to_params(v))


async def load_vehicle(
    conn: asyncpg.Connection,
    vehicle_id: int,
) -> Optional[Vehicle]:
    row = await _rows.load_vehicle(conn, vehicle_id)
    if row is None:
        return None
    return _row_to_vehicle(row)


async def load_all_vehicles(
    conn: asyncpg.Connection,
) -> list[Vehicle]:
    return [_row_to_vehicle(r) for r in await _rows.load_all_vehicles(conn)]


async def load_vehicles_by_parent(
    conn: asyncpg.Connection,
    parent_id: int,
) -> list[Vehicle]:
    return [_row_to_vehicle(r)
            for r in await _rows.load_vehicles_by_parent(conn, parent_id)]


async def delete_vehicle(
    conn: asyncpg.Connection,
    vehicle_id: int,
) -> bool:
    return await _rows.delete_vehicle(conn, vehicle_id)


def _selftest_roundtrip() -> None:
    raise NotImplementedError(
        "Retired")


if __name__ == "__main__":
    logger.info("vehicles.persistence self-test starting")
    _selftest_roundtrip()
    logger.info("vehicles.persistence self-test passed")
