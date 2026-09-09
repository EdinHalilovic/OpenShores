
from __future__ import annotations

import struct

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import (
    _EMPIRE_FLAG_OVERRIDE,
    _FLAG_BY_EMPIRE_CACHE,
    apply_announcement,
    empire_for_avatar,
    set_empire_taxes,
    set_place_name,
)
from openshores.network.broadcast import _broadcast_to_peers
from openshores.protocol.atoms.galaxy_rename import (
    _build_sector_atom_rename_pkt,
    _build_system_atom_rename_pkt,
    _build_world_atom_rename_pkt,
)
from openshores.protocol.atoms.aucomm import _read_qstring
from openshores.network.empire_broadcast import broadcast_dg_empire_to_members

logger = get_logger(__name__)


async def handle_chat_change_empire_flag_player(
        payload: bytes, sender_session_auid: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    actor = int(sender_session_auid) & 0xFFFFFFFF
    if not actor:
        logger.warning("0x4A reject: no actor")
        return
    try:
        empire_id = int(await empire_for_avatar(
            conn, actor,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    except Exception:
        empire_id = 0
    if not empire_id:
        logger.warning("0x4A reject: actor=0x%08x has no empire", actor)
        return
    flag_bytes = bytes(payload[1:])
    _EMPIRE_FLAG_OVERRIDE[empire_id] = flag_bytes
    _FLAG_BY_EMPIRE_CACHE.pop(empire_id, None)
    logger.info("0x4A apply: empire=%s actor=0x%08x flag_len=%d sig=%s",
                empire_id, actor, len(flag_bytes),
                flag_bytes[:8].hex() if flag_bytes else "<empty>")
    try:
        await broadcast_dg_empire_to_members(
            empire_id, reason="player-change-flag",
            _live_avatars=_live_avatars, conn=conn, name_long=name_long,
            name_short=name_short, capital_name=capital_name,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    except Exception as _bce:
        logger.warning("0x4A broadcast err: %r", _bce)


async def handle_chat_empire_chg_flag_agent(
        payload: bytes, sender_session_auid: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    actor = int(sender_session_auid) & 0xFFFFFFFF
    if len(payload) < 3:
        logger.warning("0xB8 reject: body too short (%dB)", len(payload))
        return
    empire_id = struct.unpack(">H", payload[1:3])[0]
    flag_bytes = bytes(payload[3:])
    if not empire_id:
        logger.warning("0xB8 reject: empire_id=0")
        return
    _EMPIRE_FLAG_OVERRIDE[empire_id] = flag_bytes
    _FLAG_BY_EMPIRE_CACHE.pop(empire_id, None)
    logger.info("0xB8 apply: empire=%s actor=0x%08x flag_len=%d sig=%s",
                empire_id, actor, len(flag_bytes),
                flag_bytes[:8].hex() if flag_bytes else "<empty>")
    try:
        await broadcast_dg_empire_to_members(
            empire_id, reason="agent-change-flag",
            _live_avatars=_live_avatars, conn=conn, name_long=name_long,
            name_short=name_short, capital_name=capital_name,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    except Exception as _bce:
        logger.warning("0xB8 broadcast err: %r", _bce)


async def handle_chat_empire_chg_name(
        payload: bytes, sender_session_auid: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    actor = int(sender_session_auid) & 0xFFFFFFFF
    if len(payload) < 7:
        logger.warning("0xB9 reject: body too short (%dB)", len(payload))
        return
    try:
        empire_id = struct.unpack(">H", payload[1:3])[0]
        qs_len = struct.unpack(">i", payload[3:7])[0]
        if qs_len < 0:
            new_name = ""
        elif 7 + qs_len > len(payload):
            logger.warning("0xB9 reject: qstring overruns body (%d bytes claimed, %d available)", qs_len, len(payload) - 7)
            return
        else:
            new_name = payload[7:7 + qs_len].decode("utf-16-be",
                                                    errors="replace")
        new_name = new_name.strip()
    except Exception as _pe:
        logger.warning("0xB9 parse fail: %r body_hex=%s",
                       _pe, payload[:64].hex())
        return
    if not empire_id or not new_name:
        logger.warning("0xB9 reject: empire_id=%s name=%r",
                       empire_id, new_name)
        return
    _EMPIRE_NAME_OVERRIDE[empire_id] = new_name
    logger.info("0xB9 apply: empire=%s actor=0x%08x new_name=%r",
                empire_id, actor, new_name)
    try:
        await broadcast_dg_empire_to_members(
            empire_id, reason="agent-change-name",
            _live_avatars=_live_avatars, conn=conn, name_long=name_long,
            name_short=name_short, capital_name=capital_name,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    except Exception as _bce:
        logger.warning("0xB9 broadcast err: %r", _bce)


async def handle_chat_empire_set_taxes(
        payload: bytes, sender_session_auid: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, _EMPIRE_TAX_OVERRIDE, name_long: str,
        name_short: str, capital_name: str,
        _EMPIRE_NAME_OVERRIDE) -> None:
    actor = int(sender_session_auid) & 0xFFFFFFFF
    if len(payload) < 4:
        logger.warning("0xAF reject: body too short (%dB)", len(payload))
        return
    income, sales, subsidy = struct.unpack_from(">3b", payload, 1)
    if len(payload) > 4:
        logger.debug("0xAF note: %d extra byte(s) past the 3x i8 spec: %s",
                     len(payload) - 4, payload[4:].hex())
    try:
        eid = int(await empire_for_avatar(
            conn, actor,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    except Exception:
        eid = 0
    if not eid:
        logger.warning("0xAF reject: actor=0x%08x has no empire", actor)
        return
    _EMPIRE_TAX_OVERRIDE[eid] = (income, sales, subsidy)

    sql_updated = False
    try:
        sql_updated = await set_empire_taxes(conn, eid, income, sales,
                                             subsidy)
    except Exception as _se:
        logger.warning("0xAF SQL persist err: %r", _se)

    logger.info("0xAF apply: empire=%s actor=0x%08x income=%s sales=%s subsidy=%s sql_updated=%s",
                eid, actor, income, sales, subsidy, sql_updated)
    try:
        await broadcast_dg_empire_to_members(
            eid, reason="set-taxes", _live_avatars=_live_avatars, conn=conn,
            name_long=name_long, name_short=name_short,
            capital_name=capital_name,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    except Exception as _bce:
        logger.warning("0xAF broadcast err: %r", _bce)


async def handle_chat_empire_set_announcement(
        payload: bytes, sender_session_auid: int, *, conn,
        _CITIZEN_EMPIRE_OVERRIDE, _EMPIRE_ANNOUNCEMENTS) -> None:
    try:
        text, _ = _read_qstring(payload, 1)
    except Exception as _pe:
        logger.warning("0xA4 parse err: %r hex=%s", _pe, payload[:48].hex())
        return
    text = (text or "")[:256]
    actor = int(sender_session_auid) & 0xFFFFFFFF
    try:
        empire_id = int(await empire_for_avatar(
            conn, actor,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    except Exception:
        empire_id = 0
    if not empire_id:
        logger.warning("0xA4 reject: actor=0x%08x has no empire", actor)
        return
    _EMPIRE_ANNOUNCEMENTS[empire_id] = text
    _persisted = False
    try:
        _res = await apply_announcement(conn, empire_id, text)
        _persisted = bool(_res.get("ok")) if isinstance(_res, dict) else True
    except Exception as _ape:
        logger.warning("0xA4 SQL persist err: %r", _ape)
    logger.info("0xA4 apply empire=%s actor=0x%08x persisted=%s text=%r",
                empire_id, actor, _persisted, text)


async def handle_chat_rename_world(
        payload: bytes, sender_session_auid: int, *, _SAVE,
        _WORLD_NAME_OVERRIDE, _live_avatars, conn, _CITIZEN_EMPIRE_OVERRIDE,
        name_long: str, name_short: str, capital_name: str,
        _EMPIRE_NAME_OVERRIDE, _EMPIRE_TAX_OVERRIDE) -> None:
    actor = int(sender_session_auid) & 0xFFFFFFFF
    if len(payload) < 6:
        logger.warning("0x4F reject: body too short (%dB)", len(payload))
        return
    try:
        kind = payload[1]
        qs_len = struct.unpack(">i", payload[2:6])[0]
        if qs_len < 0:
            new_name = ""
        elif 6 + qs_len > len(payload):
            logger.warning("0x4F reject: qstring overruns body (%d bytes claimed, %d available)", qs_len, len(payload) - 6)
            return
        else:
            new_name = payload[6:6 + qs_len].decode(
                "utf-16-be", errors="replace")
    except Exception as _pe:
        logger.warning("0x4F parse fail: %r body_hex=%s",
                       _pe, payload[:64].hex())
        return

    _KIND_NAME = {0: "system", 1: "planet", 2: "sector", 3: "city"}
    _kind_str = _KIND_NAME.get(kind, f"kind=0x{kind:02x}?")

    target_auid = int(_SAVE.whereabouts_auid or 0) & 0xFFFFFFFF

    _WORLD_NAME_OVERRIDE[(kind, target_auid)] = new_name

    sql_updated = False
    try:
        sql_updated = await set_place_name(conn, kind, target_auid, new_name)
    except Exception as _se:
        logger.warning("0x4F SQL persist err: %r", _se)

    logger.info("0x4F apply: actor=0x%08x kind=%s (%s) target=0x%08x newName=%r sql_updated=%s",
                actor, kind, _kind_str, target_auid, new_name, sql_updated)

    live_pushed = 0
    _live_class = "unknown"
    if target_auid:
        try:
            if kind == 1:
                _live_class = "DaWorldGlobe (planet)"
                _pkt = _build_world_atom_rename_pkt(target_auid, new_name)
                live_pushed = await _broadcast_to_peers(_pkt, _live_avatars)
            elif kind == 2:
                _live_class = "DaSector"
                _pkt = _build_sector_atom_rename_pkt(target_auid, new_name)
                live_pushed = await _broadcast_to_peers(_pkt, _live_avatars)
            elif kind == 0:
                _live_class = "DaSolarSystem (caveat: zeroes patent/vec/set)"
                _pkt = _build_system_atom_rename_pkt(target_auid, new_name)
                live_pushed = await _broadcast_to_peers(_pkt, _live_avatars)
            elif kind == 3:
                _live_class = "DaCity (live-push not implemented)"
            else:
                _live_class = f"kind=0x{kind:02x} (unknown)"
        except Exception as _lpe:
            logger.warning("0x4F live push err: %r", _lpe)
    logger.info("0x4F live atom-update -> %d peer(s) (%s)",
                live_pushed, _live_class)

    try:
        eid = int(await empire_for_avatar(
            conn, actor,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
        if eid:
            await broadcast_dg_empire_to_members(
                eid, reason="rename-world", _live_avatars=_live_avatars,
                conn=conn, name_long=name_long, name_short=name_short,
                capital_name=capital_name,
                _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
                _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
                _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    except Exception as _bce:
        logger.warning("0x4F broadcast err: %r", _bce)
