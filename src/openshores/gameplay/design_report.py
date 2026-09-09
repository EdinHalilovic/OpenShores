from __future__ import annotations

import struct

FIELDS = ("home_large",
          "home_medium",
          "home_small",
          "lounge",
          "office",
          "store",
          "shop",
          "triangles")

EXTRA_FIELDS = ("field", "arena", "auditorium", "faces", "hold")

_PRE_LEN = 4 + 4 + 4 + 8 + 4 + 8 + 4
_PRE_LEN_OLD = _PRE_LEN + 4

VERSION_SPLIT = 13

_TAIL_LEN = 4 + 8 + 4 + 4

_HEAD_LEN = 4 + 4 + 4 + 8 + 4 + 4

_MAX_QSTRING_BYTES = 0x200


def _find_qstring_start(blob: bytes) -> int | None:
    end = len(blob) - _TAIL_LEN
    for p in range(end - 4, max(-1, end - 4 - _MAX_QSTRING_BYTES), -1):
        if p < _HEAD_LEN:
            break
        (ln,) = struct.unpack_from(">I", blob, p)
        if ln == 0xFFFFFFFF:
            if p + 4 == end:
                return p
            continue
        if ln <= _MAX_QSTRING_BYTES and p + 4 + ln == end:
            return p
    return None


def parse_design_report(blob) -> dict | None:
    if not blob:
        return None
    b = bytes(blob)
    if len(b) < _TAIL_LEN + _HEAD_LEN + 4:
        return None
    try:
        store, _f218, shop, triangles = struct.unpack(">idii", b[len(b) - _TAIL_LEN:])
        p = _find_qstring_start(b)
        if p is None or p < _HEAD_LEN:
            return None
        hl, hm, hs, _f200, lounge, office = struct.unpack(
            ">iiidii", b[p - _HEAD_LEN:p])
    except struct.error:
        return None
    out = dict(zip(FIELDS, (hl, hm, hs, lounge, office, store, shop, triangles)))
    for k in ("home_large", "home_medium", "home_small", "lounge", "office",
              "store", "shop"):
        if not (0 <= out[k] <= 0xFFFF):
            return None

    version = b[0]
    pre = _PRE_LEN if version >= VERSION_SPLIT else _PRE_LEN_OLD
    start = p - _HEAD_LEN - pre
    if start >= 1:
        if version >= VERSION_SPLIT:
            fld, arena, aud, _cap, faces, _fuel, hold = struct.unpack(
                ">iiididi", b[start:p - _HEAD_LEN])
        else:
            fld, arena, aud, _cap, faces, _fuel, _extra, hold = \
                struct.unpack(">iiididii", b[start:p - _HEAD_LEN])
        extra = dict(zip(EXTRA_FIELDS, (fld, arena, aud, faces, hold)))
        if all(0 <= extra[k] <= 0xFFFF
               for k in ("field", "arena", "auditorium", "hold")):
            out.update(extra)
    out["version"] = version
    return out


def homes_from_reports(reports) -> tuple:
    large = medium = small = 0
    for r in reports:
        if not r:
            continue
        large += int(r.get("home_large", 0) or 0)
        medium += int(r.get("home_medium", 0) or 0)
        small += int(r.get("home_small", 0) or 0)
    return large, medium, small


ROOM_LEVEL_INDUSTRIES = frozenset({
    0x1e, 0x1f, 0x20, 0x22, 0x23, 0x28, 0x29, 0x2a, 0x2b, 0x2c, 0x2d, 0x2e,
    0x2f, 0x30, 0x32, 0x33, 0x34, 0x3c, 0x3d, 0x3e, 0x3f, 0x40, 0x41, 0x42,
    0x43, 0x44, 0x46, 0x47, 0x48, 0x49, 0x4a, 0x4b, 0x4c, 0x4d, 0x4e, 0x4f,
    0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5a, 0x64,
    0x6e, 0x7d,
})

ALWAYS_ONE_LEVEL = frozenset({0x46, 0x55, 0x57, 0x58})

INDUSTRY_MINE = 0x32


def _s8(v):
    v = int(v) & 0xFF
    return v - 256 if v > 127 else v


def industry_info(report, industry, gd_row, generator_jobs=0,
                  surgery_units=0, station_counts=0):
    if not report or not gd_row:
        return 0, 0
    raw = getattr(gd_row, "raw", None) or {}
    b23, b26 = _s8(raw.get(0x23, 0)), _s8(raw.get(0x26, 0))
    b27, b34 = _s8(raw.get(0x27, 0)), _s8(raw.get(0x34, 0))
    g = lambda k: int(report.get(k, 0) or 0)

    jobs = (g("arena") + g("store") + g("office") + g("lounge")
            + int(surgery_units) + int(station_counts))
    levels = 0
    ind = int(industry)

    if ind not in ROOM_LEVEL_INDUSTRIES:
        if b23 >= 0:
            jobs += g("auditorium")
        if b26 > 0:
            jobs += g("field")
        return levels, jobs

    if ind in ALWAYS_ONE_LEVEL:
        return 1, jobs

    if b23 > 0:
        levels = g("auditorium")
    elif b23 == 0:
        jobs += g("auditorium")
    if b26 > 0:
        levels += g("field")
    if b27 >= 0:
        levels += int(generator_jobs)
    if b34 >= 0:
        levels += g("shop")
    if ind == INDUSTRY_MINE and g("shop") == 0:
        levels += 1
        if g("office") != 0 and jobs != 0:
            jobs -= 1
    return levels, jobs


def city_industry_summary(pairs, industries_table):
    levels: dict = {}
    manufacturing = service = 0
    for industry, report in pairs or ():
        ind = int(industry or 0)
        if not ind:
            continue
        lv, jobs = industry_info(report, ind, (industries_table or {}).get(ind))
        manufacturing += lv
        service += jobs
        levels[ind] = levels.get(ind, 0) + (lv if lv else 1)
    return levels, manufacturing, service
