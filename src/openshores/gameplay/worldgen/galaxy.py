
from __future__ import annotations

import math
import os
import struct
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from openshores.database.repositories import galaxy as _rows
from openshores.protocol.rng import AuDice, AuNoise


@dataclass(frozen=True)
class GalaxyType:
    index: int
    name: str
    radius: int
    thickness: int
    rgb: Tuple[int, int, int]


GALAXIES: Tuple[GalaxyType, ...] = (
    GalaxyType(0, "AndromedaRising", 0x33D, 0x55, (6, 5, 8)),
    GalaxyType(1, "BlackHole", 0x15E, 0x28, (8, 5, 4)),
    GalaxyType(2, "Core", 0x2EB, 0x55, (3, 5, 8)),
    GalaxyType(3, "CrownOfOthon", 0x67A, 0x78, (8, 6, 4)),
    GalaxyType(4, "DyrathonsRetreat", 0x280, 0x5A, (5, 7, 8)),
    GalaxyType(5, "EdgeOfTheRift", 0x275, 0x28, (8, 4, 3)),
    GalaxyType(6, "FallasEmbrace", 0x342, 0x50, (5, 5, 7)),
    GalaxyType(7, "FallenLegionsOfMuturon", 0x1A7, 0x32, (5, 8, 7)),
    GalaxyType(8, "HeartOfVictorus", 0x56A, 0x96, (4, 5, 8)),
    GalaxyType(9, "HouseZanathar", 0x279, 0x32, (1, 2, 8)),
    GalaxyType(10, "IndigoSea", 0x244, 0x50, (8, 5, 7)),
    GalaxyType(11, "InkarBorderRegion", 0x3B4, 0x32, (2, 4, 8)),
    GalaxyType(12, "MuturonEncounter", 0x253, 0x32, (4, 8, 7)),
    GalaxyType(13, "RansuulsFlamingSword", 0x16D, 0x1C, (8, 6, 3)),
    GalaxyType(14, "SevenTen", 0x314, 0x32, (2, 8, 8)),
    GalaxyType(15, "ShoresOfHazeron", 0x5D0, 0x96, (4, 4, 10)),
    GalaxyType(16, "ThustrasEye", 0x4CA, 0x82, (10, 7, 2)),
    GalaxyType(17, "VeilOfTargoss", 0x37E, 0x64, (5, 6, 8)),
    GalaxyType(18, "VreenoxEclipse", 0x1C5, 0x1E, (8, 6, 7)),
    GalaxyType(19, "VulcansForge", 0x367, 0x3C, (13, 4, 2)),
)
GALAXY_BY_NAME = {g.name: g for g in GALAXIES}

GALAXY_SCALE_NUM = 2500.0
GALAXY_SCALE_DEN = 1488.0
HALF_PI = 1.5707963267948966

SYSTEMS_PER_DENSITY = 50.0

SECTOR_SIZE = 10.0

PLACE_OFFSET = 1.0 + 4.5
JITTER_DIV = 10.0
NOISE_SCALE = 4294967295.0
DEG2RAD = math.pi / 180.0


def galaxy_radius(g: GalaxyType) -> float:
    return (g.radius * GALAXY_SCALE_NUM) / GALAXY_SCALE_DEN


class DensityMap:

    __slots__ = ("width", "height", "_value")

    _CACHE: dict = {}

    def __new__(cls, path: str):
        key = os.path.abspath(path)
        hit = cls._CACHE.get(key)
        if hit is not None:
            return hit
        self = super().__new__(cls)
        self.width, self.height, self._value = _decode_png_value(path)
        cls._CACHE[key] = self
        return self

    def __init__(self, path: str):
        pass

    def value_at(self, px: int, py: int) -> float:
        px = 0 if px < 0 else (self.width - 1 if px >= self.width else px)
        py = 0 if py < 0 else (self.height - 1 if py >= self.height else py)
        return self._value[py * self.width + px]


def _decode_png_value(path: str):
    raw = open(path, "rb").read()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG")
    w = h = bitdepth = colortype = None
    idat = bytearray()
    off = 8
    while off < len(raw):
        ln = struct.unpack_from(">I", raw, off)[0]
        typ = raw[off + 4:off + 8]
        body = raw[off + 8:off + 8 + ln]
        if typ == b"IHDR":
            w, h, bitdepth, colortype = struct.unpack_from(">IIBB", body, 0)
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        off += 12 + ln
    if bitdepth != 8 or colortype not in (2, 6):
        raise ValueError(f"{path}: unsupported PNG ({bitdepth}bit type{colortype})")
    nch = 3 if colortype == 2 else 4
    data = zlib.decompress(bytes(idat))
    stride = w * nch
    out = [0.0] * (w * h)
    prev = bytearray(stride)
    pos = 0
    for y in range(h):
        f = data[pos]; pos += 1
        line = bytearray(data[pos:pos + stride]); pos += stride
        if f == 1:
            for i in range(nch, stride):
                line[i] = (line[i] + line[i - nch]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                b = prev[i]
                c = prev[i - nch] if i >= nch else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        base = y * w
        for x in range(w):
            i = x * nch
            m = line[i]
            if line[i + 1] > m:
                m = line[i + 1]
            if line[i + 2] > m:
                m = line[i + 2]
            out[base + x] = m / 255.0
        prev = line
    return w, h, out


def star_density(g: GalaxyType, dm: DensityMap, x: float, y: float, z: float) -> float:
    r = math.hypot(x, y)
    R = galaxy_radius(g)
    if r >= R:
        return 0.0
    sx = dm.width / (2.0 * R)
    sy = dm.height / (2.0 * R)
    if sx == 0.0 or sy == 0.0:
        return 0.0
    px = int(sx * x) + dm.width // 2
    py = dm.height // 2 - int(sy * y)
    v = dm.value_at(px, py)
    half = v * (1.0 - r / R) * ((g.thickness // 2) / sx)
    az = abs(z)
    if half <= 0.0 or az >= half:
        return 0.0
    return v * (math.acos(az / half) / HALF_PI)


def systems_in_sector(g: GalaxyType, dm: DensityMap,
                      cx: int, cy: int, cz: int) -> int:
    d = star_density(g, dm, cx * SECTOR_SIZE, cy * SECTOR_SIZE, cz * SECTOR_SIZE)
    if d <= 0.0:
        return 0
    n = int(d * SYSTEMS_PER_DENSITY)
    return n if n else 1


def galaxy_seed(galaxy_number: int, creation_time_unix: int) -> int:
    from . import procgen as hp
    return hp.Galaxy(galaxy_number=int(galaxy_number),
                     creation_time_unix=int(creation_time_unix)).gen_seed()


async def record_generation(con, *, galaxy_name: str, galaxy_number: int,
                            created: int, tool: str = "gen_galaxy") -> None:
    await _rows.record_generation(con, galaxy_name=galaxy_name,
                                  galaxy_number=galaxy_number,
                                  created=created, tool=tool)


async def read_generation(con) -> Optional[Dict[str, object]]:
    return await _rows.read_generation(con)


def sector_seed(gseed: int, cx: int, cy: int, cz: int) -> int:
    from . import procgen as hp
    return hp.Sector(galaxy=_FixedGalaxy(gseed),
                     location=(float(cx), float(cy), float(cz))).gen_seed()


class _FixedGalaxy:

    def __init__(self, seed):
        self._seed = int(seed)

    def gen_seed(self):
        return self._seed


def _trunc_i64(f: float) -> int:
    if f != f or f in (float("inf"), float("-inf")):
        return -(1 << 63)
    v = int(f)
    return v if -(1 << 63) <= v < (1 << 63) else -(1 << 63)


def _advance_seed(seed: int, seed_mod12: int) -> int:
    from . import procgen as hp
    while True:
        n = AuNoise.integer_noise1(seed_mod12, hp._i32(seed))
        seed = hp._u32(seed + (_trunc_i64(n * NOISE_SCALE) & 0xFFFFFFFF))
        if seed:
            return seed


@dataclass
class SystemSite:
    x: float
    y: float
    z: float
    seed: int
    rot_x_deg: int = 0
    rot_y_deg: int = 0
    rot_z_deg: int = 0


@dataclass
class SectorPlan:
    cx: int
    cy: int
    cz: int
    seed: int
    systems: List[SystemSite] = field(default_factory=list)

    @property
    def location(self):
        return (self.cx * SECTOR_SIZE, self.cy * SECTOR_SIZE, self.cz * SECTOR_SIZE)


def create_sector(g: GalaxyType, dm: DensityMap, gseed: int,
                  cx: int, cy: int, cz: int) -> Optional[SectorPlan]:
    n = systems_in_sector(g, dm, cx, cy, cz)
    if n <= 0:
        return None
    seed = sector_seed(gseed, cx, cy, cz)
    plan = SectorPlan(cx, cy, cz, seed)
    dice = AuDice(seed)
    seed_mod12 = seed % 12
    child = seed
    at_origin = (cx == 0 and cy == 0 and cz == 0)
    taken = set()

    for _ in range(n):
        if at_origin:
            pos = (0.0, 0.0, 0.0)
            taken.add(pos)
            child = _advance_seed(child, seed_mod12)
            plan.systems.append(SystemSite(0.0, 0.0, 0.0, child))
            at_origin = False
            continue
        while True:
            lx = dice.roll(1, 10) - PLACE_OFFSET
            ly = dice.roll(1, 10) - PLACE_OFFSET
            lz = dice.roll(1, 10) - PLACE_OFFSET
            if (lx, ly, lz) not in taken:
                break
        taken.add((lx, ly, lz))
        jx = dice.roll(1, 9, -5) / JITTER_DIV
        jy = dice.roll(1, 9, -5) / JITTER_DIV
        jz = dice.roll(1, 9, -5) / JITTER_DIV
        rx = dice.roll(1, 0x168, -1)
        ry = dice.roll(1, 0x168, -1)
        rz = dice.roll(1, 0x168, -1)
        child = _advance_seed(child, seed_mod12)
        plan.systems.append(SystemSite(lx + jx, ly + jy, lz + jz, child,
                                       rx, ry, rz))
    return plan


def sector_span(g: GalaxyType) -> int:
    return int(math.ceil(galaxy_radius(g) / SECTOR_SIZE))


def generate(galaxy_name: str, galaxy_number: int, creation_time_unix: int, *,
             maps_dir: str = "galaxy_maps", bounds=None, progress=None):
    g = GALAXY_BY_NAME[galaxy_name]
    dm = DensityMap(os.path.join(maps_dir, g.name + ".png"))
    gseed = galaxy_seed(galaxy_number, creation_time_unix)
    if bounds is None:
        s = sector_span(g)
        bounds = ((-s, s), (-s, s), (-s, s))
    (x0, x1), (y0, y1), (z0, z1) = bounds
    out: List[SectorPlan] = []
    for cx in range(x0, x1 + 1):
        if progress:
            progress(cx, x1)
        for cy in range(y0, y1 + 1):
            for cz in range(z0, z1 + 1):
                p = create_sector(g, dm, gseed, cx, cy, cz)
                if p is not None:
                    out.append(p)
    return g, gseed, out


PRIMARY_TYPE_TABLE = (1, 1, 2, 6, 6, 6, 6, 6, 5, 4, 3, 3, 3)

PRIMARY_SIZE_TABLE = (0, 1, 2, 3, 4, 5, 5, 5, 5, 5, 5, 6, 7)

STAR_TYPE_NO_PLANETS = 7


ZONE_TABLE = (
    1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,0,0,0,0,0,
    0,0,0,0,0,0,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,1,1,1,
    1,1,1,1,1,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,0,0,0,
    0,0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,1,1,1,1,1,1,
    2,2,1,1,1,1,0,0,0,1,1,1,2,2,2,2,2,2,2,2,2,2,0,0,
    2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,
    2,2,2,2,2,2,2,2,2,2,2,2,2,3,2,2,2,2,2,2,2,2,2,2,
    3,3,3,3,4,3,3,3,3,3,3,3,2,3,3,4,4,4,4,5,4,4,4,4,
    4,4,4,3,4,4,5,5,5,5,6,5,5,5,5,5,5,5,4,5,5,6,6,6,
    6,6,6,6,6,6,6,6,6,5,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
    1,1,1,1,1,1,1,1,1,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,
    0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,1,1,1,
    1,1,1,1,1,1,1,0,0,0,0,0,1,1,1,1,1,1,1,2,2,1,1,0,
    0,0,0,1,1,1,1,2,2,2,2,2,2,2,1,0,0,0,1,1,1,2,2,2,
    2,2,2,2,2,2,2,0,0,1,1,1,2,2,2,2,2,2,2,2,2,2,2,0,
    1,1,2,2,2,2,2,2,2,2,2,2,2,2,2,1,2,2,2,2,3,3,3,3,
    3,3,2,2,2,2,2,2,2,3,3,4,4,4,4,4,4,3,3,2,2,2,2,2,
    4,4,5,5,5,5,5,5,4,4,3,3,2,2,3,5,5,6,6,6,6,6,6,5,
    5,4,4,2,2,4,6,6,6,6,6,6,6,6,6,6,5,5,3,3,5,6,6,6,
    6,6,6,6,6,6,6,6,6,4,4,6,6,6,6,6,6,6,6,6,6,6,6,6,
    1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,1,1,1,1,1,1,1,1,1,
    1,1,0,0,0,0,1,1,1,1,1,2,2,2,2,2,2,1,0,0,0,1,1,1,
    1,2,2,2,2,2,2,2,2,0,0,0,1,1,1,1,2,2,2,2,2,2,2,2,
    2,0,0,1,1,1,2,2,2,2,2,2,2,2,2,2,0,0,1,1,1,2,2,2,
    2,2,2,2,2,2,2,2,2,1,2,2,2,2,3,3,3,3,3,2,2,2,2,2,
    2,2,2,2,3,4,4,4,4,4,3,3,2,2,2,2,2,2,2,4,5,5,5,5,
    5,4,4,3,2,2,2,2,2,3,5,6,6,6,6,6,5,5,4,3,3,2,2,3,
    4,6,6,6,6,6,6,6,6,5,4,4,2,2,4,5,6,6,6,6,6,6,6,6,
    6,5,5,2,3,5,6,6,6,6,6,6,6,6,6,6,6,6,3,4,6,6,6,6,
    6,6,6,6,6,6,6,6,6,4,5,6,6,6,6,6,6,6,6,6,6,6,6,6,
    1,1,1,1,2,2,2,2,2,2,2,2,1,0,0,1,1,1,1,2,2,2,2,2,
    2,2,2,1,0,0,1,1,1,1,2,2,2,2,2,2,2,2,2,0,0,1,1,1,
    1,2,2,2,2,2,2,2,2,2,0,0,1,1,1,1,2,2,2,2,2,2,2,2,
    2,2,0,1,1,1,2,2,2,3,3,3,2,2,2,2,2,2,1,1,1,2,2,3,
    4,4,4,3,3,2,2,2,2,1,1,2,2,3,4,5,5,5,4,4,3,3,2,2,
    2,2,2,2,4,5,6,6,6,5,5,4,4,3,3,2,2,2,3,5,6,6,6,6,
    6,6,5,5,4,4,2,2,2,4,6,6,6,6,6,6,6,6,6,5,5,2,2,3,
    5,6,6,6,6,6,6,6,6,6,6,6,2,2,4,6,6,6,6,6,6,6,6,6,
    6,6,6,2,3,5,6,6,6,6,6,6,6,6,6,6,6,6,2,4,6,6,6,6,
    6,6,6,6,6,6,6,6,6,3,5,6,6,6,6,6,6,6,6,6,6,6,6,6,
    1,1,1,1,1,2,2,2,2,2,2,0,0,0,0,1,1,1,1,2,2,2,2,2,
    2,2,0,0,0,0,1,1,1,1,2,2,2,2,2,2,2,0,0,0,0,1,1,1,
    2,2,2,2,2,2,2,3,0,0,0,0,1,1,1,2,2,2,2,3,3,3,4,0,
    0,0,0,1,1,1,2,2,3,3,4,4,4,5,0,0,0,0,1,1,1,2,3,4,
    4,5,5,5,6,0,0,0,0,1,2,2,2,4,5,5,6,6,6,6,0,0,0,0,
    2,2,2,3,5,6,6,6,6,6,6,0,0,0,0,2,2,2,4,6,6,6,6,6,
    6,6,0,0,0,0,2,2,2,5,6,6,6,6,6,6,6,0,0,0,0,2,2,3,
    6,6,6,6,6,6,6,6,0,0,0,0,2,2,4,6,6,6,6,6,6,6,6,0,
    0,0,0,2,2,5,6,6,6,6,6,6,6,6,0,0,0,0,2,3,6,6,6,6,
    6,6,6,6,6,0,0,0,0,2,4,6,6,6,6,6,6,6,6,6,0,0,0,0,
    1,1,1,1,2,2,2,2,2,2,2,4,4,5,6,1,1,1,1,2,2,2,2,2,
    3,3,5,5,6,6,1,1,1,1,2,2,2,2,3,4,4,6,6,6,6,1,1,1,
    2,2,2,2,3,4,5,5,6,6,6,6,1,1,1,2,2,2,3,4,5,6,6,6,
    6,6,6,1,1,1,2,2,3,4,5,6,6,6,6,6,6,6,1,1,2,2,3,4,
    5,6,6,6,6,6,6,6,6,1,2,2,2,4,5,6,6,6,6,6,6,6,6,6,
    2,2,2,3,5,6,6,6,6,6,6,6,6,6,6,2,2,2,4,6,6,6,6,6,
    6,6,6,6,6,6,2,2,2,5,6,6,6,6,6,6,6,6,6,6,6,2,2,3,
    6,6,6,6,6,6,6,6,6,6,6,6,2,2,4,6,6,6,6,6,6,6,6,6,
    6,6,6,2,2,5,6,6,6,6,6,6,6,6,6,6,6,6,2,3,6,6,6,6,
    6,6,6,6,6,6,6,6,6,2,4,6,6,6,6,6,6,6,6,6,6,6,6,6,
    0,0,0,0,0,0,0,2,2,3,3,5,6,6,6,0,0,0,0,0,0,0,2,3,
    4,4,6,6,6,6,0,0,0,0,0,0,0,3,4,5,5,6,6,6,6,0,0,0,
    0,0,0,0,4,5,6,6,6,6,6,6,0,0,0,0,0,0,0,5,6,6,6,6,
    6,6,6,0,0,0,0,0,0,0,6,6,6,6,6,6,6,6,0,0,0,0,0,0,
    0,6,6,6,6,6,6,6,6,0,0,0,0,0,0,0,6,6,6,6,6,6,6,6,
    0,0,0,0,0,0,0,6,6,6,6,6,6,6,6,0,0,0,0,0,0,0,6,6,
    6,6,6,6,6,6,0,0,0,0,0,0,0,6,6,6,6,6,6,6,6,0,0,0,
    0,0,0,0,6,6,6,6,6,6,6,6,0,0,0,0,0,0,0,6,6,6,6,6,
    6,6,6,0,0,0,0,0,0,0,6,6,6,6,6,6,6,6,0,0,0,0,0,0,
    0,6,6,6,6,6,6,6,6,0,0,0,0,0,0,0,6,6,6,6,6,6,6,6,
    3,3,4,4,5,5,6,6,6,6,6,6,6,6,6,4,4,5,5,6,6,6,6,6,
    6,6,6,6,6,6,5,5,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
    6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
    6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
    6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
    6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
    6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
    6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
    6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
    6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
)
assert len(ZONE_TABLE) == 8 * 16 * 15

ZONE_MIN_ORBIT = 0
ZONE_HABITABLE = 4
ZONE_PLANET_MIN = 2


def type_index(star_type: int, subclass: int) -> int:
    idx = int(star_type) * 2 + (1 if int(subclass) >= 5 else 0)
    if int(star_type) == 6 and int(subclass) == 9:
        idx = 14
    return idx


def init_zones(size: int, star_type: int, subclass: int):
    t = type_index(star_type, subclass)
    base = (int(size) << 4) * 15
    zones = [ZONE_TABLE[base + o * 15 + t] for o in range(16)]
    hab = -1
    mn = -1
    for o, zv in enumerate(zones):
        if zv == ZONE_HABITABLE:
            hab = o
        elif zv == ZONE_MIN_ORBIT:
            mn = o
    if hab < 0 and zones[15] < 4:
        hab = 16
    return zones, hab, mn


AU_PER_ORBIT = 0.25


def orbit_radius_au(orbit_index: int) -> float:
    return (int(orbit_index) + 1) * AU_PER_ORBIT


RINGWORLD_CHANCE = 3

