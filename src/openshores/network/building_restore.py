
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.database.repositories.bd_restore import (
    bd_restore_rows,
    city_capitol_rows,
)
from openshores.database.repositories.city_sim_state import _load_city_founder
from openshores.database.repositories.city_site import _city_id_variants
from openshores.database.repositories.world import _table_columns
from openshores.gameplay.building_manproc import _load_building_manproc
from openshores.gameplay.city_founding import _load_capitol_blueprint_report

logger = get_logger(__name__)


async def _restore_persisted_buildings(*, conn, spawn_city_building):
    rows = []
    try:
        cols = await _table_columns(conn, "a_Bd")
        if "id" not in cols:
            return
        want = ["id", "idp", "locX", "locY", "locZ", "name", "allegiance",
                "industry", "designId", "designRpt",
                "rotX", "rotY", "rotZ", "capitol", "cityName",
                "cstateBlob"]
        sel = [c for c in want if c in cols]
        rows = await bd_restore_rows(conn, sel)
        rows = [dict(zip(sel, r)) for r in rows]
        city_map = {}
        try:
            ccols = await _table_columns(conn, "a_City")
            if "id" in ccols:
                _has_cap = "capitol" in ccols
                for cr in await city_capitol_rows(conn, has_capitol=_has_cap,
                                                  has_name=("name" in ccols)):
                    city_map[int(cr[0]) & 0xFFFFFFFF] = (
                        int(cr[1] or 0) & 0xFFFFFFFF, cr[2] or "")
        except Exception as exc:
            logger.error(f"[capitol-restore] a_City identity query err: {exc!r}")
        for r in rows:
            try:
                if int(r.get("industry") or 0) != 0x7B:
                    continue
                _own_city = int(r.get("capitol") or 0) & 0xFFFFFFFF
                if not _own_city:
                    continue
                _cap0, _nm0 = city_map.get(_own_city, (0, ""))
                if not _cap0:
                    city_map[_own_city] = (
                        int(r.get("id") or 0) & 0xFFFFFFFF,
                        _nm0 or (r.get("cityName") or ""))
            except Exception as exc:
                logger.error(f"[capitol-restore] capitol back-fill err for "
                             f"0x{int(r.get('id') or 0) & 0xFFFFFFFF:08x}: {exc!r}")
                continue
    except Exception as exc:
        logger.error(f"[capitol-restore] a_Bd query err: {exc!r}")
        return
    n = 0
    for r in rows:
        bid = int(r.get("id") or 0) & 0xFFFFFFFF
        if not bid:
            continue
        x = r.get("locX"); y = r.get("locY"); z = r.get("locZ")
        if x is None or y is None or z is None:
            continue
        report = r.get("designRpt")
        did = int(r.get("designId") or 0) & 0xFFFFFFFF
        cblob = None
        dmat = 0
        if not report:
            try:
                rb, _nm, did2, cblob, dmat = await _load_capitol_blueprint_report(
                    conn, selector=(did or None))
                if rb:
                    report = rb
                    did = did or did2
            except Exception as exc:
                logger.error(f"[capitol-restore] blueprint fallback err for "
                             f"0x{bid:08x}: {exc!r}")
        if not report:
            logger.warning(f"[capitol-restore] 0x{bid:08x} '{r.get('name', '')}' has no designRpt and no blueprint fallback.")
            continue
        _cid = int(r.get("capitol") or 0) & 0xFFFFFFFF
        _cap_auid, _cname = city_map.get(_cid, (0, ""))
        _cname = (r.get("cityName") or "") or _cname
        _fnd = (await _load_city_founder(
            conn, _cid, _city_id_variants=_city_id_variants) if _cid else None) or {}
        _cblob = r.get("cstateBlob") or None
        _cblob = bytes(_cblob) if _cblob else None
        try:
            await spawn_city_building(
                bid, int(r.get("idp") or 0) & 0xFFFFFFFF, (x, y, z),
                bytes(report), name=(r.get("name") or ""),
                empire=int(r.get("allegiance") or 0) & 0xFFFFFFFF,
                btype=int(r.get("industry") or 0x7b) & 0xFF,
                design_id=did,
                under_construction=bool(_cblob),
                construction_blob=_cblob,
                rot=(float(r.get("rotX") or 0.0),
                     float(r.get("rotY") or 0.0),
                     float(r.get("rotZ") or 0.0)),
                capitol_auid=_cap_auid, city_name=_cname,
                founder_auid=int(_fnd.get("auid") or 0) & 0xFFFFFFFF,
                founder_name=_fnd.get("name") or "",
                **dict(zip(("manproc", "mproc_cfg"),
                           await _load_building_manproc(conn, _cid, bid))))
            n += 1
        except Exception as exc:
            logger.error(f"[capitol-restore] spawn err 0x{bid:08x}: {exc!r}")
    if n:
        logger.info(f"[capitol-restore] restored {n} founded "
                    f"building{'s' if n != 1 else ''} from a_Bd")


def start_building_restore(*, conn, spawn_city_building) -> None:
    asyncio.create_task(_restore_persisted_buildings(
        conn=conn, spawn_city_building=spawn_city_building))
