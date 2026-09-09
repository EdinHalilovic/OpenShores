
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.gear_entry import _gear_cid_of
from openshores.gameplay.hazards import _is_in_gravity
from openshores.gameplay.use_action_tables import ENV_SUIT_BODY_CIDS

logger = get_logger(__name__)


def _wearing_env_suit(gear) -> bool:
    try:
        for _e in (gear or ()):
            if (int(_e[0]) & 0x0F) != 6:
                continue
            if _gear_cid_of(_e) in ENV_SUIT_BODY_CIDS:
                return True
    except Exception as exc:
        logger.debug(f'Env-suit check gave up on a malformed gear list: {exc!r}.')
    return False


def _apply_stamina_modifiers(auid, rate: int, *, gear,
                             tock_state, live_avatars) -> int:
    rate = int(rate)
    if _wearing_env_suit(gear):
        rate -= 1
    in_gravity = _is_in_gravity(auid, tock_state=tock_state,
                                live_avatars=live_avatars)
    if not in_gravity:
        rate += 2
    return rate
