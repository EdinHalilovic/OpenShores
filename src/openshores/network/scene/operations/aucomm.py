
from __future__ import annotations

from openshores.core.config import Deployment
from openshores.core.logging import get_logger
from openshores.gameplay.dispatch import register
from openshores.protocol.atoms.aucomm import (
    SUBTYPE_ACCEPT_TELEPORT,
    SUBTYPE_INVITE_TELEPORT,
    _build_accept_teleport_ack,
    _parse_aucomm_invite_teleport_tail,
    _parse_base_header,
)
from openshores.protocol.atoms.person import _build_daperson_xform_update
from openshores.protocol.auid import _as_auid
from openshores.protocol.encryption import au_crypt, net_crypt_key
from openshores.protocol.framing import write_framed
from openshores.protocol.scene_init import build_scene_world_redirect
from openshores.protocol.stream import QDS
from openshores.world.chat_writer import _chat_only_writer

logger = get_logger(__name__)


@register(0x0A)
async def handle_0x0A_aucomm(
    session,
    payload: bytes,
    *,
    live_avatars: dict,
    _broadcast_to_peers,
    _stamina_byte,
    agent_bits_for,
) -> None:
    if len(payload) < 1 + 4 + 1:
        logger.warning("A 0x0A AuComm frame from conn#%s is too short to "
                       "carry an envelope; dropped. first16=%s",
                       getattr(session, 'conn_n', '?'),
                       payload[:16].hex(' '))
        return

    s = QDS(payload)
    op_byte = s.read_u8()
    if op_byte != 0x0A:
        logger.warning("A frame whose first byte is 0x%02x reached the 0x0A "
                       "handler; dropped.", op_byte)
        return

    cipher_len = s.read_u32()
    if cipher_len == 0 or cipher_len > len(payload) - 5:
        logger.warning("A 0x0A AuComm frame declares cipherLen=%d inside a "
                       "%d-byte payload; dropped. first16=%s",
                       cipher_len, len(payload), payload[:16].hex(' '))
        return
    cipher = bytes(s.buf[s.pos:s.pos + cipher_len])

    session_lo = getattr(session, "aucomm_session_lo", 1)
    key = net_crypt_key(int(session_lo))
    plaintext = au_crypt(cipher, key)

    try:
        header = _parse_base_header(plaintext)
    except Exception as exc:
        logger.warning("The AuComm base header from conn#%s does not parse; "
                       "packet dropped: %r plaintext[:32]=%s",
                       getattr(session, 'conn_n', '?'), exc,
                       plaintext[:32].hex(' '))
        return

    sub = header["subType"]
    logger.debug("AuComm in from conn#%s subType=0x%02x flags=0x%02x "
                 "sender=0x%08x target=0x%08x plaintextLen=%d",
                 getattr(session, 'conn_n', '?'), sub, header['flags'],
                 header['senderId'], header['targetId'], len(plaintext))

    if sub in (SUBTYPE_INVITE_TELEPORT, SUBTYPE_ACCEPT_TELEPORT):
        try:
            tail = _parse_aucomm_invite_teleport_tail(plaintext, header)
        except Exception as exc:
            logger.warning("An AuCommInviteTeleport body does not parse; "
                           "packet dropped: %r plaintext[:32]=%s",
                           exc, plaintext[:32].hex(' '))
            return
        await _do_teleport(
            session, header, tail, subtype=sub,
            live_avatars=live_avatars,
            _broadcast_to_peers=_broadcast_to_peers,
            _stamina_byte=_stamina_byte,
            agent_bits_for=agent_bits_for)
        return

    logger.info("AuComm subType 0x%02x has no handler here; packet dropped. "
                "plaintext[:32]=%s", sub, plaintext[:32].hex(' '))


async def _do_teleport(session, header: dict, tail: dict,
                       *, subtype: int,
                       live_avatars: dict,
                       _broadcast_to_peers,
                       _stamina_byte,
                       agent_bits_for) -> None:
    await teleport_to_player(
        session,
        dest_auid=int(tail["destAuId"]) & 0xFFFFFFFF,
        dest_text=tail.get("destText") or "",
        source_label=f"aucomm subtype=0x{subtype:02x}",
        send_aucomm_ack=True,
        ack_target_id=int(header.get("senderId") or 0) & 0xFFFFFFFF,
        ack_session_lo=int(getattr(session, "aucomm_session_lo", 1)),
        live_avatars=live_avatars,
        _broadcast_to_peers=_broadcast_to_peers,
        _stamina_byte=_stamina_byte,
        agent_bits_for=agent_bits_for)


async def teleport_to_player(session, *, dest_auid: int,
                             dest_text: str = "",
                             source_label: str = "teleport",
                             send_aucomm_ack: bool = False,
                             ack_target_id: int = 0,
                             ack_session_lo: int = 1,
                             live_avatars: dict,
                             _broadcast_to_peers,
                             _stamina_byte,
                             agent_bits_for) -> bool:
    dest_auid = int(dest_auid) & 0xFFFFFFFF
    requester_auid = int(getattr(session, "player_auid", 0)) & 0xFFFFFFFF

    if dest_auid == 0:
        logger.debug("0x%08x asked to teleport to AuId 0; nothing to do.",
                     requester_auid)
        return False

    if dest_auid == requester_auid:
        logger.debug("0x%08x asked to teleport to itself; ignored.",
                     requester_auid)
        return False

    dest_entry = live_avatars.get(dest_auid)
    if not dest_entry:
        logger.info('0x%08x asked to teleport to 0x%08x, which is not among the %d avatar(s) on line.',
                    requester_auid, dest_auid, len(live_avatars))
        return False

    dest_xyz = dest_entry.get("xyz")
    dest_parent_world = (dest_entry.get("parent_world")
                         or dest_entry.get("AP"))
    if dest_xyz is None or dest_parent_world is None:
        logger.warning("0x%08x carries an incomplete position. Xyz=%r parent_world=%r.",
                       dest_auid, dest_xyz, dest_parent_world)
        return False

    new_x = float(dest_xyz[0]) + 1.5
    new_y = float(dest_xyz[1])
    new_z = float(dest_xyz[2])
    dest_parent_world_int = _as_auid(dest_parent_world)

    cur_parent_world_int = (int(session.parent_world_auid)
                            & 0xFFFFFFFF
                            if session.parent_world_auid else 0)

    logger.info("0x%08x teleports to 0x%08x (name=%r) on parent_world "
                "0x%08x at (%.1f,%.1f,%.1f), source=%s",
                requester_auid, dest_auid, dest_text, dest_parent_world_int,
                new_x, new_y, new_z, source_label)

    session.mark_position_dirty(new_x, new_y, new_z,
                                parent_world=dest_parent_world_int)

    own_entry = live_avatars.get(requester_auid)
    if isinstance(own_entry, dict):
        own_entry["xyz"] = (new_x, new_y, new_z)
        own_entry["parent_world"] = dest_parent_world_int

    cross_world = (cur_parent_world_int != 0
                   and dest_parent_world_int != cur_parent_world_int)

    if cross_world:
        await _push_world_redirect(
            session, dest_parent_world_int)

    _bits = agent_bits_for(requester_auid)
    daperson_pkt = _build_daperson_xform_update(
        player_auid=requester_auid,
        parent_auid=dest_parent_world_int,
        x=new_x, y=new_y, z=new_z,
        agent_bits=_bits,
        _stamina_byte=_stamina_byte)
    await write_framed(session.writer, daperson_pkt)
    logger.debug("0x12 DaPerson (parent+xform) sent, %d byte(s).",
                 len(daperson_pkt))

    n = await _broadcast_to_peers(daperson_pkt, live_avatars)
    logger.debug("The move went out to %d peer(s).", n)

    if send_aucomm_ack:
        ack_pkt = _build_accept_teleport_ack(
            sender_id=requester_auid,
            sender_name=session.avatar_name or "",
            target_id=ack_target_id,
            dest_auid=dest_auid,
            dest_text=dest_text,
            session_lo=ack_session_lo)
        _ack_entry = live_avatars.get(int(requester_auid) & 0xFFFFFFFF)
        _ack_w = (_chat_only_writer(_ack_entry)
                  if _ack_entry else None)
        if _ack_w is None:
            logger.warning('0x%08x has no chat channel, so its 0x9D AcceptTeleport ack is skipped.', requester_auid)
        else:
            await write_framed(_ack_w, ack_pkt)
            logger.debug("0x9D AcceptTeleport ack sent on the chat channel, "
                         "%d byte(s).", len(ack_pkt))

    return True


async def _push_world_redirect(session, new_parent_world: int) -> None:
    deployment = Deployment.from_env()
    pkt = build_scene_world_redirect(
        server_name=deployment.public_host,
        port=deployment.scene_port,
        world_state=2,
        account_id_lo=int(new_parent_world) & 0xFFFFFFFF,
        account_id_hi=0,
        extra=0)
    await write_framed(session.writer, pkt)
    logger.debug("0x22 world-redirect (cross-sector) sent, new_parent="
                 "0x%08x, %d byte(s).", new_parent_world, len(pkt))
