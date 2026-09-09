
from __future__ import annotations

import traceback as _rtb
import traceback as _sttb

from openshores.core.logging import get_logger
from openshores.gameplay import damageable as _dmg
from openshores.gameplay import story_npc as _snpc
from openshores.gameplay import story_targoss as _story

logger = get_logger(__name__)

_STORY_UI_ON = True


def story_mark_pending(auid, *, _STORY_PENDING) -> None:
    try:
        _a = int(auid) & 0xFFFFFFFF
    except (TypeError, ValueError):
        logger.debug("[story] mark pending: auid %r is not an int", auid)
        return
    if _a:
        _STORY_PENDING.add(_a)
        logger.info("[story] avatar 0x%08x marked pending "
                    "(character created)", _a)


def _story_task_done(task, auid) -> None:
    try:
        if task.cancelled():
            logger.info("[story] 0x%08x: task CANCELLED", int(auid))
            return
        exc = task.exception()
    except Exception:
        logger.debug("[story] task for auid %r is not done", auid)
        return
    if exc is not None:
        logger.error("[story] 0x%08x: task failed: %r", int(auid), exc)
        _sttb.print_exception(type(exc), exc, exc.__traceback__)
    else:
        logger.info("[story] 0x%08x: task finished", int(auid))


def _stop_story_for_dead_npc(d) -> bool:
    if d is None or d.kind != _dmg.KIND_STORY:
        return False
    target = int(d.auid) & 0xFFFFFFFF
    stopped = False
    for _avatar, _s in list((getattr(_snpc, "_NPCS", None) or {}).items()):
        if (int(_s.get("auid") or 0) & 0xFFFFFFFF) == target:
            _story._DROPPED.add(int(_avatar) & 0xFFFFFFFF)
            stopped = True
    if stopped:
        logger.info('[story] narrator 0x%08x was killed.',
                    target)
    return stopped


def _purge_story_npc_state(auid) -> bool:
    target = int(auid) & 0xFFFFFFFF
    dropped = False
    for _k, _s in list((getattr(_snpc, "_NPCS", None) or {}).items()):
        if (int(_s.get("auid") or 0) & 0xFFFFFFFF) == target:
            _snpc._NPCS.pop(_k, None)
            dropped = True
    if dropped:
        logger.info('[corpse-sweep] story NPC 0x%08x state dropped.', target)
    return dropped


def _retire_task_done(task, auid) -> None:
    try:
        if task.cancelled():
            return
        exc = task.exception()
    except Exception:
        logger.debug("[carcass] retire task for auid %r is not done", auid)
        return
    if exc is not None:
        logger.error("[carcass] retire of 0x%08x failed: %r", int(auid), exc)
        _rtb.print_exception(type(exc), exc, exc.__traceback__)
