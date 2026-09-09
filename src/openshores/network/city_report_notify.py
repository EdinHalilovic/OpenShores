
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.protocol.atoms.aucomm import build_chat_aucomm_v4
from openshores.protocol.framing import write_framed
from openshores.protocol.stream import QDS
from openshores.world.chat_writer import _chat_only_writer

logger = get_logger(__name__)


async def _notify_city_report(cauid: int, info: dict, text: str, *,
                              live_avatars: dict):
    if not text:
        return
    sender_name = (info.get("name") or f"City 0x{cauid & 0xFFFFFFFF:08x}")
    tail = QDS()
    tail.write_qstring(text)
    body = tail.getvalue()
    sent = 0
    for peer_auid, peer_entry in list(live_avatars.items()):
        w = _chat_only_writer(peer_entry)
        if w is None:
            continue
        if w.is_closing():
            continue
        try:
            pkt = build_chat_aucomm_v4(
                type_byte=0x29, body_after_parent=body,
                sender_auid_int=cauid & 0xFFFFFFFF, sender_name=sender_name,
                target_auid_int=int(peer_auid) & 0xFFFFFFFF)
            await write_framed(w, pkt)
            sent += 1
        except Exception as exc:                        # noqa: BLE001
            logger.warning('City report did not reach player 0x%08x: %r.',
                           int(peer_auid) & 0xFFFFFFFF, exc)
    if sent:
        logger.info("City report for 0x%08x '%s' delivered to %d player(s).",
                    cauid & 0xFFFFFFFF, sender_name, sent)
