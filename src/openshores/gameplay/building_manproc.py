
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.bd_restore import (
    city_developments_by_variants,
)
from openshores.gameplay import city_model as _cm

logger = get_logger(__name__)


async def _load_building_manproc(conn, city_id: int, bauid: int):
    if not city_id or not bauid:
        return [], {}
    try:
        row = await city_developments_by_variants(conn, int(city_id))
        if not row or not row[0]:
            return [], {}
        for e in (_cm.developments_from_blob(row[0]) or []):
            if isinstance(e, dict) and \
                    int(e.get("bauid") or 0) == (int(bauid) & 0xFFFFFFFF):
                return ([int(v) for v in (e.get("manproc") or [])],
                        dict(e.get("mproc_cfg") or {}))
    except Exception as exc:
        logger.error(f"[bd-mfg] manproc load err city=0x{int(city_id):08x} "
                     f"bd=0x{int(bauid) & 0xFFFFFFFF:08x}: {exc!r}")
    return [], {}
