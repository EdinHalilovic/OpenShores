
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.forage.quality import _QUALITY_DESC
from openshores.gameplay.gd_tables import commodity_names as _cn

logger = get_logger(__name__)


def _quality_desc(q: int) -> str:
    q = int(q) & 0xFF
    for thr, name in _QUALITY_DESC:
        if thr <= q:
            return name
    return '?Qual'


def _forage_cid_name(cid: int, *, USE_FOOD_CIDS: dict) -> str:
    try:
        nm = _cn().get(int(cid))
        if nm:
            return str(nm)
    except Exception as exc:
        logger.warning("GD commodity name lookup for cid %r raised: %r",
                       cid, exc)
    try:
        ent = USE_FOOD_CIDS.get(int(cid))
        if ent:
            return str(ent[0])
    except Exception as exc:
        logger.warning("Food registry lookup for cid %r raised: %r",
                       cid, exc)
    return f'item {int(cid)}'
