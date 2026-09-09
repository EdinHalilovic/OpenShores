from __future__ import annotations

import functools

from openshores.core.logging import get_logger
from openshores.gameplay import damageable as _dmg
from openshores.gameplay.condition_states import _conditions_ailment_provider
from openshores.gameplay.natives import conversation as _nc
from openshores.gameplay.natives import village as _nat
from openshores.gameplay.natives.providers import _nc_msmr_provider
from openshores.gameplay.story_state import _purge_story_npc_state

logger = get_logger(__name__)


def _nc_hp_provider(player_auid: int, *,
                    tock_state):
    try:
        entry = tock_state.get(int(player_auid))
    except (TypeError, ValueError):
        return None
    if not entry:
        return None
    hp = entry.get("hp")
    max_hp = entry.get("max_hp")
    if hp is None or max_hp is None:
        return None
    return (int(hp), int(max_hp))


def _install_native_conversation_hooks(*,
                                       tock_state,
                                       condition_states,
                                       heal_hook) -> None:
    _nc.hp_provider = functools.partial(_nc_hp_provider,
                                        tock_state=tock_state)
    _nc.heal_hook = heal_hook
    _nc.msmr_provider = functools.partial(_nc_msmr_provider,
                                          tock_state=tock_state)
    _nc.ailment_provider = functools.partial(
        _conditions_ailment_provider,
        condition_states=condition_states,
        ailment_poison=_nc.AILMENT_POISON,
        ailment_disease=_nc.AILMENT_DISEASE,
        ailment_paralysis=_nc.AILMENT_PARALYSIS,
        ailment_acid=_nc.AILMENT_ACID)
    logger.info('[boot] native conversation hooks installed: hp_provider, heal_hook, msmr_provider, ailment_provider (bounty stays unwired.')


def _forget_npc_body(auid, *,
                     _DYNAMIC_SCENE_AUIDS: set) -> None:
    a = int(auid) & 0xFFFFFFFF
    _DYNAMIC_SCENE_AUIDS.discard(a)
    try:
        _purge_story_npc_state(a)
    except Exception as exc:
        logger.error("[carcass] story purge err: %r", exc)
    try:
        if a in (getattr(_nat, "_IDLE_BODIES", None) or {}):
            _nat.clear_idle_bodies([a])
            logger.info("[carcass] native 0x%08x idle body dropped", a)
    except Exception as exc:
        logger.error("[carcass] native purge err: %r", exc)
    try:
        _dmg.unregister(a)
    except Exception as exc:
        logger.error("[carcass] unregister err: %r", exc)
