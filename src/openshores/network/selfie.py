
from __future__ import annotations

import struct
import time as _hz_time_mod

from openshores.core.logging import get_logger
from openshores.database.journal import get_queue

logger = get_logger(__name__)

_SELFIE_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_SELFIE_PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"
_SELFIE_MAX_BYTES = 1048576
_SELFIE_MIN_INTERVAL_S = 10.0


async def handle_chat_send_selfie(payload: bytes, sender_session_auid: int,
                                  *, _SELFIE_LAST_AT) -> None:
    actor = int(sender_session_auid) & 0xFFFFFFFF
    if not actor:
        logger.warning("0x64 reject: no actor bound to this chat writer")
        return
    if len(payload) < 29:
        logger.warning("0x64 reject: body too short (%dB)", len(payload))
        return
    marker = struct.unpack(">i", payload[1:5])[0]
    if marker != 1:
        logger.warning("0x64 reject: marker=%s (expected 1)", marker)
        return
    png = bytes(payload[5:])
    if not png.startswith(_SELFIE_PNG_SIG):
        logger.warning("0x64 reject: bad magic %s", png[:8].hex())
        return
    if not png.endswith(_SELFIE_PNG_IEND):
        logger.warning("0x64 reject: no IEND tail %s", png[-12:].hex())
        return
    if len(png) > _SELFIE_MAX_BYTES:
        logger.warning("0x64 reject: %dB > cap %d", len(png), _SELFIE_MAX_BYTES)
        return
    if png[12:16] != b"IHDR":
        logger.warning("0x64 reject: no IHDR at +12 (%r)", png[12:16])
        return
    w, h = struct.unpack(">II", png[16:24])
    if not (0 < w <= 2048 and 0 < h <= 2048):
        logger.warning("0x64 reject: implausible IHDR %sx%s", w, h)
        return
    now = _hz_time_mod.monotonic()
    if now - _SELFIE_LAST_AT.get(actor, 0.0) < _SELFIE_MIN_INTERVAL_S:
        logger.info("0x64 THROTTLE: actor=0x%08x (min %ss between selfies)",
                    actor, _SELFIE_MIN_INTERVAL_S)
        return
    _SELFIE_LAST_AT[actor] = now
    _queue = get_queue()
    ok = _queue is not None and _queue.submit(
        "update_person_state", actor, selfie=png)
    logger.info("0x64 apply: actor=0x%08x %sx%s len=%d marker=%s queued=%s",
                actor, w, h, len(png), marker, bool(ok))
