from __future__ import annotations

import math
import struct
from typing import Optional, Tuple, List

import asyncpg

from openshores.core.logging import get_logger

logger = get_logger(__name__)


_ATOM_TABLES = (
    "a_WorldGlobe",
    "a_WorldGasGiant",
    "a_WorldRing",
    "a_WorldRingSection",
    "a_Star",
    "a_SolarSystem",
    "a_Sector",
    "a_Galaxy",
    "a_Universe",
)

GAME_UNITS_PER_AU = 2_400_000.0


async def _derive_orbit_position(
        conn: asyncpg.Connection, globe_row, *,
        wch, wc, tr) -> Optional[Tuple[float, float, float]]:
    au = globe_row.get("orbitRadius")
    if au is None:
        return None
    seed = None
    is_moon = False
    try:
        cur_id = globe_row.get("parent_atom") or globe_row.get("idp")
        for _ in range(6):
            if cur_id is None:
                return None
            row = await conn.fetchrow(
                'SELECT "genSeed" FROM "a_SolarSystem" WHERE "id"=$1',
                int(cur_id))
            if row:
                seed = row[0]
                break
            nxt = None
            for tbl in ("a_Star", "a_WorldGlobe", "a_WorldGasGiant"):
                r = await conn.fetchrow(
                    f'SELECT "parent_atom" FROM "{tbl}" WHERE "id"=$1',
                    int(cur_id))
                if r:
                    if tbl != "a_Star":
                        is_moon = True
                    nxt = r[0]
                    break
            if nxt is None:
                return None
            cur_id = nxt
    except Exception:
        return None
    if not seed:
        return None
    try:
        body = wch.make_body(dict(globe_row), int(seed), breathable=False,
                             is_moon=is_moon)
        tx, ty, tz = wc.world_transform(
            body, await _sim_time_ms(conn)).translation
        return _offset_ring_section(globe_row, float(tx), float(ty), float(tz),
                                    tr=tr)
    except Exception:
        return None


def _offset_ring_section(row, tx: float, ty: float, tz: float, *, tr):
    try:
        idx = row["sectionIndex"]
    except (KeyError, IndexError, TypeError):
        return (tx, ty, tz)
    if idx is None:
        return (tx, ty, tz)
    idx = int(idx[0] if isinstance(idx, (bytes, bytearray)) else idx)

    orbit_au = math.hypot(tx, ty, tz) / tr.AU_IN_UNITS
    if orbit_au <= 0.0:
        return (tx, ty, tz)
    sections = tr.ring_section_count(orbit_au)
    if sections <= 0:
        return (tx, ty, tz)

    phi = tr.ring_section_angle(sections) * idx
    c, s = math.cos(phi), math.sin(phi)
    return (tx * c - ty * s, tx * s + ty * c, tz)


async def _sim_time_ms(conn: asyncpg.Connection | None = None) -> float:
    if conn is not None:
        row = await conn.fetchrow(
            'SELECT "anchor_ms" FROM "b_SimTimeAnchor" ORDER BY "id" DESC '
            'LIMIT 1')
        if row and row[0]:
            return float(row[0])
    import time as _t
    return _t.time() * 1000.0


_RESOLVE_PRECEDENCE = (
    "a_Universe",
    "a_Galaxy",
    "a_Sector",
    "a_SolarSystem",
    "a_Star",
    "a_WorldGasGiant",
    "a_WorldRing",
    "a_WorldGlobe",
    "a_WorldRingSection",
)

_DUP_REPORTED: set = set()


async def _atom_tables_for(conn: asyncpg.Connection, auid: int) -> List[str]:
    out = []
    for tbl in _ATOM_TABLES:
        try:
            if await conn.fetchrow(
                    f'SELECT 1 FROM "{tbl}" WHERE "id" = $1 LIMIT 1',
                    int(auid)):
                out.append(tbl)
        except Exception:
            continue
    return out


async def _find_atom_table(conn: asyncpg.Connection, auid: int) -> Optional[str]:
    hits = await _atom_tables_for(conn, auid)
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    if auid not in _DUP_REPORTED:
        _DUP_REPORTED.add(auid)
        logger.warning(
            'Duplicate AuId 0x%08x (%s) is in %s.',
            auid, auid, ", ".join(hits))
    for tbl in _RESOLVE_PRECEDENCE:
        if tbl in hits:
            return tbl
    return hits[0]


async def _row_with_parent(conn: asyncpg.Connection, auid: int):
    tbl = await _find_atom_table(conn, auid)
    if not tbl:
        return None, None
    cols = [c[0] for c in await conn.fetch(
        """SELECT "column_name" FROM "information_schema"."columns"
            WHERE "table_schema" = 'public' AND "table_name" = $1
            ORDER BY "ordinal_position"
        """, tbl)]
    row = await conn.fetchrow(f'SELECT * FROM "{tbl}" WHERE "id" = $1',
                              int(auid))
    if not row:
        return None, None
    return tbl, dict(zip(cols, row))


async def _walk_to_root(conn: asyncpg.Connection, auid: int,
                        max_depth: int = 12) -> List[Tuple[str, dict]]:
    chain: List[Tuple[str, dict]] = []
    cur_id = auid
    seen: set = set()
    for _ in range(max_depth):
        if cur_id in seen:
            logger.warning(
                "parent_atom CYCLE at 0x%08x while walking 0x%08x; stopping "
                "with %d links resolved.",
                int(cur_id), int(auid), len(chain))
            break
        seen.add(cur_id)
        tbl, row = await _row_with_parent(conn, cur_id)
        if not row:
            break
        chain.append((tbl, row))
        parent = row.get("parent_atom")
        if not parent:
            break
        cur_id = parent
    return chain


def _unpack_orbit_au(blob: bytes) -> float:
    if not blob or len(blob) < 8:
        return 1.0
    try:
        return struct.unpack("<d", bytes(blob[:8]))[0]
    except Exception:
        return 1.0


def _terrain_floats(blob):
    if not blob:
        return None
    try:
        b = bytes(blob)
    except Exception:
        return None
    if len(b) != 24:
        return None
    import struct as _s
    return _s.unpack(">ffffff", b)


def _zone_byte(blob: bytes) -> int:
    if not blob:
        return 4
    return blob[0] if len(blob) > 0 else 4


def _byte_or(blob, default=0) -> int:
    if not blob:
        return default
    try:
        return blob[0]
    except Exception:
        return default


def _atm_byte(v) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v) & 0xFF
    try:
        b = bytes(v)
    except Exception:
        return None
    return b[0] if b else None


def _row_has_atmosphere(row) -> bool:
    dens = _atm_byte(row.get("atmDensity"))
    water = _atm_byte(row.get("water"))
    return bool(dens or water)


async def apply_sql_world_to_bundle(conn: asyncpg.Connection, bundle, *,
                                    SiblingGlobe, gen_planet, gen_moon,
                                    HAB_RANDOM, wch, wc, tr) -> bool:
    if not bundle.whereabouts_auid:
        return False

    try:
        chain = await _walk_to_root(conn, bundle.whereabouts_auid)
        if not chain:
            return False

        home_tbl, home_row = chain[0]
        home_table_set = ("a_WorldGlobe", "a_WorldGasGiant",
                          "a_WorldRing", "a_WorldRingSection")
        if home_tbl not in home_table_set:
            return False

        star_row = None; star_tbl = None
        system_row = None; system_tbl = None
        sector_row = None; sector_tbl = None
        for tbl, row in chain[1:]:
            if tbl == "a_Star" and not star_row:
                star_tbl, star_row = tbl, row
            elif tbl == "a_SolarSystem" and not system_row:
                system_tbl, system_row = tbl, row
            elif tbl == "a_Sector" and not sector_row:
                sector_tbl, sector_row = tbl, row

        if not (star_row and system_row and sector_row):
            return False

        bundle.sector_auid = sector_row["id"]
        bundle.sector_name = sector_row.get("name") or ""
        bundle.sector_position = (
            sector_row.get("locX") or 0.0,
            sector_row.get("locY") or 0.0,
            sector_row.get("locZ") or 0.0)
        bundle.sector_rotation = (
            sector_row.get("rotX") or 0.0,
            sector_row.get("rotY") or 0.0,
            sector_row.get("rotZ") or 0.0)

        bundle.system_auid = system_row["id"]
        bundle.system_name = system_row.get("name") or ""
        bundle.system_position = (
            system_row.get("locX") or 0.0,
            system_row.get("locY") or 0.0,
            system_row.get("locZ") or 0.0)
        bundle.system_rotation = (
            system_row.get("rotX") or 0.0,
            system_row.get("rotY") or 0.0,
            system_row.get("rotZ") or 0.0)

        bundle.celestial_body_auid = star_row["id"]
        bundle.star_name = star_row.get("name") or ""
        bundle.celestial_body_position = (
            star_row.get("locX") or 0.0,
            star_row.get("locY") or 0.0,
            star_row.get("locZ") or 0.0)
        bundle.celestial_body_rotation = (
            star_row.get("rotX") or 0.0,
            star_row.get("rotY") or 0.0,
            star_row.get("rotZ") or 0.0)

        def _b1(v, default=0):
            if isinstance(v, (bytes, bytearray)) and len(v) >= 1:
                return v[0]
            if isinstance(v, int):
                return v
            return default
        bundle.star_spec_type     = _b1(star_row.get("specType"), 4)
        bundle.star_spec_size     = _b1(star_row.get("specSize"), 5)
        bundle.star_spec_subclass = _b1(star_row.get("specDec"), 5)
        oz = star_row.get("orbitZones")
        if isinstance(oz, (bytes, bytearray)) and len(oz) >= 16:
            bundle.star_orbit_zones = bytes(oz[:16])
        zb = bundle.star_orbit_zones
        hab_4_indices = [i for i, b in enumerate(zb) if b == 4]
        zero_indices  = [i for i, b in enumerate(zb) if b == 0]
        bundle.star_hab_first = hab_4_indices[-1] if hab_4_indices else 0xFF
        bundle.star_hab_last  = zero_indices[-1]  if zero_indices  else 0xFF

        bundle.planet_name = home_row.get("name") or ""
        bundle.planet_auid = home_row["id"]
        bundle.planet_position = (
            home_row.get("locX") or 0.0,
            home_row.get("locY") or 0.0,
            home_row.get("locZ") or 0.0)
        if home_row.get("locX") is None:
            _derived = await _derive_orbit_position(conn, home_row,
                                                    wch=wch, wc=wc, tr=tr)
            if _derived is not None:
                bundle.planet_position = _derived
        if bundle.planet_position == (0.0, 0.0, 0.0):
            logger.warning(
                'Home world %r (auid=%s) has no position.', bundle.planet_name, home_row["id"])
        bundle.planet_rotation = (
            home_row.get("rotX") or 0.0,
            home_row.get("rotY") or 0.0,
            home_row.get("rotZ") or 0.0)
        bundle.planet_terrain = _terrain_floats(home_row.get("terrain"))
        bundle.planet_zone = _zone_byte(home_row.get("orbitZone"))
        bundle.planet_size_byte_b1 = _byte_or(home_row.get("atmType"))
        bundle.planet_size_byte_b2 = _byte_or(home_row.get("atmDensity"))
        bundle.planet_size_byte_b3 = _byte_or(home_row.get("water"))

        home_is_moon = (home_tbl == "a_WorldGlobe"
                        and (home_row.get("parent_atom") or 0) != star_row["id"])

        if home_is_moon:
            _parent_id = home_row.get("parent_atom")
            logger.info(
                "Home is a moon (auid=%s, parent=%s); position %s is "
                "parent-relative, as the engine stores it.",
                home_row["id"], _parent_id, bundle.planet_position)

        if home_tbl == "a_WorldRingSection":
            bundle.planet_kind = "ring_section"
            bundle.planet_section_index = int(home_row.get("sectionIndex") or 0)
            logger.info(
                'Home is a RING SECTION (auid=%s, section %s).',
                home_row["id"], bundle.planet_section_index)
        elif home_is_moon and _row_has_atmosphere(home_row):
            bundle.planet_kind = "globe"
            logger.info(
                'Moon %r has a real atmosphere in SQL (atmType=%s, atmDens=%s, water=%s).',
                bundle.planet_name, bundle.planet_size_byte_b1,
                bundle.planet_size_byte_b2, bundle.planet_size_byte_b3)
        elif home_is_moon:
            bundle.planet_kind = "moon"
            _g = gen_moon(home_row["id"])
            bundle.planet_size_byte_b1 = _g.atm_type
            bundle.planet_size_byte_b2 = _g.atm_dens
            bundle.planet_size_byte_b3 = _g.water
            bundle.planet_size_code = _g.size_code
            logger.info(
                'Moon %r (auid=%s) carries no atmosphere.',
                bundle.planet_name, home_row["id"])
        else:
            bundle.planet_kind = "globe"
        radius_m = home_row.get("radius")
        if radius_m and float(radius_m) <= 255.0:
            bundle.planet_size_code = int(float(radius_m))
        elif radius_m:
            d = float(radius_m) * 2
            if   d < 5_000:    sc = 1
            elif d < 8_000:    sc = 2
            elif d < 12_000:   sc = 3
            elif d < 16_000:   sc = 4
            elif d < 22_000:   sc = 5
            elif d < 30_000:   sc = 6
            elif d < 45_000:   sc = 8
            elif d < 70_000:   sc = 10
            else:              sc = 12
            bundle.planet_size_code = sc
        else:
            bundle.planet_size_code = 4

        bundle.whereabouts_auid = home_row["id"]
        bundle.whereabouts_place = bundle.planet_name
        bundle.whereabouts_display = ("On " + bundle.planet_name
                                       if bundle.planet_name else None)

        sibling_rows = []
        star_id = star_row["id"]
        for tbl in ("a_WorldGlobe", "a_WorldGasGiant",
                    "a_WorldRing", "a_WorldRingSection"):
            cols = [c[0] for c in await conn.fetch(
                """SELECT "column_name" FROM "information_schema"."columns"
                    WHERE "table_schema" = 'public' AND "table_name" = $1
                    ORDER BY "ordinal_position"
                """, tbl)]
            for row in await conn.fetch(
                    f'SELECT * FROM "{tbl}" WHERE "parent_atom" = $1 '
                    f'AND "id" != $2',
                    star_id, home_row["id"]):
                sibling_rows.append((tbl, dict(zip(cols, row))))
        top_ids = {home_row["id"]}
        for tbl, row in sibling_rows:
            top_ids.add(row["id"])
        if top_ids:
            _top_list = list(top_ids)
            placeholders = ",".join(f"${i}" for i in
                                    range(1, len(_top_list) + 1))
            for tbl in ("a_WorldGlobe", "a_WorldGasGiant"):
                cols = [c[0] for c in await conn.fetch(
                    """SELECT "column_name" FROM "information_schema"."columns"
                        WHERE "table_schema" = 'public' AND "table_name" = $1
                        ORDER BY "ordinal_position"
                    """, tbl)]
                q = (f'SELECT * FROM "{tbl}" '
                     f'WHERE "parent_atom" IN ({placeholders}) '
                     f'AND "id" != ${len(_top_list) + 1}')
                for row in await conn.fetch(q, *_top_list, home_row["id"]):
                    rd = dict(zip(cols, row))
                    if (tbl, rd["id"]) in {(t, r["id"]) for t, r in sibling_rows}:
                        continue
                    sibling_rows.append((tbl, rd))

        bundle.sibling_globes = []
        for tbl, row in sibling_rows:
            _sg_auid = row["id"]
            _sg_zone = _zone_byte(row.get("orbitZone"))
            _is_moon = (tbl == "a_WorldGlobe"
                        and (row.get("parent_atom") or 0) != star_id)
            _sql_b1 = _byte_or(row.get("atmType"))
            _sql_b2 = _byte_or(row.get("atmDensity"))
            _sql_b3 = _byte_or(row.get("water"))
            _atm_b1, _atm_b2, _atm_b3 = _sql_b1, _sql_b2, _sql_b3
            _core_radius = (_byte_or(row.get("coreRadius"))
                            if tbl == "a_WorldGasGiant" else None)
            _gen_size = 4
            _UNIFORM_DEFAULT = (2, 30, 20)
            if _is_moon and _row_has_atmosphere(row):
                pass
            elif _is_moon:
                g = gen_moon(_sg_auid)
                _atm_b1, _atm_b2, _atm_b3 = g.atm_type, g.atm_dens, g.water
                _gen_size = g.size_code
            elif (_sql_b1, _sql_b2, _sql_b3) in (
                    (0, 0, 0), _UNIFORM_DEFAULT, (None, None, None)
            ) or not (_sql_b1 or _sql_b2 or _sql_b3):
                g = gen_planet(_sg_auid, HAB_RANDOM)
                _atm_b1, _atm_b2, _atm_b3 = g.atm_type, g.atm_dens, g.water
                _gen_size = g.size_code
            sg = SiblingGlobe(
                auid=_sg_auid,
                name=row.get("name") or "",
                parent_auid=row.get("parent_atom") or 0,
                position=(row.get("locX") or 0.0,
                          row.get("locY") or 0.0,
                          row.get("locZ") or 0.0),
                rotation=(row.get("rotX") or 0.0,
                          row.get("rotY") or 0.0,
                          row.get("rotZ") or 0.0),
                size_code=_gen_size,
                size_byte_b1=_atm_b1,
                size_byte_b2=_atm_b2,
                size_byte_b3=_atm_b3,
                core_radius=int(_core_radius or 0),
                terrain=_terrain_floats(row.get("terrain")),
                zone=_sg_zone,
            )
            if tbl == "a_WorldGasGiant":
                sg.class_kind = "gas_giant"
            elif tbl == "a_WorldRingSection":
                sg.class_kind = "ring_section"
                sg.section_index = int(row.get("sectionIndex") or 0)
            elif tbl == "a_WorldRing":
                sg.class_kind = "ring"
            elif row.get("parent_atom") != star_id:
                sg.class_kind = "moon"
            else:
                sg.class_kind = "globe"
            rad = row.get("radius")
            if rad and float(rad) <= 255.0:
                sg.size_code = int(float(rad))
            elif rad:
                d = float(rad) * 2
                if   d < 5_000:    sg.size_code = 1
                elif d < 8_000:    sg.size_code = 2
                elif d < 12_000:   sg.size_code = 3
                elif d < 16_000:   sg.size_code = 4
                elif d < 22_000:   sg.size_code = 5
                elif d < 30_000:   sg.size_code = 6
                elif d < 50_000:   sg.size_code = 7
                else:              sg.size_code = 8
            if row.get("locX") is None:
                _sp = await _derive_orbit_position(conn, row,
                                                   wch=wch, wc=wc, tr=tr)
                if _sp is not None:
                    sg.position = _sp
            bundle.sibling_globes.append(sg)
        return True
    except Exception as e:
        logger.error("The SQL world load failed; the bundle keeps whatever "
                     "produced it: %r", e)
        return False
