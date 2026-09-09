from __future__ import annotations

import struct

from openshores.core.logging import get_logger
from openshores.database.repositories.empire_diplomacy import (
    DOC_NOTE,
    _add_dossier_doc,
    set_dossier_doc_state,
    set_founder_domain,
    set_known_empire_stance,
    set_war_criteria,
)
from openshores.gameplay.empire_read import _empire_for
from openshores.network.empire_policy_ops import _rebroadcast
from openshores.protocol.empire_chat_parse import _read_qstring

logger = get_logger(__name__)


def _now_ms() -> int:
    import time as _t
    return int(_t.time() * 1000)


async def on_dossier(payload: bytes, actor: int, *, conn,
                     _CITIZEN_EMPIRE_OVERRIDE, _live_avatars,
                     name_long: str, name_short: str, capital_name: str,
                     _EMPIRE_NAME_OVERRIDE,
                     _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning(f"0xCC reject: actor=0x{int(actor):08x} no empire")
        return
    body = payload[1:]
    if len(body) < 5:
        logger.warning(f"0xCC reject: short {payload.hex()}")
        return
    sub = body[0]
    known = struct.unpack_from(">I", body, 1)[0]
    aid = int(actor) & 0xFFFFFFFF
    if sub == 0x00:
        note, _ = _read_qstring(body, 5)
        idx = await _add_dossier_doc(conn, eid, known, DOC_NOTE, _now_ms(),
                                     aid, eid,
                                     text_a=note or "", doc_state=0)
        logger.info(f"0xCC add-note apply: empire={eid} known=0x{known:08x} idx={idx} note={note!r}")
        await _rebroadcast(
            eid, "dossier-note", _live_avatars=_live_avatars, conn=conn,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            name_long=name_long, name_short=name_short,
            capital_name=capital_name,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    elif sub == 0x02:
        msg, _ = _read_qstring(body, 5)
        idx = await _add_dossier_doc(conn, eid, known, DOC_NOTE, _now_ms(),
                                     aid, eid,
                                     text_a=msg or "", doc_state=0)
        logger.info(f"0xCC COURIER apply: empire={eid} known=0x{known:08x} idx={idx} msg={msg!r}")
        await _rebroadcast(
            eid, "dossier-courier", _live_avatars=_live_avatars, conn=conn,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            name_long=name_long, name_short=name_short,
            capital_name=capital_name,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    elif sub == 0x01:
        if len(body) < 14:
            logger.warning(f"0xCC DOC-STATE short: {body.hex()}")
            return
        au_time = struct.unpack_from(">Q", body, 5)[0]
        state = body[-1]
        rows = await set_dossier_doc_state(conn, eid, known, au_time, state)
        logger.info(f"0xCC DOC-STATE apply: empire={eid} known=0x{known:08x} t={au_time} state={state} rows={rows}")
        await _rebroadcast(
            eid, "dossier-state", _live_avatars=_live_avatars, conn=conn,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            name_long=name_long, name_short=name_short,
            capital_name=capital_name,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    else:
        logger.info(f"0xCC sub=0x{sub:02x} (capture): {body.hex()}")


async def on_per_empire_stance(payload: bytes, actor: int, *, conn,
                               _CITIZEN_EMPIRE_OVERRIDE, _live_avatars,
                               name_long: str, name_short: str,
                               capital_name: str,
                               _EMPIRE_NAME_OVERRIDE,
                               _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning(f"0xAC reject: actor=0x{int(actor):08x} no empire")
        return
    body = payload[1:]
    if len(body) < 5:
        logger.warning(f"0xAC reject: short {payload.hex()}")
        return
    known = struct.unpack_from(">I", body, 0)[0]
    stance = body[4]
    tribute = body[5] if len(body) > 5 else 0
    rows = await set_known_empire_stance(conn, eid, known, stance, tribute)
    logger.info(f"0xAC STANCE apply: empire={eid} known=0x{known:08x} stance={stance} tribute={tribute} rows={rows}")
    await _rebroadcast(
        eid, "per-empire-stance", _live_avatars=_live_avatars, conn=conn,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        name_long=name_long, name_short=name_short,
        capital_name=capital_name,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)


async def on_war_criteria(payload: bytes, actor: int, *, conn,
                          _CITIZEN_EMPIRE_OVERRIDE, _live_avatars,
                          name_long: str, name_short: str,
                          capital_name: str, _EMPIRE_NAME_OVERRIDE,
                          _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning(f"0xCD reject: actor=0x{int(actor):08x} no empire")
        return
    body = payload[1:]
    if not body:
        logger.warning(f"0xCD reject: empty {payload.hex()}")
        return
    count = body[0]
    need = 1 + 2 * count
    if len(body) < need:
        logger.warning(f"0xCD reject: short body {body.hex()} (count={count} needs {need})")
        return
    blob = bytes(body[:need])
    rows = await set_war_criteria(conn, eid, blob)
    logger.info(f"0xCD apply: empire={eid} count={count} blob={blob.hex()} rows={rows}")
    await _rebroadcast(
        eid, "war-criteria", _live_avatars=_live_avatars, conn=conn,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        name_long=name_long, name_short=name_short,
        capital_name=capital_name,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)


async def on_founder_domain(payload: bytes, actor: int, *, conn,
                            _CITIZEN_EMPIRE_OVERRIDE, _live_avatars,
                            name_long: str, name_short: str,
                            capital_name: str, _EMPIRE_NAME_OVERRIDE,
                            _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning(f"0xCB reject: actor=0x{int(actor):08x} no empire")
        return
    body = payload[1:]
    if not body:
        logger.warning(f"0xCB reject: empty {payload.hex()}")
        return
    domain = body[0]
    if not (1 <= domain <= 6):
        logger.warning(f"0xCB reject: domain {domain} out of range 1..6")
        return
    rows = await set_founder_domain(conn, eid, domain)
    logger.info(f"0xCB apply: empire={eid} domain={domain} rows={rows}")
    await _rebroadcast(
        eid, "founder-domain", _live_avatars=_live_avatars, conn=conn,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        name_long=name_long, name_short=name_short,
        capital_name=capital_name,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
