
from __future__ import annotations

import struct

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.repositories import chat_log
from openshores.database.repositories.person import _lookup_person_by_auid
from openshores.gameplay.chat_range import _chat_passes_range
from openshores.protocol.atoms.aucomm import (
    CHAT_CHANNEL_TABLE,
    CHAT_RANGE_NAMES,
    CHAT_SCOPE_HAS_DATA,
    build_chat_aucomm_v4,
)
from openshores.protocol.framing import write_framed
from openshores.world.chat_writer import _chat_only_writer

logger = get_logger(__name__)


async def _broadcast_AuCommChat(msg, sender_session_auid, *,
                                conn: asyncpg.Connection,
                                _live_avatars,
                                pool) -> None:
    actor_int = int(sender_session_auid) & 0xFFFFFFFF
    actor_lookup = await _lookup_person_by_auid(conn, actor_int) or {}
    sender_name = actor_lookup.get('name') or msg.get('sender_name') or 'Unknown'
    text = msg.get('text', '')
    channel = msg.get('channel', 'Galaktika')
    scope = int(msg.get('scope', 5))
    cur_range = int(msg.get('cur_range', 0))
    max_range = int(msg.get('max_range', 0))
    aux = int(msg.get('aux', 0))
    galaxy = int(msg.get('galaxy', 0))
    has_galaxy = bool(msg.get('has_galaxy'))
    logger.debug('[chat-recv] %s -> %s (scope=%d): %r' % (
        sender_name, channel, scope, text))
    flags = int(msg.get('raw_flags', 0)) & 0xFF
    if max_range or cur_range:
        flags |= 0x40
    if scope in CHAT_SCOPE_HAS_DATA:
        flags |= 0x80
    if channel in CHAT_CHANNEL_TABLE:
        channel_index = CHAT_CHANNEL_TABLE.index(channel)
    else:
        channel_index = CHAT_CHANNEL_TABLE.index('Galaktika')
    text_bytes = text[:256].encode('utf-16-be')
    tail = struct.pack('>i', len(text_bytes)) + text_bytes
    range_byte = ((max_range & 0x0F) << 4) | (cur_range & 0x0F)
    has_range = bool(flags & 0x40)
    sender_entry = _live_avatars.get(actor_int) or {}
    sender_xyz = sender_entry.get('xyz')
    _members = []
    for _a, _e in _live_avatars.items():
        _has_chat = _e.get('chat_writer') is not None
        _members.append('0x%08x:%s%s' % (
            _a, _e.get('name', '?'),
            '+chat' if _has_chat else '-chat'))
    logger.debug('[chat-recv] live_avatars: %s' % (_members,))
    delivered = 0
    skipped_oor = 0
    _sender_entry_diag = _live_avatars.get(actor_int) or {}
    logger.debug('[chat-echo] sender 0x%08x %r: chat_writer=%s scene_writer=%s' % (
        actor_int,
        _sender_entry_diag.get('name', '?'),
        ('bound' if _sender_entry_diag.get('chat_writer') is not None else 'MISSING'),
        ('open' if (_sender_entry_diag.get('writer') and
                     not _sender_entry_diag['writer'].is_closing()) else 'closed'),
    ))
    for peer_auid, peer_entry in list(_live_avatars.items()):
        if scope == 14 and peer_auid != actor_int:
            continue
        peer_writer = peer_entry.get('writer')
        if peer_writer is None or peer_writer.is_closing():
            continue
        if has_range and peer_auid != actor_int:
            peer_xyz = peer_entry.get('xyz')
            if not _chat_passes_range(max_range, sender_xyz, peer_xyz):
                skipped_oor += 1
                continue
        _is_self = (peer_auid == actor_int)
        target_writer = _chat_only_writer(peer_entry)
        if target_writer is None:
            if _is_self:
                logger.warning("[chat-echo] self-echo skipped: no chat channel yet (the scene socket is not a safe fallback)")
            continue
        try:
            _orig_target = int(msg.get('target_auid', 0))
            if _is_self:
                _send_target = _orig_target
            else:
                _send_target = int(peer_auid)
            pkt = build_chat_aucomm_v4(
                type_byte=0x29,
                body_after_parent=tail,
                sender_auid_int=actor_int,
                sender_name=sender_name,
                target_auid_int=_send_target,
                channel_index=channel_index,
                flags_byte=flags,
                range_byte=range_byte,
                scope=scope,
                aux_i32=aux,
            )
            await write_framed(target_writer, pkt)
            delivered += 1
            if _is_self:
                logger.debug("[chat-echo] sent self-echo to 0x%08x via %s (target_auid=0x%08x, %dB)" % (
                                 peer_auid,
                                 ('chat' if peer_entry.get('chat_writer')
                                   is target_writer else 'scene'),
                                 _send_target, len(pkt)))
        except Exception as exc:
            logger.warning('[chat-recv] peer push err auid=0x%08x: %r' % (
                peer_auid, exc))
    try:
        chat_log.record_soon(pool, channel, actor_int, sender_name, text)
    except Exception:
        logger.debug("Chat history append skipped for %r" % (channel,))
    if has_range:
        _rname = (CHAT_RANGE_NAMES[max_range]
                  if 0 <= max_range < len(CHAT_RANGE_NAMES) else '?')
        logger.debug('[chat-recv] delivered to %d peer(s) '
                     '(skipped %d out-of-range, range=%s)' % (
                         delivered, skipped_oor, _rname))
    else:
        logger.debug('[chat-recv] delivered to %d peer(s)' % delivered)
