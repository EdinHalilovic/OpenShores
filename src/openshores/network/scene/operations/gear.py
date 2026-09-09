
from __future__ import annotations

from typing import Awaitable, Callable

from openshores.core.logging import get_logger
from openshores.database.journal import get_queue
from openshores.gameplay.dispatch import register
from openshores.protocol.atoms.gear import _pack_au_gear
from openshores.protocol.stream import QDS

logger = get_logger(__name__)


@register(0x60)
async def handle_0x60_move_gear_slot(
    session,
    payload: bytes,
    *,
    _push_augear_refresh_for: Callable[..., Awaitable[None]],
) -> None:
    s = QDS(payload)
    s.read_u8()

    src_slot = s.read_u8()
    src_sub = s.read_u8()
    flag = s.read_u8()
    dst_slot = s.read_u8()

    logger.debug("MoveGearItemToSlot src=(slot=%d, sub=%d) flag=%d "
                 "dst_slot=%d.", src_slot, src_sub, flag, dst_slot)

    _mv_auid = session.player_auid
    if _mv_auid == 0:
        logger.debug('Gear move arrived before this connection had an avatar.')
        return

    _mv_state = session.augear

    _mv_src_idx = -1
    for _i, _e in enumerate(_mv_state):
        if (len(_e) >= 2 and int(_e[0]) == int(src_slot)
                and int(_e[1]) == int(src_sub)):
            _mv_src_idx = _i
            break

    if _mv_src_idx == -1:
        logger.debug("Avatar 0x%08x carries nothing in slot %d sub %d; the "
                     "move is ignored.", _mv_auid, src_slot, src_sub)
        return

    _mv_entry = _mv_state[_mv_src_idx]

    _used_subs = {int(_e[1]) for _i2, _e in enumerate(_mv_state)
                  if _i2 != _mv_src_idx
                  and len(_e) >= 2
                  and int(_e[0]) == int(dst_slot)}
    _dst_sub = 0
    while _dst_sub in _used_subs and _dst_sub < 16:
        _dst_sub += 1

    _mv_entry[0] = int(dst_slot)
    _mv_entry[1] = _dst_sub
    logger.debug("Gear moved from slot %d sub %d to slot %d sub %d.",
                 src_slot, src_sub, dst_slot, _dst_sub)

    _aug_blob = _pack_au_gear(_mv_state)
    _queue = get_queue()
    _ok = _queue is not None and _queue.submit(
        "update_person_state", _mv_auid, inv=bytes(_aug_blob))
    if _ok:
        logger.debug("Gear queued for the database, %d byte(s) of inv.",
                     len(_aug_blob))

    await _push_augear_refresh_for(_mv_auid, log_prefix="move")
