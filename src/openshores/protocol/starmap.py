
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Optional


def pack_i8(v: int) -> bytes:    return struct.pack(">b", v)
def pack_u8(v: int) -> bytes:    return struct.pack(">B", v)
def pack_i16(v: int) -> bytes:   return struct.pack(">h", v)
def pack_i32(v: int) -> bytes:   return struct.pack(">i", v)
def pack_u32(v: int) -> bytes:   return struct.pack(">I", v)
def pack_f32(v: float) -> bytes: return struct.pack(">f", v)


def pack_qstring(s: Optional[str]) -> bytes:
    if s is None:
        return pack_i32(-1)
    utf = s.encode("utf-16-be")
    return pack_i32(len(utf)) + utf


def pack_auid(auid: int) -> bytes:
    return pack_u32(auid & 0xFFFFFFFF)


@dataclass
class StarMapCity:
    auid:       int    = 0
    flags:      int    = 0
    int_val:    int    = 0
    name:       str    = ""


@dataclass
class StarMapWormhole:
    flags:      int    = 0
    x:          float  = 0.0
    y:          float  = 0.0
    z:          float  = 0.0


@dataclass
class StarMapSystem:
    auid:          int                    = 0
    flags:         int                    = 0
    x:             float                  = 0.0
    y:             float                  = 0.0
    z:             float                  = 0.0
    name:          str                    = ""
    owner_flag:    int                    = 0
    owner_int:     int                    = 0
    cities:        List[StarMapCity]      = field(default_factory=list)
    wormholes:     List[StarMapWormhole]  = field(default_factory=list)


@dataclass
class StarMapSector:
    auid:      int                    = 0
    flags:     int                    = 0
    x:         float                  = 0.0
    y:         float                  = 0.0
    z:         float                  = 0.0
    name:      str                    = ""
    systems:   List[StarMapSystem]    = field(default_factory=list)


def encode_city_body(c: StarMapCity) -> bytes:
    return pack_i8(c.flags) + pack_i32(c.int_val) + pack_qstring(c.name)


def encode_wormhole(w: StarMapWormhole) -> bytes:
    return (pack_i8(w.flags)
            + pack_f32(w.x) + pack_f32(w.y) + pack_f32(w.z))


def encode_system_body(sys: StarMapSystem) -> bytes:
    buf = pack_i16(len(sys.cities))
    for c in sys.cities:
        buf += pack_auid(c.auid) + encode_city_body(c)
    buf += pack_i8(sys.flags)
    buf += pack_f32(sys.x) + pack_f32(sys.y) + pack_f32(sys.z)
    buf += pack_qstring(sys.name)
    if sys.flags & 5:
        buf += pack_i8(sys.owner_flag) + pack_i32(sys.owner_int)
    buf += pack_i8(len(sys.wormholes))
    for w in sys.wormholes:
        buf += encode_wormhole(w)
    return buf


def encode_sector_body(sec: StarMapSector) -> bytes:
    buf = pack_i8(sec.flags)
    buf += pack_f32(sec.x) + pack_f32(sec.y) + pack_f32(sec.z)
    buf += pack_qstring(sec.name)
    buf += pack_i16(len(sec.systems))
    for sys in sec.systems:
        buf += pack_auid(sys.auid) + encode_system_body(sys)
    return buf


def encode_star_map_data(sectors: List[StarMapSector]) -> bytes:
    buf = pack_i16(len(sectors))
    for sec in sectors:
        buf += pack_auid(sec.auid) + encode_sector_body(sec)
    return buf


def build_from_save(save_bundle) -> List[StarMapSector]:
    sectors = []
    sector_names = save_bundle.name_pools.get("sector", [])
    star_names   = save_bundle.name_pools.get("star", [])
    city_names   = save_bundle.name_pools.get("generic", [])

    if not sector_names:
        sector_names = [getattr(save_bundle, "sector_name", "Home Sector")]
    if not star_names:
        star_names = [getattr(save_bundle, "star_name", "Home")]

    def _pos(name: str, salt: int = 0):
        import hashlib
        h = hashlib.sha256((name + str(salt)).encode("utf-8")).digest()
        x = ((int.from_bytes(h[0:4], "big")) / 0xFFFFFFFF - 0.5) * 1000.0
        y = ((int.from_bytes(h[4:8], "big")) / 0xFFFFFFFF - 0.5) * 1000.0
        z = ((int.from_bytes(h[8:12], "big")) / 0xFFFFFFFF - 0.5) * 1000.0
        return (x, y, z)

    next_auid = 0x010000

    stars_per_sector = max(1, len(star_names) // max(1, len(sector_names)))

    for si, sname in enumerate(sector_names):
        sx, sy, sz = _pos(sname, 0)
        sec = StarMapSector(
            auid=next_auid, flags=0,
            x=sx, y=sy, z=sz, name=sname,
        )
        next_auid += 1

        beg = si * stars_per_sector
        end = beg + stars_per_sector
        for star in star_names[beg:end]:
            tx, ty, tz = _pos(star, 1)
            sys_obj = StarMapSystem(
                auid=next_auid, flags=0,
                x=tx, y=ty, z=tz, name=star,
            )
            next_auid += 1
            sec.systems.append(sys_obj)
        sectors.append(sec)

    leftover = star_names[len(sectors) * stars_per_sector:]
    if leftover and sectors:
        for star in leftover:
            tx, ty, tz = _pos(star, 1)
            sys_obj = StarMapSystem(
                auid=next_auid, flags=0,
                x=tx, y=ty, z=tz, name=star,
            )
            next_auid += 1
            sectors[-1].systems.append(sys_obj)

    return sectors
