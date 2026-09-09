
from __future__ import annotations

from openshores.core.config import (
    DEFAULT_CITY_CYCLE_SECONDS as CITY_CYCLE_INTERVAL_SEC,
)
from openshores.core.logging import get_logger
from openshores.gameplay import manufacturing as _mf
from openshores.gameplay.city_seed import _manufacturing_procs
from openshores.gameplay.industry_econ import _selected_output_per_worker

logger = get_logger(__name__)

_OPW_CACHE = {}


def _industry_output_per_worker(industry_id, kind, out_cid, mpids=None):
    chosen = _selected_output_per_worker(mpids, kind, out_cid)
    if chosen is not None:
        return chosen
    if kind not in ("food", "air", "power"):
        return 0
    key = (int(industry_id), kind)
    if key in _OPW_CACHE:
        return _OPW_CACHE[key]
    val = 0
    procs = _manufacturing_procs()
    if procs:
        try:
            cid = None if kind == "food" else out_cid
            val = int(_mf.output_per_worker(
                industry_id, procs, commodity=cid,
                seconds=CITY_CYCLE_INTERVAL_SEC))
        except Exception as exc:
            logger.warning(f"[city-sim] yield lookup failed for industry "
                           f"0x{int(industry_id):02x}: {exc!r}")
            val = 0
    _OPW_CACHE[key] = val
    return val
