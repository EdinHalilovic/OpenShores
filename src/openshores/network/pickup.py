
from __future__ import annotations

import math as _m
import time as _t

from openshores.core.logging import get_logger
from openshores.database.journal import get_queue
from openshores.gameplay.burden import _can_carry
from openshores.gameplay.gear_slots import SLOT_NAMES, _add_gear_item
from openshores.protocol.atoms.gear import _pack_au_gear
from openshores.protocol.atoms.item import _extract_cid_from_auitem_body
from openshores.protocol.framing import write_framed
from openshores.world.session import Session

logger = get_logger(__name__)


_LAST_PICKUP_TS: float = 0.0


async def _execute_pickup(target_auid: int, source: str = "auto",
                          actor_auid: int = 0, *, _live_avatars,
                          _tock_state, _get_augear, _DROPPED_ITEMS,
                          _DYNAMIC_SCENE_AUIDS,
                          _build_augear_only_daperson_update) -> bool:
    global _LAST_PICKUP_TS

    if actor_auid:
        _actor_auid_int = int(actor_auid) & 0xFFFFFFFF
        _actor_auid_bytes = _actor_auid_int.to_bytes(4, "big")
    else:
        _actor_auid_int = 0
        _actor_auid_bytes = b""
        _live_sessions = [
            e["session"]
            for e in _live_avatars.values()
            if isinstance(e, dict) and isinstance(
                e.get("session"), Session)
            and e["session"].player_auid != 0]
        if len(_live_sessions) == 1:
            _sess = _live_sessions[0]
            _actor_auid_int = _sess.player_auid
            _actor_auid_bytes = _sess.player_auid_bytes
        if _actor_auid_int == 0:
            return False
    _actor_entry = _live_avatars.get(_actor_auid_int) or {}
    _actor_writer = _actor_entry.get("writer")
    if _actor_writer is None or _actor_writer.is_closing():
        logger.warning("[pickup-{}]   no live scene writer for actor "
                       "auid=0x{:08x}; aborting".format(
                           source, _actor_auid_int))
        return False
    _actor_augear = _get_augear(_actor_auid_int)
    if target_auid == 0 or target_auid not in _DROPPED_ITEMS:
        return False

    entry = _DROPPED_ITEMS[target_auid]

    range_check = source == "lookat"
    dist = -1.0
    if range_check:
        range_m = 30.0
        item_xyz = entry["xyz"]
        player_xyz = _actor_entry.get("xyz")
        if player_xyz is None:
            return False
        dx = item_xyz[0] - player_xyz[0]
        dy = item_xyz[1] - player_xyz[1]
        dz = item_xyz[2] - player_xyz[2]
        dist = _m.sqrt(dx * dx + dy * dy + dz * dz)
        if dist > range_m:
            return False

    try:
        _pk_cid = _extract_cid_from_auitem_body(bytes(entry['body'])) & 0xFFFF
        _pk_dna = (_tock_state.get(_actor_auid_int) or {}).get("dna")
        _pk_ok, _pk_why = _can_carry(_pk_dna, _actor_augear, _pk_cid, 1)
    except Exception as _pkb:                           # noqa: BLE001
        logger.warning(f"[pickup-{source}]   burden check failed: {_pkb!r}")
        _pk_ok, _pk_why = True, None
    if not _pk_ok:
        logger.info(f'[pickup-{source}]   TOO HEAVY target=0x{target_auid:08x} ({_pk_why}).')
        return False

    target_slot, new_sub = _add_gear_item(
        _actor_augear, int(entry['typeId']), bytes(entry['body']))
    if target_slot is None:
        logger.info(f"[pickup-{source}]   NO ROOM (gear full) target=0x{target_auid:08x} typeId=0x{entry['typeId']:02X}.")
        return False

    logger.info(f"[pickup-{source}] PICKUP target=0x{target_auid:08x} "
                f"dist={dist:.2f}m typeId=0x{entry['typeId']:02X} "
                f"-> slot={target_slot} ({SLOT_NAMES[target_slot]}) "
                f"sub={new_sub}")
    _LAST_PICKUP_TS = _t.monotonic()

    _DYNAMIC_SCENE_AUIDS.discard(target_auid)
    del _DROPPED_ITEMS[target_auid]
    try:
        _queue = get_queue()
        if _queue is not None:
            _queue.submit("dropped_item_delete", auid=target_auid)
    except Exception as _sqd:                           # noqa: BLE001
        logger.warning(f"[pickup-{source}]   SQL delete failed: {_sqd!r}")

    try:
        new_aug = _pack_au_gear([
            (e[0], e[1], e[2], e[3]) for e in _actor_augear
        ])
        reply = _build_augear_only_daperson_update(
            _actor_auid_bytes, new_aug)
        await write_framed(_actor_writer, reply)
        logger.debug(f"[pickup-{source}]   -> AuGear refresh slot={target_slot} "
                     f"sub={new_sub}; slots="
                     f"{[(e[0], e[1]) for e in _actor_augear]} "
                     f"actor=0x{_actor_auid_int:08x}")
    except Exception as _pse:                           # noqa: BLE001
        logger.error(f"[pickup-{source}]   AuGear push failed: {_pse!r}")
        return False

    try:
        _queue = get_queue()
        _player_auid_int = _actor_auid_int
        _ok = _queue is not None and _queue.submit(
            "update_person_state", _player_auid_int, inv=bytes(new_aug))
        if _ok:
            logger.debug(f"[pickup-{source}]   SQL: persisted inv "
                         f"len={len(new_aug)} for auid="
                         f"0x{_player_auid_int:08x}")
        else:
            logger.warning(f"[pickup-{source}]   SQL: inv persist returned "
                           f"False (player row may not exist)")
    except Exception as _spe:                           # noqa: BLE001
        logger.error(f"[pickup-{source}]   SQL inv persist failed: "
                     f"{_spe!r}")

    try:
        _builder = getattr(
            _actor_writer, "_scene_manifest_builder", None)
        if _builder:
            _manifest_pkt = _builder()
            await write_framed(_actor_writer, _manifest_pkt)
            logger.debug(f"[pickup-{source}]   -> scene 0x18 manifest re-emit "
                         f"({len(_manifest_pkt)}B; auid=0x{target_auid:08x} "
                         f"removed)")
        else:
            logger.warning(f'[pickup-{source}]   no scene manifest builder.')
    except Exception as _me:                            # noqa: BLE001
        logger.warning(f"[pickup-{source}]   manifest re-emit failed: {_me!r}")
    for _peer_auid, _peer_entry in list(_live_avatars.items()):
        if _peer_auid == _actor_auid_int:
            continue
        _pw = _peer_entry.get("writer")
        if _pw is None or _pw.is_closing():
            continue
        try:
            _pb = getattr(
                _pw, "_scene_manifest_builder", None)
            if _pb is None:
                continue
            _pm = _pb()
            await write_framed(_pw, _pm)
            logger.debug("[pickup-%s]   -> peer auid=0x%08x: "
                         "manifest re-emit (%dB; removed=0x%08x)" % (
                             source, _peer_auid, len(_pm), target_auid))
        except Exception as _pme:                       # noqa: BLE001
            logger.warning("[pickup-%s]   peer manifest err auid=0x%08x: "
                           "%r" % (source, _peer_auid, _pme))
    return True


_PICKUP_TARGET_FIRST_SEEN: dict = {}


async def _try_pickup_from_target_pin(target_auid: int, *, _live_avatars,
                                      _tock_state, _get_augear,
                                      _DROPPED_ITEMS, _DYNAMIC_SCENE_AUIDS,
                                      _build_augear_only_daperson_update
                                      ) -> bool:
    if target_auid == 0:
        _PICKUP_TARGET_FIRST_SEEN.clear()
        return False
    if target_auid not in _DROPPED_ITEMS:
        return False
    hold = 0.3
    debounce = 0.6
    now = _t.monotonic()
    if now - _LAST_PICKUP_TS < debounce:
        return False
    first = _PICKUP_TARGET_FIRST_SEEN.get(target_auid)
    if first is None:
        _PICKUP_TARGET_FIRST_SEEN[target_auid] = now
        return False
    if now - first < hold:
        return False
    _PICKUP_TARGET_FIRST_SEEN.pop(target_auid, None)
    return await _execute_pickup(
        target_auid, source="targetpin", _live_avatars=_live_avatars,
        _tock_state=_tock_state, _get_augear=_get_augear,
        _DROPPED_ITEMS=_DROPPED_ITEMS,
        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
        _build_augear_only_daperson_update=(
            _build_augear_only_daperson_update))
