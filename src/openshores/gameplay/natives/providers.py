
from __future__ import annotations

from openshores.core.logging import get_logger

logger = get_logger(__name__)


def _person_sex(player_auid: int):
    raise NotImplementedError(
        "a_Person SQL moved out of gameplay.")


def _nc_msmr_provider(player_auid: int, *,
                      tock_state) -> str:
    sex = None
    try:
        entry = tock_state.get(int(player_auid)) or {}
        sex = entry.get("sex")
    except (TypeError, ValueError):
        return ""
    if sex is None:
        try:
            col = _person_sex(player_auid)
            if col is not None:
                sex = int(col)
        except Exception as exc:
            logger.debug(
                'Sex lookup for avatar 0x%08x failed: %r.',
                int(player_auid) & 0xFFFFFFFF, exc)
    if sex is None:
        return ""
    return "Mr" if int(sex) != 0 else "Ms"
