
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.journal import get_queue
from openshores.gameplay.burden import _can_carry
from openshores.gameplay.forage.say_name import _item_say_name
from openshores.gameplay.gear_slots import _add_gear_item
from openshores.gameplay.worldgen import zone_resources as _zrq
from openshores.network.flag_spawn import spawn_world_flag
from openshores.network.forage_notify import _forage_notify
from openshores.protocol.atoms.gear import _pack_au_gear
from openshores.protocol.atoms.item_seed import _pack_auitem_seed_body
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


_FORAGE_DEFAULT_CID = 130
_FORAGE_QUALITY = 0x3D
_FORAGE_TYPEID = 0x01
_FORAGE_REJECT_CIDS = frozenset({6, 7, 8, 9, 28, 77, 82, 104, 132, 133, 231})
_FORAGE_REJECT_RANGES = ((384, 511),)


async def _execute_forage(target_world_auid, action=0, arg=0,
                          actor_auid=0, *, _live_avatars, _tock_state,
                          _get_augear, _DROPPED_ITEMS, _DYNAMIC_SCENE_AUIDS,
                          alloc_daitem_auid, _person_zone, USE_FOOD_CIDS,
                          _build_augear_only_daperson_update):
    if not actor_auid:
        logger.warning('[forage] no actor auid; aborting')
        return False
    actor_int = int(actor_auid) & 0xFFFFFFFF
    actor_bytes = actor_int.to_bytes(4, 'big')
    actor_entry = _live_avatars.get(actor_int) or {}
    actor_writer = actor_entry.get('writer')
    if actor_writer is None or actor_writer.is_closing():
        logger.warning('[forage] no live scene writer for actor 0x%08x'
                       % actor_int)
        return False
    actor_augear = _get_augear(actor_int)

    cid = int(arg) & 0x7FFF
    is_fruit = bool((int(arg) >> 15) & 0x1)
    if cid == 0:
        cid = _FORAGE_DEFAULT_CID & 0xFFFF
    if cid == 0x145:
        _default = _FORAGE_DEFAULT_CID & 0xFFFF
        logger.warning('[forage] arg cid=0x145 is reserved (Forage Specimen); '
                       'rejecting and falling back to cid=%d' % _default)
        cid = _default
    _bad = cid in _FORAGE_REJECT_CIDS or any(
        _lo <= cid <= _hi for _lo, _hi in _FORAGE_REJECT_RANGES)
    if _bad:
        _default = _FORAGE_DEFAULT_CID & 0xFFFF
        logger.warning("[forage] cid=%d (0x%x) is in the reject set (client-side commodity-cache bug, typically resolves after first drop); falling back to cid=%d" % (
                           cid, cid, _default))
        cid = _default
    sub_idx = int(action) & 0xFF

    _zone = None
    try:
        _zone = await _person_zone(actor_int, int(target_world_auid))
    except Exception as exc:                            # noqa: BLE001
        logger.warning(f'[forage] zone lookup failed: {exc!r}')
    _forage_q = _FORAGE_QUALITY & 0xFF
    if _zone is not None:
        try:
            _zq = int(_zrq.quality(_zone, cid))
        except Exception as exc:                        # noqa: BLE001
            logger.warning(f'[forage] zone quality lookup failed: {exc!r}')
            _zq = 0
        if _zq:
            logger.debug('[forage] zone quality for cid=%d is %d (pinned default was '
                         '%d)' % (cid, _zq, _forage_q))
            _forage_q = _zq & 0xFF
        else:
            logger.debug('[forage] cid=%d has no AuZoneResource::Quality entry; '
                         'keeping default Q%d' % (cid, _forage_q))


    forage_type = _FORAGE_TYPEID & 0xFF
    body = _pack_auitem_seed_body(
        typeId=forage_type,
        cid=cid,
        byte14=sub_idx if sub_idx else 5,
        quality=_forage_q,
        name='',
        flora_dna=None,
        for_world=False,
    )

    _over_burden = False
    try:
        _fg_dna = (_tock_state.get(actor_int) or {}).get('dna')
        _ok_weight, _why_weight = _can_carry(_fg_dna, actor_augear, cid, 1)
        _over_burden = not _ok_weight
    except Exception as exc:                            # noqa: BLE001
        logger.warning(f'[forage] burden check failed: {exc!r}')
    if _over_burden:
        _parent = int(target_world_auid) & 0xFFFFFFFF
        _dropped = None
        try:
            _dropped = await spawn_world_flag(
                actor_int, _parent, flag_cid=int(cid),
                quality=int(_forage_q), alloc_daitem_auid=alloc_daitem_auid,
                _tock_state=_tock_state, _live_avatars=_live_avatars,
                _DROPPED_ITEMS=_DROPPED_ITEMS,
                _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
        except Exception as exc:                        # noqa: BLE001
            logger.error(f'[forage] over-burden drop err: {exc!r}')
        logger.info("[forage] OVER BURDEN cid=%d (%s). Foraged and dropped it (Thought: 'Foraged %%1 and dropped it. No room to carry %%1.')"
                    % (cid, _why_weight))
        _say = _item_say_name(cid, _forage_q, USE_FOOD_CIDS=USE_FOOD_CIDS)
        await _forage_notify(
            actor_int,
            f'Foraged {_say} and dropped it. '
            f'No room to carry {_say}.',
            live_avatars=_live_avatars)
        return _dropped is not None

    dest_slot, new_sub = _add_gear_item(
        actor_augear, forage_type, bytes(body))
    if dest_slot is None:
        logger.info('[forage]   NO ROOM (gear full) cid=%d isFruit=%d sub=%d; '
                    "engine would emit Thought 'I have no room to carry %%1.'" % (
                        cid, int(is_fruit), sub_idx))
        await _forage_notify(
            actor_int,
            f'I have no room to carry '
            f'{_item_say_name(cid, _forage_q, USE_FOOD_CIDS=USE_FOOD_CIDS)}.',
            live_avatars=_live_avatars)
        return False
    logger.info('[forage] FORAGE actor=0x%08x world=0x%08x cid=%d '
                'isFruit=%d sub=%d -> slot=%d sub=%d (size=%dB)' % (
                    actor_int, int(target_world_auid), cid, int(is_fruit),
                    sub_idx, dest_slot, new_sub, len(body)))
    try:
        new_aug = _pack_au_gear([
            (e[0], e[1], e[2], e[3]) for e in actor_augear
        ])
        reply = _build_augear_only_daperson_update(actor_bytes, new_aug)
        await write_framed(actor_writer, reply)
        logger.debug('[forage]   -> AuGear refresh slot=%d sub=%d slots=%r '
                     'actor=0x%08x' % (
                         dest_slot, new_sub,
                         [(e[0], e[1]) for e in actor_augear],
                         actor_int))
    except Exception as exc:                            # noqa: BLE001
        logger.error('[forage]   AuGear push failed: %r' % (exc,))
        await _forage_notify(
            actor_int,
            f'I have no room to carry '
            f'{_item_say_name(cid, _forage_q, USE_FOOD_CIDS=USE_FOOD_CIDS)}.',
            live_avatars=_live_avatars)
        return False

    await _forage_notify(
        actor_int,
        f'Foraged {_item_say_name(cid, _forage_q, USE_FOOD_CIDS=USE_FOOD_CIDS)}.',
        live_avatars=_live_avatars)

    try:
        _queue = get_queue()
        _ok = _queue is not None and _queue.submit(
            'update_person_state', actor_int, inv=bytes(new_aug))
        if _ok:
            logger.debug('[forage]   SQL persisted inv len=%d for auid=0x%08x' % (
                len(new_aug), actor_int))
    except Exception as spe:                            # noqa: BLE001
        logger.error('[forage]   SQL persist failed: %r' % (spe,))
    return True
