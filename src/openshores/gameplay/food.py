
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.city_sim import food_commodity_ids

logger = get_logger(__name__)

_CORPSE_LINGER_S = 2.0

_AUTO_EAT_DEFAULT = False


def _hunger_i16(actor_auid: int, hunger: int, *, _tock_state) -> int:
    key = int(actor_auid) & 0xFFFFFFFF
    val = int(hunger) & 0x7FFF
    ent = _tock_state.get(key) or {}
    flag = ent.get("auto_eat")
    if flag is None:
        flag = _AUTO_EAT_DEFAULT
    return val | (0x8000 if flag else 0)


def _is_food_cid(cid, *, USE_FOOD_CIDS):
    return int(cid) & 0xFFFF in USE_FOOD_CIDS


def _food_value(cid, quality, *, USE_FOOD_CIDS):
    cid = int(cid) & 0xFFFF
    if cid not in USE_FOOD_CIDS:
        return 0
    _, nutrition = USE_FOOD_CIDS[cid]
    q = max(0, min(100, int(quality) & 0xFF))
    val = int(round((0.5 + q / 100.0) * nutrition)) + q // 10
    return max(1, val)


def _edible_cids():
    try:
        return food_commodity_ids()
    except Exception as exc:
        logger.warning("Edible-commodity table unreadable: %r", exc)
        return frozenset()
