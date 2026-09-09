
from __future__ import annotations

from typing import Awaitable, Callable, Optional

from openshores.core.logging import get_logger
from openshores.database.repositories.person import (
    _load_all_persons_from_sql,
    _lookup_person_by_auid,
)
from openshores.network import connection_state as _connection_state
from openshores.network.scene.creation_world import push_creation_world
from openshores.network.session_reset import _create_in_flight_active
from openshores.protocol.framing import write_framed
from openshores.protocol.scene_init import build_scene_init_succeeded
from openshores.protocol.scene_parse import _parse_scene_0x38

logger = get_logger(__name__)

_BOB_AUID = 0x5A3E6


async def handle_0x3b(
    conn,
    session,
    parser_s,
    *,
    conn_n: int,
    save,
    bootstrap_did_push: bool,
    sent_scene_init: bool,
    do_world_bootstrap: Callable[[str], Awaitable[None]],
) -> bool:
    unit_id = 0
    try:
        unit_id = parser_s.read_u32()
    except Exception as _uid_exc:
        logger.debug("[scene]   0x3B unit_id unreadable: %r", _uid_exc)
    logger.debug(f"[scene]   <- 0x3B SelectActiveUnit unit_id=0x{unit_id:08x}")

    known_auids = {int(save.person_auid)}
    try:
        for row in await _load_all_persons_from_sql(conn):
            known_auids.add(int(row["auid"]))
    except Exception as _roster_exc:
        logger.warning("[scene]   0x3B roster read failed: %r", _roster_exc)

    if (conn_n >= 1 and not bootstrap_did_push
            and not sent_scene_init
            and unit_id in known_auids):
        logger.info(f"[scene]   conn #{conn_n} SelectActiveUnit "
                    f"unit_id=0x{unit_id:08x} -> running world bootstrap")
        label = (
            "c1-select" if conn_n == 1
            else f"c{conn_n}-select")
        await do_world_bootstrap(label)
        return True
    elif unit_id != 0:
        logger.info(f'[scene]   conn #{conn_n} 0x3B unit_id=0x{unit_id:08x} not in known AuIds {sorted((hex(a) for a in known_auids))}.')
    return False


async def handle_0x38(
    conn,
    session,
    parser_s,
    *,
    writer,
    conn_n: int,
    save,
    active_avatar_auid: int,
    bootstrap_did_push: bool,
    sent_scene_init: bool,
    conn_tasks: list,
    do_world_bootstrap: Callable[[str], Awaitable[None]],
    ticker_c2_factory: Callable[[object], Awaitable[None]],
    build_scene_dn_detail_type,
    name_long: str,
    name_short: str,
    capital_name: str,
    _CITIZEN_EMPIRE_OVERRIDE: dict,
    _EMPIRE_NAME_OVERRIDE: dict,
    _EMPIRE_TAX_OVERRIDE: dict,
) -> tuple[int, bool, bool]:
    import asyncio as _asyncio

    fields = _parse_scene_0x38(parser_s)
    logger.debug(f"[scene]   0x38 fields: {fields}")

    cid = int(fields.get("charId", 0) or 0)

    if cid == 0 and _create_in_flight_active():
        if _connection_state._create_defer_replayed:
            logger.info(f'[scene]   conn #{conn_n} 0x38 charId=0.')
            return (active_avatar_auid, bootstrap_did_push, sent_scene_init)
        _connection_state._create_defer_replayed = True
        _person_atom = (_connection_state._create_person_auid_atom
                        or (b"\x00\x00\x00\x01" + b"\x00" * 12))
        logger.info(f'[scene]   conn #{conn_n} 0x38 charId=0 with a create in flight.')
        await push_creation_world(
            conn, writer, _person_atom,
            label="post-defer replay",
            save=save,
            build_scene_dn_detail_type=build_scene_dn_detail_type,
            name_long=name_long, name_short=name_short,
            capital_name=capital_name,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
        return (active_avatar_auid, bootstrap_did_push, sent_scene_init)

    known_auids = {int(save.person_auid)}
    try:
        for row in await _load_all_persons_from_sql(conn):
            known_auids.add(int(row["auid"]))
    except Exception as _roster_exc:
        logger.warning("[scene]   0x38 roster read failed: %r", _roster_exc)
    known_auids.add(_BOB_AUID)

    if (conn_n >= 1 and not bootstrap_did_push
            and not sent_scene_init
            and cid in known_auids):
        active_avatar_auid = cid
        own_lookup = await _lookup_person_by_auid(conn, int(cid))
        owner_name = (
            own_lookup["name"]
            if own_lookup and own_lookup.get("name")
            else save.person_name)
        logger.info(f"[scene]   conn #{conn_n} ResumeEmpire "
                    f"charId=0x{cid:08x} ({owner_name}) "
                    f"-> running world bootstrap")
        bootstrap_did_push = True
        label = ("c1-resume" if conn_n == 1
                 else f"c{conn_n}-resume")
        await do_world_bootstrap(label, cid)
        return (active_avatar_auid, bootstrap_did_push, True)
    elif conn_n >= 1 and cid != 0:
        if cid not in known_auids:
            why = (f"not in known AuIds "
                   f"{sorted(hex(a) for a in known_auids)}")
        elif bootstrap_did_push:
            why = "bootstrap already fired this session (dup 0x38 retry)"
        elif sent_scene_init:
            why = "scene init already sent"
        else:
            why = "gate logic mismatch"
        logger.info(f"[scene] conn #{conn_n} 0x38 charId=0x{cid:08x}. {why}.")

    if bootstrap_did_push and not sent_scene_init:
        sent_scene_init = True
        conn_label = "conn2"
        logger.info(f"[scene]   {conn_label}: client ready -> "
                    f"sending 0x2A + 0x38 + ticker "
                    f"(charId={fields.get('charId')})")

        person_auid_fallback = int(active_avatar_auid or save.person_auid)
        pkt_2a = bytes([0x2A]) + person_auid_fallback.to_bytes(4, "big")
        await write_framed(writer, pkt_2a)
        logger.debug(f"[scene]   -> {conn_label} 0x2A "
                     f"InitSucceeded(playerUnit="
                     f"0x{person_auid_fallback:08x}) "
                     f"({len(pkt_2a)}B)")

        import time as _tt
        ausec = int(_tt.time() * 1_000_000)
        sls = build_scene_init_succeeded(
            motd=save.motd, autime_usec=ausec)
        await write_framed(writer, sls)
        logger.debug(f"[scene]   -> {conn_label} 0x38 "
                     f"InitSucceeded ({len(sls)}B)")

        conn_tasks.append(
            _asyncio.create_task(ticker_c2_factory(writer)))
        logger.info("[scene]   -> conn2 ticker started "
                    "(4 Hz, 0x18 flag=2 heartbeat)")

    return (active_avatar_auid, bootstrap_did_push, sent_scene_init)
