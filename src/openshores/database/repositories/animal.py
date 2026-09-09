
from __future__ import annotations

import asyncpg

POSE_STANDING = 0x24

_A_ANIMAL_DDL = """
CREATE TABLE IF NOT EXISTS "a_Animal" (
    "id"                             BIGINT PRIMARY KEY,
    "idp"                            BIGINT,
    "locX"                           DOUBLE PRECISION,
    "locY"                           DOUBLE PRECISION,
    "locZ"                           DOUBLE PRECISION,
    "rotX"                           DOUBLE PRECISION,
    "rotY"                           DOUBLE PRECISION,
    "rotZ"                           DOUBLE PRECISION,
    "timeCreate"                     BIGINT,
    "timeModified"                   BIGINT,
    "timeTick"                       BIGINT,
    "timeTock"                       BIGINT,
    "timeDeath"                      BIGINT,
    "name"                           TEXT,
    "allegiance"                     BIGINT,
    "arenaTeam"                      INTEGER,
    "conditions"                     BYTEA,
    "hunger"                         INTEGER,
    "seatIndex"                      INTEGER,
    "hp"                             INTEGER,
    "sex"                            INTEGER,
    "dna"                            BYTEA,
    "islefty"                        INTEGER,
    "pose"                           INTEGER,
    "whichConsole"                   INTEGER,
    "atRest"                         INTEGER,
    "vecX"                           DOUBLE PRECISION,
    "vecY"                           DOUBLE PRECISION,
    "vecZ"                           DOUBLE PRECISION,
    "stamina"                        INTEGER,
    "minsToFullGrown"                INTEGER,
    "parent_atom"                    BIGINT
)
"""


async def ensure_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(_A_ANIMAL_DDL)


async def register_species(conn: asyncpg.Connection, dna_bytes: bytes,
                           name: str) -> bool:
    dna_bytes = bytes(dna_bytes)
    row = await conn.fetchrow(
        'SELECT "id" FROM "z_Specie" WHERE "dna" = $1', dna_bytes)
    if row is not None:
        return False
    sid = (hash(dna_bytes) & 0x7FFFFFFF) | 0x80000000
    await conn.execute(
        'INSERT INTO "z_Specie" ("id", "idp", "name", "dna", '
        '"timeCreate", "hp", "hunger", "stamina", "pose", "sex") '
        'VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)',
        sid, 0, name, dna_bytes, 0, 100, 0, 0x7F, POSE_STANDING, 0)
    return True


__all__ = ["POSE_STANDING", "ensure_schema", "register_species"]
