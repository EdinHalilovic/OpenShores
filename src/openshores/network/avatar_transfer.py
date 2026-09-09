
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import (
    empire_for_avatar,
    invalidate_empire_membership_cache,
)
from openshores.network import login_ops as _ops
from openshores.network.aucomm_relay import _send_aucomm_to_avatar
from openshores.protocol.atoms.aucomm import (
    AUCOMM_TYPE_OFFER_AVATAR,
    build_aucomm_avatar_packet,
)

logger = get_logger(__name__)


async def handle_aucomm_offer_avatar(parsed: dict, actor: int, *,
                                     _live_avatars) -> None:
    avatar = int(parsed.get("avatar_auid", 0)) & 0xFFFFFFFF
    target = int(parsed.get("target_auid", 0)) & 0xFFFFFFFF
    giver = int(actor) & 0xFFFFFFFF
    res = _ops.record_avatar_offer(avatar, giver, target)
    if not res["ok"]:
        logger.warning("OFFER rejected 0x%08x %r from 0x%08x to 0x%08x: %s",
                       avatar, parsed.get("avatar_name"), giver, target,
                       res["reason"])
        return
    pkt = build_aucomm_avatar_packet(
        AUCOMM_TYPE_OFFER_AVATAR, avatar, parsed.get("avatar_name") or "",
        giver, parsed.get("sender_name") or "", target)
    ok = await _send_aucomm_to_avatar(target, pkt, _live_avatars=_live_avatars)
    logger.info("OFFER 0x%08x %r from 0x%08x -> 0x%08x (%s)",
                avatar, parsed.get("avatar_name"), giver, target,
                "relayed" if ok else "target not online; offer still pending")


async def handle_aucomm_accept_avatar(parsed: dict, actor: int, *,
                                      _live_avatars, conn,
                                      _CITIZEN_EMPIRE_OVERRIDE) -> None:
    avatar = int(parsed.get("avatar_auid", 0)) & 0xFFFFFFFF
    accepter = int(actor) & 0xFFFFFFFF
    res = await _ops.transfer_avatar(
        _live_avatars, conn, avatar, accepter,
        empire_for_avatar=empire_for_avatar,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if res["moved"]:
        logger.info("ACCEPTED 0x%08x %r: %r -> %r", avatar,
                    parsed.get("avatar_name"), res["from_user"], res["to_user"])
        invalidate_empire_membership_cache()
    else:
        logger.warning("ACCEPT refused 0x%08x by 0x%08x: %s",
                       avatar, accepter, res["reason"])
