from __future__ import annotations
import datetime as _dt

from openshores.core.logging import get_logger
from openshores.gameplay import gd_tables as _gd
from openshores.gameplay.city_sim import ItemStock
from openshores.protocol.stream import QDS

logger = get_logger(__name__)


KIND_CITY, KIND_CAPITOL, KIND_HQ = 0, 1, 2


def report_kind_default() -> int:
    return KIND_CAPITOL


DEFAULT_INDUSTRY_QUALITY = 1
DEFAULT_INDUSTRY_QOP = 1


POWER_CAPACITY_PER_LEVEL = 50
POWER_USE_PER_CITIZEN = 4


def build_city_industry_hash(industries):
    rows = []
    if isinstance(industries, dict):
        items = sorted(industries.items())
    else:
        items = list(industries or [])
    for it in items:
        if isinstance(it, (tuple, list)):
            ind = int(it[0])
            lv = int(it[1]) if len(it) > 1 else 0
            qual = int(it[2]) if len(it) > 2 else DEFAULT_INDUSTRY_QUALITY
            qop = int(it[3]) if len(it) > 3 else DEFAULT_INDUSTRY_QOP
        else:
            ind, lv = int(it), 0
            qual = qop = DEFAULT_INDUSTRY_QUALITY
        if ind <= 0 or lv <= 0:
            continue
        rows.append((ind & 0xFF, qual & 0xFF, lv, qop & 0xFF))
    if len(rows) > 127:
        raise ValueError("AuCityIndustryHash count is i8; got %d" % len(rows))
    q = QDS()
    q.write_i8(len(rows))
    for ind, qual, lv, qop in rows:
        q.write_u8_wrapped(ind)
        q.write_u8_wrapped(qual or 1)
        q.write_i32(lv)
        q.write_u8_wrapped(qop or 1)
    return q.getvalue()


def industries_from_report(rd):
    if not isinstance(rd, dict) or "industries" not in rd:
        return None
    raw = rd.get("industries")
    if not isinstance(raw, dict):
        return None
    out = {}
    for k, v in raw.items():
        try:
            ind, lv = int(k), int(v)
        except (TypeError, ValueError):
            continue
        if ind > 0 and lv > 0:
            out[ind] = lv
    return out


def industries_from_developments(devs):
    out = {}
    for d in (devs or []):
        if not isinstance(d, dict):
            continue
        if d.get("kind", "building") != "building":
            continue
        cpid = int(d.get("cpid") or 0)
        if not cpid:
            continue
        ind = _gd.construction_process_industry(cpid) or 0
        if not ind:
            ind = cpid
        out[ind] = out.get(ind, 0) + 1
    return out


def build_aucityreport(*, name="", population=0, timestamp_ms=None,
                       kind=KIND_CITY, fields=None, probe=False,
                       dna: bytes = b"", founder_auid=0, founder_name="",
                       extra_flags=0, races=None, events=None, inventory=None,
                       industries=None, tools=None) -> bytes:
    if timestamp_ms is None:
        timestamp_ms = int(_dt.datetime.now(_dt.timezone.utc).timestamp() * 1000)
    f = dict(fields or {})
    if name and 0x1B8 not in f:
        f[0x1B8] = name
    if population and 0x08 not in f:
        f[0x08] = int(population)

    def g(off, default=0):
        if probe:
            return off
        return f.get(off, default)

    def gs(off):
        if probe:
            return "s%x" % off
        v = f.get(off, "")
        return v if isinstance(v, str) else ""

    q = QDS()
    flags = 0x8000 | ((int(kind) & 0x3) << 12) | (int(extra_flags) & 0x01FF)
    if founder_auid or founder_name:
        flags |= 0x400
    q.write_u16(flags)
    q.write_u8_wrapped(7)
    q.write_i32(g(0x00)); q.write_i32(g(0x04)); q.write_i32(g(0x08))
    for off in (0x10, 0x18, 0x20, 0x28):
        q.write_f64(g(off))
    for off in (0x30, 0x38, 0x40, 0x48, 0x50, 0x58, 0x60, 0x68, 0x70, 0x78, 0x80):
        q.write_f64(g(off))
    for off in range(0x88, 0x108, 0x08):
        q.write_f64(g(off))
    q.write_qstring(gs(0x108))
    _races = list(races or [])
    q.write_i32(len(_races))
    for _dna, _pop in _races:
        q.write_bytes((bytes(_dna) + bytes(24))[:24] if _dna else bytes(24))
        q.write_i32(int(_pop))
    q.write_u8_wrapped(g(0x11c)); q.write_u8_wrapped(g(0x120)); q.write_u8_wrapped(g(0x124))
    q.write_qstring(gs(0x128))
    _events = list(events or [])
    q.write_i16_wrapped(len(_events))
    for _msg, _ts in _events:
        q.write_qstring(_msg or "")
        q.write_qdatetime(int(_ts) if _ts else timestamp_ms)
        q.write_u8_wrapped(0)
    q.write_u8_wrapped(0)
    q.write_u8_wrapped(g(0x158))
    q.write_i32(g(0x26c)); q.write_i32(g(0x270)); q.write_i32(g(0x274))
    q.write_i32(g(0x15c))
    q.write_raw(build_city_industry_hash(industries))
    if inventory:
        q.write_raw(build_auitemhash(list(inventory)))
    else:
        q.write_i32(0)
    for off in (0x178, 0x17c, 0x180, 0x184):
        q.write_i32(g(off))
    q.write_f64(g(0x188))
    q.write_i16_wrapped(g(0x190)); q.write_i16_wrapped(g(0x192))
    q.write_f64(g(0x198)); q.write_f64(g(0x1a0))
    q.write_f32(g(0x1a8)); q.write_i32(g(0x1ac)); q.write_u8_wrapped(g(0x1b0))
    q.write_qstring(gs(0x1b8))
    _dna = (bytes(dna) + bytes(24))[:24] if dna else bytes(24)
    q.write_bytes(_dna)
    q.write_qstring(gs(0x1e8)); q.write_qstring(gs(0x1e0)); q.write_i32(g(0x1f0))
    q.write_u8_wrapped(g(0x281)); q.write_u8_wrapped(g(0x282)); q.write_u8_wrapped(g(0x283))
    q.write_i32(g(0x1f8))
    q.write_i32(0)
    q.write_u8_wrapped(g(0x208)); q.write_qstring(gs(0x210)); q.write_qstring(gs(0x218))
    q.write_i32(0)
    q.write_qstring(gs(0x228)); q.write_qstring(gs(0x230))
    if tools:
        q.write_raw(build_auitemhash(list(tools)))
    else:
        q.write_i32(0)
    q.write_i16_wrapped(g(0x240)); q.write_u8_wrapped(g(0x242)); q.write_i32(g(0x244))
    q.write_u8_wrapped(0)
    q.write_qdatetime(timestamp_ms)
    q.write_u8_wrapped(g(0x258)); q.write_i32(g(0x25c))
    q.write_u8_wrapped(g(0x140)); q.write_i32(g(0x144)); q.write_i32(g(0x1f4))
    if founder_auid or founder_name:
        q.write_u32(int(founder_auid) & 0xFFFFFFFF)
        q.write_qstring(founder_name or "")
    return q.getvalue()


def build_aucityreporthistory(reports) -> bytes:
    q = QDS()
    q.write_i16_wrapped(len(reports))
    for r in reports:
        q.write_raw(r)
    return q.getvalue()


def _encode_auitem(commodity_id, quantity=None, quality=None, kind=1):
    q = QDS()
    q.write_u8_wrapped(0x01)
    flags = 0
    if quantity is not None:
        flags |= 0x01
    if quality is not None:
        flags |= 0x04
    q.write_u8_wrapped(flags)
    q.write_i16_wrapped(int(commodity_id) & 0xFFFF)
    if flags & 0x01:
        q.write_i32(int(quantity))
    if flags & 0x04:
        q.write_u8_wrapped(int(quality) & 0xFF)
    q.write_u8_wrapped(int(kind) or 1)
    return q.getvalue()


def build_auitemhash(items):
    q = QDS()
    q.write_i32(len(items))
    for it in items:
        cid = it[0]
        qty = it[1] if len(it) > 1 else None
        qual = it[2] if len(it) > 2 else None
        q.write_raw(_encode_auitem(cid, qty, qual))
    return q.getvalue()


def inventory_from_info(info, rd):
    return _itemhash_from_snapshot(info, "stock")


def tools_from_info(info, rd=None):
    return _itemhash_from_snapshot(info, "tools")


def _itemhash_from_snapshot(info, key):
    snap = (info or {}).get("sim_snapshot") or {}
    try:
        stacks = ItemStock.from_json(snap.get(key)).stacks
    except Exception:
        return []
    totals = {}
    for s in stacks:
        try:
            c = int(s.commodity); q = int(s.quantity); qual = int(s.quality)
        except Exception:
            continue
        if q <= 0 or not (0 <= c <= 0xFFFF):
            continue
        tot, best_q, best_qty = totals.get(c, (0, 0, 0))
        if q > best_qty:
            best_q, best_qty = qual, q
        totals[c] = (tot + q, best_q, best_qty)
    return [(c, tot, max(1, min(255, best_q)))
            for c, (tot, best_q, _n) in sorted(totals.items())]


def home_triple_is_fatal(large, medium, small) -> bool:
    return int(small) > 0 and (int(medium) + 2 * int(large)) == 0


import math as _math


def report_fields_from_info(info, rd, geo=None):
    info = info or {}
    rd = rd or {}
    geo = geo or {}
    name = (info.get("name") or rd.get("name") or "")
    ts = int(rd.get("t", 0) or 0) or None
    fields = {}
    if name:
        fields[0x1b8] = name

    _pop = rd.get("population")
    if _pop is None:
        _pop = (info.get("sim_snapshot") or {}).get("population", 0)
    fields[0x08] = int(_pop or 0)
    if rd.get("jobs_manufacturing") or rd.get("jobs_service"):
        fields[0x17c] = int(rd.get("jobs_manufacturing") or 0)
        fields[0x184] = int(rd.get("jobs_service") or 0)

    fields[0x1f0] = int(_pop or 0)

    if rd.get("lat") is not None and rd.get("lon") is not None:
        fields[0x1a0] = _math.radians(float(rd["lat"]))
        fields[0x198] = _math.radians(float(rd["lon"]))
    else:
        blds = info.get("buildings") or []
        lats = [float(b.get("lat", 0.0)) for b in blds if b.get("lat") is not None]
        lons = [float(b.get("lon", 0.0)) for b in blds if b.get("lon") is not None]
        if lats and lons:
            fields[0x1a0] = _math.radians(sum(lats) / len(lats))
            fields[0x198] = _math.radians(sum(lons) / len(lons))

    if rd.get("unemployed") is not None:
        fields[0x244] = max(0, int(rd.get("unemployed") or 0))

    _hl = int(rd.get("homes_large") or 0)
    _hm = int(rd.get("homes_medium") or 0)
    _hs = int(rd.get("homes_small") or 0)
    if home_triple_is_fatal(_hl, _hm, _hs):
        logger.warning(
            '%d small homes with no medium or large ones: ReportCapitol @1800bffcd would divide by zero computing the Cramped Living Conditions penalty, so the housing figures are withheld.', _hs)
    elif _hl or _hm or _hs:
        fields[0x26c], fields[0x270], fields[0x274] = _hl, _hm, _hs

    def _str(v):
        return v if (isinstance(v, str) and v) else None
    _loc = {
        0x1e8: _str(geo.get("planet_name")),
        0x1e0: _str(geo.get("system_name") or geo.get("star_name")),
        0x228: _str(geo.get("system_name")),
        0x230: _str(geo.get("system_coords")),
        0x210: _str(geo.get("sector_name")),
        0x218: _str(geo.get("sector_coords")),
    }
    for off, val in _loc.items():
        if val:
            fields[off] = val
    if rd.get("bank") is not None:
        fields[0x10] = float(rd.get("bank") or 0.0)
    if rd.get("treasury") is not None:
        fields[0xa0] = float(rd.get("treasury") or 0.0)
    _snap = info.get("sim_snapshot") or {}
    _pop = int(rd.get("population", _snap.get("population", 0)) or 0)
    _power_levels = 0
    try:
        _inds = industries_from_report(rd)
        if _inds is None:
            _inds = industries_from_developments(info.get("buildings"))
        _power_levels = sum(lv for ind, lv in _inds.items()
                            if ind in _gd.POWER_PRODUCER_INDUSTRIES)
    except Exception:
        _power_levels = 0
    if _power_levels:
        _cap = _power_levels * POWER_CAPACITY_PER_LEVEL
        _con = _pop * POWER_USE_PER_CITIZEN
        fields[0x15c] = _cap
        fields[0x1f8] = min(_con, _cap)
        fields[0x1f4] = max(0, _cap - _con)
    else:
        fields[0x15c] = 0
        fields[0x1f8] = 0
        fields[0x1f4] = 0
    return name, ts, fields


def races_from_report(info, rd):
    pop = int((rd or {}).get("population", 0) or 0)
    if pop <= 0:
        return []
    founder = (info or {}).get("founder") or {}
    dna_hex = founder.get("dna") or ""
    try:
        dna = bytes.fromhex(dna_hex) if dna_hex else b""
    except Exception:
        dna = b""
    return [(dna, pop)]


_EVENT_MSG = {
    "starvation": "{n} citizens starved to death.",
    "suffocation": "{n} citizens suffocated to death.",
    "births": "{n} new residents were born.",
    "no_power": "The city has no electricity.",
    "underserved": "City services are short of demand.",
    "decay": "{detail}",
    "housing": "{detail}",
}


def events_from_report(rd):
    rd = rd or {}
    ts = int(rd.get("t", 0) or 0) or None
    out = []
    for ev in (rd.get("events") or []):
        kind = ev.get("kind")
        tpl = _EVENT_MSG.get(kind)
        if not tpl:
            continue
        try:
            msg = tpl.format(n=int(ev.get("count", 0) or 0), detail=ev.get("detail", ""))
        except Exception:
            msg = ev.get("detail", "") or str(kind)
        out.append((msg, ts))
    return out
