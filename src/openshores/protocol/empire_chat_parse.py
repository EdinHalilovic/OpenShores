
from __future__ import annotations

import logging
import struct
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def _s32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


def _read_qstring(body: bytes, off: int) -> Tuple[Optional[str], int]:
    if off + 4 > len(body):
        return None, off
    n = struct.unpack_from(">I", body, off)[0]
    off += 4
    if n == 0xFFFFFFFF:
        return None, off
    raw = body[off:off + n]
    off += n
    return raw.decode("utf-16-be", "replace"), off


def parse_policy_toggle(body: bytes) -> Optional[Tuple[int, int]]:
    if len(body) < 2:
        return None
    return body[0], body[1]


def parse_contrail_color(body: bytes) -> Optional[Tuple[int, int]]:
    if len(body) < 2:
        return None
    return body[0], body[1]


def parse_role(body: bytes) -> Optional[Tuple[int, int]]:
    if len(body) < 3:
        return None
    return struct.unpack_from(">H", body, 0)[0], body[2]


def parse_emperor(body: bytes) -> Optional[Tuple[int, int, Optional[str]]]:
    if len(body) < 6:
        return None
    eid = struct.unpack_from(">H", body, 0)[0]
    auid = struct.unpack_from(">I", body, 2)[0]
    name, _ = _read_qstring(body, 6)
    return eid, auid, name


def parse_rewards(body: bytes) -> Optional[List[int]]:
    if len(body) < 64:
        return None
    return [struct.unpack_from(">i", body, i * 4)[0] for i in range(16)]


def parse_announcement(body: bytes) -> Optional[str]:
    s, _ = _read_qstring(body, 0)
    return s or ""


def _read_qstring_be(buf: bytes, off: int) -> Tuple[str, int]:
    if off + 4 > len(buf):
        return "", off
    n = struct.unpack_from(">I", buf, off)[0]
    off += 4
    if n == 0 or n == 0xFFFFFFFF:
        return "", off
    raw = bytes(buf[off:off + n])
    off += n
    try:
        return raw.decode("utf-16-be"), off
    except Exception:
        logger.warning("Empire chat QString: undecodable UTF-16-BE at off=%d n=%d", off - n - 4, n)
        return "", off


def _parse_found_city(payload: bytes):
    off = 1
    try:
        idi = payload[off]; off += 1
        qty = struct.unpack_from(">i", payload, off)[0]; off += 4
        mat = struct.unpack_from(">H", payload, off)[0]; off += 2
        x, y, z = struct.unpack_from(">ddd", payload, off); off += 24
        yaw = struct.unpack_from(">f", payload, off)[0]; off += 4
        levels = struct.unpack_from(">h", payload, off)[0]; off += 2
        flag = payload[off]; off += 1
        disc = payload[off]; off += 1
        city = system = sector = None
        config = None
        if disc == 0x01:
            city, off = _read_qstring_be(payload, off)
            system, off = _read_qstring_be(payload, off)
            sector, off = _read_qstring_be(payload, off)
        elif disc == 0x02:
            config = struct.unpack_from(">h", payload, off)[0]; off += 2
        elif disc != 0x00:
            logger.warning('[found-city] 0xE3 unknown discriminator 0x%02x (idi=0x%02x).',
                           disc, idi)
        return {"idi": idi, "qty": qty, "design_serial": qty & 0xFFFFFFFF,
                "material": mat, "xyz": (x, y, z),
                "yaw": yaw, "levels": levels, "flag": flag,
                "disc": disc, "config": config,
                "has_names": (disc == 0x01),
                "altitude": yaw, "facing": levels,
                "city": city, "system": system, "sector": sector}
    except Exception as exc:
        logger.warning("[found-city] parse err: %r raw=%s",
                       exc, bytes(payload[:56]).hex())
        return None


_CONSTRUCTION_OP_NAMES = {
    (0, 0x0a): "grade", (0, 0x0b): "road_dirt", (0, 0x0c): "road_asphalt",
    (0, 0x0d): "road_concrete",
    (1, 0x01): "defoliate", (1, 0x02): "clear", (1, 0x03): "irrigate",
}


def _parse_construction_op(payload: bytes, *, units_fpm: float):
    off = 1
    subtype = payload[off]; off += 1
    p1 = list(struct.unpack_from(">ddd", payload, off)); off += 24
    p2 = list(struct.unpack_from(">ddd", payload, off)); off += 24
    d = {"subtype": subtype, "p1": p1, "p2": p2}
    if subtype == 0x00:
        d["flag"] = payload[off]; off += 1
        d["width_wire"] = struct.unpack_from(">f", payload, off)[0]; off += 4
        d["width"] = d["width_wire"] / units_fpm
        d["optype"] = payload[off]; off += 1
    else:
        d["radius_wire"] = struct.unpack_from(">f", payload, off)[0]; off += 4
        d["radius"] = d["radius_wire"] / units_fpm
        tail = bytes(payload[off:off + 5])
        d["optype"] = tail[1] if len(tail) >= 2 else 0
        d["params"] = tail.hex()
    d["op"] = _CONSTRUCTION_OP_NAMES.get((subtype, d["optype"]),
                                         "op_%d_%02x" % (subtype, d["optype"]))
    return d


TOWN_SQUARE_CPID = 1


def _parse_town_square(payload: bytes):
    try:
        off = 1
        world = struct.unpack_from(">I", payload, off)[0]; off += 4
        x, y, z = struct.unpack_from(">ddd", payload, off); off += 24
        city, off = _read_qstring_be(payload, off)
        system, off = _read_qstring_be(payload, off)
        sector, off = _read_qstring_be(payload, off)
        yaw = 0.0
        if len(payload) >= 4:
            yaw = struct.unpack_from(">f", payload, len(payload) - 4)[0]
        return {"world": world & 0xFFFFFFFF,
                "xyz": (float(x), float(y), float(z)),
                "city": city, "system": system, "sector": sector,
                "yaw": float(yaw), "idi": TOWN_SQUARE_CPID}
    except Exception as exc:
        logger.warning("[town-square] parse err: %r raw=%s",
                       exc, bytes(payload[:64]).hex())
        return None


_CHAT_CONSTRUCT_LEN = {0x00: 56, 0x01: 59}


def parse_chat_construction_op(payload: bytes) -> dict:
    payload = bytes(payload)
    if len(payload) < 2:
        raise ValueError("0x06 frame too short (%dB)" % len(payload))
    if payload[0] != 0x06:
        raise ValueError("Not an 0x06 frame (op=0x%02x)" % payload[0])
    sub = payload[1]
    need = _CHAT_CONSTRUCT_LEN.get(sub)
    if need is None:
        raise ValueError("Unknown 0x06 subtype 0x%02x" % sub)
    if len(payload) < need:
        raise ValueError("0x06 sub%d truncated: %dB < %dB spec"
                         % (sub, len(payload), need))
    d = {"subtype": sub,
         "p1": list(struct.unpack_from(">ddd", payload, 2)),
         "p2": list(struct.unpack_from(">ddd", payload, 26)),
         "leftover": len(payload) - need}
    if sub == 0x00:
        d["flag"] = payload[50]
        d["width"] = struct.unpack_from(">f", payload, 51)[0]
        d["optype"] = payload[55]
    else:
        d["radius"] = struct.unpack_from(">f", payload, 50)[0]
        d["flag"] = payload[54]
        d["optype"] = payload[55]
        d["params"] = payload[54:59].hex()
    d["op"] = _CONSTRUCTION_OP_NAMES.get((0 if sub == 0 else 1, d["optype"]),
                                         "op_%d_%02x" % (sub, d["optype"]))
    return d


def parse_chat_demolish(payload: bytes) -> dict:
    payload = bytes(payload)
    if len(payload) < 29:
        raise ValueError("0x02 frame truncated: %dB < 29B spec" % len(payload))
    if payload[0] != 0x02:
        raise ValueError("Not an 0x02 frame (op=0x%02x)" % payload[0])
    return {"auid": struct.unpack_from(">I", payload, 1)[0],
            "pos": list(struct.unpack_from(">ddd", payload, 5)),
            "leftover": len(payload) - 29}
