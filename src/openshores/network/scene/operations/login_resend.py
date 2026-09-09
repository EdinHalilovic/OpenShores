
from __future__ import annotations

from typing import Awaitable, Callable

from openshores.core.logging import get_logger
from openshores.gameplay.dispatch import register
from openshores.protocol.framing import write_framed
from openshores.protocol.login import parse_login_request

logger = get_logger(__name__)


@register(0x03)
async def handle_0x03_login_resend(
    session,
    payload: bytes,
    *,
    _dispatch_login: Callable[..., Awaitable[bytes]],
) -> None:
    req = parse_login_request(payload)
    logger.debug("Login resent on the scene port for %r.", req.username)
    reply = await _dispatch_login(
        req, peer_host=session.peer_host)
    await write_framed(session.writer, reply)
    logger.debug("Login resend answered with %d bytes, opcode 0x%02x.",
                 len(reply), reply[0])
