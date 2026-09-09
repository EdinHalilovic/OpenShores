
from __future__ import annotations

import struct

from openshores.core.logging import get_logger
from openshores.database.repositories.agent import is_walkable_globe
from openshores.network.agent import teleport_to_world
from openshores.network.chat_binding import _chat_writer_auid
from openshores.network.scene.operations.aucomm import teleport_to_player
from openshores.world.registry import session_for_writer

logger = get_logger(__name__)


async def handle_teleport_to_player(
        payload: bytes, writer, _bound_auid: int, *,
        _live_avatars: dict, _PENDING_CHAT_AUIDS: list, conn,
        agent_bits: dict, agent_rank: dict, pb2_last_cursor: dict,
        manifest_suppress: set, force_scene_manifest_push,
        peer_upright_euler, _stamina_byte, retarget_bundle_to_avatar,
        broadcast_to_peers, _broadcast_to_peers, agent_bits_for) -> None:
    if len(payload) < 7:
        logger.warning(f"0xBE short frame "
                       f"len={len(payload)} hex={payload.hex()}")
        return
    try:
        target_auid = struct.unpack(
            ">I", payload[1:5])[0]
        with_ride = payload[5]
        is_summon = payload[6]
    except Exception as _be:                            # noqa: BLE001
        logger.warning(f"0xBE decode error: {_be!r}")
        return
    logger.info(f"0xBE TeleportToPlayer "
                f"target=0x{target_auid:08x} "
                f"withRide={with_ride} isSummon={is_summon}")

    _req_sess = session_for_writer(_live_avatars, writer)
    if _req_sess is None:
        _auid = _chat_writer_auid(
            writer, live_avatars=_live_avatars,
            _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS)
        _entry = (_live_avatars.get(int(_auid))
                  if _auid else None) or {}
        _req_sess = _entry.get("session")
    if _req_sess is None:
        logger.warning("0xBE no session for chat "
                       "writer; dropping")
        return

    try:
        _tp_ok = await teleport_to_player(
            _req_sess,
            dest_auid=target_auid,
            dest_text="",
            source_label=(
                f"chat-0xBE"
                f" withRide={with_ride}"
                f" isSummon={is_summon}"),
            send_aucomm_ack=False,
            live_avatars=_live_avatars,
            _broadcast_to_peers=_broadcast_to_peers,
            _stamina_byte=_stamina_byte,
            agent_bits_for=agent_bits_for)
    except Exception as _te:                            # noqa: BLE001
        logger.warning(f"0xBE teleport failed: {_te!r}")
        _tp_ok = False
    if not _tp_ok:
        try:
            _actor_tp = _chat_writer_auid(
                writer, live_avatars=_live_avatars,
                _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS) or _bound_auid
            if _actor_tp and await is_walkable_globe(conn, target_auid):
                logger.info(f"0xBE dest 0x{target_auid:08x} is a world. Cross-system teleport")
                await teleport_to_world(
                    conn, _live_avatars, agent_bits, agent_rank,
                    _actor_tp, target_auid,
                    label="agent:chat-0xBE",
                    pb2_last_cursor=pb2_last_cursor,
                    manifest_suppress=manifest_suppress,
                    force_scene_manifest_push=force_scene_manifest_push,
                    peer_upright_euler=peer_upright_euler,
                    _stamina_byte=_stamina_byte,
                    retarget_bundle_to_avatar=retarget_bundle_to_avatar,
                    broadcast_to_peers=broadcast_to_peers)
        except Exception as _wte:                       # noqa: BLE001
            logger.warning(f"0xBE world-teleport failed: "
                           f"{_wte!r}")
