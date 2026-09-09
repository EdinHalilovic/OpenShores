
from __future__ import annotations

import time as _t

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import (
    invalidate_empire_membership_cache,
)
from openshores.network.empire_broadcast import broadcast_dg_empire_to_members

logger = get_logger(__name__)

_EMPIRE_INVITE_TIMEOUT_SEC = 300.0


async def handle_aucomm_invite_to_empire(parsed: dict,
                                         sender_session_auid: int, *,
                                         _PENDING_EMPIRE_INVITES) -> None:
    invitee = int(parsed.get("invitee_auid", 0)) & 0xFFFFFFFF
    empire_id = int(parsed.get("empire_id", 0)) & 0xFFFFFFFF
    inviter = int(sender_session_auid) & 0xFFFFFFFF
    invitee_name = parsed.get("invitee_name", "")
    if not invitee or not empire_id:
        logger.warning("Reject: invitee=0x%08x empire=%s. Both must be non-zero", invitee, empire_id)
        return
    now = _t.monotonic()
    timeout = _EMPIRE_INVITE_TIMEOUT_SEC
    cur = [(e, i, t) for (e, i, t) in
           _PENDING_EMPIRE_INVITES.get(invitee, [])
           if now - t < timeout and e != empire_id]
    cur.append((empire_id, inviter, now))
    _PENDING_EMPIRE_INVITES[invitee] = cur
    logger.info("PENDING: empire=%s invitee=0x%08x (%r) inviter=0x%08x; "
                "%d active invite(s) for this invitee",
                empire_id, invitee, invitee_name, inviter, len(cur))


async def handle_aucomm_accept_invite_to_empire(parsed: dict,
                                                sender_session_auid: int, *,
                                                _PENDING_EMPIRE_INVITES,
                                                _CITIZEN_EMPIRE_OVERRIDE,
                                                _live_avatars, conn,
                                                name_long,
                                                name_short,
                                                capital_name,
                                                _EMPIRE_NAME_OVERRIDE,
                                                _EMPIRE_TAX_OVERRIDE
                                                ) -> None:
    acceptor = int(sender_session_auid) & 0xFFFFFFFF
    empire_id = int(parsed.get("empire_id", 0)) & 0xFFFFFFFF
    if not acceptor or not empire_id:
        logger.warning("Reject: acceptor=0x%08x empire=%s",
                       acceptor, empire_id)
        return
    pending = _PENDING_EMPIRE_INVITES.get(acceptor, [])
    timeout = _EMPIRE_INVITE_TIMEOUT_SEC
    now = _t.monotonic()
    match = None
    fresh = []
    for (e, i, t) in pending:
        if now - t >= timeout:
            continue
        if e == empire_id and match is None:
            match = (e, i, t)
        else:
            fresh.append((e, i, t))
    if match is None:
        logger.warning("Reject: acceptor=0x%08x no pending invite for empire=%s (pending=%s)", acceptor, empire_id,
                       [hex(e) for (e, _, _) in pending])
        return
    _PENDING_EMPIRE_INVITES[acceptor] = fresh
    logger.info("ACCEPTED: acceptor=0x%08x empire=%s (inviter was 0x%08x)",
                acceptor, empire_id, match[1])
    _CITIZEN_EMPIRE_OVERRIDE[acceptor] = empire_id
    invalidate_empire_membership_cache()
    try:
        await broadcast_dg_empire_to_members(
            empire_id, reason="accept-invite", _live_avatars=_live_avatars,
            conn=conn, name_long=name_long, name_short=name_short,
            capital_name=capital_name,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    except Exception as _bce:
        logger.warning("Broadcast err: %r", _bce)
