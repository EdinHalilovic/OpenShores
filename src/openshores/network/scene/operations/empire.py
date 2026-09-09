
from __future__ import annotations


from openshores.core.logging import get_logger
from openshores.database.repositories.empire import (
    empire_for_avatar,
    named_empire_ids,
)
from openshores.gameplay.dispatch import register
from openshores.gameplay.empire.dg_empire import build_scene_dg_empire_0x31
from openshores.gameplay.room_types import build_scene_all_dn_room_types_0x30
from openshores.protocol.framing import write_framed
from openshores.protocol.stream import QDS

logger = get_logger(__name__)


def _session_avatar(session) -> int:
    return int(getattr(session, "player_auid", 0) or 0) & 0xFFFFFFFF


async def _empire_ids(conn) -> list[int]:
    return await named_empire_ids(conn)


@register(0x31)
async def handle_0x31_request_empire(
    session,
    payload: bytes,
    *,
    conn,
    name_long: str,
    name_short: str,
    capital_name: str,
    _CITIZEN_EMPIRE_OVERRIDE: dict,
    _EMPIRE_NAME_OVERRIDE: dict,
    _EMPIRE_TAX_OVERRIDE: dict,
) -> None:
    s = QDS(payload)
    s.read_u8()
    requested = s.read_u32()
    _avatar = _session_avatar(session)
    _own_empire = int(await empire_for_avatar(
        conn, _avatar,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    _bind = _avatar if (_own_empire and _own_empire == int(requested)) else 0
    logger.debug("0x31 RequestEmpire auid=0x%08x. Replying with DgEmpire (session avatar 0x%08x, own empire 0x%08x, +0x94 bind 0x%08x).", requested, _avatar, _own_empire, _bind)
    _rsp = await build_scene_dg_empire_0x31(
        conn, True, player_avatar_id=_bind,
        empire_id=int(requested),
        name_long=name_long, name_short=name_short,
        capital_name=capital_name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    await write_framed(session.writer, _rsp)
    logger.debug("Sent DgEmpire in reply to client 0x31, %d bytes.", len(_rsp))


@register(0x3E)
async def handle_0x3E_request_full_empires(
    session,
    payload: bytes,
    *,
    conn,
    name_long: str,
    name_short: str,
    capital_name: str,
    _CITIZEN_EMPIRE_OVERRIDE: dict,
    _EMPIRE_NAME_OVERRIDE: dict,
    _EMPIRE_TAX_OVERRIDE: dict,
) -> None:
    empire_ids: list[int] = await _empire_ids(conn)

    if not empire_ids:
        _self_empire = int(await empire_for_avatar(
            conn, _session_avatar(session),
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) or 1
        empire_ids = [_self_empire]
        logger.debug("0x3E no g_Empire rows; falling back to session "
                     "empire %s.", _self_empire)

    logger.debug("0x3E RequestFullEmpires. Streaming %d empire(s): %s.",
                 len(empire_ids), [hex(e) for e in empire_ids])

    _dn_room_frames = build_scene_all_dn_room_types_0x30()
    _dn_room_total = 0
    for _rt_pkt in _dn_room_frames:
        await write_framed(session.writer, _rt_pkt)
        _dn_room_total += len(_rt_pkt)
    logger.debug("Sent DnRoomType x%d (0x3E re-stream, %dB).",
                 len(_dn_room_frames), _dn_room_total)

    _player_auid = _session_avatar(session)
    for i, eid in enumerate(empire_ids):
        _is_last = (i == len(empire_ids) - 1)
        _pkt = await build_scene_dg_empire_0x31(
            conn,
            last_flag=_is_last,
            player_avatar_id=_player_auid,
            empire_id=eid,
            name_long=name_long, name_short=name_short,
            capital_name=capital_name,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
        await write_framed(session.writer, _pkt)
        logger.debug("Sent DgEmpire eid=0x%08x (%dB, last=%d).",
                     eid, len(_pkt), int(_is_last))
