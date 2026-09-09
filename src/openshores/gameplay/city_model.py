
from __future__ import annotations

import math
import struct
import os
from typing import Optional

from openshores.core.logging import get_logger
from openshores.database.repositories.city import read_city_world_auid
from openshores.database.repositories.world import read_atom_globe

logger = get_logger(__name__)

_IND_TO_CPID_WARNED = set()
_CPROC_TABLE_CACHE = None


def _cproc_table():
    global _CPROC_TABLE_CACHE
    if _CPROC_TABLE_CACHE is None:
        from . import gd_tables as _gd
        _CPROC_TABLE_CACHE = _gd.load_construction_processes()
    return _CPROC_TABLE_CACHE


def industry_to_cpid_safe(industry, default_cpid=67):
    ind = int(industry or 0) & 0xFF
    table = _cproc_table()
    if table:
        from . import gd_tables as _gd
        cpid = _gd.industry_to_cpid(ind, table)
        if cpid:
            return cpid & 0x7F
        if ind not in _IND_TO_CPID_WARNED:
            _IND_TO_CPID_WARNED.add(ind)
            logger.warning('Industry 0x%02x has no construction process in GD.', ind)
        return 0
    if ind not in _IND_TO_CPID_WARNED:
        _IND_TO_CPID_WARNED.add(ind)
        logger.warning("GD unavailable; industry 0x%02x falls back to cpid "
                       "%d.", ind, int(default_cpid) & 0x7F)
    return int(default_cpid) & 0x7F


WORLD_UNITS_PER_METER = 3.280839895013123
WIRE_FEET_PER_METER = WORLD_UNITS_PER_METER
DEFAULT_ROAD_WIDTH_M = 8.0
DEFAULT_ROAD_WIDTH_WORLD = DEFAULT_ROAD_WIDTH_M * WORLD_UNITS_PER_METER


def road_width_full_world(rd, default=DEFAULT_ROAD_WIDTH_WORLD):
    ww = rd.get("width_wire")
    if ww:
        return float(ww)
    wm = rd.get("width_m")
    if wm:
        return float(wm) * WORLD_UNITS_PER_METER
    wl = rd.get("width")
    if wl:
        return float(wl)
    return float(default)


def road_width_full_m(rd, default=DEFAULT_ROAD_WIDTH_M):
    return road_width_full_world(rd) / WORLD_UNITS_PER_METER


def _road_width(rd, default=None):
    return road_width_full_world(rd) * 0.5


_WORLD_SIZE_CACHE: dict = {}


def _db_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "hazeron.db")


async def world_size_code(conn, world_auid) -> Optional[int]:
    key = int(world_auid) & 0xFFFFFFFF
    if not key:
        return None
    if key in _WORLD_SIZE_CACHE:
        return _WORLD_SIZE_CACHE[key]
    size = None
    globe = await read_atom_globe(conn, key)
    if globe is not None and globe["radius"] is not None:
        size = int(float(globe["radius"])) & 0xFF
    _WORLD_SIZE_CACHE[key] = size
    return size


def invalidate_world_size_cache() -> None:
    _WORLD_SIZE_CACHE.clear()
    _CITY_WORLD_CACHE.clear()


_CITY_WORLD_CACHE: dict = {}


async def city_world_auid(conn, city_auid) -> Optional[int]:
    key = int(city_auid) & 0xFFFFFFFF
    if not key:
        return None
    if key in _CITY_WORLD_CACHE:
        return _CITY_WORLD_CACHE[key]
    world = None
    row = await read_city_world_auid(conn, key)
    if row and row[0] is not None:
        world = int(row[0]) & 0xFFFFFFFF
    _CITY_WORLD_CACHE[key] = world
    return world


_SEA_RADIUS_FALLBACK_LOGGED: set = set()


async def _sea_level_radius_m(conn, world_auid=None):
    size = await world_size_code(conn, world_auid) if world_auid else None
    if size:
        from .worldgen import world_gen as _wg
        return size * _wg.UNITS_PER_SIZE
    _k = int(world_auid or 0) & 0xFFFFFFFF
    if _k not in _SEA_RADIUS_FALLBACK_LOGGED:
        _SEA_RADIUS_FALLBACK_LOGGED.add(_k)
        logger.warning('World 0x%08x has no size byte.', _k)
    return None


_ALT_LOGGED = set()


async def _bld_alt_logged(conn, bld, world_auid=None) -> float:
    alt = await building_alt_msl(conn, bld, world_auid)
    key = (int(world_auid or 0) & 0xFFFFFFFF, bld.get("cpid"), round(alt, 1))
    if key not in _ALT_LOGGED:
        _ALT_LOGGED.add(key)
        rg = await _sea_level_radius_m(conn, world_auid)
        logger.debug("Bld cpid=%s design=%s alt_msl=%.2fm (R_sea=%s, world=0x%08x size=%s) yaw->0x190=%.3f",
                     bld.get("cpid"), bld.get("design_id", 0), alt,
                     rg if rg else "n/a",
                     int(world_auid or 0) & 0xFFFFFFFF,
                     await world_size_code(conn, world_auid),
                     float(bld.get("facing", 0.0)))
    return alt


async def building_alt_msl(conn, bld, world_auid=None) -> float:
    if bld.get("alt_msl") is not None:
        return float(bld["alt_msl"])
    xyz = bld.get("xyz")
    if xyz:
        rg = await _sea_level_radius_m(conn, world_auid)
        if rg:
            x, y, z = (float(v) for v in xyz)
            return math.sqrt(x * x + y * y + z * z) - rg
    return 0.0


def _road_alt_offset():
    return 0.0


DEV_BUILDING = 0x01
DEV_BLD_BASE = 0x02
DEV_BUILDING_3 = 0x03
DEV_SPACECRAFT_FACTORY = 0x05
DEV_FARM = 0x06
DEV_HOUSE = 0x07
DEV_LOGGING_CAMP = 0x08
DEV_MINE = 0x09
DEV_ORCHARD = 0x0A
DEV_PARK = 0x0B
DEV_SOLAR_POWER = 0x0C
DEV_WELL = 0x0D
DEV_WIND_POWER = 0x0E
DEV_ZOO = 0x0F
DEV_GLOBE_ROAD = 0x10
DEV_BIODOME = 0x11
DEV_GUARD_TOWER = 0x12
DEV_ORBITAL_FACTORY = 0x13
DEV_MEDIA = 0x14

CITY_AUX_CAPITAL = 0x08
CITY_AUX_HABITABLE_CAPITAL = 0x10

CITY_IDENTITY = 0x0001
CITY_PATENTS = 0x0002
CITY_FLAGS = 0x0004
CITY_MANUFACTURING = 0x0008
CITY_DNA = 0x0010
CITY_BUILDINGS_FULL = 0x0020
CITY_BUILDINGS_INC = 0x0040
CITY_ROADS_FULL = 0x0080
CITY_ROADS_INC = 0x0100
CITY_MARKERS = 0x0200
CITY_GAMES = 0x0400
CITY_DEV_MAP_7F0 = 0x0800
CITY_DEV_MAP_7A8 = 0x1000


def _qstring(s: Optional[str]) -> bytes:
    if s is None:
        return struct.pack(">I", 0xFFFFFFFF)
    raw = s.encode("utf-16-be")
    return struct.pack(">I", len(raw)) + raw


def encode_auglobellf(lat_rad: float, lon_rad: float) -> bytes:
    return struct.pack(">ff", float(lon_rad), float(lat_rad))


def xyz_to_latlon(xyz, r_globe: Optional[float] = None):
    x, y, z = (float(v) for v in xyz)
    r = math.sqrt(x * x + y * y + z * z)
    if r < 1e-9:
        return (0.0, 0.0)
    lat = math.atan2(z, math.hypot(x, y))
    lon = math.atan2(y, x)
    return (lat, lon)


def encode_dpbuilding_body(cpid: int, lat_rad: float, lon_rad: float, *,
                           facing: float = 0.0,
                           param190: float = 0.0,
                           levels: int = 1,
                           material: int = 0,
                           construction_env: int = 0,
                           construction_start_ms: int = 0,
                           val16a: int = 0,
                           val48: int = 0,
                           flag49: bool = False,
                           design_id: int = 0,
                           construction_blob: Optional[bytes] = None) -> bytes:
    b = bytearray()
    devflags = cpid & 0x7F
    if construction_blob:
        devflags |= 0x80
    b.append(devflags)
    if construction_blob:
        b += bytes(construction_blob)
    b += struct.pack(">f", float(facing))
    b += encode_auglobellf(lat_rad, lon_rad)
    if construction_blob:
        has_start = bool(val48)
    else:
        has_start = True
    word = design_id & 0x7FFFFFFF
    if has_start:
        word |= 0x80000000
    b += struct.pack(">I", word)
    b += struct.pack(">f", float(param190))
    if has_start:
        b += struct.pack(">q", int(construction_start_ms))
    sub = construction_env & 0x07
    if flag49:
        sub |= 0x08
    if val16a:
        sub |= 0x10
    if val48:
        sub |= 0x20
    if levels >= 2:
        sub |= 0x40
    if material:
        sub |= 0x80
    b.append(sub)
    if sub & 0x10:
        b += struct.pack(">H", val16a & 0xFFFF)
    if sub & 0x20:
        b.append(val48 & 0xFF)
    if sub & 0x40:
        b.append(levels & 0xFF)
    if sub & 0x80:
        b += struct.pack(">H", material & 0xFFFF)
    return bytes(b)


def decode_dpbuilding_body(buf: bytes, off: int = 0, read_construction=None):
    devflags = buf[off]; off += 1
    cpid = devflags & 0x7F
    cblob = None
    if devflags & 0x80:
        if read_construction is None:
            raise ValueError("Construction process present but no reader given")
        cblob, off = read_construction(buf, off)
    facing = struct.unpack_from(">f", buf, off)[0]; off += 4
    lon, lat = struct.unpack_from(">ff", buf, off); off += 8
    word = struct.unpack_from(">I", buf, off)[0]; off += 4
    param190 = struct.unpack_from(">f", buf, off)[0]; off += 4
    start_ms = 0
    if word & 0x80000000:
        start_ms = struct.unpack_from(">q", buf, off)[0]; off += 8
    sub = buf[off]; off += 1
    env = sub & 0x07
    flag49 = bool(sub & 0x08)
    val16a = val48 = levels = material = 0
    if sub & 0x10:
        val16a = struct.unpack_from(">H", buf, off)[0]; off += 2
    if sub & 0x20:
        val48 = buf[off]; off += 1
    if sub & 0x40:
        levels = buf[off]; off += 1
    if sub & 0x80:
        material = struct.unpack_from(">H", buf, off)[0]; off += 2
    return ({
        "cpid": cpid, "construction_blob": cblob, "facing": facing,
        "lat": lat, "lon": lon, "word": word & 0x7FFFFFFF,
        "param190": param190, "construction_start_ms": start_ms,
        "construction_env": env, "flag49": flag49, "val16a": val16a,
        "val48": val48, "levels": (levels or 1), "material": material,
    }, off)


ROAD_CPID_TO_KIND = {2: 0, 3: 1, 4: 2, 5: 4, 7: 3, 0x4A: 5, 0x50: 6, 0x51: 7}
ROAD_OPTYPE_TO_CPID = {0x0A: 5, 0x0B: 2, 0x0C: 3, 0x0D: 4}


def encode_deconstructionprocess(cpid: int, *, env: int = 1, levels: int = 1,
                                 design_id: Optional[int] = None) -> bytes:
    b = bytearray()
    b.append((int(cpid) & 0x7F) | (0x80 if design_id is not None else 0))
    b.append(int(env) & 0xFF)
    b += struct.pack(">h", int(levels) & 0xFFFF)
    b.append(0)
    b.append(0)
    b += struct.pack(">h", 0)
    b.append(0)
    if design_id is not None:
        b += struct.pack(">i", int(design_id))
    return bytes(b)


def serialize_road_cstate(cstate) -> bytes:
    cpid = int(cstate.get("cpid", cstate.get("procId", 0))) & 0x7F
    labor = int(cstate.get("labor", 0))
    comps = cstate.get("components", []) or []
    designId = int(cstate.get("designId", 0) or 0)
    b = bytearray()
    b.append(cpid | (0x80 if designId else 0x00))
    b.append(int(cstate.get("f10", 0)) & 0xFF)
    b += struct.pack(">h", labor)
    b.append(len(comps) & 0xFF)
    for comp in comps:
        cid, b2, eff, req, applied = (list(comp) + [0, 0, 0, 0, 0])[:5]
        b += (struct.pack(">h", int(cid) & 0xFFFF) + struct.pack(">B", int(b2) & 0xFF)
              + struct.pack(">B", int(eff) & 0xFF) + struct.pack(">i", int(req))
              + struct.pack(">i", int(applied)) + struct.pack(">B", 0))
    b.append(int(cstate.get("f28", 0)) & 0xFF)
    b += struct.pack(">h", int(cstate.get("f2a", 0)))
    b.append(int(cstate.get("flags2", 0)) & 0xFF)
    if designId:
        b += struct.pack(">i", designId & 0xFFFFFFFF)
    return bytes(b)


def _road_construction_blob(rd, cpid):
    cst = rd.get("cstate")
    if cst:
        return serialize_road_cstate(cst)
    if rd.get("under_construction"):
        return encode_deconstructionprocess(int(cpid))
    return None


def encode_dpgloberoad_body(road_cpid: int, lat1, lon1, lat2, lon2, *,
                            width: float = DEFAULT_ROAD_WIDTH_WORLD * 0.5, alt1: float = 0.0,
                            alt2: float = 0.0, render_kind: Optional[int] = None,
                            construction_blob: Optional[bytes] = None) -> bytes:
    if render_kind is None:
        render_kind = ROAD_CPID_TO_KIND.get(int(road_cpid) & 0x7F, 0)
    b = bytearray()
    if construction_blob:
        b.append((int(road_cpid) & 0x7F) | 0x80)
        b += bytes(construction_blob)
    else:
        b.append(int(road_cpid) & 0x7F)
    b.append(((int(render_kind) & 0x0F) << 4) | 0x02)
    b += struct.pack(">f", float(alt1))
    b += encode_auglobellf(float(lat1), float(lon1))
    b += struct.pack(">f", float(alt2))
    b += encode_auglobellf(float(lat2), float(lon2))
    b += struct.pack(">f", float(width))
    return bytes(b)


GEO_ROAD_OPTYPES = {0x0A, 0x0B, 0x0C, 0x0D}


def _road_ll_key(rd):
    la1, lo1 = _road_endpoint_ll(rd, 1)
    la2, lo2 = _road_endpoint_ll(rd, 2)
    q = 1e-5
    return (round(la1 / q), round(lo1 / q), round(la2 / q), round(lo2 / q))


_DEVLL_NUDGE_RAD = 1.5e-6


def _devll_f32_key(la2, lo2):
    return struct.unpack(">ff", struct.pack(">ff", float(lo2), float(la2)))


def resolve_devll_collisions(ll2_pairs):
    seen = set()
    out = []
    nudged = 0
    for la2, lo2 in ll2_pairs:
        rla2, rlo2 = float(la2), float(lo2)
        key = _devll_f32_key(rla2, rlo2)
        if key not in seen:
            seen.add(key)
            out.append((rla2, rlo2))
            continue
        step = 0
        while key in seen and step < 4096:
            step += 1
            rla2 = float(la2) + (_DEVLL_NUDGE_RAD * step)
            rlo2 = float(lo2) + (_DEVLL_NUDGE_RAD * (step // 2))
            key = _devll_f32_key(rla2, rlo2)
        seen.add(key)
        out.append((rla2, rlo2))
        nudged += 1
    return out, nudged


def dedupe_roads(roads):
    if not roads:
        return list(roads or [])
    seen = set()
    out = []
    for rd in roads:
        key = _road_ll_key(rd)
        if key in seen:
            continue
        seen.add(key)
        out.append(rd)
    return out


def encode_geo_road_feature(optype, latA, lonA, altA, latB, lonB, altB, *,
                            width: float = DEFAULT_ROAD_WIDTH_WORLD, construction_blob=None,
                            quality_bit: bool = False) -> bytes:
    b = bytearray()
    b.append(int(optype) & 0xFF)
    b += encode_auglobellf(float(latA), float(lonA))
    flags = (0x01 if quality_bit else 0) | (0x80 if construction_blob else 0)
    b.append(flags)
    b += struct.pack(">f", float(altA))
    b += encode_auglobellf(float(latB), float(lonB))
    b += struct.pack(">f", float(altB))
    b += struct.pack(">f", float(width))
    if construction_blob:
        b += bytes(construction_blob)
    return bytes(b)


def _road_endpoint_ll(rd, which):
    pkey = "p1" if which == 1 else "p2"
    p = rd.get(pkey)
    if p and len(p) >= 3:
        return xyz_to_latlon(p)
    if which == 1:
        lat, lon = float(rd.get("lat1", 0.0)), float(rd.get("lon1", 0.0))
    else:
        lat, lon = float(rd.get("lat2", 0.0)), float(rd.get("lon2", 0.0))
    if abs(lat) > math.pi / 2 + 1e-6 or abs(lon) > math.pi + 1e-6:
        lat, lon = math.radians(lat), math.radians(lon)
    return (lat, lon)


def road_devll_for_emit(rd):
    cached = rd.get("_devll")
    if cached:
        return (float(cached[0]), float(cached[1]))
    return _road_endpoint_ll(rd, 2)


def merge_roads_into_geo_payload(geo_payload: bytes, roads) -> bytes:
    roads = [r for r in (roads or [])
             if int(r.get("road_type", 0x0B)) in GEO_ROAD_OPTYPES]
    if not roads:
        return geo_payload
    count = geo_payload[0] if geo_payload else 0
    body = bytearray(geo_payload[1:] if geo_payload else b"")
    added = 0
    for rd in roads:
        if added + count >= 0xFF:
            break
        optype = int(rd.get("road_type", 0x0B))
        cblob = _road_construction_blob(
            rd, ROAD_OPTYPE_TO_CPID.get(optype, 2))
        _la1, _lo1 = _road_endpoint_ll(rd, 1)
        _la2, _lo2 = road_devll_for_emit(rd)
        _ao = _road_alt_offset()
        body += encode_geo_road_feature(
            optype,
            _la2, _lo2, float(rd.get("alt2", 0.0) or 0.0) + _ao,
            _la1, _lo1, float(rd.get("alt1", 0.0) or 0.0) + _ao,
            width=road_width_full_world(rd),
            construction_blob=cblob)
        added += 1
    return bytes([(count + added) & 0xFF]) + bytes(body)


async def encode_dacity_body(conn, buildings, *, name: Optional[str] = None,
                             identity_report: str = "", identity_auid: int = 0,
                             aux: int = 0, roads=None,
                             is_capital: bool = False,
                             habitable_capital: bool = False,
                             world_auid=None) -> bytes:
    flags = 0
    if name is not None or identity_auid:
        flags |= CITY_IDENTITY
    if buildings:
        flags |= CITY_BUILDINGS_FULL
    if roads is not None:
        roads = dedupe_roads(roads)
        flags |= CITY_ROADS_FULL
    aux = int(aux) & 0xFF
    if is_capital:
        aux |= CITY_AUX_CAPITAL
    if habitable_capital:
        aux |= CITY_AUX_HABITABLE_CAPITAL
    b = bytearray()
    b += struct.pack(">H", flags)
    b.append(aux & 0xFF)
    if flags & CITY_IDENTITY:
        b += _qstring(name)
        b += struct.pack(">I", identity_auid & 0xFFFFFFFF)
        b += _qstring(identity_report)
    if flags & CITY_BUILDINGS_FULL:
        b += struct.pack(">h", len(buildings))
        for bld in buildings:
            dev_type = int(bld.get("type", DEV_BUILDING)) & 0xFF
            b.append(dev_type)
            b += encode_dpbuilding_body(
                int(bld["cpid"]), float(bld["lat"]), float(bld["lon"]),
                facing=await _bld_alt_logged(conn, bld, world_auid),
                param190=float(bld.get("param190", bld.get("facing", 0.0))),
                levels=int(bld.get("levels", 1)),
                material=int(bld.get("material", 0)),
                construction_env=int(bld.get("construction_env", 0)),
                construction_start_ms=int(bld.get("construction_start_ms", 0)),
                val16a=int(bld.get("val16a", 0)),
                val48=int(bld.get("val48", 0)),
                flag49=bool(bld.get("flag49", False)),
                design_id=int(bld.get("design_id", 0)),
                construction_blob=bld.get("construction_blob"),
            )
    if flags & CITY_ROADS_FULL:
        b += struct.pack(">h", len(roads))
        _ll2_pairs = [_road_endpoint_ll(rd, 2) for rd in roads]
        _ll2_resolved, _n_nudged = resolve_devll_collisions(_ll2_pairs)
        for _rd, _res in zip(roads, _ll2_resolved):
            _rd["_devll"] = (float(_res[0]), float(_res[1]))
        if _n_nudged:
            logger.info("DevLL(ll2) collision: nudged %d of %d road(s) to "
                        "distinct city+0x5c8 keys so each stays "
                        "listable/workable in the City dock.",
                        _n_nudged, len(roads))
        for _idx, rd in enumerate(roads):
            b.append(DEV_GLOBE_ROAD)
            _cpid = rd.get("cpid")
            if _cpid is None:
                _cpid = ROAD_OPTYPE_TO_CPID.get(int(rd.get("road_type", 0x0B)), 2)
            _rk = rd.get("render_kind")
            _cblob = _road_construction_blob(rd, int(_cpid))
            _la1, _lo1 = _road_endpoint_ll(rd, 1)
            _la2, _lo2 = _ll2_resolved[_idx]
            b += encode_dpgloberoad_body(
                int(_cpid),
                _la1, _lo1, _la2, _lo2,
                width=road_width_full_world(rd) * 0.5,
                alt1=float(rd.get("alt1", 0.0) or 0.0) + _road_alt_offset(),
                alt2=float(rd.get("alt2", 0.0) or 0.0) + _road_alt_offset(),
                render_kind=(None if _rk is None else int(_rk)),
                construction_blob=_cblob)
    return bytes(b)


def decode_dacity_body(buf: bytes, off: int = 0, read_construction=None):
    flags = struct.unpack_from(">H", buf, off)[0]; off += 2
    aux = buf[off]; off += 1
    out = {"flags": flags, "aux": aux, "name": None,
           "identity_report": None, "identity_auid": 0, "buildings": []}
    if flags & CITY_IDENTITY:
        nm, off = _read_qstring(buf, off)
        out["name"] = nm
        out["identity_auid"] = struct.unpack_from(">I", buf, off)[0]; off += 4
        rep, off = _read_qstring(buf, off)
        out["identity_report"] = rep
    if flags & CITY_BUILDINGS_FULL:
        count = struct.unpack_from(">h", buf, off)[0]; off += 2
        for _ in range(count):
            dev_type = buf[off]; off += 1
            bld, off = decode_dpbuilding_body(buf, off, read_construction)
            bld["type"] = dev_type
            out["buildings"].append(bld)
    return out, off


def _read_qstring(buf: bytes, off: int):
    n = struct.unpack_from(">I", buf, off)[0]; off += 4
    if n == 0xFFFFFFFF:
        return None, off
    raw = buf[off:off + n]; off += n
    return raw.decode("utf-16-be"), off


def capitol_building_from_info(info, bauid: int = 0) -> dict:
    lat, lon = xyz_to_latlon(info["xyz"])
    out = {
        "type": DEV_BUILDING,
        "cpid": industry_to_cpid_safe(info.get("idi", 0x7B)),
        "lat": lat,
        "lon": lon,
        "facing": float(info.get("yaw", 0.0) or 0.0),
        "levels": int(info.get("levels", 1) or 1),
        "xyz": tuple(float(v) for v in info["xyz"]),
    }
    if bauid:
        out["bauid"] = int(bauid) & 0xFFFFFFFF
    return out

def developments_to_blob(buildings) -> bytes:
    import json
    return json.dumps(list(buildings), separators=(",", ":")).encode("utf-8")


def developments_from_blob(blob) -> list:
    import json
    if not blob:
        return []
    if isinstance(blob, (bytes, bytearray)):
        blob = bytes(blob).decode("utf-8")
    data = json.loads(blob)
    return data if isinstance(data, list) else []

