
from __future__ import annotations

import struct
from pathlib import Path

from openshores.core.config import Config

_CPROC_ANCHOR = 397280
_CPROC_FIELD_BYTES = 5


DEFAULT_GD_PATHS = ("GD", "gd")


def find_gd(path=None):
    # Config.load, not Deployment.from_env: from_env reads the environment
    # only, so gd_path set in openshores.toml was never consulted here.
    for cand in (([path] if path else [])
                 + [Config.load().deployment.gd_path]
                 + list(DEFAULT_GD_PATHS)):
        if cand and Path(cand).exists():
            return str(cand)
    return None


def _read_qstring(data, off, maxlen=400):
    if off + 4 > len(data):
        return None, off
    n = struct.unpack_from(">I", data, off)[0]
    if n == 0xFFFFFFFF:
        return "", off + 4
    if n > maxlen or n % 2:
        return None, off
    try:
        return data[off + 4:off + 4 + n].decode("utf-16-be"), off + 4 + n
    except Exception:
        return None, off


class ConstructionProcess:
    __slots__ = ("cpid", "name", "industry_id", "terrain", "radius",
                 "unknown1", "unknown2")

    def __init__(self, cpid, name, fields):
        self.cpid = cpid
        self.name = name
        self.industry_id = fields[0]
        self.unknown1 = fields[1]
        self.unknown2 = fields[2]
        self.terrain = fields[3]
        self.radius = fields[4]

    def __repr__(self):
        return ("ConstructionProcess(cpid=%d, name=%r, industry=%d, "
                "terrain=%d, radius=%d)" % (self.cpid, self.name,
                                            self.industry_id, self.terrain,
                                            self.radius))


_CPROC_CACHE = None


def load_construction_processes(path=None):
    global _CPROC_CACHE
    if path is None and _CPROC_CACHE is not None:
        return _CPROC_CACHE
    gd = find_gd(path)
    if gd is None:
        return {}
    try:
        data = Path(gd).read_bytes()
    except Exception:
        return {}
    out = {}
    off, expect = _CPROC_ANCHOR, 1
    while off < len(data) - 8:
        if data[off] != expect:
            break
        name, after = _read_qstring(data, off + 1)
        if not name or not all(c.isprintable() for c in name):
            break
        if after + _CPROC_FIELD_BYTES > len(data):
            break
        out[expect] = ConstructionProcess(
            expect, name, data[after:after + _CPROC_FIELD_BYTES])
        off = after + _CPROC_FIELD_BYTES
        expect += 1
    if not _validate(out):
        return {}
    if path is None:
        _CPROC_CACHE = out
    return out


_EXPECTED = {
    1: ("Town Square", 1),
    2: ("Dirt", 2),
    3: ("Asphalt", 2),
    4: ("Concrete", 2),
    5: ("Graded Area", 2),
}
_EXPECTED_RADIUS = {2: 5, 3: 8, 4: 8, 5: 5}


def _validate(table):
    if len(table) < 50:
        return False
    for cpid, (name, industry) in _EXPECTED.items():
        row = table.get(cpid)
        if row is None or row.name != name or row.industry_id != industry:
            return False
    for cpid, radius in _EXPECTED_RADIUS.items():
        if table[cpid].radius != radius:
            return False
    return True


def road_cpid_radius(table=None):
    t = table if table is not None else load_construction_processes()
    return {c: t[c].radius for c in (2, 3, 4, 5) if c in t}


def construction_process_industry(cpid, table=None):
    t = table if table is not None else load_construction_processes()
    row = t.get(int(cpid) & 0xFF)
    return row.industry_id if row else 0


def industry_to_cpid(industry, table=None):
    t = table if table is not None else load_construction_processes()
    ind = int(industry) & 0xFF
    for cpid in sorted(t):
        if t[cpid].industry_id == ind:
            return cpid
    return 0


_CCOMP_OFFSET = 400036
_CCOMP_STRIDE = 8


class ConstructionComponent:
    __slots__ = ("seq", "cpid", "commodity", "quantity", "effect", "pad")

    def __init__(self, seq, cpid, commodity, quantity, effect, pad=0):
        self.seq = seq
        self.cpid = cpid
        self.commodity = commodity
        self.quantity = quantity
        self.effect = effect
        self.pad = pad

    def as_server_row(self):
        return [self.commodity, 0, self.effect, self.quantity, 0]

    def __repr__(self):
        return ("ConstructionComponent(cpid=%d, commodity=%d, qty=%d, effect=%d)"
                % (self.cpid, self.commodity, self.quantity, self.effect))


def load_construction_components(path=None):
    gd = find_gd(path)
    if gd is None:
        return {}
    try:
        data = Path(gd).read_bytes()
    except Exception:
        return {}
    if _CCOMP_OFFSET + 4 > len(data):
        return {}
    count = struct.unpack_from(">I", data, _CCOMP_OFFSET)[0]
    off = _CCOMP_OFFSET + 4
    if count <= 0 or off + count * _CCOMP_STRIDE > len(data):
        return {}
    out = {}
    for i in range(count):
        seq, cpid, com, qty, eff, pad = struct.unpack_from(">HBHBBB", data, off)
        if seq != i + 1:
            return {}
        out.setdefault(cpid, []).append(
            ConstructionComponent(seq, cpid, com, qty, eff, pad=pad))
        off += _CCOMP_STRIDE
    return out if _validate_construction_components(out) else {}


_EXPECTED_COMPONENTS = {
    5: [(2, 0, 2, 0), (3, 0, 2, 1), (82, 0, 2, 0), (114, 0, 2, 0)],
    2: [(2, 0, 2, 0), (3, 0, 2, 1), (82, 0, 2, 0), (114, 0, 2, 0)],
    3: [(2, 0, 2, 0), (3, 0, 2, 1), (23, 0, 5, 1), (82, 0, 2, 0), (114, 0, 2, 0)],
    4: [(2, 0, 2, 0), (3, 0, 2, 1), (76, 0, 5, 1), (82, 0, 2, 0), (114, 0, 2, 0)],
}


def _validate_construction_components(table):
    for cpid, expected in _EXPECTED_COMPONENTS.items():
        rows = table.get(cpid)
        if rows is None:
            return False
        got = sorted((c.commodity, 0, c.effect, c.quantity) for c in rows)
        if got != sorted(expected):
            return False
    return True


_INDUSTRY_COUNT_OFFSET = 235437

_INDUSTRY_ORDER = (
    ('u8', 0x12), ('u8', 0x00), ('str', 0x08), ('u8', 0x10), ('u8', 0x13),
    ('u8', 0x11), ('u8', 0x21), ('u8', 0x26), ('u8', 0x22), ('u8', 0x23),
    ('u8', 0x24), ('u8', 0x25), ('u8', 0x27), ('u8', 0x28), ('u8', 0x29),
    ('u8', 0x2a), ('u8', 0x2b), ('u8', 0x2c), ('u8', 0x2d), ('str', 0x40),
    ('u8', 0x2e), ('u8', 0x2f), ('u8', 0x30), ('u8', 0x31), ('u8', 0x35),
    ('u8', 0x32), ('u8', 0x33), ('u8', 0x34), ('u8', 0x36), ('u8', 0x37),
    ('u8', 0x38), ('u8', 0x39), ('u8', 0x3a), ('u8', 0x3b), ('str', 0x18),
    ('u8', 0x20),
)

TROOP_INDUSTRIES = frozenset({1, 10, 11, 12, 0x80})
POWER_PLANT_INDUSTRIES = frozenset(set(range(0x3C, 0x45)) | {0x5A})
HOMES_INDUSTRIES = (0x14, 0x15, 0x16, 0x1E, 0x20)


def _s8(b):
    return b - 256 if b > 127 else b


class Industry:
    __slots__ = ("industry_id", "name", "population", "jobs", "storage",
                 "capacitor", "generator", "category", "build_rule", "raw")

    def __init__(self, industry_id, f):
        self.industry_id = industry_id
        self.name = f[0x08]
        self.population = f[0x10]
        self.jobs = _s8(f[0x13])
        self.storage = f[0x11] * 10
        self.capacitor = f[0x12] * 10
        self.generator = f[0x27]
        self.category = f[0x00]
        self.build_rule = f[0x20]
        self.raw = f

    @property
    def troops(self):
        return abs(self.jobs) if self.industry_id in TROOP_INDUSTRIES else 0

    @property
    def is_power_plant(self):
        return self.industry_id in POWER_PLANT_INDUSTRIES

    def __repr__(self):
        return ("Industry(0x%02x, %r, pop=%d, jobs=%d, storage=%d, cap=%d)"
                % (self.industry_id, self.name, self.population, self.jobs,
                   self.storage, self.capacitor))


def load_industries(path=None):
    gd = find_gd(path)
    if gd is None:
        return {}
    try:
        data = Path(gd).read_bytes()
    except Exception:
        return {}
    off = _INDUSTRY_COUNT_OFFSET
    if off + 2 > len(data):
        return {}
    count = struct.unpack_from(">h", data, off)[0]
    off += 2
    if not (0 < count < 1000):
        return {}
    out = {}
    for idx in range(count):
        f = {}
        for kind, key in _INDUSTRY_ORDER:
            if kind == 'u8':
                if off >= len(data):
                    return {}
                f[key] = data[off]
                off += 1
            else:
                s, off2 = _read_qstring(data, off)
                if s is None:
                    return {}
                f[key] = s
                off = off2
        out[idx] = Industry(idx, f)
    return out if _validate_industries(out) else {}


def _validate_industries(table):
    expect = {0x01: "Town Square", 0x02: "Road", 0x14: "House",
              0x15: "Condominium", 0x16: "Apartment", 0x1E: "Farm",
              0x20: "Orchard", 0x7B: "Capitol"}
    for k, name in expect.items():
        if k not in table or table[k].name != name:
            return False
    if any(table[k].population <= 0 for k in HOMES_INDUSTRIES):
        return False
    negative = {k for k, v in table.items() if v.jobs < 0}
    if not TROOP_INDUSTRIES.issubset(negative):
        return False
    if any(table[k].generator == 0 for k in POWER_PLANT_INDUSTRIES if k in table):
        return False
    return True


def homes_per_level(industry, table=None):
    if int(industry) not in HOMES_INDUSTRIES:
        return 0
    t = table if table is not None else load_industries()
    row = t.get(int(industry))
    return row.population if row else 0


_MANUPROC_OFFSET = 255819

COMMODITY_AIR = 5
COMMODITY_POWER = 3


class ManufacturingProcess:

    __slots__ = ("process_id", "name", "commodity", "industry_id",
                 "output_qty", "work_units", "flags", "tail")

    def __init__(self, process_id, name, commodity, industry_id,
                 output_qty, work_units, flags=0, tail=0):
        self.process_id = process_id
        self.name = name
        self.commodity = commodity
        self.industry_id = industry_id
        self.output_qty = output_qty
        self.work_units = work_units
        self.flags = flags
        self.tail = tail

    @property
    def f14(self):
        return self.output_qty

    @property
    def f16(self):
        return self.work_units

    def __repr__(self):
        return ("ManufacturingProcess(%d, %r, industry=%d -> commodity=%d)"
                % (self.process_id, self.name, self.industry_id, self.commodity))


def load_manufacturing_processes(path=None):
    gd = find_gd(path)
    if gd is None:
        return []
    try:
        data = Path(gd).read_bytes()
    except Exception:
        return []
    off = _MANUPROC_OFFSET
    if off + 2 > len(data):
        return []
    count = struct.unpack_from(">h", data, off)[0]
    off += 2
    if not (0 < count < 20000):
        return []
    out = []
    for _ in range(count):
        if off + 1 > len(data):
            return []
        flags = data[off]; off += 1
        pid = struct.unpack_from(">h", data, off)[0]; off += 2
        name, off = _read_qstring(data, off)
        if name is None:
            return []
        if off + 8 > len(data):
            return []
        com = struct.unpack_from(">h", data, off)[0]; off += 2
        ind = data[off]; off += 1
        output_qty = struct.unpack_from(">h", data, off)[0]; off += 2
        work_units = struct.unpack_from(">h", data, off)[0]; off += 2
        tail = data[off]; off += 1
        out.append(ManufacturingProcess(pid, name, com, ind,
                                        output_qty, work_units,
                                        flags=flags, tail=tail))
    return out if _validate_manufacturing(out) else []


def _validate_manufacturing(procs):
    if len(procs) < 100:
        return False
    power = {p.industry_id for p in procs if p.commodity == COMMODITY_POWER}
    if power != set(range(0x3C, 0x45)):
        return False
    if not any(p.commodity == COMMODITY_AIR for p in procs):
        return False
    return True


FOOD_PRODUCER_INDUSTRIES = frozenset({0x1E, 0x20, 0x22, 0x23, 0x28, 0x2B, 0x2D, 0x2E})
AIR_PRODUCER_INDUSTRIES = frozenset({0x53})
POWER_PRODUCER_INDUSTRIES = frozenset(range(0x3C, 0x45))


def producer_kind(industry_id):
    i = int(industry_id)
    if i in FOOD_PRODUCER_INDUSTRIES:
        return "food"
    if i in POWER_PRODUCER_INDUSTRIES:
        return "power"
    if i in AIR_PRODUCER_INDUSTRIES:
        return "air"
    return "other"


def verify_producer_sets(procs=None):
    p = procs if procs is not None else load_manufacturing_processes()
    if not p:
        return True, "manufacturing table unavailable; skipped"
    air = industries_producing(COMMODITY_AIR, p)
    power = industries_producing(COMMODITY_POWER, p)
    detail = []
    ok = True
    if air != set(AIR_PRODUCER_INDUSTRIES):
        ok = False; detail.append("air %s != %s" % (sorted(air), sorted(AIR_PRODUCER_INDUSTRIES)))
    if power != set(POWER_PRODUCER_INDUSTRIES):
        ok = False; detail.append("power %s != %s" % (sorted(power), sorted(POWER_PRODUCER_INDUSTRIES)))
    return ok, "; ".join(detail) or "sets agree"


def industries_producing(commodity, procs=None):
    p = procs if procs is not None else load_manufacturing_processes()
    return {x.industry_id for x in p if x.commodity == int(commodity)}


_MFGCOMP_COUNT_OFFSET = 334040
_MFGCOMP_OFFSET = 334044
_MFGCOMP_STRIDE = 9
_MFGCOMP_END = 397278


class ManufacturingComponent:
    __slots__ = ("index", "process_id", "commodity", "quantity", "effect")

    def __init__(self, index, process_id, commodity, quantity, effect):
        self.index = index
        self.process_id = process_id
        self.commodity = commodity
        self.quantity = quantity
        self.effect = effect

    @property
    def is_consumed(self):
        return self.effect == 5 and self.quantity > 0

    @property
    def is_required(self):
        return self.effect == 5 and self.quantity == 0

    def __repr__(self):
        return ("ManufacturingComponent(mpid=%d, cid=%d, qty=%d, effect=%d)"
                % (self.process_id, self.commodity, self.quantity, self.effect))


_MFGCOMP_CACHE = None


def load_manufacturing_components(path=None):
    global _MFGCOMP_CACHE
    if path is None and _MFGCOMP_CACHE is not None:
        return _MFGCOMP_CACHE
    gd = find_gd(path)
    if gd is None:
        return []
    try:
        data = Path(gd).read_bytes()
    except Exception:
        return []
    if _MFGCOMP_COUNT_OFFSET + 4 > len(data):
        return []
    n = struct.unpack_from(">i", data, _MFGCOMP_COUNT_OFFSET)[0]
    if n <= 0 or _MFGCOMP_OFFSET + n * _MFGCOMP_STRIDE > len(data):
        return []
    if _MFGCOMP_OFFSET + n * _MFGCOMP_STRIDE != _MFGCOMP_END:
        return []
    out = []
    for i in range(n):
        b = _MFGCOMP_OFFSET + i * _MFGCOMP_STRIDE
        idx, pid, cid, qty = struct.unpack_from(">hhhh", data, b)
        out.append(ManufacturingComponent(idx, pid, cid, qty, data[b + 8]))
    if not _validate_manufacturing_components(out):
        return []
    if path is None:
        _MFGCOMP_CACHE = out
    return out


def _validate_manufacturing_components(comps):
    if not comps:
        return False
    procs = load_manufacturing_processes()
    if procs:
        valid = {p.process_id for p in procs}
        if sum(1 for c in comps if c.process_id in valid) < len(comps) * 0.99:
            return False
    if any(not (1 <= c.effect <= 6) for c in comps):
        return False
    return True


_COMPS_BY_PROCESS = None


def components_for_process(process_id, comps=None):
    global _COMPS_BY_PROCESS
    if comps is not None:
        return [c for c in comps if c.process_id == int(process_id)]
    if _COMPS_BY_PROCESS is None:
        idx = {}
        for c in load_manufacturing_components():
            idx.setdefault(c.process_id, []).append(c)
        _COMPS_BY_PROCESS = idx
    return _COMPS_BY_PROCESS.get(int(process_id), [])


def process_by_id(process_id, procs=None):
    p = procs if procs is not None else load_manufacturing_processes()
    for x in p:
        if x.process_id == int(process_id):
            return x
    return None


def processes_for_industry(industry_id, procs=None):
    p = procs if procs is not None else load_manufacturing_processes()
    return [x for x in p
            if x.industry_id == int(industry_id)
            and ", Method for" not in x.name]


_MFG_INDUSTRY_CACHE = None


def manufacturing_industries(procs=None):
    global _MFG_INDUSTRY_CACHE
    if procs is None and _MFG_INDUSTRY_CACHE is not None:
        return _MFG_INDUSTRY_CACHE
    p = procs if procs is not None else load_manufacturing_processes()
    if not p:
        return set()
    out = {x.industry_id for x in p
           if x.industry_id and ", Method for" not in x.name}
    if procs is None:
        _MFG_INDUSTRY_CACHE = out
    return out


def industry_output_commodities(procs=None):
    p = procs if procs is not None else load_manufacturing_processes()
    out = {}
    for x in p:
        out.setdefault(x.industry_id, set()).add(x.commodity)
    return out


def construction_components_as_rows(path=None):
    return {cpid: [c.as_server_row() for c in rows]
            for cpid, rows in load_construction_components(path).items()}


_FOOD_CACHE = None
_GD_FOOD_FINGERPRINT = __import__("re").compile(
    rb"\xff\xff\xff\xff.\x00\x00\x00\x00", __import__("re").DOTALL)


def load_food_commodities(path=None):
    global _FOOD_CACHE
    if path is None and _FOOD_CACHE is not None:
        return _FOOD_CACHE
    gd = path or find_gd()
    if not gd:
        return {}
    try:
        with open(gd, "rb") as fh:
            data = fh.read()
    except OSError:
        return {}
    out = {}
    for m in _GD_FOOD_FINGERPRINT.finditer(data):
        fp = m.start()
        if fp < 59:
            continue
        cid = int.from_bytes(data[fp - 59:fp - 57], "big", signed=True)
        if not 0 < cid < 4096:
            continue
        food_flag = int.from_bytes(data[fp - 4:fp], "big")
        nutrition = data[fp + 4]
        if ((food_flag >> 1) & 1) and 0 < nutrition < 200:
            out[cid] = nutrition
    if path is None:
        _FOOD_CACHE = out
    return out


_DETAILTYPE_COUNT_OFFSET = 2
_DETAILTYPE_OFFSET = 4
_DETAILTYPE_END = 52431
_DETAILTYPE_TAIL = 8
_DETAILTYPE_MAXSTR = 4000


class DetailType:
    __slots__ = ("type_id", "sc_header", "sc_subtitle", "bd_header",
                 "bd_subtitle", "tail")

    def __init__(self, type_id, strings, tail):
        self.type_id = type_id
        (self.sc_header, self.sc_subtitle,
         self.bd_header, self.bd_subtitle) = strings
        self.tail = tail

    def __repr__(self):
        return ("DetailType(%d, %r / %r)"
                % (self.type_id, self.sc_header, self.bd_header))


_DETAILTYPE_CACHE = None

_DETAILTYPE_ANCHORS = {1: "Navigator Station", 5: "Door", 8: "Hatch",
                       142: "Light Pole"}


def load_detail_types(path=None):
    global _DETAILTYPE_CACHE
    if path is None and _DETAILTYPE_CACHE is not None:
        return _DETAILTYPE_CACHE
    gd = find_gd(path)
    if gd is None:
        return []
    try:
        data = Path(gd).read_bytes()
    except Exception:
        return []
    if _DETAILTYPE_COUNT_OFFSET + 2 > len(data):
        return []
    count = struct.unpack_from(">h", data, _DETAILTYPE_COUNT_OFFSET)[0]
    if not (0 < count < 2000):
        return []
    out, off = [], _DETAILTYPE_OFFSET
    for _ in range(count):
        if off + 1 > len(data):
            return []
        rid = data[off]
        off += 1
        strings = []
        for _ in range(4):
            s, off2 = _read_qstring(data, off, maxlen=_DETAILTYPE_MAXSTR)
            if s is None:
                return []
            strings.append(s)
            off = off2
        if off + _DETAILTYPE_TAIL > len(data):
            return []
        out.append(DetailType(rid, strings,
                              bytes(data[off:off + _DETAILTYPE_TAIL])))
        off += _DETAILTYPE_TAIL
    if off != _DETAILTYPE_END:
        return []
    if [d.type_id for d in out] != list(range(count)):
        return []
    for tid, name in _DETAILTYPE_ANCHORS.items():
        if out[tid].sc_header != name:
            return []
    if path is None:
        _DETAILTYPE_CACHE = out
    return out


_ROOMTYPE_COUNT_OFFSET = 52431
_ROOMTYPE_OFFSET = 52433
_ROOMTYPE_END = 58931


class RoomType:
    __slots__ = ("type_id", "sc_header", "sc_subtitle", "bd_header",
                 "bd_subtitle", "raw")

    def __init__(self, type_id, strings, raw=b""):
        self.type_id = type_id
        (self.sc_header, self.sc_subtitle,
         self.bd_header, self.bd_subtitle) = strings
        self.raw = raw

    def __repr__(self):
        return ("RoomType(%d, %r / %r)"
                % (self.type_id, self.sc_header, self.bd_header))


_ROOMTYPE_CACHE = None

_ROOMTYPE_ANCHORS = {2: "Bridge", 5: "Hold", 10: "Galley", 21: "Weapon Bay"}


def load_room_types(path=None):
    global _ROOMTYPE_CACHE
    if path is None and _ROOMTYPE_CACHE is not None:
        return _ROOMTYPE_CACHE
    gd = find_gd(path)
    if gd is None:
        return []
    try:
        data = Path(gd).read_bytes()
    except Exception:
        return []
    if _ROOMTYPE_COUNT_OFFSET + 2 > len(data):
        return []
    count = struct.unpack_from(">h", data, _ROOMTYPE_COUNT_OFFSET)[0]
    if not (0 < count < 200):
        return []
    out, off = [], _ROOMTYPE_OFFSET
    for _ in range(count):
        start = off
        if off + 4 > len(data):
            return []
        rid = struct.unpack_from(">i", data, off)[0]
        off += 4
        strings = []
        for _ in range(4):
            s, off2 = _read_qstring(data, off)
            if s is None:
                return []
            strings.append(s)
            off = off2
        out.append(RoomType(rid, strings, bytes(data[start:off])))
    if off != _ROOMTYPE_END:
        return []
    if [r.type_id for r in out] != list(range(count)):
        return []
    for tid, name in _ROOMTYPE_ANCHORS.items():
        if out[tid].sc_header != name:
            return []
    if path is None:
        _ROOMTYPE_CACHE = out
    return out


_COMMODITY_COUNT_OFFSET = 58931
_COMMODITY_OFFSET = 58933
_COMMODITY_END = 235437

_COMMODITY_LAYOUT = (
    2,
    4,
    17,
    17,
    4,
    4,
    1,
    4,
    2,
    4,
    'q',
    1,
    1,
    'q',
    'q',
    4,
    24,
    1,
    'q',
    1,
    2,
    1,
    1,
    20,
    1,
    20,
    4,
)

_COMMODITY_FLAGS_AT = 55

_COMMODITY_BITSWEAR_AT = 49


_FLD_PACK_SIZE = 20
_FLD_STACK_LIMIT = 21
_FLD_MODE1 = 22
_FLD_WEAPON1 = 23
_FLD_MODE2 = 24
_FLD_WEAPON2 = 25
_FLD_WEIGHT = 26

_WB_RANGE = 0
_WB_EFFECT1 = 2
_WB_DAMAGE1 = 3
_WB_EFFECT2 = 11
_WB_DAMAGE2 = 12


def _field_offsets(raw):
    off = 0
    offsets = []
    n = len(raw)
    for item in _COMMODITY_LAYOUT:
        offsets.append(off)
        if item == 'q':
            if off + 4 > n:
                return None
            slen = struct.unpack_from(">I", raw, off)[0]
            off += 4 + (0 if slen == 0xFFFFFFFF else slen)
        else:
            off += item
        if off > n:
            return None
    return offsets if off == n else None


class Commodity:

    __slots__ = ("index", "cid", "name", "description", "bitmap", "model",
                 "flags", "raw")

    def __init__(self, index, cid, strings, flags, raw):
        self.index = index
        self.cid = cid
        self.description, self.bitmap, self.model, self.name = strings
        self.flags = flags
        self.raw = raw

    @property
    def vacant(self):
        return self.cid == 0 and not self.name

    @property
    def is_broker_item(self):
        return bool(self.flags & 1)

    @property
    def bits_wear(self):
        if not self.raw or len(self.raw) < _COMMODITY_BITSWEAR_AT + 4:
            return 0
        return struct.unpack_from(
            ">I", self.raw, _COMMODITY_BITSWEAR_AT)[0]

    @property
    def _offsets(self):
        return _field_offsets(self.raw) if self.raw else None

    @property
    def weight(self):
        o = self._offsets
        if o is None:
            return 0.0
        try:
            return float(struct.unpack_from(">f", self.raw, o[_FLD_WEIGHT])[0])
        except Exception:
            return 0.0

    @property
    def pack_size(self):
        o = self._offsets
        if o is None:
            return (0, 0)
        i = o[_FLD_PACK_SIZE]
        if i + 2 > len(self.raw):
            return (0, 0)
        return (self.raw[i], self.raw[i + 1])

    @property
    def pack_volume(self):
        w, h = self.pack_size
        return int(w) * int(h)

    @property
    def stack_limit(self):
        o = self._offsets
        if o is None:
            return 0
        i = o[_FLD_STACK_LIMIT]
        return self.raw[i] if i < len(self.raw) else 0

    def weapon_block(self, sub=1):
        o = self._offsets
        if o is None:
            return (0, 0, 0, 0, 0)
        mi = o[_FLD_MODE1 if sub == 1 else _FLD_MODE2]
        bi = o[_FLD_WEAPON1 if sub == 1 else _FLD_WEAPON2]
        if bi + 20 > len(self.raw) or mi >= len(self.raw):
            return (0, 0, 0, 0, 0)
        b = self.raw
        return (b[mi], b[bi + _WB_EFFECT1],
                struct.unpack_from(">h", b, bi + _WB_DAMAGE1)[0],
                b[bi + _WB_EFFECT2],
                struct.unpack_from(">h", b, bi + _WB_DAMAGE2)[0])

    def __repr__(self):
        return ("Commodity(%d, %r, flags=0x%x)"
                % (self.cid, self.name, self.flags))


def _read_commodity_row(data, off):
    start = off
    strings = []
    for item in _COMMODITY_LAYOUT:
        if item == 'q':
            if off + 4 > len(data):
                return None
            n = struct.unpack_from(">I", data, off)[0]
            if n == 0xFFFFFFFF:
                strings.append("")
                off += 4
                continue
            if n > 4000 or n % 2 or off + 4 + n > len(data):
                return None
            try:
                strings.append(data[off + 4:off + 4 + n].decode("utf-16-be"))
            except Exception:
                return None
            off += 4 + n
        else:
            off += item
            if off > len(data):
                return None
    return (struct.unpack_from(">h", data, start)[0],
            strings,
            struct.unpack_from(">I", data, start + _COMMODITY_FLAGS_AT)[0],
            bytes(data[start:off]),
            off)


_COMMODITY_ANCHORS = {
    31: "Pistol", 48: "Lumber", 51: "Metal", 73: "Medical Kit",
    76: "Stone", 86: "Log", 116: "Knife", 117: "Shotgun", 233: "Bone",
    662: "Private Security Contractor Technology",
}

_COMMODITY_ROWS_CACHE = None


def _validate_commodities(rows):
    if len(rows) < 500:
        return False
    by_cid = {c.cid: c for c in rows if c.cid}
    for cid, name in _COMMODITY_ANCHORS.items():
        row = by_cid.get(cid)
        if row is None or row.name != name:
            return False
    return all(c.index == c.cid for c in rows if not c.vacant)


def load_commodity_rows(path=None):
    global _COMMODITY_ROWS_CACHE
    if path is None and _COMMODITY_ROWS_CACHE is not None:
        return _COMMODITY_ROWS_CACHE
    gd = find_gd(path)
    if gd is None:
        return []
    try:
        data = Path(gd).read_bytes()
    except Exception:
        return []
    if _COMMODITY_COUNT_OFFSET + 2 > len(data):
        return []
    count = struct.unpack_from(">h", data, _COMMODITY_COUNT_OFFSET)[0]
    if not (0 < count < 5000):
        return []
    out, off = [], _COMMODITY_OFFSET
    for idx in range(count):
        r = _read_commodity_row(data, off)
        if r is None:
            return []
        cid, strings, flags, raw, off = r
        out.append(Commodity(idx, cid, strings, flags, raw))
    if off != _COMMODITY_END:
        return []
    if not _validate_commodities(out):
        return []
    if path is None:
        _COMMODITY_ROWS_CACHE = out
    return out


def load_commodities(path=None):
    return {c.cid: c for c in load_commodity_rows(path)
            if c.cid and not c.vacant}


_COMMODITY_FLAGS_CACHE = None


def commodity_flags(path=None):
    global _COMMODITY_FLAGS_CACHE
    if path is None and _COMMODITY_FLAGS_CACHE is not None:
        return _COMMODITY_FLAGS_CACHE
    out = {c.cid: c.flags for c in load_commodity_rows(path)
           if c.cid and not c.vacant}
    if path is None and out:
        _COMMODITY_FLAGS_CACHE = out
    return out


def is_broker_item(cid, default=None):
    f = commodity_flags().get(int(cid) & 0xFFFF)
    return default if f is None else bool(f & 1)


_TECH_EXTRA = (0x11E, 0x15C, 0x15E, 0x221)
_TECH_HIGH_MASK = 0x7C43FF


def is_tech(cid):
    c = int(cid)
    if 0 <= c - 0x9E <= 0x43:
        return True
    v = c - 0x280
    if 0 <= v <= 0x16 and (_TECH_HIGH_MASK >> (v & 0x1F)) & 1:
        return True
    return c in _TECH_EXTRA


_PATENT_CIDS = frozenset(
    list(range(356, 368)) + list(range(370, 372)) + list(range(374, 382))
    + list(range(383, 385)) + list(range(386, 404)) + list(range(406, 408))
    + [411] + list(range(413, 421)) + list(range(423, 427))
    + list(range(429, 433)) + list(range(434, 437)) + list(range(439, 441))
    + list(range(442, 451)) + list(range(452, 458)) + [459]
    + list(range(461, 464)) + list(range(465, 471)) + list(range(473, 475))
    + [476, 478, 485, 487] + list(range(489, 500)) + list(range(502, 505))
    + list(range(506, 545)) + list(range(547, 579)) + list(range(580, 582))
    + [584] + list(range(599, 609)) + list(range(613, 617)) + [618]
    + list(range(620, 622)) + [639, 653] + list(range(656, 658))
)


def is_patent(cid):
    return int(cid) in _PATENT_CIDS


_COMMODITY_NAME_CACHE = None

_NAME_ANCHORS = {
    87: "Atmosphere Density",
    88: "Water in the Environment",
    89: "Vegetation Density",
    94: "Sunlight",
}


def commodity_names(path=None):
    global _COMMODITY_NAME_CACHE
    if path is None and _COMMODITY_NAME_CACHE is not None:
        return _COMMODITY_NAME_CACHE
    out = {c.cid: c.name for c in load_commodity_rows(path)
           if c.cid and not c.vacant and c.name}
    if path is None and out:
        _COMMODITY_NAME_CACHE = out
    return out


def commodity_name(cid, default=None):
    n = commodity_names().get(int(cid) & 0xFFFF)
    if n:
        return n
    return default if default is not None else f"cid 0x{int(cid) & 0xFFFF:x}"
