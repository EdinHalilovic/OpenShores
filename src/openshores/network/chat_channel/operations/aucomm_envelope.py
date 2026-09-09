
from __future__ import annotations

import struct

from openshores.core.logging import get_logger
from openshores.gameplay.natives.conversation import (
    on_hail,
    parse_hail_request,
    pick_addressee,
)
from openshores.network.chat_binding import _chat_writer_auid
from openshores.protocol.atoms.aucomm import _parse_AuCommChat, _q_uncompress
from openshores.protocol.encryption import au_crypt

logger = get_logger(__name__)


async def handle_aucomm_envelope(payload: bytes, peer, writer,
                                 _bound_auid: int, *,
                                 _live_avatars: dict,
                                 _PENDING_CHAT_AUIDS: list,
                                 AUCOMM_HANDLERS: dict,
                                 _broadcast_AuCommChat) -> None:
    try:
        if len(payload) < 9:
            raise ValueError('0x0A frame too short')
        clen = struct.unpack('>i', payload[5:9])[0]
        if clen < 0 or 9 + clen > len(payload):
            raise ValueError('0x0A clen out of range')
        cipher = payload[9:9 + clen]
        crypt_key = 0x6E32 & 0xFFFF
        compressed = au_crypt(cipher, crypt_key)
        plain = _q_uncompress(compressed)
        if not plain:
            raise ValueError('0x0A empty plaintext')
        type_byte = plain[0]
        logger.debug('[chat] <- %s 0x0A type=0x%02X plen=%d' % (
            peer, type_byte, len(plain)))
        if type_byte == 0x29:
            logger.debug('[chat-recv] plaintext_body_hex=%s' %
                         plain[1:].hex())
            msg = _parse_AuCommChat(plain[1:])
            if msg is not None:
                actor = _chat_writer_auid(
                    writer, live_avatars=_live_avatars,
                    _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS) or _bound_auid
                if not actor:
                    logger.warning('[chat-recv] no bound auid; '
                                   'cannot rebroadcast')
                else:
                    await _broadcast_AuCommChat(msg, actor)
        elif type_byte == 0x2B:
            logger.info("[chat-recv] 0x2B ChatChoice INBOUND from %s (unexpected, the story reply is a bare 0x7C, not an AuComm): %s"
                        % (peer, plain[1:24].hex()))
        elif type_byte == 0x3F:
            _hail_handled = False
            try:
                _hail = parse_hail_request(plain[1:])
                _hactor = _chat_writer_auid(
                    writer, live_avatars=_live_avatars,
                    _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS) or _bound_auid
                if (_hail is not None and _hactor
                        and _hail.get('channel') == 'Voice'):
                    _target = pick_addressee(_live_avatars, _hactor)
                    logger.info('[chat-recv] 0x3F Hello from 0x%08x '
                                'on Voice -> native %s'
                                % (_hactor,
                                   ('0x%08x' % _target) if _target
                                   else 'none in range'))
                    if _target is not None:
                        _pkts = on_hail(
                            _hactor, _target,
                            _hail.get('sender_name') or '',
                            env_atom_auid=_hail.get(
                                'target_auid', 0))
                        for _p in _pkts:
                            writer.write(_p)
                        if _pkts:
                            await writer.drain()
                            _hail_handled = True
                        logger.debug('[chat-recv]   sent %d packet(s)'
                                     % len(_pkts))
            except Exception as _hexc:                  # noqa: BLE001
                logger.warning('[chat-recv] 0x3F hail handler err: %r'
                               % (_hexc,))
            if not _hail_handled:
                logger.info('[chat-recv] 0x3F not answered by a native '
                            '(no villager in range, wrong channel, or '
                            'the feature is off)')
        else:
            _table = AUCOMM_HANDLERS or {}
            _entry = _table.get(type_byte)
            if _entry is not None:
                _name, _parser, _handler = _entry
                try:
                    parsed = _parser(plain[1:])
                    if parsed is None:
                        logger.warning("[chat] %s parse failed (type=0x%02X)" % (_name, type_byte))
                    else:
                        actor = _chat_writer_auid(
                            writer, live_avatars=_live_avatars,
                            _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS
                        ) or _bound_auid
                        if not actor:
                            logger.warning("[chat] %s dispatch skipped: no bound auid" % _name)
                        else:
                            await _handler(parsed, actor)
                except Exception as _heh:               # noqa: BLE001
                    logger.warning('[chat]   %s handler err: %r' % (
                        _name, _heh))
            else:
                logger.debug('[chat]   non-chat AuCommPacket type='
                             '0x%02X (no handler)' % type_byte)
    except Exception as exc:                            # noqa: BLE001
        logger.warning('[chat] 0x0A decrypt/dispatch err: %r '
                       'plen=%d hex=%s' % (
                           exc, len(payload), payload[:32].hex()))
