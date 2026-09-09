
from __future__ import annotations

import struct

from openshores.core.logging import get_logger
from openshores.database.repositories.blueprint import published_blueprints
from openshores.gameplay import gd_tables as _gd

logger = get_logger(__name__)

async def _iter_capitol_blueprints(conn):
    out = []
    for r in await published_blueprints(conn):
        rb = r["report_bytes"]
        if not rb:
            continue
        out.append({
            "stem": r["stem"],
            "name": r["name"] or "",
            "design_id": int(r["design_id"]) & 0xFFFFFFFF,
            "report": bytes(rb),
            "cblob": bytes(r["construction_blob"] or b""),
            "dmat": int(r["design_material"] or 0) & 0xFFFF,
        })
    return out


async def _blueprints_by_id(conn):
    out = {}
    for r in await published_blueprints(conn):
        db = bytes(r["design_blob"] or b"")
        if len(db) < 6:
            continue
        did = int(r["design_id"]) & 0xFFFFFFFF
        out[did] = (r["name"] or "?", db)
    return out


def _work_site_loc(payload: bytes):
    body = bytes(payload[1:])
    if len(body) < 2 or not body[1]:
        return None
    if len(body) < 10:
        logger.warning("Work-site frame set useLoc but carries only %dB of "
                       "body: %s", len(body), body.hex())
        return None
    try:
        lat, lon = struct.unpack_from(">ff", body, 2)
    except Exception as exc:
        logger.warning("Work-site useLoc body did not unpack: %s", exc)
        return None
    logger.info('Work-site frame carries useLoc=1 lat=%.6f lon=%.6f rad (body=%s).', lat, lon, body.hex())
    return (lat, lon)


_MFG_INDUSTRIES_LEGACY = set(range(40, 53)) | {0x57}


def _mfg_industries():
    try:
        gd = _gd.manufacturing_industries()
    except Exception as exc:
        logger.error("GD manufacturing industries unreadable; falling back to "
                     "the legacy set. %s", exc)
        gd = set()
    return (gd | _MFG_INDUSTRIES_LEGACY) if gd else set(_MFG_INDUSTRIES_LEGACY)


def _mfg_industry_for(dev):
    try:
        return int(_gd.construction_process_industry(
            int(dev.get("cpid") or 0)) or 0) & 0xFF
    except Exception as exc:
        logger.debug("Development has an unreadable cpid; industry 0. %s", exc)
        return 0
