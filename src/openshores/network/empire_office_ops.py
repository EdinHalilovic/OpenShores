
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.empire_apply import (
    apply_policy_toggle,
    apply_rewards,
    apply_role,
)
from openshores.gameplay.empire_read import _empire_for
from openshores.protocol.empire_chat_parse import (
    parse_emperor,
    parse_policy_toggle,
    parse_rewards,
    parse_role,
)

logger = get_logger(__name__)


async def on_policy(payload: bytes, actor: int, *,
                   conn,
                   _CITIZEN_EMPIRE_OVERRIDE,
                   _rebroadcast) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning("0xB1 reject: actor=0x%08x has no empire", int(actor))
        return
    parsed = parse_policy_toggle(payload[1:])
    if parsed is None:
        logger.warning("0xB1 reject: short body %s", payload.hex())
        return
    idx, val = parsed
    res = await apply_policy_toggle(conn, eid, idx, val)
    logger.info("0xB1 apply: empire=%s index=%s value=%s -> %s",
                eid, idx, val, res)
    await _rebroadcast(eid, "policy")


async def on_rewards(payload: bytes, actor: int, *,
                    conn,
                    _CITIZEN_EMPIRE_OVERRIDE,
                    _rebroadcast) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning("Reject: actor=0x%08x no empire", int(actor))
        return
    rewards = parse_rewards(payload[1:])
    if rewards is None:
        logger.warning("Reject: body too short (%dB, need 64) %s",
                       len(payload) - 1, payload.hex())
        return
    res = await apply_rewards(conn, eid, rewards)
    logger.info("Apply: empire=%s -> %s", eid, res)
    await _rebroadcast(eid, "rewards")


async def on_role(payload: bytes, actor: int, *,
                 conn,
                 _CITIZEN_EMPIRE_OVERRIDE,
                 _rebroadcast) -> None:
    parsed = parse_role(payload[1:])
    if parsed is None:
        logger.warning("0xBA reject: short body %s", payload.hex())
        return
    eid, role = parsed
    if not eid:
        eid = await _empire_for(
            conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    res = await apply_role(conn, eid, role)
    logger.info("0xBA apply: empire=%s role=%s -> %s", eid, role, res)
    if eid:
        await _rebroadcast(eid, "role")


async def on_emperor(payload: bytes, actor: int, *,
                    conn,
                    _CITIZEN_EMPIRE_OVERRIDE,
                    _rebroadcast) -> None:
    parsed = parse_emperor(payload[1:])
    if parsed is None:
        logger.warning("0xB7 reject: short body %s", payload.hex())
        return
    eid, auid, name = parsed
    logger.warning("0xB7 capture (not yet persisted): empire=%s new_emperor=0x%08x name=%r", eid, auid, name)
    if eid:
        await _rebroadcast(eid, "emperor")
