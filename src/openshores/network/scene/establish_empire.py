
from __future__ import annotations

from typing import Awaitable, Callable

from openshores.core.accounts import default_store
from openshores.core.config import Deployment
from openshores.core.logging import get_logger
from openshores.core.whereabouts import write_whereabouts_all
from openshores.database.repositories.empire import (
    empire_for_avatar,
    found_empire,
)
from openshores.database.repositories.person import (
    clear_synthetic_auid,
    create_character,
    create_person,
)
from openshores.gameplay.avatar_stats import _avatar_start_stats
from openshores.gameplay.homestead import (
    DEFAULT_POLICY,
    GALAXY_CHOICES,
    REGION_NAMES,
    HomesteadError,
    describe_policy,
    policy_for_name,
)
from openshores.gameplay.spawn import _homestead_with_retry
from openshores.gameplay.story_state import story_mark_pending
from openshores.network import connection_state as _connection_state
from openshores.network import session_reset as _session_reset
from openshores.network.peer_ip_state import (
    _variant_b_handled_get,
    _variant_b_handled_set,
)
from openshores.network.scene.creation_world import push_creation_world
from openshores.network.session_reset import _create_in_flight_active
from openshores.protocol import scene_parse as _scene_parse
from openshores.protocol.completion_chain import build_scene_scene_logged_in
from openshores.protocol.framing import write_framed
from openshores.protocol.scene_init import build_scene_world_redirect
from openshores.protocol.scene_parse import _parse_scene_0x24

logger = get_logger(__name__)


_variant_b_last_payload: dict = {}

PLACEHOLDER_PERSON_AUID = (0x7F000001).to_bytes(4, "big")


async def handle_0x24(
    conn,
    session,
    parser_s,
    *,
    writer,
    conn_n: int,
    sent_scene_init: bool,
    peer_host: str,
    active_avatar_auid: int,
    bootstrap_did_push: bool,
    do_world_bootstrap: Callable[..., Awaitable[None]],
    save,
    build_scene_dn_detail_type,
    _live_avatars: dict,
    session_usernames_by_ip: dict,
    variant_b_handled_by_ip: dict,
    _STORY_PENDING,
    name_long: str,
    name_short: str,
    capital_name: str,
    _CITIZEN_EMPIRE_OVERRIDE: dict,
    _EMPIRE_NAME_OVERRIDE: dict,
    _EMPIRE_TAX_OVERRIDE: dict,
) -> None:
    import asyncio as _asyncio
    import struct as _struct
    import time as _tmod

    _expect_b = None
    if _create_in_flight_active() and _connection_state._create_defer_replayed:
        _expect_b = True
    parsed_0x24 = _parse_scene_0x24(
        parser_s, expect_variant_b=_expect_b,
        _create_defer_echo_world=_connection_state._create_defer_echo_world,
        GALAXY_CHOICES=GALAXY_CHOICES, REGION_NAMES=REGION_NAMES)
    logger.debug(f"[scene]   0x24 fields: {parsed_0x24}")

    if ((parsed_0x24 or {}).get("_variant") == "A_establish_first_empire"
            and conn_n >= 1 and bootstrap_did_push
            and int(active_avatar_auid) != 0):
        _founder = int(active_avatar_auid) & 0xFFFFFFFF
        _cur_emp = int(await empire_for_avatar(
            conn, _founder,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
        if _cur_emp == 0:
            _ename = (parsed_0x24 or {}).get("empireName") or ""
            try:
                _new_eid = await found_empire(
                    conn, _founder, _ename,
                    _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
            except Exception as _fe:
                logger.error(f"[scene] 0x24 found-empire error (non-fatal): {_fe!r}")
                _new_eid = 0
            if _new_eid:
                logger.info(f'[scene]   0x24 FOUND EMPIRE: avatar 0x{_founder:08x} -> empire 0x{_new_eid:08x} {_ename!r}.')
                try:
                    _deployment = Deployment.from_env()
                    sli = build_scene_scene_logged_in(
                        scene_name=_deployment.public_host,
                        port=_deployment.scene_port,
                        flag=2)
                    await write_framed(writer, sli)
                except Exception as _se:
                    logger.warning(f"[scene]   0x24 found-empire reconnect err: {_se!r}")
                return

    is_variant_b = (parsed_0x24 or {}).get("_variant") == "B_avatar_submit"

    if not is_variant_b and (parsed_0x24 or {}).get("origin_plausible"):
        _scene_parse._last_avatar_origin = (int(parsed_0x24["origin_galaxy"]),
                                            int(parsed_0x24["origin_region"]))
        logger.debug(f"[scene]   0x24 origin stashed: "
                     f"{_scene_parse._last_avatar_origin}")
    if is_variant_b:
        _vb_holder = _live_avatars.get(0x1)
        if _vb_holder is not None:
            _vb_w = _vb_holder.get("writer")
            if _vb_w is not None and not _vb_w.is_closing():
                logger.warning("[scene] 0x24 variant B rejected: another fresh avatar is already in flight (synth=0x1 holder writer is still online).")
                return
            else:
                logger.info("[scene]   0x24 variant B: clearing "
                            "stale synth=0x1 _live_avatars entry "
                            "(writer closed)")
                _live_avatars.pop(0x1, None)
                clear_synthetic_auid(0x1)
        _vb_name = (parsed_0x24 or {}).get("charName")
        _vb_blob = (parsed_0x24 or {}).get("avatar_blob")
        _vb_payload = (_vb_name, _vb_blob)

        _live_ent = _live_avatars.get(int(active_avatar_auid or 0))
        if (isinstance(_live_ent, dict) and _live_ent.get("writer") is writer
                and int(active_avatar_auid or 0) != 0):
            logger.warning(f"[scene] 0x24 variant B refused: this socket is already carrying live avatar 0x{int(active_avatar_auid):08x}.")
            return

        if _variant_b_handled_get(
                peer_host, variant_b_handled_by_ip=variant_b_handled_by_ip):
            if _vb_payload == _variant_b_last_payload.get(peer_host):
                logger.info('[scene]   0x24 variant B (DUPLICATE re-send, same name+DNA).')
                return
            if not (_vb_name and _vb_blob):
                logger.info('[scene]   0x24 variant B (null/partial ack after a completed create).')
                return
            logger.info(f'[scene]   0x24 variant B: payload differs ({_vb_name!r}) on host {peer_host}.')
            _variant_b_handled_set(
                peer_host, False,
                variant_b_handled_by_ip=variant_b_handled_by_ip)
        _variant_b_last_payload[peer_host] = _vb_payload

        _pb_0x24 = parsed_0x24 or {}
        _is_null_ack = (
            _pb_0x24.get("charName") is None
            and _pb_0x24.get("avatar_blob") is None
        )
        if sent_scene_init and _is_null_ack:
            logger.info('[scene]   0x24 variant B (post-resume ack, null charName+blob).')
            _variant_b_handled_set(
                peer_host, True,
                variant_b_handled_by_ip=variant_b_handled_by_ip)
            return

        _variant_b_handled_set(
            peer_host, True,
            variant_b_handled_by_ip=variant_b_handled_by_ip)
        logger.info("[scene]   0x24 variant B -> persisting avatar")

        _vb_new_id = None

        try:
            _b_u0 = int(parsed_0x24.get("u32_0") or 0)
            _b_u1 = int(parsed_0x24.get("u32_1") or 0)
            _b_u2 = int(parsed_0x24.get("u32_2") or 0)
            _echo_ok = bool(parsed_0x24.get("echo_matches_our_0x22"))
            logger.debug(f"[scene]   variant B defer echo: "
                         f"idSectorOrWorld=0x{_b_u0:08x} "
                         f"idEmpire=0x{_b_u1:08x} "
                         f"u32_2=0x{_b_u2:08x}  "
                         f"({'matches' if _echo_ok else 'does NOT match'} the 0x22 "
                         f"we sent"
                         + ("" if not _connection_state._create_defer_echo_world else
                            f", ours was 0x{_connection_state._create_defer_echo_world:08x}")
                         + ")")
            if not _echo_ok and _connection_state._create_defer_echo_world:
                logger.warning("[scene]")
        except Exception as _auid_exc:
            logger.warning(f"[scene] variant B defer-echo decode failed (non-fatal): {_auid_exc!r}")

        try:
            _bname = parsed_0x24.get("charName") or save.person_name
            _bhex = parsed_0x24.get("avatar_blob") or (
                (save.person_dna24.hex() if save.person_dna24 else "00" * 24))
            logger.debug(f"[scene]   variant B raw: charName={_bname!r} "
                         f"blob_hex={_bhex} (len={len(_bhex)//2}B)")
            _bdna = bytes.fromhex(_bhex)[:24]
            if len(_bdna) < 24:
                _bdna += b"\x00" * (24 - len(_bdna))
            logger.debug(f"[scene]   persisted avatar (in-memory): "
                         f"name={_bname!r} "
                         f"dna={_bdna.hex()}")


            try:
                _homesteaded = False
                _homestead_world = ""
                if getattr(_scene_parse, "_last_avatar_origin", None):
                    _g, _r = _scene_parse._last_avatar_origin
                    _GC, _RN, _HE = GALAXY_CHOICES, REGION_NAMES, HomesteadError
                    try:
                        logger.info(f'[scene]   variant B: homesteading {_bname!r} in {_GC.get(_g, _g)} / {(_RN[_r] if 0 <= _r < len(_RN) else _r)}.')
                        _hs_t0 = _tmod.monotonic()
                        _new_id, _home = await create_character(
                            conn,
                            _bname, _bdna,
                            stats=_avatar_start_stats(_bdna),
                            homestead_with_retry=_homestead_with_retry,
                            policy_for_name=policy_for_name,
                            DEFAULT_POLICY=DEFAULT_POLICY,
                            describe_policy=describe_policy,
                            galaxy=_GC[_g], region=_r)
                        logger.info(f"[scene]   variant B: homestead search took "
                                    f"{_tmod.monotonic() - _hs_t0:.1f}s")
                        _homesteaded = True
                        _homestead_world = _home.home_globe_name or ""
                        logger.info(f"[scene]   variant B: homesteaded "
                                    f"{_bname!r} on "
                                    f"{_home.home_globe_name!r} in "
                                    f"{_home.system_name!r} "
                                    f"({_GC[_g]} / {_RN[_r]})")
                    except _HE as _he:
                        _new_id = None
                        logger.error(f"[scene] homestead failed after retries ({_he}); not creating the character. The chosen Origin {_GC.get(_g, _g)} / {(_RN[_r] if 0 <= _r < len(_RN) else _r)} could not be honoured.")
                    finally:
                        _scene_parse._last_avatar_origin = None
                else:
                    _new_id = await create_person(
                        conn, _bname, _bdna,
                        stats=_avatar_start_stats(_bdna))
                if _new_id is not None:
                    _vb_new_id = int(_new_id)
                    logger.info(f"[scene]   variant B: created "
                                f"a_Person id={_new_id} "
                                f"name={_bname!r}")
                    logger.info('[scene]   variant B: no _last_avatar_auid captured.')
                    _link_user = ""
                    try:
                        _scene_peer = writer.get_extra_info(
                            "peername")
                        _scene_host = (_scene_peer[0]
                            if isinstance(_scene_peer, tuple)
                            else "")
                    except Exception:
                        _scene_host = ""
                    if _scene_host:
                        _link_user = (
                            session_usernames_by_ip.get(
                                _scene_host, ""))
                    if not _link_user:
                        _link_user = _session_reset._session_username
                        if _link_user and _scene_host:
                            logger.info(f"[scene]   variant B: "
                                        f"per-IP session miss for "
                                        f"{_scene_host!r}; falling "
                                        f"back to legacy global "
                                        f"username {_link_user!r}")
                    if _link_user:
                        try:
                            _was_new = (default_store()
                                .add_avatar(
                                    _link_user, _new_id))
                            if _was_new:
                                logger.info(f"[scene]   variant B: "
                                            f"linked avatar "
                                            f"{_new_id} -> account "
                                            f"{_link_user!r}")
                            else:
                                logger.info(f"[scene]   variant B: "
                                            f"avatar {_new_id} "
                                            f"already linked to "
                                            f"account "
                                            f"{_link_user!r} "
                                            f"(no-op)")
                        except Exception as _link_exc:
                            logger.error(f"[scene] variant B: account link failed: {_link_exc!r}")
                    else:
                        logger.warning(f"[scene] variant B: no active session username for scene host {_scene_host!r}. Avatar not linked to any account")
                    logger.info(f'[scene]   variant B: avatar {_new_id} left UNAFFILIATED (no auto-empire.')
                    try:
                        _wb_where = (_homestead_world
                                     or save.whereabouts_display)
                        if _link_user and _wb_where:
                            _ww_seed = write_whereabouts_all
                            _wb_n = _ww_seed(
                                _link_user, _wb_where, verbose=False)
                            if _wb_n > 0:
                                logger.info(f"[scene]   variant B: "
                                            f"whereabouts seeded for "
                                            f"{_link_user!r} ({_wb_n} reg "
                                            f"base(s)) -> "
                                            f"{_wb_where!r}")
                    except Exception as _wbx:
                        logger.warning(f"[scene] variant B: whereabouts seed failed (non-fatal): {_wbx!r}")
                else:
                    logger.warning("[scene]   variant B: NO avatar row was created "
                                   "(see the reason logged above)")
            except Exception as _db_exc:
                import traceback as _tb
                logger.error(f"[scene] variant B DB create failed: {_db_exc!r}")
                _tb.print_exc()
        except Exception as _persist_exc:
            import traceback
            logger.error(f"[scene] variant B persistence failed: {_persist_exc!r}")
            traceback.print_exc()


        if _vb_new_id is None:
            _connection_state._create_in_flight_end(
                "variant B produced no avatar")
            logger.warning("[scene] variant B: not sending 0x2A.")
            return

        try:
            story_mark_pending(int(_vb_new_id), _STORY_PENDING=_STORY_PENDING)
        except Exception as _vb_story_exc:
            logger.warning(f"[story] could not mark 0x{int(_vb_new_id):08x} pending "
                           f"(non-fatal): {_vb_story_exc!r}")

        logger.info(f"[scene]   variant B: bootstrapping avatar 0x{_vb_new_id:08x} "
                    f"in place -> atoms + DataComplete + 0x2A InitSucceeded")
        try:
            await do_world_bootstrap("variantB-inline", _vb_new_id)
        except Exception as _vb_boot_exc:
            import traceback as _vbtb
            logger.error(f"[scene] variant B inline bootstrap failed: {_vb_boot_exc!r}")
            _vbtb.print_exc()
        finally:
            _connection_state._create_in_flight_end("variant B committed")
        return

    AUID_UNI_A    = b"\x00\x00\x01\x01" + b"\x00" * 12
    AUID_GAL_A    = b"\x00\x00\x01\x02" + b"\x00" * 12
    AUID_SEC_A    = b"\x00\x00\x01\x03" + b"\x00" * 12
    AUID_SYS_A    = b"\x00\x00\x01\x04" + b"\x00" * 12
    AUID_STAR_A   = b"\x00\x00\x01\x05" + b"\x00" * 12
    AUID_WORLD_A  = b"\x00\x00\x01\x07" + b"\x00" * 12
    AUID_PERSON_A = PLACEHOLDER_PERSON_AUID + b"\x00" * 12

    _connection_state._create_person_auid_atom = AUID_PERSON_A

    await push_creation_world(
        conn, writer, AUID_PERSON_A, label="variant A",
        save=save,
        build_scene_dn_detail_type=build_scene_dn_detail_type,
        name_long=name_long, name_short=name_short,
        capital_name=capital_name,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)

    _defer_world = int(save.planet_auid or 1) & 0xFFFFFFFF
    _deployment = Deployment.from_env()
    _redir = build_scene_world_redirect(
        server_name=_deployment.public_host, port=_deployment.scene_port,
        world_state=2,
        account_id_lo=_defer_world, account_id_hi=0)
    await write_framed(writer, _redir)
    _connection_state._create_defer_echo_world = _defer_world
    _connection_state._create_in_flight_begin()
    logger.info(f'[scene]   -> 0x22 EstDeferred handoff after variant A ({len(_redir)}B).')
