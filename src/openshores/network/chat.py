
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories import chat_log
from openshores.protocol.atoms.aucomm import (
    AUCOMM_TYPE_CHAT,
    AUCOMM_TYPE_CHAT_CONTINUED,
    CHAT_CHANNEL_SCOPE,
    CHAT_CHANNEL_TABLE,
    CHAT_TEXT_LIMIT,
    SYSTEM_CHANNEL,
    SYSTEM_SENDER_AUID,
    SYSTEM_SENDER_NAME,
    build_chat_aucomm_v4,
)
from openshores.protocol.framing import write_framed
from openshores.protocol.stream import QDS
from openshores.world.chat_writer import _chat_only_writer

logger = get_logger(__name__)


async def broadcast_system_message(live_avatars: dict, text: str, *,
                                   channel: str = SYSTEM_CHANNEL,
                                   sender_name: str = SYSTEM_SENDER_NAME,
                                   sender_auid: int = SYSTEM_SENDER_AUID,
                                   pool,
                                   ) -> int:
    if not text:
        return 0
    try:
        idx = CHAT_CHANNEL_TABLE.index(channel)
    except ValueError:
        logger.error("Announcement not sent: unknown channel %r. Known: %s.",
                     channel, ", ".join(CHAT_CHANNEL_TABLE))
        return 0
    scope = CHAT_CHANNEL_SCOPE[idx]
    type_byte = (AUCOMM_TYPE_CHAT if len(text) < CHAT_TEXT_LIMIT
                 else AUCOMM_TYPE_CHAT_CONTINUED)
    tail = QDS()
    tail.write_qstring(text)
    body = tail.getvalue()

    sent = 0
    for peer_auid, peer_entry in list(live_avatars.items()):
        w = _chat_only_writer(peer_entry)
        if w is None:
            continue
        try:
            if w.is_closing():
                continue
        except Exception:                               # noqa: BLE001
            pass
        try:
            pkt = build_chat_aucomm_v4(
                type_byte=type_byte, body_after_parent=body,
                sender_auid_int=int(sender_auid) & 0xFFFFFFFF,
                sender_name=sender_name,
                target_auid_int=int(peer_auid) & 0xFFFFFFFF,
                channel_index=idx, scope=scope)
            await write_framed(w, pkt)
            sent += 1
        except Exception as exc:                        # noqa: BLE001
            logger.warning(
                "System message not delivered to auid=0x%08x: %r",
                int(peer_auid) & 0xFFFFFFFF, exc)
    try:
        chat_log.record_soon(pool, channel, sender_auid, sender_name, text)
    except Exception:                                   # noqa: BLE001
        logger.debug("Chat history append skipped for %r", channel)
    _icon = ("ComputerEye"
             if (scope == 0x0E and int(sender_auid) & 0xFFFFFFFF == 1)
             else "Range*")
    logger.info("Announcement on %s (scope %d) as 0x%08x [%s] reached %d "
                "player(s): %r", channel, scope,
                int(sender_auid) & 0xFFFFFFFF, _icon, sent, text)
    return sent
