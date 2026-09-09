
from __future__ import annotations

from typing import NamedTuple, Optional

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.pool import LOCK_SPACE_PERSON, _immediate, _now_ms
from openshores.database.repositories.spawn import (
    StubSpawnUnavailable,
    _stub_spawn,
)
from openshores.protocol.atoms.gear import (
    _apply_weapon_typeid_migration,
    _unpack_au_gear,
)
from openshores.protocol.atoms.item import _extract_cid_from_auitem_body

logger = get_logger(__name__)


def _rows_affected(status: str) -> int:
    return int(status.rsplit(" ", 1)[-1])


_session_login_ms: dict[int, int] = {}

_synthetic_auid_map: dict[int, int] = {}


def register_synthetic_auid(synthetic_auid: int, db_id: int) -> None:
    key = int(synthetic_auid) & 0xFFFFFFFF
    val = int(db_id) & 0xFFFFFFFF
    _synthetic_auid_map[key] = val


def clear_synthetic_auid(synthetic_auid: int) -> None:
    _synthetic_auid_map.pop(int(synthetic_auid) & 0xFFFFFFFF, None)


async def mark_online(conn: asyncpg.Connection, auid: int, perm: int = 5) -> bool:
    rid = await _resolve_person_id(conn, auid)
    if rid is None:
        return False
    now = _now_ms()
    status = await conn.execute(
        'UPDATE "a_Person" SET "isonline" = 1, "timeModified" = $1 '
        'WHERE "id" = $2',
        now, rid
    )
    _session_login_ms[rid] = now
    return _rows_affected(status) > 0


async def flush_online_time(conn: asyncpg.Connection, auid: int) -> bool:
    rid = await _resolve_person_id(conn, auid)
    if rid is None:
        return False
    start_ms = _session_login_ms.get(rid)
    if start_ms is None:
        return False
    now = _now_ms()
    elapsed_secs = max(0, (now - start_ms) // 1000)
    if elapsed_secs == 0:
        return False
    status = await conn.execute(
        'UPDATE "a_Person" '
        'SET "timeOnlineSecs" = "timeOnlineSecs" + $1, "timeModified" = $2 '
        'WHERE "id" = $3',
        elapsed_secs, now, rid
    )
    _session_login_ms[rid] = now
    return _rows_affected(status) > 0


async def mark_offline(conn: asyncpg.Connection, auid: int) -> bool:
    await flush_online_time(conn, auid)
    rid = await _resolve_person_id(conn, auid)
    if rid is None:
        return False
    status = await conn.execute(
        'UPDATE "a_Person" SET "isonline" = 0, "timeModified" = $1 '
        'WHERE "id" = $2',
        _now_ms(), rid
    )
    _session_login_ms.pop(rid, None)
    return _rows_affected(status) > 0


def _person_id_candidates(auid: int) -> tuple:
    a = int(auid) & 0xFFFFFFFF
    return (a, (a << 8) & 0xFFFFFFFF)


async def _resolve_person_id(conn: asyncpg.Connection, auid: int):
    hint = int(auid) & 0xFFFFFFFF
    mapped = _synthetic_auid_map.get(hint)
    if mapped is not None:
        row = await conn.fetchrow('SELECT "id" FROM "a_Person" WHERE "id" = $1', mapped)
        if row:
            return int(row[0])
    row = await conn.fetchrow('SELECT "id" FROM "a_Person" WHERE "id" = $1', hint)
    if row:
        return int(row[0])
    row = await conn.fetchrow(
        'SELECT "id" FROM "a_Person" WHERE ("id" >> 8) = $1', hint)
    if row:
        return int(row[0])
    return None


async def read_person_state(conn: asyncpg.Connection, auid: int):
    rid = await _resolve_person_id(conn, auid)
    if rid is None:
        return None
    row = await conn.fetchrow(
        'SELECT "locX", "locY", "locZ", "hp", "hunger", "stamina", "pose", '
        '"isonline", "idp", '
        '"xp", "bank", CAST("social" AS INTEGER), "islefty", "dna", '
        '"max_hp", "timeOnlineSecs", "max_stamina", "max_hunger", "sex", '
        '"seaChest" '
        'FROM "a_Person" WHERE "id" = $1', rid)
    if not row:
        return None
    out = {}
    lx, ly, lz = row[0], row[1], row[2]
    if (lx is not None and ly is not None and lz is not None
            and (abs(float(lx)) > 1e-6 or abs(float(ly)) > 1e-6
                 or abs(float(lz)) > 1e-6)):
        out["locXYZ"] = (float(lx), float(ly), float(lz))
    if row[3]  is not None: out["hp"]             = int(row[3])
    if row[4]  is not None: out["hunger"]         = int(row[4])
    if row[5]  is not None: out["stamina"]        = int(row[5])
    if row[6]  is not None: out["pose"]           = int(row[6])
    if row[7]  is not None: out["isonline"]       = int(row[7])
    if row[8]  is not None: out["idp"]            = int(row[8])
    if row[9]  is not None: out["xp"]             = int(row[9])
    if row[10] is not None: out["bank"]            = float(row[10])
    if row[11] is not None: out["reputation"]      = int(row[11])
    if row[12] is not None: out["islefty"]         = int(row[12])
    if row[13] is not None: out["dna"]             = bytes(row[13])
    if row[14] is not None: out["max_hp"]          = int(row[14])
    if row[15] is not None: out["timeOnlineSecs"]  = int(row[15])
    if row[16] is not None: out["max_stamina"]     = int(row[16])
    if row[17] is not None: out["max_hunger"]      = int(row[17])
    if row[18] is not None: out["sex"]             = int(row[18])
    if row[19] is not None: out["seaChest"]        = bytes(row[19])
    return out or None


async def read_person_position(conn: asyncpg.Connection, auid: int):
    rid = await _resolve_person_id(conn, auid)
    if rid is None:
        return None
    row = await conn.fetchrow(
        'SELECT "locX", "locY", "locZ" FROM "a_Person" WHERE "id" = $1', rid)
    if not row:
        return None
    lx, ly, lz = float(row[0] or 0.0), float(row[1] or 0.0), float(row[2] or 0.0)
    if abs(lx) < 1e-6 and abs(ly) < 1e-6 and abs(lz) < 1e-6:
        return None
    return (lx, ly, lz)


async def update_person_position(conn: asyncpg.Connection, auid: int,
                                 x: float, y: float, z: float,
                                 vx: float = None, vy: float = None,
                                 vz: float = None) -> bool:
    fields = {
        "locX": float(x),
        "locY": float(y),
        "locZ": float(z),
    }
    if vx is not None: fields["vecX"] = float(vx)
    if vy is not None: fields["vecY"] = float(vy)
    if vz is not None: fields["vecZ"] = float(vz)
    return await update_person_state(conn, auid, **fields)


async def update_person_state(conn: asyncpg.Connection, auid: int, **fields) -> bool:
    if not fields:
        return False
    rid = await _resolve_person_id(conn, auid)
    if rid is None:
        return False
    valid = {row["column_name"] for row in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = $1""",
        "a_Person")}
    clean = {k: v for k, v in fields.items() if k in valid}
    if not clean:
        return False
    clean.setdefault("timeModified", _now_ms())
    parts = ", ".join(f'"{k}" = ${i}' for i, k in enumerate(clean, 1))
    vals = list(clean.values()) + [rid]
    status = await conn.execute(
        f'UPDATE "a_Person" SET {parts} WHERE "id" = ${len(vals)}', *vals)
    return _rows_affected(status) > 0


async def _load_augear_from_sql(conn: asyncpg.Connection, player_auid_int):
    row = await conn.fetchrow(
        'SELECT "inv" FROM "a_Person" WHERE "id" = $1',
        int(player_auid_int) & 0xFFFFFFFF)
    if not row or not row[0]:
        return None
    blob = bytes(row[0])
    try:
        entries = _unpack_au_gear(blob)
    except Exception as exc:
        logger.warning(
            "Equipment blob for avatar 0x%08x will not decode (%r); the "
            "avatar loads with nothing held. blob_hex=%s",
            player_auid_int, exc, blob.hex())
        return None
    logger.debug("Avatar 0x%08x: %d equipment slot(s) in a_Person.inv.",
                 player_auid_int, len(entries))
    for e in entries:
        cid = _extract_cid_from_auitem_body(bytes(e[3])) if len(e) >= 4 else 0
        logger.debug("Slot=%s sub=%s typeId=0x%02x cid=%d (%#x) bodylen=%d",
                     e[0], e[1], e[2], cid, cid, len(e[3]))
    _apply_weapon_typeid_migration(entries, source=f"sql:0x{player_auid_int:x}")
    return entries


async def _load_all_persons_from_sql(conn: asyncpg.Connection):
    rows = await conn.fetch(
        'SELECT "id", "name", "locX", "locY", "locZ", "inv", "dna" '
        'FROM "a_Person" ORDER BY "id"')
    out = []
    for rid, name, lx, ly, lz, inv, dna in rows:
        xyz = None
        if lx is not None and ly is not None and lz is not None:
            xyz = (float(lx), float(ly), float(lz))
        out.append({
            "auid": int(rid) & 0xFFFFFFFF,
            "name": str(name) if name is not None else "",
            "xyz": xyz,
            "inv": bytes(inv) if inv else b"",
            "dna": bytes(dna) if dna else b"",
        })
    return out


async def _lookup_person_by_auid(conn: asyncpg.Connection, auid_int):
    row = await conn.fetchrow(
        'SELECT "id", "name", "locX", "locY", "locZ", "dna", "sex", "islefty" '
        'FROM "a_Person" WHERE "id" = $1',
        int(auid_int) & 0xFFFFFFFF)
    if not row:
        return None
    rid, name, lx, ly, lz, dna, _sex, _lefty = row
    xyz = None
    if lx is not None and ly is not None and lz is not None:
        xyz = (float(lx), float(ly), float(lz))
    dna_bytes = bytes(dna or b"")[:24]
    if len(dna_bytes) < 24:
        dna_bytes = dna_bytes + b"\x00" * (24 - len(dna_bytes))
    return {
        "auid": int(rid) & 0xFFFFFFFF,
        "name": str(name) if name is not None else "",
        "xyz": xyz,
        "dna": dna_bytes,
        "sex": None if _sex is None else int(_sex),
        "islefty": None if _lefty is None else bool(_lefty),
    }


async def read_person_inv(conn: asyncpg.Connection, auid: int):
    rid = await _resolve_person_id(conn, auid)
    if rid is None:
        return None, b""
    row = await conn.fetchrow(
        'SELECT "inv" FROM "a_Person" WHERE "id" = $1', rid)
    if not row or not row[0]:
        return rid, b""
    return rid, bytes(row[0])


_SPAWN_PLANET_ID = 1494406
_SPAWN_GALAXY_ID = 117
_SPAWN_LOC_X     = 12511.849824272622
_SPAWN_LOC_Y     = 12535.980575589503
_SPAWN_LOC_Z     = -5851.405423170647


def _pad_dna(dna24: bytes) -> bytes:
    dna = bytes(dna24)[:24]
    return dna + bytes(24 - len(dna)) if len(dna) < 24 else dna


async def create_character(conn: asyncpg.Connection, name: str, dna24: bytes,
                           sex: int = 1, *,
                           stats: tuple,
                           homestead_with_retry,
                           policy_for_name, DEFAULT_POLICY, describe_policy,
                           galaxy: str = "ShoresOfHazeron", region=8,
                           galaxy_number: int = 1, created: int = 1577836800):
    dna = _pad_dna(dna24)
    _hp, _ms, _hunger = stats

    async def _insert(home, pos):
        now = _now_ms()
        return await conn.fetchval(
            'INSERT INTO "a_Person"'
            ' ("name", "dna", "sex", "idp", "spawnGalaxy", "locX", "locY", "locZ",'
            '  "hp", "max_hp", "stamina", "max_stamina", "hunger", "max_hunger",'
            '  "bank", "xp", "isonline", "atRest", "autoEat", "islefty", "inv",'
            '  "timeCreate", "timeModified")'
            ' VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,'
            '0.0,0,0,1,1,0,$15,$16,$17)'
            ' RETURNING "id"',
            name, dna, int(sex), int(home.home_globe_auid),
            _SPAWN_GALAXY_ID,
            float(pos[0]), float(pos[1]), float(pos[2]),
            _hp, _hp, _ms, _ms, _hunger, _hunger,
            bytes(1), now, now)

    policy = policy_for_name(name)
    if policy is not DEFAULT_POLICY:
        logger.info("create_character %r matches the %r home policy; "
                    "searching for %s",
                    name, policy.label, describe_policy(policy))

    home, _pos, new_id = await homestead_with_retry(
        conn, galaxy=galaxy, region=region, galaxy_number=galaxy_number,
        created=created, then=_insert, policy=policy)

    logger.info("create_character %r -> %r in %r (%s %s, cell %s), "
                "%s atom rows, seed rerolled %sx%s",
                name, home.home_globe_name, home.system_name,
                home.galaxy.name, region, home.sector_cell,
                home.rows_written, home.reroll_attempts,
                "" if policy is DEFAULT_POLICY
                else f" under the {policy.label!r} policy")
    return new_id, home


async def create_person(conn: asyncpg.Connection, name: str, dna24: bytes,
                        sex: int = 1, *, stats: tuple):
    try:
        now = _now_ms()
        dna = bytes(dna24)[:24]
        if len(dna) < 24:
            dna += b"\x00" * (24 - len(dna))
        _empty_inv = b"\x00"
        _start_hp, _ms, _start_hunger = stats
        _idp, _sx, _sy, _sz = await _stub_spawn(conn)
        return await conn.fetchval(
            'INSERT INTO "a_Person"'
            ' ("name", "dna", "sex",'
            '  "idp", "spawnGalaxy",'
            '  "locX", "locY", "locZ",'
            '  "hp", "max_hp", "stamina", "max_stamina", "hunger", "max_hunger",'
            '  "bank", "xp",'
            '  "isonline", "atRest", "autoEat", "islefty",'
            '  "inv",'
            '  "timeCreate", "timeModified")'
            ' VALUES'
            ' ($1, $2, $3,'
            '  $4, $5,'
            '  $6, $7, $8,'
            '  $9, $10, $11, $12, $13, $14,'
            '  0.0, 0,'
            '  0, 1, 1, 0,'
            '  $15,'
            '  $16, $17)'
            ' RETURNING "id"',
            name,
            dna,
            int(sex),
            _idp,
            _SPAWN_GALAXY_ID,
            _sx, _sy, _sz,
            _start_hp,
            _start_hp,
            _ms,
            _ms,
            _start_hunger,
            _start_hunger,
            _empty_inv,
            now, now,
        )
    except StubSpawnUnavailable as exc:
        logger.error("No character created for %r: %s", name, exc)
        return None


PLACEHOLDER_AVATAR_NAME = '(wizard-placeholder)'


async def create_placeholder_person(conn: asyncpg.Connection, sex: int = 1):
    try:
        now = _now_ms()
        empty_dna = b"\x00" * 24
        empty_inv = b"\x00"
        _idp, _sx, _sy, _sz = await _stub_spawn(conn)
        new_id = await conn.fetchval(
            'INSERT INTO "a_Person"'
            ' ("name", "dna", "sex",'
            '  "idp", "spawnGalaxy",'
            '  "locX", "locY", "locZ",'
            '  "hp", "max_hp", "stamina", "max_stamina", "hunger", "max_hunger",'
            '  "bank", "xp",'
            '  "isonline", "atRest", "autoEat", "islefty",'
            '  "inv",'
            '  "timeCreate", "timeModified")'
            ' VALUES'
            ' ($1, $2, $3,'
            '  $4, $5,'
            '  $6, $7, $8,'
            '  100, 100, 100, 100, 100, 100,'
            '  0.0, 0,'
            '  0, 1, 1, 0,'
            '  $9,'
            '  $10, $11)'
            ' RETURNING "id"',
            PLACEHOLDER_AVATAR_NAME,
            empty_dna,
            int(sex),
            _idp,
            _SPAWN_GALAXY_ID,
            _sx, _sy, _sz,
            empty_inv,
            now, now,
        )
        logger.info("Wizard placeholder row id=%s created; awaiting the "
                    "variant-B submit.", new_id)
        return new_id
    except StubSpawnUnavailable as exc:
        logger.error("No wizard placeholder created: %s", exc)
        return None


class _WizardRejected(Exception):
    pass


class WizardCommit(NamedTuple):

    person_id: int
    home: object = None

    @property
    def homesteaded(self) -> bool:
        return self.home is not None

    @property
    def world_name(self) -> str:
        return getattr(self.home, "home_globe_name", "") or ""


async def update_person_from_wizard(conn: asyncpg.Connection, db_id: int,
                                    name: str, dna24: bytes, sex: int = 1, *,
                                    stats: tuple,
                                    homestead_with_retry,
                                    policy_for_name, DEFAULT_POLICY,
                                    describe_policy, GALAXY_CHOICES,
                                    REGION_NAMES,
                                    origin=None) -> Optional[WizardCommit]:
    dna = _pad_dna(dna24)
    hp, stamina, hunger = stats

    async def _write(home=None, pos=None):
        async with _immediate(conn, LOCK_SPACE_PERSON,
                              int(db_id) & 0xFFFFFFFF):
            row = await conn.fetchrow(
                'SELECT "name" FROM "a_Person" WHERE "id" = $1',
                int(db_id) & 0xFFFFFFFF
            )
            if row is None:
                raise _WizardRejected(f"Row id={db_id} not found")
            if row[0] != PLACEHOLDER_AVATAR_NAME:
                raise _WizardRejected(
                    f"Row id={db_id} name={row[0]!r} is not a placeholder.")

            sets = ['"name" = ?', '"dna" = ?', '"sex" = ?',
                    '"islefty" = COALESCE("islefty", 0)',
                    '"hp" = ?', '"max_hp" = ?',
                    '"stamina" = ?', '"max_stamina" = ?',
                    '"hunger" = ?', '"max_hunger" = ?',
                    '"timeModified" = ?']
            args = [name, dna, int(sex),
                    hp, hp, stamina, stamina, hunger, hunger, _now_ms()]
            if home is not None and pos is not None:
                sets[-1:-1] = ['"idp" = ?', '"locX" = ?', '"locY" = ?', '"locZ" = ?']
                args[-1:-1] = [int(home.home_globe_auid),
                               float(pos[0]), float(pos[1]), float(pos[2])]

            clause = ", ".join(sets)
            for _n in range(1, len(args) + 1):
                clause = clause.replace("?", f"${_n}", 1)
            await conn.execute(
                f'UPDATE "a_Person" SET {clause} WHERE "id" = ${len(args) + 1}',
                *args, int(db_id) & 0xFFFFFFFF,
            )
            return True

    try:
        pre = await conn.fetchrow('SELECT "name" FROM "a_Person" WHERE "id" = $1',
                                  int(db_id) & 0xFFFFFFFF)
        if pre is None:
            raise _WizardRejected(f"Row id={db_id} not found")
        if pre[0] != PLACEHOLDER_AVATAR_NAME:
            raise _WizardRejected(
                f"Row id={db_id} name={pre[0]!r} is not a placeholder.")

        if origin is None:
            await _write()
            logger.info("Wizard commit: id=%s name=%r dna=%s",
                        db_id, name, dna.hex())
            return WizardCommit(int(db_id) & 0xFFFFFFFF, None)

        g_idx, r_idx = int(origin[0]), int(origin[1])
        if g_idx not in GALAXY_CHOICES:
            raise _WizardRejected(
                f"Galaxy index {g_idx} is not one the client offers")

        policy = policy_for_name(name)
        if policy is not DEFAULT_POLICY:
            logger.info("Wizard commit: %r matches the %r home policy; "
                        "searching for %s",
                        name, policy.label, describe_policy(policy))

        home, _pos, _ = await homestead_with_retry(
            conn, galaxy=GALAXY_CHOICES[g_idx], region=r_idx,
            galaxy_number=1, created=1577836800, then=_write, policy=policy)

        logger.info("Wizard commit: id=%s name=%r homesteaded on %r in %r "
                    "(%s / %s), %s atom rows, seed rerolled %sx%s",
                    db_id, name, home.home_globe_name, home.system_name,
                    home.galaxy.name, REGION_NAMES[home.region_index],
                    home.rows_written, home.reroll_attempts,
                    "" if policy is DEFAULT_POLICY
                    else f" under the {policy.label!r} policy")
        return WizardCommit(int(db_id) & 0xFFFFFFFF, home)

    except _WizardRejected as exc:
        logger.warning("Wizard commit refused for id=%s: %s", db_id, exc)
        return None
    except Exception as exc:
        logger.error(
            "Character creation failed for id=%s (%r). The placeholder is left for the orphan cleanup and no character was created; the player's Origin choice %s could not be honoured.",
            db_id, exc, origin)
        return None


async def clear_all_online_flags(conn: asyncpg.Connection) -> int:
    rows = await conn.fetch('SELECT "id", "name" FROM "a_Person" WHERE "isonline" = 1')
    stale = [(int(r[0]), r[1]) for r in rows]
    if not stale:
        return 0
    await conn.execute('UPDATE "a_Person" SET "isonline" = 0 WHERE "isonline" = 1')
    logger.info("Cleared %s stale online flag(s) left by a restart: %s%s",
                len(stale),
                ", ".join(f"0x{i:08x} {n!r}" for i, n in stale[:8]),
                " ..." if len(stale) > 8 else "")
    return len(stale)


async def cleanup_orphan_placeholders(conn: asyncpg.Connection,
                                      min_age_seconds: int = 0) -> int:
    cutoff = _now_ms() - (int(min_age_seconds) * 1000)
    rows = await conn.fetch(
        'SELECT "id" FROM "a_Person" '
        'WHERE "name" = $1 AND "timeCreate" <= $2',
        PLACEHOLDER_AVATAR_NAME, cutoff,
    )
    ids = [int(r[0]) for r in rows]
    if not ids:
        return 0
    for _id in ids:
        await conn.execute('DELETE FROM "a_Person" WHERE "id" = $1', _id)
    logger.info("Deleted %s abandoned wizard row(s): %s",
                len(ids), [hex(i) for i in ids])
    return len(ids)


async def repair_null_avatar_fields(conn: asyncpg.Connection, *,
                                    dna_max_stamina, dna_max_hp) -> int:
    rows = await conn.fetch(
        'SELECT "id", "name", "hp", "max_hp", "max_stamina", "max_hunger", '
        '       "islefty", "dna" '
        'FROM "a_Person"'
    )
    touched = 0
    for rid, name, hp, max_hp, max_stam, max_hu, islefty, dna in rows:
        if name == PLACEHOLDER_AVATAR_NAME:
            continue
        sets = {}
        if max_stam is None:
            if dna and len(dna) >= 24:
                sets["max_stamina"] = int(dna_max_stamina(bytes(dna)))
            else:
                sets["max_stamina"] = 127
        if max_hp is None:
            base_hp = int(hp) if hp is not None and int(hp) > 0 else 46
            want = 46
            if dna and len(dna) >= 24:
                want = int(dna_max_hp(bytes(dna)))
            sets["max_hp"] = max(base_hp, want)
        if max_hu is None:
            resolved_max_hp = sets.get("max_hp", max_hp)
            if resolved_max_hp is None:
                resolved_max_hp = 46
            sets["max_hunger"] = int(resolved_max_hp) * 2
        if islefty is None:
            sets["islefty"] = 0
        if not sets:
            continue
        sets["timeModified"] = _now_ms()
        parts = ", ".join(f'"{k}" = ${i}' for i, k in enumerate(sets, 1))
        vals = list(sets.values()) + [int(rid)]
        await conn.execute(
            f'UPDATE "a_Person" SET {parts} WHERE "id" = ${len(vals)}', *vals
        )
        touched += 1
        logger.info("Repaired a_Person id=0x%08x name=%r -> %s",
                    int(rid), name,
                    {k: v for k, v in sets.items() if k != 'timeModified'})
    return touched


async def read_spawn_record(conn: asyncpg.Connection, actor_auid: int):
    return await conn.fetchrow(
        'SELECT "spawncity", "spawnCityName", "spawnx", "spawny", '
        '"spawnship", "spawnShipName", "berthType", '
        '"arenaEntered", "arenaExitParent", '
        '"arenaExitLocX", "arenaExitLocY", "arenaExitLocZ" '
        'FROM "a_Person" WHERE "id" = $1', int(actor_auid) & 0xFFFFFFFF)
