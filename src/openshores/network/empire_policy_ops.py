
from __future__ import annotations

import struct

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import (
    _update_empire,
    empire_for_avatar,
    invalidate_empire_membership_cache,
    read_empire_row,
)
from openshores.database.repositories.empire_apply import apply_contrail_color
from openshores.database.repositories.empire_schema import _founder_of
from openshores.gameplay import empire_model as _em
from openshores.gameplay.empire.dg_empire import build_scene_dg_empire_0x31
from openshores.gameplay.empire_office import (
    _serialize_theme,
    parse_assign_office,
)
from openshores.gameplay.empire_read import _empire_for
from openshores.network.empire_broadcast import broadcast_dg_empire_to_members
from openshores.protocol.empire_chat_parse import parse_contrail_color
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)

async def _rebroadcast(
        eid: int, reason: str, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    try:
        await broadcast_dg_empire_to_members(
            int(eid), reason=reason,
            _live_avatars=_live_avatars, conn=conn, name_long=name_long,
            name_short=name_short, capital_name=capital_name,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    except Exception as exc:
        logger.warning("%s broadcast err: %r", reason, exc)

async def on_contrail(
        payload: bytes, actor: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning("0x98 reject: actor=0x%08x has no empire",
                       int(actor))
        return
    parsed = parse_contrail_color(payload[1:])
    if parsed is None:
        logger.warning("0x98 reject: short body %s", payload.hex())
        return
    comp, val = parsed
    res = await apply_contrail_color(conn, eid, comp, val)
    logger.info("0x98 apply: empire=%s component=%s value=%s -> %s",
                eid, comp, val, res)
    if res.get("ok"):
        await _rebroadcast(
            eid, "contrail",
            _live_avatars=_live_avatars, conn=conn, name_long=name_long,
            name_short=name_short, capital_name=capital_name,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)

SINGLE_BYTE_POLICY_OP = {
    0xA9: ("defaultStance", "DefaultPoliticalStance"),
    0xA7: ("cityDebt",      "CityDebtPolicy"),
    0xAA: ("immig",         "ImmigrationPolicy"),
    0xA2: ("rightToFound",  "RightToFound"),
    0xB0: ("trespass",      "TrespassPolicy"),
}

def _make_policy_handler(
        opcode: int, column: str, label: str, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE):
    async def _handler(payload: bytes, actor: int) -> None:
        eid = await _empire_for(
            conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
        if not eid:
            logger.warning("0x%02X %s reject: actor=0x%08x no empire",
                           opcode, label, int(actor))
            return
        if len(payload) < 2:
            logger.warning("0x%02X %s reject: short body %s",
                           opcode, label, payload.hex())
            return
        val = payload[1] & 0xFF
        ok = await _update_empire(conn, eid, **{column: val})
        logger.info("0x%02X %s apply: empire=%s %s=%s ok=%s",
                    opcode, label, eid, column, val, ok)
        await _rebroadcast(
            eid, label,
            _live_avatars=_live_avatars, conn=conn, name_long=name_long,
            name_short=name_short, capital_name=capital_name,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    return _handler

async def on_commerce(
        payload: bytes, actor: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning("0xA8 reject: actor=0x%08x no empire",
                       int(actor))
        return
    body = payload[1:]
    if len(body) < 4:
        logger.warning("0xA8 reject: short body %s", payload.hex())
        return
    n = struct.unpack_from(">i", body, 0)[0]
    blob = body[4:4 + n] if 0 < n <= len(body) - 4 else b""
    ok = await _update_empire(conn, eid, commerce=blob)
    logger.info("0xA8 apply: empire=%s %dB ok=%s", eid, len(blob), ok)
    await _rebroadcast(
        eid, "commerce",
        _live_avatars=_live_avatars, conn=conn, name_long=name_long,
        name_short=name_short, capital_name=capital_name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)

async def on_theme_color(
        payload: bytes, actor: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning("0xD5 reject: actor=0x%08x no empire", int(actor))
        return
    body = payload[1:]
    if len(body) < 2:
        logger.warning("0xD5 reject: short body %s", payload.hex())
        return
    idx = body[0]
    if idx >= 6:
        logger.warning("0xD5 reject: idx %s out of range", idx)
        return
    spec = body[1]
    if spec == 0:
        a = r = g = b = 0
    else:
        try:
            a16, r16, g16, b16, _pad = struct.unpack_from(">5H", body, 2)
            a, r, g, b = a16 >> 8, r16 >> 8, g16 >> 8, b16 >> 8
        except Exception as exc:
            logger.warning("0xD5 parse err: %r %s", exc, payload.hex())
            return
    theme = list((await _em.load_empire(conn, eid)).status.theme or [])
    while len(theme) < 6:
        theme.append((255, 0, 0, 0))
    theme[idx] = (a, r, g, b)
    ok = await _update_empire(conn, eid, theme=_serialize_theme(theme))
    logger.info("0xD5 apply: empire=%s idx=%s argb=(%s,%s,%s,%s) ok=%s",
                eid, idx, a, r, g, b, ok)
    await _rebroadcast(
        eid, "theme",
        _live_avatars=_live_avatars, conn=conn, name_long=name_long,
        name_short=name_short, capital_name=capital_name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)

async def on_contrail_set(
        payload: bytes, actor: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning("0x98 reject: actor=0x%08x no empire", int(actor))
        return
    body = payload[1:]
    if len(body) < 2:
        logger.warning("0x98 reject: short body %s", payload.hex())
        return
    hue, sat = body[0], body[1]
    ok = await _update_empire(conn, eid, contrailHue=hue,
                              contrailSat=sat)
    logger.info("0x98 apply: empire=%s hue=%s sat=%s ok=%s",
                eid, hue, sat, ok)
    await _rebroadcast(
        eid, "contrail",
        _live_avatars=_live_avatars, conn=conn, name_long=name_long,
        name_short=name_short, capital_name=capital_name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)

async def on_zonebuild(
        payload: bytes, actor: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning("0xB1 reject: actor=0x%08x no empire", int(actor))
        return
    body = payload[1:]
    if len(body) < 2:
        logger.warning("0xB1 reject: short body %s", payload.hex())
        return
    which, permit = body[0], body[1]
    STANCE_BIT = {0: 0, 1: 1, 2: 2, 4: 3}
    bit = STANCE_BIT.get(which)
    if bit is None:
        logger.warning("0xB1 no-op: stance %s has no stored bit", which)
        return
    try:
        cur = int((await _em.load_empire(conn, eid)).status.zone_build) & 0xFF
    except Exception:
        logger.warning("0xB1: empire %s has no readable zoneBuildPolicy; "
                       "starting from 0.", eid)
        cur = 0
    cur = (cur | (1 << bit)) if permit else (cur & ~(1 << bit) & 0xFF)
    ok = await _update_empire(conn, eid, zoneBuildPolicy=cur & 0xFF)
    logger.info("0xB1 apply: empire=%s which=%s bit=%s permit=%s -> 0x%02x ok=%s", eid, which, bit, permit, cur, ok)
    await _rebroadcast(
        eid, "zonebuild",
        _live_avatars=_live_avatars, conn=conn, name_long=name_long,
        name_short=name_short, capital_name=capital_name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)

async def _push_no_empire(
        target: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> bool:
    tgt = int(target) & 0xFFFFFFFF
    entry = _live_avatars.get(tgt)
    if not isinstance(entry, dict):
        return False
    w = entry.get("writer")
    if w is None or w.is_closing():
        return False
    try:
        pkt = await build_scene_dg_empire_0x31(
            conn,
            last_flag=True, player_avatar_id=tgt,
            empire_id=0, emperor_auid=0,
            name_long=name_long, name_short=name_short,
            capital_name=capital_name,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
        await write_framed(w, pkt)
        logger.info("No-empire 0x31 -> player 0x%08x (%dB). Client should show Found/Join UI", tgt, len(pkt))
        return True
    except Exception as _ne:
        logger.warning("No-empire push err for 0x%08x: %r", tgt, _ne)
        return False

async def on_kick_renounce(
        payload: bytes, actor: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning("0x4E reject: actor=0x%08x no empire", int(actor))
        return
    body = payload[1:]
    if len(body) < 4:
        logger.warning("0x4E reject: short body %s", payload.hex())
        return
    target = struct.unpack_from(">I", body, 0)[0]
    actor_i = int(actor) & 0xFFFFFFFF
    kind = "RENOUNCE" if target == actor_i else "KICK"

    row = await read_empire_row(conn, eid, ("citizens",))
    blob = bytes(row[0]) if row and row[0] is not None else b""
    in_blob = False
    if len(blob) >= 4:
        count = struct.unpack(">I", blob[:4])[0]
        recs = [blob[4 + i * 16: 4 + (i + 1) * 16] for i in range(count)]
        recs = [r for r in recs if len(r) == 16]
        if recs:
            founder = struct.unpack(">I", recs[0][:4])[0]
            removing_founder = (target == founder)
            if removing_founder and kind == "KICK":
                logger.warning("0x4E reject: cannot kick the emperor/founder 0x%08x (only self-renounce)", target)
                return
            new_recs = [r for r in recs
                        if struct.unpack(">I", r[:4])[0] != target]
            if len(new_recs) != len(recs):
                new_blob = struct.pack(">I", len(new_recs)) + b"".join(new_recs)
                check = _em._parse_citizens(new_blob)
                if target in check or (not removing_founder
                                       and founder not in check):
                    logger.warning("0x4E ABORT: post-rewrite "
                                   "validation failed, not writing")
                    return
                await _update_empire(conn, eid, citizens=new_blob)
                in_blob = True
                if removing_founder:
                    _succ = (struct.unpack(">I", new_recs[0][:4])[0]
                             if new_recs else 0)
                    if _succ:
                        logger.info("0x4E RENOUNCE: emperor 0x%08x "
                                    "renounced; succession -> new "
                                    "emperor 0x%08x", target, _succ)
                    else:
                        logger.info('0x4E RENOUNCE: emperor 0x%08x renounced.', target)
                else:
                    logger.info("0x4E %s: removed 0x%08x from citizens "
                                "BLOB (%d->%d)", kind, target, len(recs),
                                len(new_recs))

    was_member = in_blob or (
        (int(await empire_for_avatar(
            conn, target,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE))
         & 0xFFFFFFFF) == (eid & 0xFFFFFFFF))
    if not was_member:
        logger.warning("0x4E no-op: 0x%08x not a citizen of empire %s",
                       target, eid)
        return

    try:
        if _CITIZEN_EMPIRE_OVERRIDE.pop(target, None) is not None:
            logger.info("0x4E %s: cleared invite override for 0x%08x",
                        kind, target)
    except Exception as _oe:
        logger.warning("0x4E override-clear err: %r", _oe)

    try:
        invalidate_empire_membership_cache()
    except Exception as _ce:
        logger.warning("0x4E cache-invalidate err: %r", _ce)

    try:
        await _em.remove_office(conn, eid, target)
    except Exception as _re:
        logger.warning("0x4E office-drop err: %r", _re)

    logger.info("0x4E %s apply: empire=%s removed=0x%08x (now empire-less)", kind, eid, target)
    await _rebroadcast(
        eid, "citizen-remove",
        _live_avatars=_live_avatars, conn=conn, name_long=name_long,
        name_short=name_short, capital_name=capital_name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    await _push_no_empire(
        target,
        _live_avatars=_live_avatars, conn=conn, name_long=name_long,
        name_short=name_short, capital_name=capital_name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)

async def on_assign_office(
        payload: bytes, actor: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning("0x94 reject: actor=0x%08x no empire", int(actor))
        return
    parsed = parse_assign_office(payload[1:])
    if parsed is None:
        logger.warning("0x94 parse-fail: %s", payload.hex())
        return
    citizen, title, f1, f2, role_id = parsed
    if citizen == await _founder_of(conn, eid):
        logger.warning("0x94 reject: refuses to retitle founder/emperor 0x%08x", citizen)
        return
    await _em.set_office(conn, eid, citizen, title=title, rights1=f1,
                         rights2=f2, role_id=role_id)
    logger.info("0x94 ASSIGN apply: empire=%s citizen=0x%08x title=%r rights=(%#010x,%#010x)", eid, citizen, title, f1, f2)
    await _rebroadcast(
        eid, "assign-office",
        _live_avatars=_live_avatars, conn=conn, name_long=name_long,
        name_short=name_short, capital_name=capital_name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)

async def on_revoke_office(
        payload: bytes, actor: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning("0xA1 reject: actor=0x%08x no empire", int(actor))
        return
    body = payload[1:]
    if len(body) < 4:
        logger.warning("0xA1 reject: short %s", payload.hex())
        return
    target = struct.unpack_from(">I", body, 0)[0]
    if target == await _founder_of(conn, eid):
        logger.warning("0xA1 reject: cannot revoke founder/emperor")
        return
    await _em.remove_office(conn, eid, target)
    logger.info("0xA1 REVOKE apply: empire=%s target=0x%08x",
                eid, target)
    await _rebroadcast(
        eid, "revoke-office",
        _live_avatars=_live_avatars, conn=conn, name_long=name_long,
        name_short=name_short, capital_name=capital_name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)

async def on_resign_office(
        payload: bytes, actor: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning("0xA0 reject: actor=0x%08x no empire", int(actor))
        return
    aid = int(actor) & 0xFFFFFFFF
    if aid == await _founder_of(conn, eid):
        logger.warning("0xA0 no-op: founder/emperor cannot resign")
        return
    await _em.remove_office(conn, eid, aid)
    logger.info("0xA0 RESIGN apply: empire=%s actor=0x%08x", eid, aid)
    await _rebroadcast(
        eid, "resign-office",
        _live_avatars=_live_avatars, conn=conn, name_long=name_long,
        name_short=name_short, capital_name=capital_name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)

async def on_change_boss(
        payload: bytes, actor: int, *, _live_avatars, conn,
        _CITIZEN_EMPIRE_OVERRIDE, name_long: str, name_short: str,
        capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> None:
    eid = await _empire_for(
        conn, actor, _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if not eid:
        logger.warning("0xA5 reject: actor=0x%08x no empire", int(actor))
        return
    body = payload[1:]
    if len(body) < 8:
        logger.warning("0xA5 reject: short %s", payload.hex())
        return
    citizen = struct.unpack_from(">I", body, 0)[0]
    new_boss = struct.unpack_from(">I", body, 4)[0]
    cur = (await _em._load_offices(conn, eid)).get(citizen & 0xFFFFFFFF)
    if cur is not None:
        await _em.set_office(conn, eid, citizen, title=cur.title,
                             rights1=cur.rights1, rights2=cur.rights2,
                             role_id=(cur.role_id or citizen),
                             boss_id=new_boss)
    else:
        await _em.set_office(conn, eid, citizen, title="", rights1=0,
                             rights2=0, role_id=citizen,
                             boss_id=new_boss)
    logger.info("0xA5 CHANGEBOSS apply: empire=%s citizen=0x%08x boss=0x%08x", eid, citizen, new_boss)
    await _rebroadcast(
        eid, "change-boss",
        _live_avatars=_live_avatars, conn=conn, name_long=name_long,
        name_short=name_short, capital_name=capital_name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
