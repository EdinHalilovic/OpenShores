
from __future__ import annotations

import asyncio
import struct

from openshores.core.logging import get_logger
from openshores.gameplay.empire_office import classify_unhandled
from openshores.network.chat_binding import _chat_writer_auid
from openshores.network.chat_channel.operations import (
    aucomm_envelope,
    inventory,
    make_commodity,
    raw_frames,
    specie,
    teleport,
)
from openshores.network.session_reset import _signal_init_ack
from openshores.protocol.framing import read_framed
from openshores.world.registry import session_for_writer

logger = get_logger(__name__)


async def handle_chat(reader, writer, *,
                      _live_avatars: dict, _PENDING_CHAT_AUIDS: list,
                      _PLAYER_AUID: bytes, _DROPPED_ITEMS: dict,
                      _DYNAMIC_SCENE_AUIDS: set, _PARENT_WORLD_AUID, _SAVE,
                      _tock_state: dict, _CHAT_UNKNOWN_COUNTS: dict,
                      _CHAT_UNKNOWN_PRINT_FIRST_N: int,
                      _CHAT_UNKNOWN_PRINT_EVERY_N: int, conn,
                      _get_augear, _can_hold_item,
                      _build_augear_only_daperson_update,
                      _broadcast_AuCommChat, _veh_note_ground_radius,
                      on_chat_construction_op, on_chat_demolish,
                      alloc_daitem_auid, set_active_chat_writer,
                      AUCOMM_HANDLERS: dict,
                      CHAT_DIRECT_EMPIRE_HANDLERS: dict,
                      CHAT_DIRECT_HANDLERS_EMPIRE_MUTATIONS: dict,
                      CHAT_DIRECT_HANDLERS_AGENT: dict,
                      agent_bits: dict, agent_rank: dict,
                      pb2_last_cursor: dict, manifest_suppress: set,
                      force_scene_manifest_push, peer_upright_euler,
                      _stamina_byte, retarget_bundle_to_avatar,
                      broadcast_to_peers, _broadcast_to_peers,
                      agent_bits_for, CONTAINER_CIDS, CONTAINER_CAPACITIES,
                      USE_FOOD_CIDS) -> None:
    global _ACTIVE_CHAT_WRITER
    peer = writer.get_extra_info("peername")
    _announced_chat = False
    _ACTIVE_CHAT_WRITER = writer
    _bound_auid = _chat_writer_auid(
        writer, live_avatars=_live_avatars,
        _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS)
    if _bound_auid:
        if _announced_chat:
            logger.info("[chat] %s bound to player auid=0x%08x" % (
                peer, _bound_auid))
        _ent = _live_avatars.get(int(_bound_auid))
        if _ent is not None:
            _ent['chat_writer'] = writer
    else:
        if _announced_chat:
            logger.info("[chat] %s no scene peer found yet. Will retry on first packet" % (peer,))
    try:
        while True:
            try:
                payload = await read_framed(reader)
            except asyncio.IncompleteReadError:
                if _announced_chat:
                    logger.info(f"[chat] {peer} closed (incomplete read)")
                break
            if not payload:
                if _announced_chat:
                    logger.info(f"[chat] {peer} empty payload, closing")
                break
            if not _announced_chat:
                logger.info(f"[chat] {peer} CONNECTED. Chat channel established")
                if _bound_auid:
                    logger.info("[chat] %s bound to player auid=0x%08x" % (
                        peer, _bound_auid))
                _announced_chat = True
            _now_auid = _chat_writer_auid(
                writer, live_avatars=_live_avatars,
                _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS)
            if _now_auid and _now_auid != _bound_auid:
                if _bound_auid:
                    logger.info("[chat] %s chat writer re-bound 0x%08x -> 0x%08x "
                                "(avatar changed under an open chat socket)"
                                % (peer, _bound_auid, _now_auid))
                _bound_auid = _now_auid
            if _bound_auid:
                _ent_rb = _live_avatars.get(int(_bound_auid))
                if _ent_rb is not None and _ent_rb.get('chat_writer') is not writer:
                    _ent_rb['chat_writer'] = writer
                    logger.info("[chat] %s late-bound chat writer to auid=0x%08x"
                                % (peer, _bound_auid))
            op = payload[0]

            if op != 0xB3:
                _h = (op in CHAT_DIRECT_EMPIRE_HANDLERS) or op == 0x0A \
                    or op in (0x02, 0x06)
                logger.debug(
                    f"[chat-rx] op=0x{op:02X} len={len(payload)} "
                    f"handled={_h} hex={payload[:96].hex()}")

            if op == 0xB3:
                logger.debug(
                    f"[chat-0xB3 raw] len={len(payload)} {payload.hex()}")

            if op == 0x0B and len(payload) >= 13:
                try:
                    _ack_auid = struct.unpack_from(">I", payload, 9)[0]
                    _signal_init_ack(_ack_auid)
                except Exception as _acke:              # noqa: BLE001
                    logger.warning(f"[chat] 0x0B init-ack parse failed "
                                   f"(non-fatal): {_acke!r}")

            if op == 0x0A:
                await aucomm_envelope.handle_aucomm_envelope(
                    payload, peer, writer, _bound_auid,
                    _live_avatars=_live_avatars,
                    _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS,
                    AUCOMM_HANDLERS=AUCOMM_HANDLERS,
                    _broadcast_AuCommChat=_broadcast_AuCommChat)
                continue

            if op in (0x02, 0x06):
                await raw_frames.handle_construction_op(
                    payload, op, peer, writer, _bound_auid,
                    _live_avatars=_live_avatars,
                    _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS,
                    set_active_chat_writer=set_active_chat_writer,
                    on_chat_construction_op=on_chat_construction_op,
                    on_chat_demolish=on_chat_demolish)
                continue

            if op in (0x7C, 0x7D, 0x7E, 0x7F):
                await raw_frames.handle_story_op(
                    payload, op, peer, writer, _bound_auid,
                    _live_avatars=_live_avatars,
                    _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS)
                continue

            try:
                if await raw_frames.dispatch_chat_direct(
                        payload, op, peer, writer, _bound_auid,
                        _live_avatars=_live_avatars,
                        _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS,
                        set_active_chat_writer=set_active_chat_writer,
                        CHAT_DIRECT_EMPIRE_HANDLERS=(
                            CHAT_DIRECT_EMPIRE_HANDLERS),
                        CHAT_DIRECT_HANDLERS_EMPIRE_MUTATIONS=(
                            CHAT_DIRECT_HANDLERS_EMPIRE_MUTATIONS),
                        CHAT_DIRECT_HANDLERS_AGENT=(
                            CHAT_DIRECT_HANDLERS_AGENT)):
                    continue
            except Exception as _edie:                  # noqa: BLE001
                logger.warning(f"[chat]   empire-admin dispatch err on op="
                               f"0x{op:02X}: {_edie!r}")

            try:
                if op in inventory._INV_OPS:
                    await inventory.handle_inventory_op(
                        payload, op, peer, writer,
                        _live_avatars=_live_avatars,
                        _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS,
                        _PLAYER_AUID=_PLAYER_AUID,
                        _DROPPED_ITEMS=_DROPPED_ITEMS,
                        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                        _PARENT_WORLD_AUID=_PARENT_WORLD_AUID,
                        _SAVE=_SAVE, _tock_state=_tock_state,
                        alloc_daitem_auid=alloc_daitem_auid,
                        _get_augear=_get_augear,
                        _can_hold_item=_can_hold_item,
                        _build_augear_only_daperson_update=(
                            _build_augear_only_daperson_update),
                        agent_bits_for=agent_bits_for,
                        CONTAINER_CIDS=CONTAINER_CIDS,
                        CONTAINER_CAPACITIES=CONTAINER_CAPACITIES,
                        USE_FOOD_CIDS=USE_FOOD_CIDS)
                elif op == 0xC2:
                    await make_commodity.handle_make_commodity(
                        payload, writer,
                        _live_avatars=_live_avatars,
                        _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS,
                        _PLAYER_AUID=_PLAYER_AUID,
                        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                        _tock_state=_tock_state, conn=conn,
                        _get_augear=_get_augear,
                        _build_augear_only_daperson_update=(
                            _build_augear_only_daperson_update),
                        _veh_note_ground_radius=_veh_note_ground_radius)

                elif op == 0xBE:
                    await teleport.handle_teleport_to_player(
                        payload, writer, _bound_auid,
                        _live_avatars=_live_avatars,
                        _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS,
                        conn=conn, agent_bits=agent_bits,
                        agent_rank=agent_rank,
                        pb2_last_cursor=pb2_last_cursor,
                        manifest_suppress=manifest_suppress,
                        force_scene_manifest_push=force_scene_manifest_push,
                        peer_upright_euler=peer_upright_euler,
                        _stamina_byte=_stamina_byte,
                        retarget_bundle_to_avatar=retarget_bundle_to_avatar,
                        broadcast_to_peers=broadcast_to_peers,
                        _broadcast_to_peers=_broadcast_to_peers,
                        agent_bits_for=agent_bits_for)

                elif op == 0xB3:
                    await specie.handle_specie_requested(
                        payload, writer, _DROPPED_ITEMS=_DROPPED_ITEMS)

                else:
                    n = _CHAT_UNKNOWN_COUNTS.get(op, 0) + 1
                    _CHAT_UNKNOWN_COUNTS[op] = n
                    if n <= _CHAT_UNKNOWN_PRINT_FIRST_N:
                        logger.info(f"[chat] <- {peer} op=0x{op:02X} "
                                    f"len={len(payload)}: {payload.hex()}")
                        logger.info(f"[chat]   unknown opcode 0x{op:02X}, "
                                    f"no handler yet (occurrence #{n})")
                        _hint = classify_unhandled(op, payload[1:])
                        logger.info(f"[chat]   [empire?] op=0x{op:02X}: {_hint}")
                    elif n % _CHAT_UNKNOWN_PRINT_EVERY_N == 0:
                        logger.info(f"[chat]   opcode 0x{op:02X} seen {n}× "
                                    f"(suppressed; len={len(payload)})")
                    _cp_sess = session_for_writer(
                        _live_avatars, writer)
                    _cp_lookat = (_cp_sess.lookat_target_auid
                                  if _cp_sess is not None else 0)
                    if (_cp_lookat
                            and _cp_lookat in _DROPPED_ITEMS):
                        logger.info(f"[chat-probe-near-drop] op=0x{op:02X} "
                                    f"lookat=0x{_cp_lookat:08x} "
                                    f"len={len(payload)}: {payload.hex()}")
            except Exception as _he:                    # noqa: BLE001
                logger.warning(f"[chat]   handler error on 0x{op:02X}: {_he!r}")
    except Exception as _outer_exc:                     # noqa: BLE001
        logger.warning(f"[chat] handler exit: {_outer_exc!r}")
    finally:
        try:
            _bound_for_cleanup = (
                getattr(writer, "_player_auid", None)
                or _bound_auid)
            if _bound_for_cleanup:
                _ent_cleanup = _live_avatars.get(int(_bound_for_cleanup))
                if (_ent_cleanup is not None
                        and _ent_cleanup.get("chat_writer") is writer
                        and _announced_chat):
                    logger.info(f"[chat] {peer} closed; leaving chat_writer "
                                f"slot in place for auid=0x"
                                f"{int(_bound_for_cleanup):08x} (broadcast "
                                f"falls back to scene on next push)")
                if int(_bound_for_cleanup) in _PENDING_CHAT_AUIDS:
                    _PENDING_CHAT_AUIDS.remove(
                        int(_bound_for_cleanup))
                if int(_bound_for_cleanup) in _PENDING_CHAT_AUIDS:
                    _PENDING_CHAT_AUIDS.remove(
                        int(_bound_for_cleanup))
        except Exception as _ce:                        # noqa: BLE001
            logger.warning(f"[chat] {peer} cleanup err (non-fatal): {_ce!r}")
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as _close_exc:                 # noqa: BLE001
            logger.debug(f"[chat] {peer} close err: {_close_exc!r}")
        if _announced_chat:
            logger.info(f"[chat] {peer} disconnected")
