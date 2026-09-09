
from __future__ import annotations

import logging

from openshores.protocol.stream import QDS

logger = logging.getLogger(__name__)


def _parse_scene_0x38(s: QDS) -> dict:
    out = {
        "sceneVersion": s.read_qstring(),
        "session_hi":   s.read_i32(),
        "session_lo":   s.read_i32(),
        "charId":       s.read_u32(),
        "osKind":       s.read_u8(),
        "winVersion":   s.read_u16(),
        "flag40":       s.read_u8(),
        "extra":        s.read_u8(),
    }
    return out


_last_avatar_origin = None


def _parse_scene_0x24(s: QDS, expect_variant_b: "bool | None" = None, *,
                      _create_defer_echo_world: int,
                      GALAXY_CHOICES, REGION_NAMES) -> dict:
    start = s.pos
    total_remaining = len(s.buf) - start
    peek_u32 = int.from_bytes(s.buf[start:start+4], "big") if total_remaining >= 4 else 0
    _looks_like_b = (
        peek_u32 == 1
        or (_create_defer_echo_world
            and peek_u32 == _create_defer_echo_world)
        or (peek_u32 & 1)
    )
    if expect_variant_b is None:
        expect_variant_b = _looks_like_b and total_remaining >= 21
    if expect_variant_b and total_remaining >= 21:
        out = {
            "_variant":     "B_avatar_submit",
            "u32_0":        s.read_u32(),
            "u32_1":        s.read_u32(),
            "u32_2":        s.read_u32(),
            "charName":     s.read_qstring(),
            "flag":         s.read_u8(),
        }
        out["echo_world"]  = out["u32_0"]
        out["echo_empire"] = out["u32_1"]
        out["echo_matches_our_0x22"] = bool(
            _create_defer_echo_world
            and out["u32_0"] == _create_defer_echo_world)
        try:
            blob = s.read_bytes()
            out["avatar_blob"] = blob.hex() if blob else None
        except Exception as e:
            out["avatar_rest_hex"] = bytes(s.buf[s.pos:]).hex()
            out["_blob_err"] = repr(e)
        return out

    out = {"_variant": "A_establish_first_empire",
           "empireName": s.read_qstring()}
    qimg_marker = s.read_i32()
    if qimg_marker == 0:
        out["flag"] = None
    else:
        out["flag"] = f"<non-null QImage marker=0x{qimg_marker:08X}>"
        out["_rest_hex"] = bytes(s.buf[s.pos:]).hex()
        return out
    out["race1"]    = s.read_u8()
    out["race2"]    = s.read_u8()
    out["charName"] = s.read_qstring()
    out["flags"]    = s.read_u8()
    out["gender"]   = out["flags"] & 0x03
    out["lefty"]    = bool(out["flags"] & 0x04)

    r, g = out["race1"], out["race2"]
    plausible = (g in GALAXY_CHOICES) and (0 <= r < len(REGION_NAMES))
    out["origin_galaxy"] = g
    out["origin_region"] = r
    out["origin_plausible"] = plausible
    _verdict = ("matches the Origin row" if plausible else
                "does not match the Origin row")
    _rname = REGION_NAMES[r] if 0 <= r < len(REGION_NAMES) else "?"
    logger.debug("0x24 ORIGIN: galaxy=%s (%s) region=%s (%s) - %s",
                 g, GALAXY_CHOICES.get(g, '?'), r, _rname, _verdict)
    return out
