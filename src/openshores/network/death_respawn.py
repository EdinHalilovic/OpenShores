
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.database.journal import get_queue
from openshores.network.corpse import _drop_player_corpse

logger = get_logger(__name__)


async def _run_death_respawn(writer, auid, *, max_hp: int = 46,
                             dead_pose: int = 0x12,
                             alive_pose: int = 0x24,
                             dead_pause_s: float = 3.0,
                             tock_state,
                             alloc_daitem_auid,
                             _live_avatars,
                             _DROPPED_ITEMS,
                             _DYNAMIC_SCENE_AUIDS,
                             world_atom_auids):
    auid = int(auid)
    entry = tock_state.setdefault(
        auid,
        {"pose": 0x24, "last_minute": -1, "last_hour": -1,
         "hp": max_hp, "stamina": 0x7F})
    if entry.get("dying"):
        return
    entry["dying"] = True
    old_hp = int(entry.get("hp", 0))
    try:
        await _drop_player_corpse(
            auid, alloc_daitem_auid=alloc_daitem_auid,
            _live_avatars=_live_avatars,
            _DROPPED_ITEMS=_DROPPED_ITEMS,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
            world_atom_auids=world_atom_auids)
    except Exception as exc:
        logger.error(f"[death]     corpse drop failed (non-fatal): {exc!r}")
    import time as _drr_t
    _t0 = _drr_t.monotonic()
    logger.info(
        f"[death]     t={_drr_t.strftime('%H:%M:%S', _drr_t.localtime())} "
        f"auid=0x{auid:08x} hp={old_hp} (pause {dead_pause_s:.1f}s)")
    try:
        await asyncio.sleep(float(dead_pause_s))
    except Exception:
        logger.debug(f"[death]     auid=0x{auid:08x} pause interrupted")
    entry["hp"] = int(max_hp)
    entry["pose"] = int(alive_pose) & 0xFF
    entry["dying"] = False
    logger.info(
        f"[respawn]   t={_drr_t.strftime('%H:%M:%S', _drr_t.localtime())} (+{_drr_t.monotonic() - _t0:.2f}s after death) auid=0x{auid:08x} -> hp={max_hp} (in-place.")
    logger.info(f"[respawn]   skipping pose write; bio-ticker live-push "
                f"will carry HP={max_hp} on next tick")
    try:
        import time as _rs_t
        _persist_kw = {"hp": max_hp,
                       "timeDeath": int(_rs_t.time() * 1000)}
        _queue = get_queue()
        if _queue is not None:
            _queue.submit("update_person_state", auid, **_persist_kw)
    except Exception as _rsq_e:
        logger.error(f"[respawn]   sql persist err: {_rsq_e!r}")


def _start_death_respawn(w, target_auid, *,
                         _ts_entry,
                         _SAVE,
                         tock_state,
                         alloc_daitem_auid,
                         _live_avatars,
                         _DROPPED_ITEMS,
                         _DYNAMIC_SCENE_AUIDS,
                         world_atom_auids) -> asyncio.Task:
    try:
        _drr_max_hp = int(
            _ts_entry.get("max_hp") or
            int(_SAVE.person_hit_points) or 46)
    except (ValueError, TypeError):
        _drr_max_hp = 46
    _drr_pause = 2.0
    return asyncio.create_task(
        _run_death_respawn(
            w, target_auid,
            max_hp=_drr_max_hp,
            dead_pose=0x12,
            alive_pose=0x24,
            dead_pause_s=_drr_pause,
            tock_state=tock_state,
            alloc_daitem_auid=alloc_daitem_auid,
            _live_avatars=_live_avatars,
            _DROPPED_ITEMS=_DROPPED_ITEMS,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
            world_atom_auids=world_atom_auids))
