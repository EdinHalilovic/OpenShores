
from __future__ import annotations

import time as _t

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import (
    apply_announcement,
    empire_for_avatar,
)
from openshores.network.empire_broadcast import broadcast_dg_empire_to_members

logger = get_logger(__name__)


_EMPIRE_DIPLO_LOG_MAX: int = 64


async def handle_aucomm_announcement(parsed: dict, sender_session_auid: int,
                                     *, _EMPIRE_ANNOUNCEMENTS,
                                     _live_avatars, conn,
                                     _CITIZEN_EMPIRE_OVERRIDE,
                                     name_long,
                                     name_short,
                                     capital_name,
                                     _EMPIRE_NAME_OVERRIDE,
                                     _EMPIRE_TAX_OVERRIDE) -> None:
    text = parsed.get("announcement", "") or ""
    actor = int(sender_session_auid) & 0xFFFFFFFF
    try:
        empire_id = int(await empire_for_avatar(
            conn, actor,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    except Exception:
        empire_id = 0
    if not empire_id:
        logger.warning("Reject: actor=0x%08x has no empire", actor)
        return
    _EMPIRE_ANNOUNCEMENTS[empire_id] = text
    try:
        await apply_announcement(conn, empire_id, text)
    except Exception as _ape:
        logger.warning("SQL persist err: %r", _ape)
    logger.info("Empire=%s actor=0x%08x text=%r", empire_id, actor, text)
    try:
        await broadcast_dg_empire_to_members(
            empire_id, reason="announcement", _live_avatars=_live_avatars,
            conn=conn, name_long=name_long, name_short=name_short,
            capital_name=capital_name,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    except Exception as _bce:
        logger.warning("Broadcast err: %r", _bce)


async def handle_aucomm_diplomatic_message(parsed: dict,
                                           sender_session_auid: int, *,
                                           _EMPIRE_DIPLO_LOG, conn,
                                           _CITIZEN_EMPIRE_OVERRIDE
                                           ) -> None:
    text = parsed.get("message", "") or ""
    actor = int(sender_session_auid) & 0xFFFFFFFF
    target = int(parsed.get("target_auid", 0)) & 0xFFFFFFFF
    try:
        from_emp = int(await empire_for_avatar(
            conn, actor,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    except Exception:
        from_emp = 0
    logger.info("from_empire=%s actor=0x%08x target=0x%08x: %r",
                from_emp, actor, target, text)
    entry = dict(from_empire=from_emp, target_auid=target, message=text,
                 t=_t.monotonic())
    log = _EMPIRE_DIPLO_LOG.setdefault(from_emp, [])
    log.append(entry)
    if len(log) > _EMPIRE_DIPLO_LOG_MAX:
        del log[: len(log) - _EMPIRE_DIPLO_LOG_MAX]


async def handle_aucomm_city_surrender_offered(parsed: dict,
                                               sender_session_auid: int, *,
                                               _PENDING_CITY_SURRENDERS
                                               ) -> None:
    actor = int(sender_session_auid) & 0xFFFFFFFF
    from_emp = int(parsed.get("from_empire", 0)) & 0xFFFFFFFF
    to_emp = int(parsed.get("to_empire", 0)) & 0xFFFFFFFF
    city_ids = parsed.get("city_ids", []) or []
    city_names = parsed.get("city_names", []) or []
    key = (from_emp, to_emp)
    pending = _PENDING_CITY_SURRENDERS.setdefault(key, [])
    pending.append(dict(city_ids=city_ids, city_names=city_names,
                        t=_t.monotonic()))
    logger.info("OFFERED: from=%s to=%s cities=%s actor=0x%08x",
                from_emp, to_emp, list(zip(city_ids, city_names)), actor)


async def handle_aucomm_city_surrender_accepted(parsed: dict,
                                                sender_session_auid: int, *,
                                                _PENDING_CITY_SURRENDERS,
                                                _live_avatars, conn,
                                                _CITIZEN_EMPIRE_OVERRIDE,
                                                name_long,
                                                name_short,
                                                capital_name,
                                                _EMPIRE_NAME_OVERRIDE,
                                                _EMPIRE_TAX_OVERRIDE
                                                ) -> None:
    actor = int(sender_session_auid) & 0xFFFFFFFF
    src_emp = int(parsed.get("source_empire", 0)) & 0xFFFFFFFF
    dst_emp = int(parsed.get("target_empire", 0)) & 0xFFFFFFFF
    city_ids = parsed.get("city_ids", []) or []
    logger.info("ACCEPTED: src=%s dst=%s cities=%s actor=0x%08x",
                src_emp, dst_emp, city_ids, actor)
    key = (src_emp, dst_emp)
    pending = _PENDING_CITY_SURRENDERS.get(key, [])
    if pending:
        _PENDING_CITY_SURRENDERS[key] = [
            e for e in pending
            if not all(cid in city_ids for cid in e["city_ids"])]
    _bkw = dict(_live_avatars=_live_avatars, conn=conn, name_long=name_long,
                name_short=name_short, capital_name=capital_name,
                _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
                _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
                _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    try:
        if src_emp:
            await broadcast_dg_empire_to_members(
                src_emp, reason="surrender-source", **_bkw)
        if dst_emp:
            await broadcast_dg_empire_to_members(
                dst_emp, reason="surrender-target", **_bkw)
    except Exception as _bce:
        logger.warning("Broadcast err: %r", _bce)


async def handle_aucomm_citizen_order(parsed: dict,
                                      sender_session_auid: int) -> None:
    actor = int(sender_session_auid) & 0xFFFFFFFF
    order_enum = int(parsed.get("order_enum", 0)) & 0xFF
    target = int(parsed.get("target_id", 0)) & 0xFFFFFFFF
    recipients = parsed.get("recipients", []) or []
    logger.debug("actor=0x%08x enum=0x%02x target=0x%08x recipients=%s "
                 "xyz=(%.1f,%.1f,%.1f) extra=%r",
                 actor, order_enum, target, [hex(r) for r in recipients],
                 parsed.get("x", 0), parsed.get("y", 0), parsed.get("z", 0),
                 parsed.get("extra_text", ""))
