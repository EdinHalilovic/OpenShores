
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.blueprint import (
    blueprint_by_design_id,
    published_blueprints,
)
from openshores.database.repositories.empire import empire_for_avatar
from openshores.gameplay.blueprint_lookup import _blueprints_by_id
from openshores.protocol.atoms import design_exchange as _dx
from openshores.protocol.framing import write_framed
from openshores.world.chat_writer import _chat_only_writer

logger = get_logger(__name__)


async def on_blueprint_request(payload: bytes, actor: int, *,
                               _live_avatars: dict, _ACTIVE_CHAT_WRITER,
                               conn, _CITIZEN_EMPIRE_OVERRIDE) -> None:
    kind = payload[1] if len(payload) > 1 else 0
    actor_i = int(actor) & 0xFFFFFFFF
    if kind != 1:
        logger.info(f"[bp-exchange] 0xDE kind={kind} (not building). Not served yet")
        return
    empire = 0
    try:
        empire = int(await empire_for_avatar(
            conn, actor_i,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    except Exception as _ee:
        logger.warning(f"[bp-exchange] empire lookup for 0x{actor_i:08x} failed; "
                       f"player-empire logged as 0: {_ee!r}")
    reports, designs, names = [], [], []
    for row in await published_blueprints(conn):
        if not row["report_bytes"]:
            logger.warning(f"[bp-exchange] skip {row['stem']}: no report_bytes (decode-only?)")
            continue
        reports.append((bytes(row["report_bytes"]),
                        int(row["design_state"])))
        designs.append(bytes(row["design_blob"]))
        names.append(row["name"] or "?")
    if not reports:
        logger.warning('[bp-exchange] 0xDE: no real blueprints in hz_blueprint.')
        return
    ent = _live_avatars.get(actor_i) or {}
    w = _ACTIVE_CHAT_WRITER or _chat_only_writer(ent)
    if w is None or w.is_closing():
        logger.warning(f"[bp-exchange] 0xDE: no chat writer for 0x{actor_i:08x}; reply dropped")
        return
    try:
        reply = _dx.bd_exchange_reply_real(reports, empire=0)
        await write_framed(w, reply)
        _states = [r[1] for r in reports]
        logger.info(f"[bp-exchange] BUILD=2026-06-17-fields 0xDE -> {len(reports)} REAL blueprints "
                    f"({len(reply)}B) names={names} states={_states} (1=Final) "
                    f"to 0x{actor_i:08x} (player-empire 0x{empire:08x}, entry-empire=0)")
        for _db, _nm in zip(designs, names):
            push = _dx.bd_design_push(_db)
            await write_framed(w, push)
            logger.debug(f"[bp-exchange]   pushed 0xDF design {_nm!r} ({len(push)}B)")
    except Exception as _se:
        logger.warning(f"[bp-exchange] 0xDE/0xDF send err: {_se!r}")


async def on_design_request(payload: bytes, actor: int, *,
                            _live_avatars: dict, _ACTIVE_CHAT_WRITER,
                            conn) -> None:
    import struct as _struct
    actor_i = int(actor) & 0xFFFFFFFF
    if len(payload) < 5:
        logger.warning(f"[bp-design] 0xDF short payload: {payload.hex()}")
        return
    did = _struct.unpack_from(">I", payload, 1)[0]
    hit = await blueprint_by_design_id(conn, did)
    if hit is None:
        bps = await _blueprints_by_id(conn)
        logger.warning(f"[bp-design] 0xDF id=0x{did:08x} ({did}): no matching blueprint "
                       f"(have: {sorted(bps)})")
        return
    name, db = (hit["name"] or "?"), bytes(hit["design_blob"])
    ent = _live_avatars.get(actor_i) or {}
    w = _ACTIVE_CHAT_WRITER or _chat_only_writer(ent)
    if w is None or w.is_closing():
        logger.warning(f"[bp-design] 0xDF: no chat writer for 0x{actor_i:08x}")
        return
    try:
        push = _dx.bd_design_push(db)
        await write_framed(w, push)
        logger.info(f"[bp-design] 0xDF id={did} -> pushed design {name!r} ({len(push)}B) "
                    f"to 0x{actor_i:08x}")
    except Exception as _se:
        logger.warning(f"[bp-design] 0xDF push err: {_se!r}")
