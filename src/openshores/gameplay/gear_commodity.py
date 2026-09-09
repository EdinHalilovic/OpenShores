
from __future__ import annotations

from openshores.gameplay import gd_tables as _gd


def _pack_volume_for_cid(cid: int):
    try:
        row = _gd.load_commodities().get(int(cid) & 0xFFFF)
        return None if row is None else int(row.pack_volume)
    except Exception:
        return None


def _weight_for_cid(cid: int) -> float:
    try:
        row = _gd.load_commodities().get(int(cid) & 0xFFFF)
        return 0.0 if row is None else float(row.weight)
    except Exception:
        return 0.0


def _bits_wear_for_cid(cid: int):
    try:
        row = _gd.load_commodities().get(int(cid) & 0xFFFF)
        return None if row is None else int(row.bits_wear)
    except Exception:
        return None
