
from __future__ import annotations

import asyncio
import functools as _functools
import inspect as _inspect
import struct
import time as _tconn_init
import time as _time_mod
from dataclasses import replace

from openshores.core.logging import get_logger
from openshores.database.journal import get_queue
from openshores.network.connection_state import (
    _cleanup_ip_state_if_idle,
    _clear_init_ack,
    _conn0_hold_reason,
    _init_ack_event,
)
from openshores.database.repositories.bundle_retarget import (
    _retarget_bundle_to_avatar,
)
from openshores.database.repositories.empire import empire_for_avatar
from openshores.database.repositories.city import (
    planet_city_ids,
    planet_city_atom_rows,
)
from openshores.database.repositories.person import (
    _load_all_persons_from_sql,
    _load_augear_from_sql,
    _lookup_person_by_auid,
    clear_synthetic_auid,
    mark_offline,
    mark_online,
    read_person_inv,
    read_person_state,
    update_person_position,
    update_person_state,
)
from openshores.database.repositories.planet_time import (
    _flush_planet_times,
    _stable_planet_time_ms,
)
from openshores.database.repositories.world import (
    dropped_items_load_all,
    read_atom_gasgiant,
    read_atom_globe,
)
from openshores.gameplay.augear_registry import _get_augear
from openshores.gameplay.avatar_registry import (
    _STORY_PENDING,
    _STORY_TASKS,
    _tock_state,
)
from openshores.gameplay.city_model import developments_from_blob
from openshores.gameplay.food import _hunger_i16
from openshores.gameplay.vehicle_registry import (
    _PENDING_DISMOUNT,
    _PLAYER_MOUNTED_VEHICLE,
    _VEH_PARENT_WATCH,
)
from openshores.gameplay.condition_registry import _CONDITION_STATES
from openshores.gameplay.combat.damage import _register_damageable_npcs
from openshores.gameplay.dacity_frame import build_scene_dacity
from openshores.gameplay.detail_types import (
    build_scene_all_dn_detail_types_0x2f,
    build_scene_dn_detail_type,
)
from openshores.gameplay.empire.dg_empire import build_scene_dg_empire_0x31
from openshores.gameplay.gd_all_tables import (
    build_scene_all_db_commodity_0x2b,
    build_scene_all_db_construction_component_0x2c,
    build_scene_all_db_construction_process_0x2d,
    build_scene_all_db_industry_0x32,
    build_scene_all_db_manufacturing_component_0x33,
    build_scene_all_db_manufacturing_process_0x34,
)
from openshores.gameplay.ground_registry import (
    _DROPPED_ITEMS,
    _FORAGE_WARMUP_BY_WORLD,
)
from openshores.gameplay.fauna_world import _build_fauna_entries
from openshores.gameplay.ground_snap import _peer_upright_euler
from openshores.gameplay.room_types import (
    build_scene_all_dn_room_types_0x30,
    build_scene_dn_room_type,
)
from openshores.gameplay.scene_manifest import _DYNAMIC_SCENE_AUIDS
from openshores.gameplay.vehicles.atom_packet import (
    build_da_vehicle_update,
    build_scene_atoms,
)
from openshores.gameplay.vehicles.spawn import (
    commit_vehicle,
    get_active_vehicle,
    list_active_vehicles,
)
from openshores.gameplay.world_atoms import _WORLD_ATOM_AUIDS
from openshores.gameplay.story_state import _STORY_UI_ON, _story_task_done
from openshores.gameplay.world_body import _build_wg_body
from openshores.gameplay.worldgen.ring_reference import _ring_ref_section_auid
from openshores.protocol.atoms.base_update import _bpt2, _bpt2_tc
from openshores.protocol.atoms.gear import _pack_au_gear
from openshores.protocol.atoms.gear_variety import _build_variety_gear_entries
from openshores.protocol.atoms.daitem_drop import _build_daitem_drop_packet
from openshores.protocol.atoms.item import _extract_cid_from_auitem_body
from openshores.protocol.atoms.item_seed import _pack_auitem_seed_body
from openshores.protocol.atoms.weapon import _weapon_cid_sets
from openshores.network.bio_ticker import start_bio_ticker
from openshores.network.broadcast import _MANIFEST_SUPPRESS
from openshores.network.chat_state import _PENDING_CHAT_AUIDS
from openshores.network.fauna_loops import start_fauna_loops
from openshores.network.peer_ip_state import (
    _scene_connect_n_dec,
    _scene_connect_n_inc,
    _variant_b_handled_get,
)
from openshores.network.session_reset import (
    _create_in_flight_active,
    _create_in_flight_end,
)
from openshores.network.commodity_overrides import _send_commodity_overrides
from openshores.network.pickup import _try_pickup_from_target_pin
from openshores.network.scene_probes import SCENE_PROBES
from openshores.network.vehicle_lifecycle import _finalize_vehicle_dismount
from openshores.network.vehicle_mount import _finalize_vehicle_mount
from openshores.network.vehicle_terrain import _VEH_PARENT_FLOOR
from openshores.network.weapon_reload import _handle_reload_weapon_trigger
from openshores.network.planet_geo_resend import _WG_ATOM_HDR, _WG_GEO_PARTS
from openshores.network.daitem_lifecycle import _daitem_lifecycle
from openshores.network.static_tables import (
    _static_tables_already_sent,
    _static_tables_key,
    _static_tables_mark_sent,
)
from openshores.network.scene.adhoc import _handle_scene_adhoc
from openshores.network.scene.bootstrap_flow import handle_0x38, handle_0x3b
from openshores.network.scene.establish_empire import handle_0x24
from openshores.network.scene.ticker_c2 import _ticker_c2_factory
from openshores.network.scene.conn_tickers import (
    start_corpse_sweeper,
    start_manifest_ticker,
    start_natives_idle_ticker,
    start_story_npc_ticker,
    start_ticker_eager,
)
from openshores.network.scene.conn0 import (
    _CONN0_HOLD_REASONS,
    _conn0_redirect_decision,
    _frame_is_resume_hello,
)
from openshores.network.scene.hello import (
    _frame_is_new_avatar_hello,
    _scene_hello_char_id,
)
from openshores.network.scene.manifest import _build_scene_manifest
from openshores.network.vehicle_loops import _davehicle_keepalive_start
from openshores.world.registry import (
    attach_to_live_avatars,
    detach_from_live_avatars,
)
from openshores.protocol.completion_chain import build_scene_empire_data_complete
from openshores.protocol.delta_tick import parse as _parse_delta_tick
from openshores.protocol.scene_opcodes import _ACK_OPCODES, SCENE_OP_NAMES
from openshores.protocol.stream import QDS
from openshores.protocol.framing import (
    read_framed,
    write_framed,
    write_framed_burst,
)
from openshores.protocol.scene_init import (
    build_scene_init_succeeded,
    build_scene_world_redirect,
)
from openshores.core.config import Deployment
from openshores.world.session import Session

logger = get_logger(__name__)

_GRAB_PROBE_LAST: dict = {}


async def handle_scene(conn, reader, writer, *,
                       _SAVE,
                       PUBLIC_HOST: str,
                       _FIRST_FRAME_WAIT_SEC: float,
                       _live_avatars: dict,
                       _CITIZEN_EMPIRE_OVERRIDE: dict,
                       _get_starmap_blob,
                       _scene_connect_n_by_ip: dict,
                       _variant_b_handled_by_ip: dict,
                       force_closed_once_by_ip: dict,
                       session_usernames_by_ip: dict,
                       _SHOW_ACKS: bool,
                       SCENE_PROBE_NAME: str,
                       OPCODE_HANDLERS: dict,
                       _handle_fire_weapon_trigger,
                       _last_avatar_name: str,
                       _last_avatar_dna: bytes,
                       actor_cursor: dict,
                       agent_bits_for,
                       _build_augear_only_daperson_update,
                       gather_planet_roads,
                       get_or_init_planet_geo,
                       _stamina_byte,
                       augear_states: dict,
                       alloc_daitem_auid,
                       raise_daitem_auid_floor,
                       name_long: str,
                       name_short: str,
                       capital_name: str,
                       _EMPIRE_NAME_OVERRIDE: dict,
                       _EMPIRE_TAX_OVERRIDE: dict,
                       sim_time_anchor_full: int,
                       sim_time_state: dict,
                       natives_idle_bodies,
                       spawn_world_flag,
                       story_npcs,
                       story_atom_id,
                       story_name,
                       SiblingGlobe, gen_planet, gen_moon, HAB_RANDOM,
                       wch, wc, tr) -> None:
    _SAVE = replace(_SAVE)
    peer = writer.get_extra_info("peername")
    _peer_host_scene = peer[0] if isinstance(peer, tuple) and peer else ""
    conn_n = _scene_connect_n_inc(
        _peer_host_scene, scene_connect_n_by_ip=_scene_connect_n_by_ip)
    _conn_t0 = _tconn_init.monotonic()
    _last_rx_t = None
    _last_rx_op = None
    _op_tally: dict = {}
    _session = Session(
        writer=writer,
        peer=peer if isinstance(peer, tuple) else ("?", 0),
        peer_host=_peer_host_scene,
        conn_n=conn_n,
        conn_t0=_conn_t0,
    )
    _conn_tasks: list = _session.conn_tasks
    _announced_scene = False

    try:
        first_frame = await asyncio.wait_for(read_framed(reader), timeout=0.3)
    except asyncio.TimeoutError:
        first_frame = None
        if not _announced_scene:
            logger.info(
                f"[scene] {peer} connected  (conn #{conn_n})  t0={_conn_t0:.3f}")
            _announced_scene = True
    except (asyncio.IncompleteReadError, ConnectionError) as e:
        if _announced_scene:
            logger.info(f"[scene]   early disconnect: {e!r}")
        else:
            _scene_connect_n_dec(
                _peer_host_scene, scene_connect_n_by_ip=_scene_connect_n_by_ip)
        writer.close()
        return

    if first_frame and not _announced_scene:
        logger.info(
            f"[scene] {peer} connected  (conn #{conn_n})  t0={_conn_t0:.3f}")
        _announced_scene = True

    if first_frame and first_frame[0] in (0x35, 0x3C):
        _scene_connect_n_dec(
            _peer_host_scene, scene_connect_n_by_ip=_scene_connect_n_by_ip)
        await _handle_scene_adhoc(
            conn, first_frame, writer, peer,
            _live_avatars=_live_avatars,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _get_starmap_blob=_get_starmap_blob)
        return

    bootstrap_did_push = False
    _active_avatar_auid: int = int(_SAVE.person_auid)
    sent_scene_init = False
    _pending_first_frame = first_frame
    _dt_debug_count = 0
    _DT_DEBUG_BUDGET = 6

    try:
        _no_redirect = False

        _create_live = _create_in_flight_active()
        if (conn_n == 0 and first_frame is None
                and not _no_redirect and not _create_live):
            try:
                first_frame = await asyncio.wait_for(
                    read_framed(reader), timeout=_FIRST_FRAME_WAIT_SEC)
                _pending_first_frame = first_frame
            except asyncio.TimeoutError:
                logger.info(f'[scene]   conn #0 said nothing for {_FIRST_FRAME_WAIT_SEC:.0f}s.')
            except (asyncio.IncompleteReadError, ConnectionError) as _ffe:
                logger.info(f"[scene] conn #0 closed while waiting for its first frame: {_ffe!r}")
                writer.close()
                return

        if _create_live and _frame_is_resume_hello(
                first_frame, _scene_hello_char_id=_scene_hello_char_id):
            _create_in_flight_end("client sent a resume hello instead")
            _create_live = False

        _conn0_decision = _conn0_redirect_decision(
            conn_n, first_frame,
            create_in_flight=_create_live,
            no_redirect=_no_redirect,
            _frame_is_new_avatar_hello=_frame_is_new_avatar_hello)
        if conn_n == 0 and _conn0_decision != "redirect":
            _extra = (f" (client hairpinned in from {_peer_host_scene!r})"
                      if _conn0_decision == "create_in_flight" else "")
            logger.info(
                f"[scene]   "
                f"{_conn0_hold_reason(_conn0_decision, conn0_hold_reasons=_CONN0_HOLD_REASONS)}"
                f"{_extra}")
        elif conn_n == 0:
            _scene_port = Deployment.from_env().scene_port
            redirect = build_scene_world_redirect(
                server_name=PUBLIC_HOST, port=_scene_port, world_state=2,
                account_id_lo=1, account_id_hi=0, extra=0)
            await write_framed(writer, redirect)
            logger.info(f"[scene]   -> 0x22 WORLD_REDIRECT state=2 "
                        f"port={_scene_port} ({len(redirect)}B)")

        async def _do_world_bootstrap(_boot_label: str,
                                      _override_auid: int = 0) -> None:
            nonlocal sent_scene_init, _active_avatar_auid
            _is_create_finish = "variantB-inline" in _boot_label
            if _override_auid:
                _active_avatar_auid = int(_override_auid)
                logger.info(f"[scene]   {_boot_label}: _active_avatar_auid "
                            f"pinned to 0x{_active_avatar_auid:08x} "
                            f"(override from 0x38 handler)")
            logger.info(
                f"[scene]   {_boot_label} bootstrap: pushing empire + atoms (deferring 0x38/0x2A)")
            try:
                await _send_commodity_overrides(writer)
            except Exception as _co_exc:
                logger.warning(f"[commodity] {_boot_label} override push failed: "
                               f"{_co_exc!r}")

            logger.info(f"[scene] {_boot_label} 0x29 prelude suppressed (v56: case-0x29 is abort+reconnect, not ack.")

            _universe_auid_int = int(_SAVE.universe_auid)
            _person_auid_int = int(_active_avatar_auid)
            if int(_person_auid_int) != int(_SAVE.person_auid):
                logger.info("[scene]   active-avatar bootstrap: "
                            "_person_auid_int = 0x%08x "
                            "(save default was 0x%08x)" % (
                                _person_auid_int, int(_SAVE.person_auid)))

            if _variant_b_handled_get(
                    _peer_host_scene,
                    variant_b_handled_by_ip=_variant_b_handled_by_ip):
                logger.info(f"[scene] {_boot_label} _variant_b_handled set but _last_avatar_auid=0. Using save AuId 0x{_person_auid_int:08x} unchanged")


            for name, pkt in [
                ("DnDetailType0", build_scene_dn_detail_type(0, "Human", "")),
                ("DnRoomType0", build_scene_dn_room_type(0, "Hall", "")),
            ]:
                await write_framed(writer, pkt)
                logger.info(f"[scene]   -> conn2 {name} ({len(pkt)}B)")

            await _retarget_bundle_to_avatar(
                conn, _SAVE, int(_person_auid_int),
                SiblingGlobe=SiblingGlobe, gen_planet=gen_planet,
                gen_moon=gen_moon, HAB_RANDOM=HAB_RANDOM, wch=wch, wc=wc,
                tr=tr)
            _sector_auid_int = int(_SAVE.sector_auid) or 0x00000103
            _system_auid_int = int(_SAVE.system_auid) or 0x00000104
            _planet_auid_int = int(_SAVE.planet_auid) or 0x00000107
            _layer2_gas_giant = None
            _layer2_world_idp = 0
            try:
                _world_row_self = await read_atom_globe(
                    conn, int(_planet_auid_int))
                if _world_row_self:
                    _layer2_world_idp = int(
                        _world_row_self.get("idp") or 0)
                    logger.info(
                        f"World {_planet_auid_int:#x} SQL idp={_layer2_world_idp:#x} ({_world_row_self.get('name')!r}, locXYZ={_world_row_self.get('locXYZ')})")
                    if _layer2_world_idp:
                        _gg_row = await read_atom_gasgiant(
                            conn, _layer2_world_idp)
                        if _gg_row:
                            _layer2_gas_giant = _gg_row
                            logger.info(
                                f"Layer 2: world's parent {_layer2_world_idp:#x} is gas giant {_gg_row['name']!r}.")
                            _moon_xyz = _world_row_self.get(
                                "locXYZ")
                            if _moon_xyz and _moon_xyz != (
                                    0.0, 0.0, 0.0):
                                logger.info(
                                    f"Layer 2: override _SAVE.planet_position {_SAVE.planet_position} -> {_moon_xyz} (SQL locXYZ, gas-giant-relative)")
                                _SAVE.planet_position = _moon_xyz
                        else:
                            logger.info(
                                f"Layer 2: world's parent {_layer2_world_idp:#x} is not a gas giant (or unknown).")
                else:
                    logger.info(
                        f"World {_planet_auid_int:#x} not in a_WorldGlobe SQL")
            except Exception as _l2_diag_e:
                logger.warning(f"Layer 2 lookup err: {_l2_diag_e!r}")
            try:
                _person_sql = await read_person_state(
                    conn, int(_person_auid_int))
                if _person_sql and "idp" in _person_sql:
                    _sql_idp = int(_person_sql["idp"])
                    if (_sql_idp
                            and _sql_idp != int(_planet_auid_int)):
                        _world_row = await read_atom_globe(conn, _sql_idp)
                        if _world_row:
                            logger.info(
                                f"SQL idp override: world 0x{_planet_auid_int:08x} ({_SAVE.planet_name!r}) -> 0x{_sql_idp:08x} ({_world_row['name']!r}) new locXYZ={_world_row['locXYZ']}")
                            _planet_auid_int = _sql_idp
                            if _world_row.get("name"):
                                _SAVE.planet_name = _world_row[
                                    "name"]
                            if _world_row.get("locXYZ") and (
                                    _world_row["locXYZ"]
                                    != (0.0, 0.0, 0.0)):
                                _SAVE.planet_position = _world_row[
                                    "locXYZ"]
                            _layer2_world_idp = int(
                                _world_row.get("idp") or 0)
                            _gg_row = await read_atom_gasgiant(
                                conn, _layer2_world_idp)
                            if _gg_row:
                                _layer2_gas_giant = _gg_row
                                logger.info(
                                    f"Layer 2: world's parent 0x{_layer2_world_idp:08x} resolved to gas giant {_gg_row['name']!r}.")
                        else:
                            logger.info(
                                f"SQL idp 0x{_sql_idp:08x} is not a known a_WorldGlobe. Keeping save default 0x{_planet_auid_int:08x}")
            except Exception as _idp_e:
                logger.warning(f"SQL idp override err (non-fatal): {_idp_e!r}")
            _AU = struct.pack(">I", _universe_auid_int)
            _AG = struct.pack(">I", int(_SAVE.galaxy_auid) or 0x102)
            _AS = struct.pack(">I", _sector_auid_int)
            _AY = struct.pack(">I", _system_auid_int)
            _AT = struct.pack(">I", int(_SAVE.celestial_body_auid) or 0x0005a66d)
            _AW = struct.pack(">I", _planet_auid_int)
            _world_parent_AP = _AT
            try:
                _layer2_world_idp = locals().get("_layer2_world_idp")
                if _layer2_world_idp:
                    _cb_int = int(_SAVE.celestial_body_auid) or 0x0005a66d
                    if int(_layer2_world_idp) != _cb_int:
                        _world_parent_AP = struct.pack(
                            ">I", int(_layer2_world_idp))
                        logger.info(
                            f"Layer 2: world wire parent -> 0x{int(_layer2_world_idp):08x} (was 0x{_cb_int:08x}=_AT)")
            except Exception as _l2_e:
                logger.warning(f"Layer 2 parent override err: {_l2_e!r}")
            _AD = b"\x00\x00\x01\x08"
            _AP = struct.pack(">I", _person_auid_int)

            import time as _time_mod
            _now_ms = int(_time_mod.time() * 1000)
            _TIME0 = struct.pack(">q", _now_ms)

            _planet_time_memo: dict = {}
            _planet_time_pending: list = []

            _TIME_HOME = struct.pack(
                ">q", await _stable_planet_time_ms(
                    conn, _planet_auid_int, now_ms=_now_ms,
                    planet_time_memo=_planet_time_memo,
                    planet_time_pending=_planet_time_pending))

            _ss_name_str = _SAVE.system_name
            _ss_name = _ss_name_str.encode("utf-16-be")
            _emp_id = 0x1
            _ss2 = (struct.pack(">I", len(_ss_name)) + _ss_name
                    + bytes([0x00])
                    + struct.pack(">i", 1)
                    + struct.pack(">i", _emp_id)
                    + struct.pack(">i", 1)
                    + struct.pack(">i", _emp_id)
                    + bytes([0x00])
                    + struct.pack(">i", 0))
            logger.info(f"[scene]   DaSolarSystem exploredBy/scannedBy "
                        f"populated with empire_id=0x{_emp_id:08x}")
            _size_code = int(_SAVE.planet_size_code)
            if _size_code == 0:
                logger.warning(
                    '[save-hookup][WARN] planet_size_code=0.')
                _size_code = 10

            _plh = _SAVE.planet_home_llf
            _home_llf_for_wg = (0.0, 0.0)
            if isinstance(_plh, (list, tuple)) and len(_plh) >= 2:
                _home_llf_for_wg = (float(_plh[0]), float(_plh[1]))
            import math as _math
            _rob_pos = _SAVE.planet_position or (0.0, 0.0, 0.0)
            _rob_mag = _math.sqrt(sum(c * c for c in _rob_pos))
            _rob_orbit_au = _rob_mag / 2_400_000.0 if _rob_mag > 0 else 1.0
            logger.info(f"[wg] robert orbit_au={_rob_orbit_au:.4f} "
                        f"(real planet pos |{_rob_mag:.0f}| game-units)")
            _home_kind = getattr(_SAVE, "planet_kind", "globe")
            _wg2 = await _build_wg_body(
                conn,
                _SAVE.planet_name,
                _SAVE.planet_zone,
                _size_code,
                _SAVE.planet_size_byte_b1,
                _SAVE.planet_size_byte_b2,
                _SAVE.planet_size_byte_b3,
                auid_seed=_planet_auid_int,
                home_llf=_home_llf_for_wg,
                home_anchor=0,
                diag_label=f"robert({_SAVE.planet_name!r})",
                orbit_au=_rob_orbit_au,
                kind=_home_kind,
                section_index=getattr(_SAVE, "planet_section_index", 0),
                terrain=getattr(_SAVE, "planet_terrain", None),
                wg_geo_parts=_WG_GEO_PARTS,
                gather_planet_roads=gather_planet_roads,
                get_or_init_planet_geo=get_or_init_planet_geo,
            )
            if _home_kind == "ring_section":
                _home_world_opcode = 0x40
                _home_world_label = "DaWorldRingSection"
            else:
                _home_world_opcode = 0x1F
                _home_world_label = "DaWorldGlobe"
            logger.info(
                f"[wg] home world {_SAVE.planet_name!r} kind={_home_kind!r} "
                f"-> op 0x{_home_world_opcode:02X} {_home_world_label}")

            _active_name_str = _last_avatar_name
            _aname_row = await _lookup_person_by_auid(
                conn, int(_active_avatar_auid))
            if _aname_row and _aname_row.get("name"):
                _active_name_str = _aname_row["name"]
            if _active_name_str != _last_avatar_name:
                logger.info("[scene]   active-avatar name override: "
                            "_pn2 from %r -> %r (auid=0x%08x)" % (
                                _last_avatar_name, _active_name_str,
                                int(_active_avatar_auid)))
            _pn2 = _active_name_str.encode("utf-16-be")
            _agent_bits_now = agent_bits_for(_active_avatar_auid)
            logger.info(f"DaPerson agent-bits = 0x{_agent_bits_now:02x} (Animal={int(bool(_agent_bits_now & 1))} Entity={int(bool(_agent_bits_now & 2))} Invisible={int(bool(_agent_bits_now & 4))} AgentOn={int(bool(_agent_bits_now & 8))} Incognito={int(bool(_agent_bits_now & 16))} Invincible={int(bool(_agent_bits_now & 32))}).")
            _nowhere_utf16 = _SAVE.planet_name.encode("utf-16-be")
            import math as _m_v65
            _px_v65, _py_v65, _pz_v65 = _SAVE.person_position
            _r_globe_v65 = (int(_SAVE.planet_size_code) or 10) * 1000.0 / 1.609344 * 5.0
            _r_spawn_v65 = _r_globe_v65
            _pmag_v65 = _m_v65.sqrt(_px_v65*_px_v65 + _py_v65*_py_v65 + _pz_v65*_pz_v65)
            if _pmag_v65 > 1e-6:
                _scale_v65 = _r_spawn_v65 / _pmag_v65
                _robert_xyz_v65 = (_px_v65*_scale_v65, _py_v65*_scale_v65, _pz_v65*_scale_v65)
                logger.info(f"The home avatar projected to spawn radius (R_globe={_r_globe_v65:.1f}, R_spawn={_r_spawn_v65:.1f}): |pos|={_pmag_v65:.1f} scale={_scale_v65:.4f} ({_px_v65:.1f},{_py_v65:.1f},{_pz_v65:.1f}) -> {_robert_xyz_v65}")
            else:
                _robert_xyz_v65 = (_r_spawn_v65, 0.0, 0.0)
                logger.info(f"The home avatar default spawn anchor (save |pos|=0): -> {_robert_xyz_v65} (equator, lon=0, R_spawn={_r_spawn_v65:.1f})")
            _hp_override: int = None  # type: ignore[assignment]
            _hunger_override: int = None  # type: ignore[assignment]
            _stamina_override: int = None  # type: ignore[assignment]
            _sql_state = await read_person_state(conn, int(_person_auid_int))
            if _sql_state:
                if "locXYZ" in _sql_state:
                    _xyz_sql = _sql_state["locXYZ"]
                    _robert_xyz_v65 = (float(_xyz_sql[0]),
                                       float(_xyz_sql[1]),
                                       float(_xyz_sql[2]))
                    logger.info(f"Spawn override from SQL a_Person.locXYZ: {_robert_xyz_v65} (v85e fresh-project ignored)")
                else:
                    logger.info(f"SQL has no persisted xyz for 0x{_person_auid_int:08x}.")
                if "hp" in _sql_state:
                    _hp_override = _sql_state["hp"]
                if "hunger" in _sql_state:
                    _hunger_override = _sql_state["hunger"]
                if "stamina" in _sql_state:
                    _stamina_override = _sql_state["stamina"]
                logger.info(f"Bio override from SQL: hp={_hp_override} hunger={_hunger_override} stamina={_stamina_override} (None = fall back to save file)")
            else:
                logger.info(f"SQL has no persisted row for 0x{_person_auid_int:08x}.")
            _bootstrap_dna = _last_avatar_dna
            if _sql_state and "dna" in _sql_state:
                _bootstrap_dna = bytes(_sql_state["dna"])
                logger.info(f"[dna-bootstrap] loaded DNA from SQL for "
                            f"0x{_person_auid_int:08x}: {_bootstrap_dna.hex()}")
            _bootstrap_person_state = (
                await read_person_state(conn, int(_active_avatar_auid)) or {})
            _bs_xp   = int(_bootstrap_person_state.get("xp")         or 0)
            _bs_rep  = int(_bootstrap_person_state.get("reputation")  or 0)
            _bs_bank = float(_bootstrap_person_state.get("bank")      or 0.0)
            _bs_maxhp = int(_bootstrap_person_state.get("max_hp")     or
                            int(_SAVE.person_hit_points) or 46)
            logger.info(f"[bootstrap] avatar stats from DB: "
                        f"xp={_bs_xp} rep={_bs_rep} "
                        f"bank={_bs_bank:.2f} max_hp={_bs_maxhp}")
            _bs_jobs_blob = b""
            if _STORY_UI_ON:
                from openshores.gameplay import story_targoss as _story_ui
                _bs_jobs_blob = _story_ui.build_job_blob()
                logger.info(f"[story] AuJobList: {len(_bs_jobs_blob)}B "
                            f"({_story_ui.catalyst_meta()['title']!r} by "
                            f"{_story_ui.catalyst_meta()['author']!r})")
            _bootstrap_sql_inv = b""
            _rid_inv, _inv_blob = await read_person_inv(
                conn, _person_auid_int)
            if _inv_blob:
                _bootstrap_sql_inv = bytes(_inv_blob)
                logger.info("[inv-emit] using SQL inv "
                            "(%d bytes) on bootstrap for "
                            "auid=0x%08x (resolved row id="
                            "%s)" % (
                                len(_bootstrap_sql_inv),
                                _person_auid_int,
                                _rid_inv))
            _pb2_cursor = actor_cursor.get(
                int(_active_avatar_auid) & 0xFFFFFFFF) or (9, 0, 0)
            _pb2 = (
                bytes([0x01])
                + struct.pack(">I", len(_pn2)) + _pn2
                + struct.pack(">i",
                              await empire_for_avatar(
                                  conn, int(_active_avatar_auid),
                                  _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE))
                + bytes([0x00])
                + bytes([0x0D])
                + bytes([(int(_SAVE.person_pose) or 0x24) & 0xFF])
                + struct.pack(">I", 24) + _bootstrap_dna
                + struct.pack(">h", (_hp_override if _hp_override is not None else (int(_SAVE.person_hit_points) or 1)))
                + bytes([(int(_SAVE.person_pose) or 0x24) & 0xFF] * 10)
                + struct.pack(">I", 0)
                + bytes([(_stamina_override if _stamina_override is not None else (int(_SAVE.person_stamina) or 0x7F)) & 0xFF])
                + bytes([0x00])
                + bytes([
                    0x8D
                    | 0x20
                    | 0x40
                ])
                + bytes([(
                    (0x40)
                    | 0x08
                    | 0x20
                    | (0x04 if _bs_jobs_blob else 0x00)
                )])
                + struct.pack(">I", _system_auid_int)
                + struct.pack(">I", len(_nowhere_utf16)) + _nowhere_utf16
                + struct.pack(">ff", *(_SAVE.planet_home_llf[:2]))
                + struct.pack(">I",
                              await empire_for_avatar(
                                  conn, int(_active_avatar_auid),
                                  _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE))
                + bytes([0x00])
                + struct.pack(">i", 0)
                + struct.pack(">h", (
                    _hunger_override if _hunger_override is not None
                    else int(_SAVE.person_hunger)
                  ) & 0x7fff)
                + bytes([agent_bits_for(_active_avatar_auid)])
                + bytes([
                    int(_pb2_cursor[0]) & 0xFF,
                    int(_pb2_cursor[1]) & 0x0F,
                    int(_pb2_cursor[2]) & 0xFF,
                ])
                + (
                    _bootstrap_sql_inv
                    if _bootstrap_sql_inv
                    else _pack_au_gear(_build_variety_gear_entries())
                )
                + _bs_jobs_blob
                + struct.pack(">iih", _bs_xp, _bs_rep, 0)
                + struct.pack(">dd", _bs_bank, 0.0)
                + bytes([0x00])
            )


            _secondary_atoms = []
            _active_name_len = struct.unpack(">I", _pb2[1:5])[0]
            _active_name_end = 5 + _active_name_len
            try:
                _all_persons = await _load_all_persons_from_sql(conn)
            except Exception as _ape:
                logger.warning("[scene]   _load_all_persons_from_sql err: %r" % (_ape,))
                _all_persons = []
            for _row in _all_persons:
                if int(_row["auid"]) == int(_active_avatar_auid):
                    continue
                _name = _row["name"] or ("Avatar 0x%08x" % _row["auid"])
                _pn2_sec = _name.encode("utf-16-be")
                _tail = _pb2[_active_name_end:]
                _row_dna = _row.get("dna") or b""
                if (len(_row_dna) == 24
                        and len(_tail) >= 35
                        and _tail[7:11] == struct.pack(">I", 24)):
                    _tail = _tail[:11] + bytes(_row_dna) + _tail[35:]
                else:
                    logger.warning(f"[scene] secondary atom: auid=0x{int(_row['auid']):08x} DNA splice skipped (row_dna_len={len(_row_dna)} tail_len={len(_tail)}.")
                _pb2_sec = (
                    _pb2[:1]
                    + struct.pack(">I", len(_pn2_sec)) + _pn2_sec
                    + _tail
                )
                _AP_sec = struct.pack(">I", int(_row["auid"]))
                _xyz_sec = _row["xyz"] if _row["xyz"] else tuple(_robert_xyz_v65)
                _secondary_atoms.append({
                    "auid": int(_row["auid"]),
                    "name": _name,
                    "AP": _AP_sec,
                    "pb2": _pb2_sec,
                    "xyz": _xyz_sec,
                })
                logger.debug("[scene]   secondary atom: auid=0x%08x name=%r xyz=%s body=%dB" % (
                    int(_row["auid"]), _name, _xyz_sec, len(_pb2_sec)))
            if not _secondary_atoms:
                logger.debug("[scene]   no secondary atoms (active=0x%08x is the only person in a_Person)" % int(_active_avatar_auid))
            if _secondary_atoms:
                _pb2_bob = _secondary_atoms[0]["pb2"]
                _AP_bob = _secondary_atoms[0]["AP"]
                _bob_xyz = _secondary_atoms[0]["xyz"]
            else:
                _pb2_bob = None
                _AP_bob = None
                _bob_xyz = None


            _PARSEC_PER_CELL = 10.0
            _sx0, _sy0, _sz0 = _SAVE.sector_position
            _rx = int(round(_sx0 / _PARSEC_PER_CELL))
            _ry = int(round(_sy0 / _PARSEC_PER_CELL))
            _rz = int(round(_sz0 / _PARSEC_PER_CELL))
            _extra_sectors = []
            _extra_sector_auids = []
            _extra_systems = []
            _extra_system_auids = []
            _next_xs_auid = 0x00a00001
            _next_xsys_auid = 0x00b00001

            _stars_by_cell: dict = {}
            for _rs in _SAVE.real_stars:
                _sp = _rs.position
                _cx = int(round(_sp[0] / _PARSEC_PER_CELL))
                _cy = int(round(_sp[1] / _PARSEC_PER_CELL))
                _cz = int(round(_sp[2] / _PARSEC_PER_CELL))
                _stars_by_cell.setdefault((_cx, _cy, _cz), []).append(_rs)
            logger.info(f"[scene]   real-star bucketing: {len(_SAVE.real_stars)} "
                        f"stars -> {len(_stars_by_cell)} sector cells")

            _halo_cells = set()
            for _dx in (-1, 0, 1):
                for _dy in (-1, 0, 1):
                    for _dz in (-1, 0, 1):
                        _cc = (_rx + _dx, _ry + _dy, _rz + _dz)
                        if _cc != (_rx, _ry, _rz):
                            _halo_cells.add(_cc)

            _emit_cells = sorted(_stars_by_cell.keys() | _halo_cells)
            _robert_cell = (_rx, _ry, _rz)


            for _cell in _emit_cells:
                if _cell == _robert_cell:
                    continue
                _gx, _gy, _gz = _cell
                _xs_pos = (float(_gx) * _PARSEC_PER_CELL,
                           float(_gy) * _PARSEC_PER_CELL,
                           float(_gz) * _PARSEC_PER_CELL)
                _xs_auid = _next_xs_auid
                _next_xs_auid += 1
                _xs_auid_bytes = struct.pack(">I", _xs_auid)
                _xs_pkt = (bytes([0x14]) + _xs_auid_bytes + _TIME0
                           + _bpt2(_AG, *_xs_pos)
                           + struct.pack(">I", 0))
                _extra_sectors.append(
                    (f"DaSector/({_gx},{_gy},{_gz})", _xs_pkt))
                _extra_sector_auids.append(_xs_auid)

                _cell_stars = _stars_by_cell.get(_cell, [])
                for _star_idx, _rs in enumerate(_cell_stars):
                    _xsys_auid = _next_xsys_auid
                    _next_xsys_auid += 1
                    _xsys_auid_bytes = struct.pack(">I", _xsys_auid)
                    _xsys_name = _rs.name.encode("utf-16-be")
                    _sxo = _rs.position[0] - _xs_pos[0]
                    _syo = _rs.position[1] - _xs_pos[1]
                    _szo = _rs.position[2] - _xs_pos[2]
                    _xsys_body = (
                        struct.pack(">I", len(_xsys_name))
                        + _xsys_name
                        + bytes([0x00])
                        + struct.pack(">i", 0)
                        + struct.pack(">i", 0)
                        + bytes([0x00])
                        + struct.pack(">i", 0)
                    )
                    _xsys_pkt = (
                        bytes([0x15]) + _xsys_auid_bytes + _TIME0
                        + _bpt2(_xs_auid_bytes, _sxo, _syo, _szo)
                        + _xsys_body
                        + b"\x00" * 16
                    )
                    _extra_systems.append(
                        (f"DaSolarSystem/{_rs.name}", _xsys_pkt))
                    _extra_system_auids.append(_xsys_auid)


            _primary_extra_systems = []
            _primary_extra_system_auids = []
            _primary_cell_stars = _stars_by_cell.get(_robert_cell, [])
            _robert_system_auids = {int(_SAVE.system_auid or 0)}
            for _rs in _primary_cell_stars:
                if _rs.auid in _robert_system_auids:
                    continue
                _xsys_auid = _next_xsys_auid
                _next_xsys_auid += 1
                _xsys_auid_bytes = struct.pack(">I", _xsys_auid)
                _xsys_name = _rs.name.encode("utf-16-be")
                _sxo = _rs.position[0] - float(_rx) * _PARSEC_PER_CELL
                _syo = _rs.position[1] - float(_ry) * _PARSEC_PER_CELL
                _szo = _rs.position[2] - float(_rz) * _PARSEC_PER_CELL
                _xsys_body = (
                    struct.pack(">I", len(_xsys_name))
                    + _xsys_name
                    + bytes([0x00])
                    + struct.pack(">i", 0)
                    + struct.pack(">i", 0)
                    + bytes([0x00])
                    + struct.pack(">i", 0)
                )
                _xsys_pkt = (
                    bytes([0x15]) + _xsys_auid_bytes + _TIME0
                    + _bpt2(_AS, _sxo, _syo, _szo)
                    + _xsys_body
                    + b"\x00" * 16
                )
                _primary_extra_systems.append(
                    (f"DaSolarSystem/primary-{_rs.name}", _xsys_pkt))
                _primary_extra_system_auids.append(_xsys_auid)
            logger.info(f"[scene] primary sector: {len(_primary_extra_systems)} additional real-star systems (plus the home main)")

            _scene_auids = [
                _universe_auid_int,
                int(_SAVE.galaxy_auid) or 0x102,
                _sector_auid_int,
            ] + _extra_sector_auids + _extra_system_auids + [
                _system_auid_int,
            ] + _primary_extra_system_auids + [
                int(_SAVE.celestial_body_auid) or 0x0005a66d,
                _planet_auid_int,
            ]
            _sibling_ok = []
            if _SAVE.sibling_globes:
                _star_auid = int(_SAVE.celestial_body_auid) or 0x5a66d
                _all_sib_auids = {sg.auid for sg in _SAVE.sibling_globes}
                _keep_auids = set()
                _home_auid = int(getattr(_SAVE, "planet_auid", 0) or 0)
                for _sg in _SAVE.sibling_globes:
                    if _sg.parent_auid == _star_auid:
                        _keep_auids.add(_sg.auid)
                    elif _home_auid and _sg.parent_auid == _home_auid:
                        _keep_auids.add(_sg.auid)
                _changed = True
                while _changed:
                    _changed = False
                    for _sg in _SAVE.sibling_globes:
                        if _sg.auid in _keep_auids:
                            continue
                        if _sg.parent_auid in _keep_auids:
                            _keep_auids.add(_sg.auid)
                            _changed = True
                _sib_by_auid = {sg.auid: sg for sg in _SAVE.sibling_globes}
                _emitted = set()
                _queue = list(_keep_auids)
                while _queue:
                    _made_progress = False
                    _next = []
                    for _a in _queue:
                        _sg = _sib_by_auid[_a]
                        _parent_ok = (
                            _sg.parent_auid == _star_auid
                            or _sg.parent_auid in _emitted
                            or _sg.parent_auid not in _all_sib_auids
                        )
                        if _parent_ok:
                            _sibling_ok.append(_sg)
                            _emitted.add(_a)
                            _made_progress = True
                        else:
                            _next.append(_a)
                    if not _made_progress:
                        break
                    _queue = _next
                _dropped = [sg.name for sg in _SAVE.sibling_globes
                            if sg.auid not in _keep_auids]
                if _dropped:
                    logger.info(f"[scene]   sibling filter dropped {len(_dropped)}"
                                f" orphan(s) (parent not in save): {_dropped}")
                logger.info(f"[scene]   sibling filter kept {len(_sibling_ok)} "
                            f"of {len(_SAVE.sibling_globes)} (in topo order)")
            try:
                if int(_planet_auid_int) != int(_SAVE.planet_auid):
                    _before = len(_sibling_ok)
                    _sibling_ok = [sg for sg in _sibling_ok
                                   if int(sg.auid)
                                   != int(_planet_auid_int)]
                    if len(_sibling_ok) < _before:
                        logger.info(
                            f"Layer 2: dropped {_before - len(_sibling_ok)} sibling(s) matching the sql-overridden planet_auid 0x{int(_planet_auid_int):08x} (now the home primary DaWorldGlobe)")
            except Exception as _l2dedup_e:
                logger.warning(f"Layer 2 dedup err: {_l2dedup_e!r}")
            _sib_max_size = 12
            if _sib_max_size < 99:
                _before = len(_sibling_ok)
                _moonish = [sg for sg in _sibling_ok
                            if (sg.size_code is not None
                                and int(sg.size_code) > _sib_max_size
                                and getattr(sg, "class_kind", "globe")
                                != "gas_giant")]
                _sibling_ok = [sg for sg in _sibling_ok
                               if sg not in _moonish]
                _dropped_auids = {sg.auid for sg in _moonish} - {_star_auid}
                _cascaded = True
                while _cascaded:
                    _cascaded = False
                    for _sg in list(_sibling_ok):
                        if _sg.parent_auid in _dropped_auids:
                            _sibling_ok.remove(_sg)
                            _moonish.append(_sg)
                            _dropped_auids.add(_sg.auid)
                            _cascaded = True
                if _moonish:
                    _moon_names = [
                        f"{sg.name}(size={int(sg.size_code)})"
                        for sg in _moonish
                    ]
                    logger.info(f"[scene]   dropped {len(_moonish)} "
                                f"moon-class sibling(s) "
                                f"(per-frame leak source per task#114): "
                                f"{', '.join(_moon_names)}")
                    logger.info(f"[scene]   sibling filter kept {len(_sibling_ok)}"
                                f" of {_before} after moon-class drop")
            _sibling_globes_enabled = bool(_sibling_ok)
            if _sibling_globes_enabled:
                for _sg in _sibling_ok:
                    _scene_auids.append(_sg.auid)
            _sib_pos_mode = "save"
            logger.info(f"[scene]   sibling position mode = "
                        f"{_sib_pos_mode!r} "
                        f"(zero made all 12 z-fight at celestial-body origin "
                        f"per v102.1)")
            _live_auids_for_manifest = {int(_active_avatar_auid)} | set(_live_avatars.keys())
            for _la in _live_auids_for_manifest:
                _scene_auids.append(_la)

            def _scene_manifest_for_conn() -> bytes:
                return _build_scene_manifest(
                    writer=writer,
                    active_avatar_auid=_active_avatar_auid,
                    scene_auids=_scene_auids,
                    live_auids_for_manifest=_live_auids_for_manifest,
                    live_avatars=_live_avatars,
                    manifest_suppress=_MANIFEST_SUPPRESS,
                    dynamic_scene_auids=_DYNAMIC_SCENE_AUIDS,
                    sim_time_anchor_full=sim_time_anchor_full,
                    sim_time_state=sim_time_state)
            try:
                for (_cid2,) in await planet_city_ids(conn, int(_planet_auid_int)):
                    _DYNAMIC_SCENE_AUIDS.add(int(_cid2) & 0xFFFFFFFF)
            except Exception as _cme:
                logger.warning(f"[scene]   city manifest-register err: {_cme!r}")
            setattr(writer, "_scene_manifest_builder", _scene_manifest_for_conn)
            logger.info(f'[scene]   {_boot_label} 0x18 SceneManifest DEFERRED until after 0x2A.')

            _star_type     = int(str(getattr(_SAVE, "star_spec_type", 4)), 0) & 0x0F
            _star_size     = int(str(getattr(_SAVE, "star_spec_size", 5)), 0) & 0x0F
            _star_subclass = int(str(getattr(_SAVE, "star_spec_subclass", 5)), 0) & 0x0F
            _star_packed = ((_star_size & 0x0F) << 4) | (_star_type & 0x0F)
            _star_info16 = bytes(getattr(_SAVE, "star_orbit_zones",
                                         b"\x01\x02\x03\x04\x04\x05\x05\x06\x06\x00\x00\x00\x00\x00\x00\x00"))
            if len(_star_info16) < 16:
                _star_info16 = (_star_info16 + b"\x00" * 16)[:16]
            elif len(_star_info16) > 16:
                _star_info16 = _star_info16[:16]
            _star_b1 = int(getattr(_SAVE, "star_hab_first", 0xFF)) & 0xFF
            _star_b2 = int(str(getattr(_SAVE, "star_companion", 0xFF)), 0) & 0xFF
            _star_b3 = int(getattr(_SAVE, "star_hab_last", 0xFF)) & 0xFF
            _STAR_TYPE_NAMES = ["O", "B", "A", "F", "G", "K", "M", "BlackHole"]
            _STAR_SIZE_NAMES = ["?", "?", "?", "?", "Subgiant",
                                "Main Seq", "Giant", "Supergiant"]
            logger.info(
                f"[da-star] type={_star_type}"
                f"({_STAR_TYPE_NAMES[_star_type] if _star_type < 8 else '?'}) "
                f"size={_star_size}"
                f"({_STAR_SIZE_NAMES[_star_size] if _star_size < 8 else '?'}) "
                f"subclass={_star_subclass} "
                f"packed=0x{_star_packed:02x} "
                f"info16={_star_info16.hex()} "
                f"hab_first={_star_b1} hab_last={_star_b3}"
            )
            _star_flag = 7
            _star_body = bytes([_star_flag])
            if _star_flag & 0x01:
                _star_body += (bytes([_star_subclass])
                               + _star_info16
                               + bytes([_star_b1])
                               + bytes([_star_b2])
                               + bytes([_star_b3])
                               + bytes([_star_packed]))
            if _star_flag & 0x02:
                _star_ring_ref = _ring_ref_section_auid(_SAVE)
                if _star_ring_ref:
                    logger.info(f'[da-star] ringworld reference section = 0x{_star_ring_ref & 4294967295:08x} (+0x3E8).')
                _star_body += struct.pack(">I", _star_ring_ref & 0xFFFFFFFF)
            if _star_flag & 0x04:
                _star_body += bytes([0x00])
            _WG_ATOM_HDR[int(_planet_auid_int) & 0xFFFFFFFF] = (
                bytes([0x1F]) + _AW + _TIME_HOME
                + _bpt2(_world_parent_AP,
                        *_SAVE.planet_position,
                        *_SAVE.planet_rotation))
            atoms_c2 = [
                ("DaUniverse",    bytes([0x1b]) + _AU + _TIME0 + bytes([0x08]) + struct.pack(">ffffff", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
                ("DaGalaxy",      bytes([0x10]) + _AG + _TIME0 + _bpt2(_AU, 0.0, 0.0, 0.0,
                                                                              *_SAVE.galaxy_rotation)
                                  + bytes([int(str(_SAVE.galaxy_name_index), 0)
                                       & 0xFF])
                                  + b"\x00" * 16),
                ("DaSector",      bytes([0x14]) + _AS + _TIME0
                                  + _bpt2(_AG, *_SAVE.sector_position,
                                          *_SAVE.sector_rotation)
                                  + struct.pack(">I", len(_SAVE.sector_name.encode("utf-16-be")))
                                  + _SAVE.sector_name.encode("utf-16-be")),
                ("DaSolarSystem", bytes([0x15]) + _AY + _TIME0
                                  + _bpt2(_AS, *_SAVE.system_position,
                                          *_SAVE.system_rotation)
                                  + _ss2 + b"\x00" * 16),
                ("DaStar",        bytes([0x17]) + _AT + _TIME0
                                  + _bpt2(_AY, *_SAVE.celestial_body_position,
                                          *_SAVE.celestial_body_rotation)
                                  + _star_body),
                (_home_world_label, bytes([_home_world_opcode])
                                  + _AW + _TIME_HOME
                                  + _bpt2(_world_parent_AP,
                                          *_SAVE.planet_position,
                                          *_SAVE.planet_rotation)
                                  + _wg2 + b"\x00" * 16),
            ]
            if _layer2_gas_giant:
                try:
                    _gg_id = int(_layer2_gas_giant["id"])
                    _gg_pos = _layer2_gas_giant.get(
                        "locXYZ") or (0.0, 0.0, 0.0)
                    _gg_atom = (
                        bytes([0x1E])
                        + struct.pack(">I", _gg_id)
                        + struct.pack(
                            ">q",
                            await _stable_planet_time_ms(
                                conn, _gg_id, now_ms=_now_ms,
                                planet_time_memo=_planet_time_memo,
                                planet_time_pending=_planet_time_pending))
                        + _bpt2(_AT, *_gg_pos, 0.0, 0.0, 0.0)
                        + bytes([0x00])
                        + b"\x00" * 16
                    )
                    atoms_c2.insert(
                        5,
                        (f"DaWorldGasGiant/"
                         f"{_layer2_gas_giant.get('name', '?')}",
                         _gg_atom))
                    logger.info(
                        f"Layer 2: spliced synthetic DaWorldGasGiant atom ({_layer2_gas_giant.get('name', '?')}, AuId=0x{_gg_id:08x}, pos={_gg_pos}, {len(_gg_atom)}B) into atoms_c2 at index 5")
                except Exception as _gg_e:
                    logger.warning(f"Layer 2 gas-giant splice err: {_gg_e!r}")
            _time_created = (int(getattr(_SAVE, "person_time_created", 0)) or _now_ms)
            _primary_lookup = await _lookup_person_by_auid(conn, int(_active_avatar_auid))
            _primary_name_str = (
                _primary_lookup["name"]
                if _primary_lookup and _primary_lookup.get("name")
                else str(_SAVE.person_name))
            _scene_avatars = [
                {"auid": int(_person_auid_int), "AP": _AP,
                 "xyz": _robert_xyz_v65, "pb2": _pb2,
                 "name": _primary_name_str,
                 "time_created": _time_created},
            ]
            for _sa in _secondary_atoms:
                _scene_avatars.append({
                    "auid": _sa["auid"], "AP": _sa["AP"],
                    "xyz": _sa["xyz"], "pb2": _sa["pb2"],
                    "name": _sa["name"],
                    "time_created": _time_created})

            _emit_self_auid = int(_person_auid_int)
            _auids_to_emit = {_emit_self_auid} | set(_live_avatars.keys())
            _emitted = set()
            _emit_order = []
            for _auid in [_emit_self_auid] + [a for a in _live_avatars.keys()
                                              if a != _emit_self_auid]:
                if _auid in _emitted:
                    continue
                _emitted.add(_auid)
                _emit_order.append(_auid)

            for _auid in _emit_order:
                if _auid == _emit_self_auid:
                    _src = next(a for a in _scene_avatars if a["auid"] == _auid)
                    _ap, _xyz, _pb, _nm = _src["AP"], _src["xyz"], _src["pb2"], _src["name"]
                    _tc = _src["time_created"]
                    _source = "self-fresh"
                elif _auid in _live_avatars:
                    _live = _live_avatars[_auid]
                    _ap, _xyz, _pb, _nm = _live["AP"], _live["xyz"], _live["pb2"], _live["name"]
                    _tc = _live["time_created"]
                    _source = "live-peer"
                else:
                    continue
                atoms_c2.append(
                    ("DaPerson",
                     bytes([0x12]) + _ap + _TIME0
                     + _bpt2_tc(_AW, _tc, *_xyz,
                                *((0.0, 0.0, 0.0)
                                  if int(_auid) == int(_active_avatar_auid)
                                  else _peer_upright_euler(_xyz)))
                     + _pb + b"\x00" * 16))
                logger.info(f"[scene]   emit avatar auid=0x{_auid:08x} "
                            f"name={_nm!r} xyz={_xyz} src={_source}")

            if _extra_sectors or _primary_extra_systems:
                atoms_c2 = (
                    atoms_c2[:3]
                    + _extra_sectors
                    + _extra_systems
                    + atoms_c2[3:4]
                    + _primary_extra_systems
                    + atoms_c2[4:]
                )
                logger.info(f"[scene]   -> conn2 spliced "
                            f"{len(_extra_sectors)} DaSector + "
                            f"{len(_extra_systems)} synth neighbour + "
                            f"{len(_primary_extra_systems)} synth primary "
                            f"around ({_rx},{_ry},{_rz})")

            if _sibling_globes_enabled:
                _sibling_emit_auids = {sg.auid for sg in _sibling_ok}
                _emitted_parent_auids = set()
                _emitted_parent_auids.add(
                    int(_SAVE.celestial_body_auid) or 0x0005a66d)
                _emitted_parent_auids |= _sibling_emit_auids
                _phantom_entries = []
                _sibling_entries = list(_phantom_entries)
                _sib_parent_resolved = None
                for _sg in _sibling_ok:
                    _sg_auid_bytes = struct.pack(">I", _sg.auid)
                    if _sib_parent_resolved is not None:
                        _sg_parent_bytes = _sib_parent_resolved
                    else:
                        _sg_parent_bytes = struct.pack(">I", _sg.parent_auid)
                    _sg_pos_save = _sg.position or (0.0, 0.0, 0.0)
                    _sg_mag = (
                        _sg_pos_save[0] ** 2
                        + _sg_pos_save[1] ** 2
                        + _sg_pos_save[2] ** 2
                    ) ** 0.5
                    _sg_orbit_au = (
                        _sg_mag / 2_400_000.0 if _sg_mag > 0 else 1.0
                    )
                    if (getattr(_sg, "class_kind", "globe") == "moon"
                            and _sg_mag <= 0):
                        _sg_orbit_au = float("0.005")
                    _sg_kind_for_body = getattr(_sg, "class_kind", "globe")
                    if _sg_kind_for_body == "ring":
                        _sg_kind_for_body = "globe"
                    _sib_zone_profiles = {
                        0: (4, 80),
                        1: (4, 10),
                        2: (0, 60),
                        3: (2, 30),
                        4: (3, 80),
                    }
                    if _sg_kind_for_body == "moon":
                        _sib_atmType, _sib_water = 0, 0
                        _sib_atmDens = 0
                    elif _sg_kind_for_body == "ring_section":
                        _sib_atmType = int(_sg.size_byte_b1 or 0) & 0xFF
                        _sib_atmDens = int(_sg.size_byte_b2 or 0) & 0xFF
                        _sib_water = int(_sg.size_byte_b3 or 0) & 0xFF
                    else:
                        _sib_atmType, _sib_water = _sib_zone_profiles.get(
                            int(_sg.zone) & 0xFF, (2, 30))
                        _sib_atmDens = (
                            _sg.size_byte_b2 if _sg.size_byte_b2 else 30)
                    _sg_body = await _build_wg_body(
                        conn,
                        _sg.name,
                        _sg.zone,
                        _sg.size_code,
                        _sib_atmType,
                        _sib_atmDens,
                        _sib_water,
                        auid_seed=_sg.auid,
                        home_llf=None,
                        diag_label=f"sibling({_sg.name!r})",
                        orbit_au=_sg_orbit_au,
                        kind=_sg_kind_for_body,
                        core_radius=getattr(_sg, "core_radius", 0),
                        section_index=getattr(_sg, "section_index", 0),
                        terrain=getattr(_sg, "terrain", None),
                        lite=(_sg_kind_for_body != "globe"),
                        wg_geo_parts=_WG_GEO_PARTS,
                        gather_planet_roads=gather_planet_roads,
                        get_or_init_planet_geo=get_or_init_planet_geo,
                    )
                    _sg_pos = _sg.position
                    logger.info(f"[scene]   sibling {_sg.name!r} auid={_sg.auid} "
                                f"pos={_sg_pos} (mode={_sib_pos_mode!r}, "
                                f"saved={_sg.position})")
                    _sg_rot = getattr(_sg, "rotation", (0.0, 0.0, 0.0)) or (0.0, 0.0, 0.0)
                    _sg_kind = getattr(_sg, "class_kind", "globe")
                    if _sg_kind == "gas_giant":
                        _sg_opcode = 0x1E
                        _sg_label = "DaWorldGasGiant"
                    elif _sg_kind == "ring":
                        _sg_opcode = 0x20
                        _sg_label = "DaWorldRing"
                    elif _sg_kind == "ring_section":
                        _sg_opcode = 0x40
                        _sg_label = "DaWorldRingSection"
                    else:
                        _sg_opcode = 0x1F
                        _sg_label = "DaWorldGlobe"
                    _sg_time = struct.pack(
                        ">q", await _stable_planet_time_ms(
                            conn, _sg.auid, now_ms=_now_ms,
                            planet_time_memo=_planet_time_memo,
                            planet_time_pending=_planet_time_pending))
                    _sg_atom = (bytes([_sg_opcode]) + _sg_auid_bytes + _sg_time
                                + _bpt2(_sg_parent_bytes, *_sg_pos, *_sg_rot)
                                + _sg_body + b"\x00" * 16)
                    _sibling_entries.append(
                        (f"{_sg_label}/{_sg.name}", _sg_atom))
                atoms_c2 = atoms_c2[:-1] + _sibling_entries + atoms_c2[-1:]
                _class_counts = {}
                for _name, _ in _sibling_entries:
                    _cls = _name.split('/')[0]
                    _class_counts[_cls] = _class_counts.get(_cls, 0) + 1
                _class_str = ', '.join(f"{n}x {c}" for c, n in _class_counts.items())
                logger.info(f"[scene]   -> conn2 spliced {len(_sibling_entries)} "
                            f"sibling atom(s) into scene ({_class_str})")

            _animal_entries = await _build_fauna_entries(
                conn,
                _planet_auid_int, _SAVE,
                int(getattr(_SAVE, "atm_type", 0) or 0),
                int(getattr(_SAVE, "atm_density", 0) or 0),
                int(getattr(_SAVE, "water", 0) or 0),
                _robert_xyz_v65,
                _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
            if _animal_entries:
                atoms_c2 = (atoms_c2[:-1] + _animal_entries
                            + atoms_c2[-1:])
                logger.info(f"[fauna] spliced {len(_animal_entries)} "
                            f"DaAnimal atoms into scene")


            _n_hurt = _register_damageable_npcs(
                idle_bodies=natives_idle_bodies,
                story_npcs=story_npcs,
                story_atom_id=story_atom_id,
                story_name=story_name)
            if _n_hurt:
                logger.info(f"[damageable] scene bootstrap registered "
                            f"{_n_hurt} NPC(s)")


            _veh_atoms = []
            _veh_parent = int(_planet_auid_int)
            try:
                _veh_atoms = await build_scene_atoms(_veh_parent, conn=conn)
            except Exception as _vse:
                logger.warning(f"[vehicles-scene] build_scene_atoms failed "
                               f"(non-fatal): {_vse!r}")
            _veh_active_total = len(list_active_vehicles())
            logger.info(f"[vehicles-scene] parent=0x{_veh_parent:08x} "
                        f"matched={len(_veh_atoms)} active_total={_veh_active_total}")
            if _veh_atoms:
                atoms_c2 = (atoms_c2[:-1] + _veh_atoms
                            + atoms_c2[-1:])
                logger.info(f"[vehicles-scene] spliced {len(_veh_atoms)} "
                            f"persisted vehicle atom(s) into scene init")
                for _vk in list_active_vehicles():
                    try:
                        if int(_vk.idp) == _veh_parent:
                            _DYNAMIC_SCENE_AUIDS.add(int(_vk.id))
                            _davehicle_keepalive_start(
                                int(_vk.id), _live_avatars=_live_avatars)
                    except Exception as _vke:
                        logger.warning(
                            f"[vehicles-scene] manifest/keepalive "
                            f"failed for 0x{int(getattr(_vk, 'id', 0)):08x}: "
                            f"{_vke!r}")
                logger.info(f"[vehicles-scene] registered "
                            f"{len(_veh_atoms)} AuId(s) in "
                            f"_DYNAMIC_SCENE_AUIDS")
            else:
                _veh_idps = sorted({int(_v.idp) for _v in list_active_vehicles()})
                if _veh_idps:
                    logger.info(f"[vehicles-scene]   no vehicles for this "
                                f"parent; DB has idps: "
                                f"{[hex(_i) for _i in _veh_idps]}")

            _cty_rows = []
            try:
                _cty_rows = await planet_city_atom_rows(conn, int(_planet_auid_int))
            except Exception as _ce:
                logger.warning(f"[scene]   city-splice query err: {_ce!r}")
            _cty_n = 0
            for (_cid, _cidp, _cx, _cy, _cz, _cnm, _cdev, _calg) in _cty_rows:
                try:
                    _cdevs = developments_from_blob(_cdev)
                    _cblds = [b for b in _cdevs
                              if b.get("kind", "building") == "building"]
                    _crds = [b for b in _cdevs if b.get("kind") == "road"]
                    _cpkt = await build_scene_dacity(
                        conn,
                        int(_cid) & 0xFFFFFFFF,
                        int(_cidp or _planet_auid_int) & 0xFFFFFFFF,
                        (_cx or 0.0, _cy or 0.0, _cz or 0.0),
                        _cblds, name=(_cnm or ""),
                        roads=(_crds or None),
                        identity_auid=int(_calg or 0) & 0xFFFFFFFF,
                        is_capital=True, habitable_capital=True)
                    atoms_c2.append(("DaCity", _cpkt))
                    _DYNAMIC_SCENE_AUIDS.add(int(_cid) & 0xFFFFFFFF)
                    _cty_n += 1
                except Exception as _cbe:
                    logger.warning(f"[scene]   city-splice build err "
                                   f"0x{int(_cid) & 0xFFFFFFFF:08x}: {_cbe!r}")
            if _cty_n:
                logger.info(f"[scene]   spliced {_cty_n} DaCity atom(s) into "
                            f"conn2 batch (parent world 0x{_planet_auid_int:08x})")

            await _flush_planet_times(
                conn, now_ms=int(_tconn_init.time() * 1000),
                planet_time_pending=_planet_time_pending)

            for name, pkt in atoms_c2:
                await write_framed(writer, pkt)
                logger.info(f"[scene]   -> conn2 atom {name} ({len(pkt)}B)")

            _robert_live_pkt = None
            _robert_live_hunger_off = 0
            _robert_live_stamina_off = 0
            _robert_live_hp_off = 0
            _robert_live_pose_off = 0
            for _ln, _lp in atoms_c2:
                if _ln == "DaPerson" and _lp[1:5] == _AP:
                    _robert_live_pkt = bytearray(_lp)
                    _robert_live_hp_off = 50 + 40 + len(_pn2)
                    _robert_live_pose_off = _robert_live_hp_off + 2
                    _robert_live_stamina_off = (
                        50 + 1 + 4 + len(_pn2) + 4 + 1 + 1 + 1
                        + 4 + 24 + 2 + 10 + 4)
                    _robert_live_hunger_off = (
                        50 + 1 + 4 + len(_pn2) + 4 + 1 + 1 + 1
                        + 4 + 24 + 2 + 10 + 4 + 1 + 1 + 1 + 1
                        + 4 + 4 + len(_nowhere_utf16)
                        + 8 + 4 + 1 + 4)
                    logger.info(f"Live-push captured DaPerson pkt len={len(_robert_live_pkt)}B hp@{_robert_live_hp_off} pose@{_robert_live_pose_off} hunger@{_robert_live_hunger_off} stamina@{_robert_live_stamina_off}")
                    break
            if _robert_live_pkt is None:
                logger.warning("Live-push: NO DaPerson packet captured (atoms_c2 missing the home atom.")

            _native_live_pkts = [bytes(_lp) for _ln, _lp in atoms_c2
                                 if _ln.startswith("DaPerson/native/")]
            _native_live_pkts = [bytes(_lp) for _ln, _lp in atoms_c2
                                 if _ln.startswith("DaPerson/native/")]

            try:
                _WORLD_ATOM_AUIDS.add(int.from_bytes(_AW, 'big'))
                if _session is not None:
                    _session.set_player_auid(_AP)
                    _session.set_parent_world(_AW)
                    _session.world_atom_auids.add(
                        int.from_bytes(_AW, 'big'))
                    _session.is_primary = True
                    _session.bootstrap_published = True
                    attach_to_live_avatars(_live_avatars, _session)
                _state = []
                _player_auid_int = int.from_bytes(_AP, "big")
                _sql_loaded = await _load_augear_from_sql(conn,
                                                          _player_auid_int)
                if _sql_loaded:
                    _slots_summary = [(e[0], e[1], e[2])
                                      for e in _sql_loaded]
                    logger.info("[inv-load] using SQL inv (%d slots) for "
                                "auid=0x%08x; slots=%r" % (
                                    len(_sql_loaded),
                                    int.from_bytes(_AP, "big"),
                                    _slots_summary))
                    _state = [list(e) for e in _sql_loaded]
                else:
                    for _entry in _build_variety_gear_entries():
                        _state.append([_entry[0], _entry[1],
                                       _entry[2], _entry[3]])
                augear_states[int(_person_auid_int) & 0xFFFFFFFF] = (
                    [list(e) for e in _state])
                if _session is not None:
                    _session.augear = augear_states[
                        int(_person_auid_int) & 0xFFFFFFFF]
                _self_src_name = next(
                    (a.get("name") for a in _scene_avatars
                     if a.get("auid") == int(_person_auid_int)),
                    None,
                )
                _diag_auid_hex = _session.player_auid_bytes.hex()
                _diag_parent = _session.parent_world_auid_bytes.hex()
                _diag_source = "session"
                logger.info(f"[bootstrap-published] auid=0x{int(_person_auid_int):08x} "
                            f"name={_self_src_name!r} "
                            f"parent_world={_diag_parent} "
                            f"scene_writer={writer.get_extra_info('peername')} "
                            f"AuGear slots={[(e[0], e[1]) for e in _state]} "
                            f"(source={_diag_source}, "
                            f"player_auid={_diag_auid_hex})")
                logger.info("[commodity] post-publish republish skipped (HZ_BOOTSTRAP_REPUBLISH=0).")
                _wsets = _weapon_cid_sets()
                _refresh_aug = _pack_au_gear(_state)
                _refresh_pkt = _build_augear_only_daperson_update(
                    _AP, _refresh_aug)
                await write_framed(writer, _refresh_pkt)
                if _wsets != (set(), set(), set()):
                    logger.info(f"[inv-migrate] connect-time gear refresh "
                                f"sent ({len(_refresh_aug)}B); cid sets="
                                f"knives={sorted(_wsets[0])} guns={sorted(_wsets[1])} "
                                f"ammo={sorted(_wsets[2])}")
                    for _idx, _e in enumerate(_state):
                        _cid = (_extract_cid_from_auitem_body(bytes(_e[3]))
                                if len(_e) >= 4 else 0)
                        logger.info(f"[inv-migrate]   slot[{_idx}] "
                                    f"slot={_e[0]} sub={_e[1]} "
                                    f"typeId=0x{_e[2]:02x} cid={_cid} "
                                    f"({_cid:#x}) bodylen={len(_e[3])}")
                else:
                    logger.info(f'[inv-prime] connect-time AuGear refresh sent ({len(_refresh_aug)}B, {len(_state)} slot(s)).')
            except Exception as _pubexc:
                logger.warning(f"Failed to publish chat-reply state: {_pubexc!r}")


            try:
                _replay = await dropped_items_load_all(conn)
                if _replay:
                    logger.info(f"Replaying {len(_replay)} persisted dropped items from SQL...")
                    for _di in _replay:
                        _auid = int(_di["auid"])
                        try:
                            _pkt = _build_daitem_drop_packet(
                                item_auid_int=_auid,
                                parent_auid=int(_di["parent_auid"]).to_bytes(
                                    4, "big"),
                                xyz=_di["xyz"],
                                item_typeId=int(_di["type_id"]),
                                item_body=bytes(_di["body"]),
                                rotation=_di["rotation"],
                                time_created_ms=int(_di["time_created_ms"]),
                            )
                            await write_framed(writer, _pkt)
                            _DROPPED_ITEMS[_auid] = {
                                "parent": int(_di["parent_auid"]).to_bytes(4, "big"),
                                "xyz": _di["xyz"],
                                "typeId": int(_di["type_id"]),
                                "body": bytes(_di["body"]),
                                "rotation": _di["rotation"],
                                "time_created_ms": int(_di["time_created_ms"]),
                            }
                            _DYNAMIC_SCENE_AUIDS.add(_auid)
                            raise_daitem_auid_floor(_auid + 1)
                            asyncio.create_task(
                                _daitem_lifecycle(_auid))
                            logger.info(f"Replayed 0x{_auid:08x} typeId=0x{int(_di['type_id']):02X} xyz={_di['xyz']} (lifecycle task started)")
                        except Exception as _re:
                            logger.warning(f"Replay 0x{_auid:08x} failed: {_re!r}")
            except Exception as _rpe:
                logger.warning(f"Replay block failed: {_rpe!r}")

            _dg_empire_pkt = await build_scene_dg_empire_0x31(
                conn,
                True, player_avatar_id=_active_avatar_auid,
                name_long=name_long, name_short=name_short,
                capital_name=capital_name,
                _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
                _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
                _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
            await write_framed(writer, _dg_empire_pkt)
            logger.info(f"[scene]   -> conn2 DgEmpire #1 (post-atoms, triggers "
                        f"+0x80=1 and FUN_1406216d0 async state init) "
                        f"({len(_dg_empire_pkt)}B)")
            await asyncio.sleep(0.05)

            logger.info(f"[scene] {_boot_label} 0x29 guard suppressed")

            await write_framed(writer, _dg_empire_pkt)
            logger.info(f"[scene]   -> conn2 DgEmpire #2 (post-atoms, triggers "
                        f"case-0x31 gate pass -> ClientUnitEmpireReceived -> 0x3B) "
                        f"({len(_dg_empire_pkt)}B)")

            if "resume" in str(_boot_label).lower():
                _early18 = _scene_manifest_for_conn()
                await write_framed(writer, _early18)
                logger.info(f'[scene]   -> {_boot_label} 0x18 SceneManifest EARLY ({len(_early18)}B).')

            _com_frames = build_scene_all_db_commodity_0x2b()
            if _com_frames:
                _com_bytes = await write_framed_burst(writer, _com_frames)
                logger.info(f"[scene]   -> conn2 DbCommodity x{len(_com_frames)} "
                            f"(opcode 0x2B, total {_com_bytes}B) - full table")
                try:
                    await _send_commodity_overrides(writer)
                except Exception as _co_exc:
                    logger.warning(f"[commodity] override re-push failed: "
                                   f"{_co_exc!r}")

            _ind_frames = build_scene_all_db_industry_0x32()
            if _ind_frames:
                _ind_total = await write_framed_burst(writer, _ind_frames)
                logger.info(f"[scene]   -> conn2 DbIndustry x{len(_ind_frames)} "
                            f"(opcode 0x32, total {_ind_total}B) - populates "
                            f"DgData->industries before DataComplete")

            _static_done = await _static_tables_already_sent(conn, peer)
            if _static_done:
                logger.info(f'[scene]   conn2 static GD tables already sent to {_static_tables_key(peer)}.')
            _static_streamed = False
            for _tbl_label, _tbl_op, _tbl_fn in (
                    ("DbConstructionProcess", 0x2D,
                     build_scene_all_db_construction_process_0x2d),
                    ("DbConstructionComponent", 0x2C,
                     build_scene_all_db_construction_component_0x2c),
                    ("DbManufacturingProcess", 0x34,
                     build_scene_all_db_manufacturing_process_0x34),
                    ("DbManufacturingComponent", 0x33,
                     build_scene_all_db_manufacturing_component_0x33)):
                if _static_done:
                    continue
                _tbl_frames = _tbl_fn()
                if not _tbl_frames:
                    continue
                _tbl_bytes = await write_framed_burst(writer, _tbl_frames)
                _static_streamed = True
                logger.info(f"[scene]   -> conn2 {_tbl_label} "
                            f"x{len(_tbl_frames)} (opcode 0x{_tbl_op:02X}, total "
                            f"{_tbl_bytes}B)")

            if _static_streamed:
                await _static_tables_mark_sent(conn, peer)

            _dt_frames = build_scene_all_dn_detail_types_0x2f()
            if _dt_frames:
                _dt_bytes = await write_framed_burst(writer, _dt_frames)
                logger.info(f"[scene]   -> conn2 DnDetailType x{len(_dt_frames)} "
                            f"(opcode 0x2F, total {_dt_bytes}B) - populates "
                            f"DgData->detailTypes before DataComplete")

            _dn_room_frames = build_scene_all_dn_room_types_0x30()
            _dn_room_total = 0
            for _rt_pkt in _dn_room_frames:
                await write_framed(writer, _rt_pkt)
                _dn_room_total += len(_rt_pkt)
            logger.info(f"[scene]   -> conn2 DnRoomType x{len(_dn_room_frames)} "
                        f"(opcode 0x30 EmpireDataContinue, total "
                        f"{_dn_room_total}B) - populates DgData->roomTypes "
                        f"before DataComplete")

            _dc = build_scene_empire_data_complete()
            await write_framed(writer, _dc)
            logger.info(f"[scene]   -> conn2 DataComplete (post-atoms) ({len(_dc)}B)")

            sent_scene_init = True
            _conn_label = _boot_label
            logger.info(f"[scene]   {_conn_label}: eager post-bootstrap burst -> "
                        + ("0x2A + ticker (create finish: no 0x38)"
                           if _is_create_finish
                           else "0x2A + 0x38 InitSucceeded + ticker"))

            _pkt_2a_eager = bytes([0x2A]) + int(_person_auid_int).to_bytes(4, "big")
            await write_framed(writer, _pkt_2a_eager)
            logger.info(f"[scene]   -> {_conn_label} 0x2A "
                        f"InitSucceeded(playerUnit=0x{int(_person_auid_int):08x}) "
                        f"({len(_pkt_2a_eager)}B)")

            if _is_create_finish and _robert_live_pkt:
                await write_framed(writer, _robert_live_pkt)
                logger.info(f"[scene] -> {_conn_label} DaPerson re-sent ({len(_robert_live_pkt)}B).")

            if _native_live_pkts:
                for _npkt in _native_live_pkts:
                    await write_framed(writer, _npkt)
                logger.info(f"[natives] {len(_native_live_pkts)} villager atom(s) re-sent.")

            import time as _tt_boot
            if _is_create_finish:
                logger.info(f"[scene] {_conn_label}: 0x38 SceneLoginSucceeded suppressed.")
            else:
                _ausec_boot = int(_tt_boot.time() * 1_000_000)
                _sls_eager = build_scene_init_succeeded(
                    motd=_SAVE.motd,
                    autime_usec=_ausec_boot)
                await write_framed(writer, _sls_eager)
                logger.info(f"[scene]   -> {_conn_label} 0x38 InitSucceeded "
                            f"({len(_sls_eager)}B)")

            _first18_delay = 4.0
            _ack_timeout = 90.0
            _acked = False
            _t_ack0 = _tt_boot.monotonic()
            try:
                await asyncio.wait_for(
                    _init_ack_event(_person_auid_int).wait(),
                    timeout=_ack_timeout)
                _acked = True
                logger.info(f'[scene]   {_conn_label} client ACK for 0x{int(_person_auid_int):08x} after {_tt_boot.monotonic() - _t_ack0:.2f}s.')
            except asyncio.TimeoutError:
                logger.warning(f"[scene] {_conn_label} no client ACK for 0x{int(_person_auid_int):08x} within {_ack_timeout:.0f}s.")
            await asyncio.sleep(_first18_delay)
            logger.info(f"[scene]   {_conn_label} waited {_first18_delay:.2f}s "
                        f"after the {'ACK' if _acked else 'ACK timeout'} so "
                        f"mode_dispatcher_slot case 1 has run FUN_140408690 and "
                        f"frame->View() is non-NULL before the first 0x18 starts "
                        f"AuModel::run")
            _repop_note = (
                "FIRST 0x18 of this connection -- also starts AuModel::run")
            _pkt_0x18_repop = _scene_manifest_for_conn()
            await write_framed(writer, _pkt_0x18_repop)
            logger.info(f"[scene] -> {_conn_label} 0x18 SceneManifest flag=1 (post-login repopulate, triggers ReconcileAtomsInScene with atoms in tree, should fire StarMapAddSector for {len(_scene_auids)} atoms; {_repop_note}) ({len(_pkt_0x18_repop)}B)")

            _augear_state_now = augear_states.get(
                int(_active_avatar_auid) & 0xFFFFFFFF)
            if _augear_state_now:
                _post_aug = _pack_au_gear(_augear_state_now)
                _ap_bytes = (int(_active_avatar_auid) & 0xFFFFFFFF
                             ).to_bytes(4, "big")
                _post_pkt = _build_augear_only_daperson_update(
                    _ap_bytes, _post_aug)
                await write_framed(writer, _post_pkt)
                logger.info(f"[scene] -> {_conn_label} post-init AuGear refresh ({len(_post_aug)}B, {len(_augear_state_now)} slot(s)). Primes the client's cycle-picker + commodity-yield cache so scroll-wheel and forage work without needing a drop first")
            else:
                logger.info(f"[scene] {_conn_label} post-init AuGear refresh skipped: no augear_states entry for 0x{int(_active_avatar_auid):08x}")

            _wparent = (
                _live_avatars.get(int(_active_avatar_auid), {})
                             .get("parent_world")
                or bytes(_AW))
            if _wparent:
                _wkey = bytes(_wparent)
                _w_auid = _FORAGE_WARMUP_BY_WORLD.get(_wkey)
                if _w_auid is None:
                    _w_auid = alloc_daitem_auid()
                    _FORAGE_WARMUP_BY_WORLD[_wkey] = _w_auid
                _w_cid = 130 & 0xFFFF
                _w_xyz = (0.0, 0.0, 0.0)
                _w_body = _pack_auitem_seed_body(
                    typeId=0x01, cid=_w_cid,
                    byte14=5, quality=0x3D,
                    name="", for_world=False)
                _w_now_ms = int(_tt_boot.time() * 1000)
                _w_pkt = _build_daitem_drop_packet(
                    item_auid_int=_w_auid,
                    parent_auid=_wparent,
                    xyz=_w_xyz,
                    item_typeId=0x01,
                    item_body=_w_body,
                    rotation=(0.0, 0.0, 0.0),
                    time_created_ms=_w_now_ms,
                )
                _DYNAMIC_SCENE_AUIDS.add(_w_auid)
                _DROPPED_ITEMS[_w_auid] = {
                    "parent": _wparent,
                    "xyz": tuple(float(v) for v in _w_xyz),
                    "typeId": 0x01,
                    "body": bytes(_w_body),
                    "rotation": (0.0, 0.0, 0.0),
                    "time_created_ms": _w_now_ms,
                }
                await write_framed(writer, _w_pkt)
                logger.info(f"[scene]   -> {_conn_label} forage warmup: "
                            f"0x11 DaItem auid=0x{_w_auid:08x} "
                            f"cid={_w_cid} parent=0x"
                            f"{int.from_bytes(_wparent, 'big'):08x} "
                            f"xyz={_w_xyz} ({len(_w_pkt)}B)")
            else:
                logger.info(f"[scene] {_conn_label} forage cache warmup skipped: no parent_world for avatar 0x{int(_active_avatar_auid):08x}")

            start_ticker_eager(
                writer, _conn_label, _conn_tasks=_conn_tasks,
                anchor_full=sim_time_anchor_full,
                anchor_low32=sim_time_anchor_full & 0xFFFFFFFF,
                sim_time_state=sim_time_state)

            start_manifest_ticker(writer, _conn_label, _conn_tasks=_conn_tasks)
            start_bio_ticker(
                writer, _conn_label, _active_avatar_auid,
                conn=conn,
                _conn_tasks=_conn_tasks,
                _session=_session,
                _SAVE=_SAVE,
                tock_state=_tock_state,
                condition_states=_CONDITION_STATES,
                live_avatars=_live_avatars,
                get_augear=_get_augear,
                agent_bits_for=agent_bits_for,
                _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
                alloc_daitem_auid=alloc_daitem_auid,
                _DROPPED_ITEMS=_DROPPED_ITEMS,
                _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                world_atom_auids=_WORLD_ATOM_AUIDS)

            start_natives_idle_ticker(writer, _conn_label, conn,
                                      _conn_tasks=_conn_tasks)

            start_story_npc_ticker(writer, _conn_label,
                                   _conn_tasks=_conn_tasks,
                                   live_avatars=_live_avatars)

            start_fauna_loops(conn, writer, _conn_label, _conn_tasks,
                              _live_avatars=_live_avatars,
                              _tock_state=_tock_state,
                              _DROPPED_ITEMS=_DROPPED_ITEMS,
                              _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                              agent_bits_for=agent_bits_for)

            start_corpse_sweeper(_conn_label, _conn_tasks=_conn_tasks,
                                 _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)

            logger.info(f'[scene]   {_conn_label}: skipping comm-packet burst (default-off.')

            if _is_create_finish:
                logger.info(f"[scene] {_conn_label}: forced close skipped.")
            else:
                logger.info(f'[scene]   {_conn_label}: HZ_NO_CLOSE_AFTER_BOOT=1.')
            logger.info(f'[scene]   {_conn_label}: forced-close already fired once this process.')
            _self_src = next(
                (a for a in _scene_avatars if a["auid"] == int(_active_avatar_auid)),
                None)
            if _self_src is not None:
                _my_atom = (
                    bytes([0x12]) + _self_src["AP"] + _TIME0
                    + _bpt2_tc(_AW, _self_src["time_created"],
                               *_self_src["xyz"],
                               *_peer_upright_euler(_self_src["xyz"]))
                    + _self_src["pb2"] + b"\x00" * 16)
                for _peer_auid, _peer_entry in list(_live_avatars.items()):
                    if _peer_auid == int(_active_avatar_auid):
                        continue
                    _pw = _peer_entry["writer"]
                    if _pw is None or _pw.is_closing():
                        continue
                    try:
                        await write_framed(_pw, _my_atom)
                        logger.info(f"[scene]   -> peer auid=0x{_peer_auid:08x}: "
                                    f"atom-add {_self_src['name']!r} "
                                    f"(0x{_active_avatar_auid:08x}) {len(_my_atom)}B")
                    except Exception as _pe:
                        logger.warning(f"[scene]   peer push error "
                                       f"auid=0x{_peer_auid:08x}: {_pe!r}")
                _bio_seed = {
                    "hp": (_hp_override if _hp_override is not None
                           else (int(_SAVE.person_hit_points)
                                 or 1)),
                    "hunger": (_hunger_override
                                if _hunger_override is not None
                                else int(_SAVE.person_hunger)) & 0x7fff,
                    "stamina": (_stamina_override
                                 if _stamina_override is not None
                                 else (int(_SAVE.person_stamina)
                                       or 0x7F)) & 0xFF,
                    "pose": (int(_SAVE.person_pose) or 0x24) & 0xFF,
                }
                _peer = writer.get_extra_info("peername")
                _remote_addr = _peer if isinstance(_peer, tuple) else None
                _prev_session_ptr = None
                _prev_entry = _live_avatars.get(
                    int(_active_avatar_auid))
                if isinstance(_prev_entry, dict):
                    _prev_session_ptr = _prev_entry.get("session")
                _live_avatars[int(_active_avatar_auid)] = {
                    "writer":       writer,
                    "remote_addr":  _remote_addr,
                    "parent_world": _AW,
                    "AP":           _self_src["AP"],
                    "xyz":          _self_src["xyz"],
                    "pb2":          _self_src["pb2"],
                    "name":         _self_src["name"],
                    "time_created": _self_src["time_created"],
                    "bio":          _bio_seed,
                    "rebootstrap":  _do_world_bootstrap,
                }
                if _prev_session_ptr is not None:
                    _live_avatars[int(_active_avatar_auid)][
                        "session"] = _prev_session_ptr
                logger.info(f"[scene]   {_conn_label}: REGISTERED live avatar "
                            f"auid=0x{_active_avatar_auid:08x} name={_self_src['name']!r} "
                            f"(total live = {len(_live_avatars)})")
                _story_auid = int(_active_avatar_auid) & 0xFFFFFFFF
                _story_pending = _story_auid in _STORY_PENDING
                if _is_create_finish or _story_pending:
                    _prev_story = _STORY_TASKS.get(_story_auid)
                    if _prev_story is not None and not _prev_story.done():
                        logger.info(f'[story] already running for 0x{_story_auid:08x}.')
                    else:
                        _STORY_PENDING.discard(_story_auid)
                        from openshores.gameplay import story_targoss as _story
                        _st_task = asyncio.create_task(
                            _story.play(_live_avatars, _story_auid,
                                        spawn_world_flag=spawn_world_flag,
                                        save=_SAVE,
                                        avatar_dna=_bootstrap_dna,
                                        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                                        augear_states=augear_states,
                                        actor_cursor=actor_cursor))
                        _STORY_TASKS[_story_auid] = _st_task
                        _st_task.add_done_callback(
                            lambda t, _a=_story_auid:
                            _story_task_done(t, _a))
                        logger.info(f"[story] started for 0x{_story_auid:08x} "
                                    f"(create_finish={_is_create_finish} "
                                    f"pending={_story_pending} "
                                    f"label={_boot_label!r})")
                else:
                    logger.info(f"[story] not started for 0x{_story_auid:08x}: "
                                f"create_finish={_is_create_finish} "
                                f"pending={_story_pending} "
                                f"label={_boot_label!r}")
                for _peer_auid, _peer_entry in list(_live_avatars.items()):
                    if _peer_auid == int(_active_avatar_auid):
                        continue
                    _pw = _peer_entry.get("writer")
                    if _pw is None or _pw.is_closing():
                        continue
                    _builder = getattr(
                        _pw, "_scene_manifest_builder", None)
                    if _builder is None:
                        continue
                    try:
                        _mpkt = _builder()
                        await write_framed(_pw, _mpkt)
                        logger.info("[scene]   -> peer auid=0x%08x: "
                                    "manifest re-emit on JOIN (%dB; "
                                    "added=0x%08x)" % (
                                        _peer_auid, len(_mpkt),
                                        int(_active_avatar_auid)))
                    except Exception as _me:
                        logger.warning("[scene]   peer manifest join-push err "
                                       "auid=0x%08x: %r" % (_peer_auid, _me))
                _PENDING_CHAT_AUIDS.append(int(_active_avatar_auid))
                logger.info("[scene]   pending chat-bind queue: %r" % (
                    [hex(a) for a in _PENDING_CHAT_AUIDS],))

                await mark_online(conn, int(_active_avatar_auid))
                _xyz = _self_src["xyz"]
                await update_person_position(
                    conn, int(_active_avatar_auid),
                    _xyz[0], _xyz[1], _xyz[2])
                logger.info(f"[scene]   {_conn_label}: SQL persist "
                            f"isonline=1 position={_xyz}")


        bootstrap_did_push = (conn_n >= 2 and _variant_b_handled_get(
            _peer_host_scene,
            variant_b_handled_by_ip=_variant_b_handled_by_ip))
        if bootstrap_did_push:
            await _do_world_bootstrap("conn #2 (post-variantB)", 0)
        elif conn_n >= 2:
            logger.info(f'[scene]   conn #{conn_n} (existing-avatar resume).')
    except Exception as e:
        logger.warning(f"[scene]   bootstrap error: {e!r}")

    sent_empire = False
    try:
        while True:
            if _pending_first_frame is not None:
                payload = _pending_first_frame
                _pending_first_frame = None
            else:
                payload = await read_framed(reader)
            op = payload[0] if payload else -1
            op_name = SCENE_OP_NAMES.get(op, f"unknown 0x{op:02X}")
            if op == 0x42:
                setattr(writer, "_hz_saw_0x42", True)
                setattr(writer, "_hz_0x42_count",
                        int(getattr(writer, "_hz_0x42_count", 0)) + 1)
                setattr(writer, "_hz_0x42_mono", _time_mod.monotonic())
            import time as _t_rx
            _t_conn = _t_rx.monotonic() - _conn_t0
            _ts = f"t+{_t_conn:6.3f}s"
            _last_rx_t = _t_conn
            _last_rx_op = op
            _hx = payload.hex() if len(payload) <= 256 else (
                payload[:128].hex() + "..." + payload[-32:].hex())
            if op in _ACK_OPCODES and not _SHOW_ACKS:
                pass
            else:
                logger.debug(f"[scene] <- conn#{conn_n} {_ts} op=0x{op:02X} "
                             f"({op_name}) len={len(payload)}: {_hx}")

            s = QDS(payload); s.read_u8()
            try:
                _new_handler = OPCODE_HANDLERS.get(op)
                if _new_handler is not None and _session is not None:
                    await _new_handler(_session, payload)
                elif op == 0x38:
                    _was_pushed_38 = bootstrap_did_push
                    (_active_avatar_auid,
                     bootstrap_did_push,
                     sent_scene_init) = await handle_0x38(
                        conn, _session, s,
                        writer=writer,
                        conn_n=conn_n,
                        save=_SAVE,
                        active_avatar_auid=_active_avatar_auid,
                        bootstrap_did_push=bootstrap_did_push,
                        sent_scene_init=sent_scene_init,
                        conn_tasks=_conn_tasks,
                        do_world_bootstrap=_do_world_bootstrap,
                        ticker_c2_factory=_functools.partial(
                            _ticker_c2_factory,
                            anchor_full=sim_time_anchor_full,
                            sim_time_state=sim_time_state),
                        build_scene_dn_detail_type=(
                            build_scene_dn_detail_type),
                        name_long=name_long,
                        name_short=name_short,
                        capital_name=capital_name,
                        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
                        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
                        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
                    if (not _was_pushed_38
                            and bootstrap_did_push
                            and sent_scene_init):
                        continue
                elif op == 0x24:
                    await handle_0x24(
                        conn, _session, s,
                        writer=writer,
                        conn_n=conn_n,
                        sent_scene_init=sent_scene_init,
                        peer_host=_peer_host_scene,
                        active_avatar_auid=int(_active_avatar_auid),
                        bootstrap_did_push=bootstrap_did_push,
                        do_world_bootstrap=_do_world_bootstrap,
                        save=_SAVE,
                        build_scene_dn_detail_type=(
                            build_scene_dn_detail_type),
                        _live_avatars=_live_avatars,
                        session_usernames_by_ip=session_usernames_by_ip,
                        variant_b_handled_by_ip=_variant_b_handled_by_ip,
                        _STORY_PENDING=_STORY_PENDING,
                        name_long=name_long,
                        name_short=name_short,
                        capital_name=capital_name,
                        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
                        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
                        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
                elif op == 0x3B:
                    if await handle_0x3b(
                            conn, _session, s,
                            conn_n=conn_n,
                            save=_SAVE,
                            bootstrap_did_push=bootstrap_did_push,
                            sent_scene_init=sent_scene_init,
                            do_world_bootstrap=_do_world_bootstrap):
                        bootstrap_did_push = True
                        continue


                if not hasattr(handle_scene, '_ai_seen_ops'):
                    handle_scene._ai_seen_ops = set()
                if op not in handle_scene._ai_seen_ops:
                    handle_scene._ai_seen_ops.add(op)
                    logger.debug(f"[active-item] first occurrence of opcode 0x{op:02x} len={len(payload)} first32={payload[:32].hex(' ')}")

                elif op == 0x42:
                    if not hasattr(handle_scene, '_ai_prev_42'):
                        handle_scene._ai_prev_42 = {}
                    _ai_conn_key = id(writer)
                    _ai_prev_full = handle_scene._ai_prev_42.get(
                        _ai_conn_key, {})
                    try:
                        _ai_dt = _parse_delta_tick(payload)
                        _watch_keys = (
                            'poses', 'flag08_i16', 'flag08_i32',
                            'flag40_u8', 'flag80_u8',
                            'flag800_i32x10', 'flag800_i16',
                            'flag800_i32',
                        )
                        _ai_diffs = []
                        for _k in _watch_keys:
                            _v = _ai_dt.get(_k)
                            if _v is None:
                                continue
                            _pv = _ai_prev_full.get(_k)
                            if _pv != _v:
                                _ai_diffs.append((_k, _pv, _v))
                                _ai_prev_full[_k] = (
                                    list(_v) if isinstance(_v, list) else _v)
                        if _ai_diffs:
                            logger.debug(
                                f'[active-item] 0x42 D '
                                f'flags=0x{_ai_dt.get("flags", 0):04x}')
                            for _k, _pv, _v in _ai_diffs:
                                logger.debug(f'[active-item]   {_k}: '
                                             f'{_pv} -> {_v}')
                        handle_scene._ai_prev_42[_ai_conn_key] = (
                            _ai_prev_full)
                    except Exception as _ai_e:
                        logger.debug(f'[active-item] 0x42 debug err: {_ai_e!r}')
                    try:
                        _dt = _parse_delta_tick(payload)
                        _proj = _dt.get("projected")
                        _local = _dt.get("position")
                        _world = _proj if _proj else None
                        try:
                            _rot = _dt.get("rotation")
                            _lakey = int(_active_avatar_auid) & 0xFFFFFFFF
                            _laentry = _live_avatars.get(_lakey)
                            if _laentry is not None:
                                if _proj is not None:
                                    _laentry["live_pos"] = tuple(
                                        float(c) for c in _proj)
                                if _rot is not None:
                                    _laentry["live_rot"] = tuple(
                                        float(c) for c in _rot)
                                if (_proj is not None
                                        and _rot is not None
                                        and not _laentry.get(
                                            "_posrot_logged")):
                                    _laentry["_posrot_logged"] = True
                                    logger.debug(f"[pos-rot] auid="
                                                 f"0x{_lakey:08x} "
                                                 f"pos=({_proj[0]:.3f},"
                                                 f"{_proj[1]:.3f},"
                                                 f"{_proj[2]:.3f}) "
                                                 f"rot=({_rot[0]:.6f},"
                                                 f"{_rot[1]:.6f},"
                                                 f"{_rot[2]:.6f})")
                        except Exception as _prce:
                            logger.warning(f"[pos-rot] cache err: {_prce!r}")
                        if _dt_debug_count < _DT_DEBUG_BUDGET:
                            _dt_debug_count += 1
                            _flags = _dt.get("flags", -1)
                            _cons = _dt.get("_consumed", -1)
                            _hex = payload[:64].hex(" ")
                            _wfmt = (
                                f"({_world[0]:.3f}, {_world[1]:.3f}, "
                                f"{_world[2]:.3f})" if _world else "None")
                            _lfmt = (
                                f"({_local[0]:.3f}, {_local[1]:.3f}, "
                                f"{_local[2]:.3f})" if _local else "None")
                            logger.debug(
                                f"[scene]   0x42 #{_dt_debug_count} "
                                f"len={len(payload)} flags=0x{_flags & 0xFFFF:04x} "
                                f"consumed={_cons} world={_wfmt} "
                                f"local={_lfmt}")
                            logger.debug(f"[scene]     raw={_hex}")
                            logger.debug(f"[scene]     decoded={_dt!r}")
                        try:
                            _ci_arr = _dt.get("flag800_i32x10") if isinstance(_dt, dict) else None
                            _ci_i16 = _dt.get("flag800_i16") if isinstance(_dt, dict) else None
                            _ci_i32 = _dt.get("flag800_i32") if isinstance(_dt, dict) else None
                            _ci_aux_i16 = _dt.get("flag08_i16") if isinstance(_dt, dict) else None
                            _ci_aux_i32 = _dt.get("flag08_i32") if isinstance(_dt, dict) else None
                            _ci_target_400 = _dt.get("auid_400") if isinstance(_dt, dict) else None
                            _ci_target_004 = _dt.get("auid_004") if isinstance(_dt, dict) else None
                            _ci_fired = (
                                (_ci_arr and any(int(v) for v in _ci_arr))
                                or _ci_target_400
                                or _ci_target_004
                                or (_ci_i16 not in (None, 0))
                                or (_ci_i32 not in (None, 0))
                                or (_ci_aux_i16 not in (None, 0))
                                or (_ci_aux_i32 not in (None, 0))
                            )
                            if _ci_fired:
                                logger.debug(
                                    f"[ci-sniff] auid="
                                    f"0x{int(_active_avatar_auid):08x} "
                                    f"flags=0x{(_dt.get('flags', 0) & 0xFFFF):04x} "
                                    f"CI[800]={_ci_arr!r} "
                                    f"f800_i16={_ci_i16!r} f800_i32={_ci_i32!r} "
                                    f"f08_i16={_ci_aux_i16!r} f08_i32={_ci_aux_i32!r} "
                                    f"target_400={_ci_target_400!r} "
                                    f"target_004={_ci_target_004!r}")

                            try:
                                _fire_seen = False
                                _reload_seen = False
                                if _ci_arr:
                                    for _idx, _v in enumerate(_ci_arr):
                                        try:
                                            _vi = int(_v)
                                        except Exception:
                                            continue
                                        if _vi == 0x73 or (_vi & 0xFF) == 0x73:
                                            _fire_seen = True
                                            logger.debug(f"[ci-fire]   0x42 trigger[{_idx}]={_vi}")
                                        if _vi == 0x89 or (_vi & 0xFF) == 0x89:
                                            _reload_seen = True
                                            logger.debug(f"[ci-reload] 0x42 trigger[{_idx}]={_vi}")
                                for _label, _val in (
                                        ("f800_i16", _ci_i16),
                                        ("f800_i32", _ci_i32),
                                        ("f08_i16", _ci_aux_i16),
                                        ("f08_i32", _ci_aux_i32)):
                                    if _val is None or _val == 0:
                                        continue
                                    try:
                                        _vi = int(_val)
                                    except Exception:
                                        continue
                                    if _vi == 0x73 or (_vi & 0xFF) == 0x73:
                                        _fire_seen = True
                                        logger.debug(f"[ci-fire]   0x42 {_label}={_vi}")
                                    if _vi == 0x89 or (_vi & 0xFF) == 0x89:
                                        _reload_seen = True
                                        logger.debug(f"[ci-reload] 0x42 {_label}={_vi}")

                                if _fire_seen:
                                    await _handle_fire_weapon_trigger(
                                        int(_active_avatar_auid),
                                        target_auid=int(_ci_target_400 or 0),
                                        writer=writer)
                                if _reload_seen:
                                    await _handle_reload_weapon_trigger(
                                        int(_active_avatar_auid),
                                        writer=writer,
                                        _AUGEAR_STATES=augear_states,
                                        actor_cursor=actor_cursor,
                                        _live_avatars=_live_avatars,
                                        _build_augear_only_daperson_update=(
                                            _build_augear_only_daperson_update))
                            except Exception as _wexc:
                                logger.warning(f"[ci-weapon] handler error: {_wexc!r}")

                            try:
                                _tgt_400_int = (
                                    int(_ci_target_400)
                                    if _ci_target_400 is not None else 0)
                            except Exception:
                                _tgt_400_int = 0
                            try:
                                await _try_pickup_from_target_pin(
                                    _tgt_400_int,
                                    _live_avatars=_live_avatars,
                                    _tock_state=_tock_state,
                                    _get_augear=_get_augear,
                                    _DROPPED_ITEMS=_DROPPED_ITEMS,
                                    _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                                    _build_augear_only_daperson_update=(
                                        _build_augear_only_daperson_update))
                            except Exception as _ppe:
                                logger.warning(f"[pickup-targetpin] error: {_ppe!r}")

                            try:
                                _f08_byte_arr = _dt.get('poses')
                                _f40 = _dt.get('flag40_u8')
                                _f80 = _dt.get('flag80_u8')
                                _flags_now = int(_dt.get('flags', 0)) & 0xFFFF
                                _CI_BITS = (
                                    0x0004 | 0x0008 | 0x0040 | 0x0080
                                    | 0x0400 | 0x0800)
                                _has_ci = bool(_flags_now & _CI_BITS)
                                if _has_ci:
                                    _key = (
                                        _ci_target_004,
                                        _ci_target_400,
                                        tuple(_ci_arr) if _ci_arr else None,
                                        _ci_i16,
                                        _ci_i32,
                                        tuple(_f08_byte_arr) if _f08_byte_arr else None,
                                        _ci_aux_i16,
                                        _ci_aux_i32,
                                        _f40,
                                        _f80,
                                    )
                                    _prev = _GRAB_PROBE_LAST.get(
                                        int(_active_avatar_auid))
                                    if _key != _prev:
                                        _GRAB_PROBE_LAST[int(_active_avatar_auid)] = _key
                                        _drop_match = (
                                            _ci_target_400 is not None
                                            and int(_ci_target_400) in _DROPPED_ITEMS)
                                        _drop_match_004 = (
                                            _ci_target_004 is not None
                                            and int(_ci_target_004) in _DROPPED_ITEMS)
                                        _star = ('  *DROP*' if _drop_match
                                                  else ('  *DROP-004*' if _drop_match_004
                                                        else ''))
                                        logger.debug(
                                            f"[grab-probe]{_star} "
                                            f"player=0x{int(_active_avatar_auid):08x} "
                                            f"flags=0x{_flags_now:04x}")
                                        if _ci_target_004 not in (None, 0):
                                            logger.debug(f"[grab-probe]   target_004=0x{int(_ci_target_004):08x}")
                                        if _ci_target_400 not in (None, 0):
                                            logger.debug(f"[grab-probe]   target_400=0x{int(_ci_target_400):08x}")
                                        if _ci_arr and any(int(v) for v in _ci_arr):
                                            logger.debug(f"[grab-probe]   CI[800]_i32x10={_ci_arr!r}")
                                        if _ci_i16 not in (None, 0):
                                            logger.debug(f"[grab-probe]   f800_i16={_ci_i16!r}")
                                        if _ci_i32 not in (None, 0):
                                            logger.debug(f"[grab-probe]   f800_i32={_ci_i32!r}")
                                        if _f08_byte_arr and any(int(v) for v in _f08_byte_arr):
                                            logger.debug(f"[grab-probe]   f08_poses={_f08_byte_arr!r}")
                                        if _ci_aux_i16 not in (None, 0):
                                            logger.debug(f"[grab-probe]   f08_i16={_ci_aux_i16!r}")
                                        if _ci_aux_i32 not in (None, 0):
                                            logger.debug(f"[grab-probe]   f08_i32={_ci_aux_i32!r}")
                                        if _f40 not in (None, 0):
                                            logger.debug(f"[grab-probe]   flag40_u8=0x{int(_f40):02x}")
                                        if _f80 not in (None, 0):
                                            logger.debug(f"[grab-probe]   flag80_u8=0x{int(_f80):02x}")
                            except Exception as _gpe:
                                logger.warning(f"[grab-probe] log error: {_gpe!r}")
                        except Exception as _cie:
                            logger.debug(f"[ci-sniff] error: {_cie!r}")

                        _poses = _dt.get("poses") if isinstance(_dt, dict) else None
                        if _poses and isinstance(_poses, (list, tuple)):
                            try:
                                _new_pose = int(_poses[0]) & 0xFF
                                _ts_entry = _tock_state.setdefault(
                                    int(_active_avatar_auid),
                                    {"pose": 0x24,
                                     "last_minute": -1,
                                     "last_hour": -1})
                                _old_pose = _ts_entry.get("pose", 0x24) & 0xFF
                                _ts_entry["pose"] = _new_pose
                                if _new_pose != _old_pose:
                                    logger.debug(f"[pose-track] auid="
                                                 f"0x{int(_active_avatar_auid):08x} "
                                                 f"pose 0x{_old_pose:02x} -> "
                                                 f"0x{_new_pose:02x} (full="
                                                 f"{[hex(p) for p in _poses[:10]]})")
                            except Exception as _pte:
                                logger.debug(f"[pose-track] error: {_pte!r}")
                        if _proj:
                            try:
                                import math as _m_alt
                                import time as _t_alt
                                _x_alt, _y_alt, _z_alt = (
                                    float(_proj[0]),
                                    float(_proj[1]),
                                    float(_proj[2]))
                                _alt = _m_alt.sqrt(
                                    _x_alt * _x_alt
                                    + _y_alt * _y_alt
                                    + _z_alt * _z_alt)
                                _ts_alt_entry = _tock_state.setdefault(
                                    int(_active_avatar_auid),
                                    {"pose": 0x24,
                                     "last_minute": -1,
                                     "last_hour": -1})
                                _last_alt = _ts_alt_entry.get(
                                    "last_alt", _alt)
                                _alt_thresh = 0.0
                                _air_window = 2.0
                                _now_alt_t = _t_alt.monotonic()
                                _was_airborne = (
                                    _now_alt_t
                                    < _ts_alt_entry.get(
                                        "airborne_until", 0.0))
                                if abs(_alt - _last_alt) > _alt_thresh:
                                    _ts_alt_entry["airborne_until"] = (
                                        _now_alt_t + _air_window)
                                _is_airborne_now = (
                                    _now_alt_t
                                    < _ts_alt_entry.get(
                                        "airborne_until", 0.0))
                                if (not _was_airborne) and _is_airborne_now:
                                    _max_stam_jp = int(
                                        _ts_alt_entry.get("max_stamina") or 0)
                                    if _max_stam_jp > 0:
                                        _jump_cost = max(
                                            1, _max_stam_jp // 15)
                                    else:
                                        _jump_cost = 7
                                    _cur_stam = int(
                                        _ts_alt_entry.get(
                                            "stamina", 127))
                                    _new_stam = max(
                                        0, _cur_stam - _jump_cost)
                                    if _new_stam != _cur_stam:
                                        _ts_alt_entry["stamina"] = _new_stam
                                        logger.debug(f"[jump-debit] auid="
                                                     f"0x{int(_active_avatar_auid):08x} "
                                                     f"stamina {_cur_stam}->"
                                                     f"{_new_stam} (cost="
                                                     f"{_jump_cost})")
                                        _now_ms_jp = int(
                                            _t_alt.time() * 1000)
                                        _hp_jp = int(
                                            _ts_alt_entry.get(
                                                "hp", 46))
                                        _hunger_jp = int(
                                            _ts_alt_entry.get("hunger", _ts_alt_entry.get("max_hunger") or 100))
                                        _hp_jp_clamped = max(
                                            -30, min(0x7fff,
                                                      _hp_jp))
                                        _jump_pkt = (
                                            bytes([0x12])
                                            + struct.pack(
                                                ">I",
                                                int(_active_avatar_auid))
                                            + struct.pack(
                                                ">q", _now_ms_jp)
                                            + bytes([0x00])
                                            + bytes([0x00])
                                            + bytes([0x04])
                                            + struct.pack(
                                                ">h", _hp_jp_clamped)
                                            + bytes([
                                                _new_stam & 0xFF])
                                            + bytes([0x00])
                                            + bytes([0x0C])
                                            + struct.pack(
                                                ">H",
                                                _hunger_i16(
                                                    int(_active_avatar_auid),
                                                    _hunger_jp,
                                                    _tock_state=_tock_state))
                                            + bytes([agent_bits_for(
                                                int(_active_avatar_auid))
                                                & 0x3F])
                                        )
                                        try:
                                            await write_framed(
                                                writer, _jump_pkt)
                                        except Exception as _jpe:
                                            logger.warning(
                                                f"[jump-debit] push "
                                                f"failed: {_jpe!r}")
                                _ts_alt_entry["last_alt"] = _alt
                            except Exception as _ale:
                                logger.debug(f"[jump-debit] airborne "
                                             f"detection error: {_ale!r}")
                        if _world:
                            _entry = _live_avatars.get(int(_active_avatar_auid))
                            if _entry is not None:
                                _prev_xyz = _entry.get("xyz")
                                _new_xyz = (float(_world[0]),
                                            float(_world[1]),
                                            float(_world[2]))
                                _entry["xyz"] = _new_xyz
                                try:
                                    import math as _xz_m
                                    _new_mag = _xz_m.sqrt(
                                        _new_xyz[0]*_new_xyz[0] +
                                        _new_xyz[1]*_new_xyz[1] +
                                        _new_xyz[2]*_new_xyz[2])
                                    _prev_mag = None
                                    if _prev_xyz:
                                        _prev_mag = _xz_m.sqrt(
                                            _prev_xyz[0]*_prev_xyz[0] +
                                            _prev_xyz[1]*_prev_xyz[1] +
                                            _prev_xyz[2]*_prev_xyz[2])
                                    _aid = int(_active_avatar_auid)
                                    _cached_mount = _PLAYER_MOUNTED_VEHICLE.get(_aid)
                                    _pending = _PENDING_DISMOUNT.get(_aid)
                                    if _pending is not None and _new_mag > 1000.0:
                                        _PENDING_DISMOUNT.pop(_aid, None)
                                        try:
                                            await _finalize_vehicle_dismount(
                                                int(_aid),
                                                int(_pending),
                                                exit_xyz=_new_xyz,
                                                live_avatars=_live_avatars,
                                                conn=conn,
                                                _VEH_PARENT_FLOOR=(
                                                    _VEH_PARENT_FLOOR),
                                                _stamina_byte=_stamina_byte,
                                                agent_bits_for=agent_bits_for)
                                        except Exception as _fde:
                                            logger.warning(f"[mount-detect] pending "
                                                           f"snapshot err: {_fde!r}")
                                        try:
                                            await update_person_position(
                                                conn,
                                                int(_active_avatar_auid),
                                                float(_new_xyz[0]),
                                                float(_new_xyz[1]),
                                                float(_new_xyz[2]))
                                            _entry["_last_sql_pos_t"] = (
                                                __import__("time").monotonic())
                                        except Exception as _pdse:
                                            logger.warning(
                                                f"[mount-detect] pending "
                                                f"dismount SQL persist "
                                                f"failed: {_pdse!r}")
                                        logger.info(f"[mount-detect] pending "
                                                    f"dismount snapshot done "
                                                    f"(player 0x{_aid:08x} "
                                                    f"vehicle 0x{int(_pending):08x})")
                                    if (_new_mag < 100.0
                                            and (_prev_mag is None or _prev_mag > 1000.0)
                                            and _cached_mount is None):
                                        _ref = _prev_xyz or _new_xyz
                                        _best = None
                                        _best_d2 = None
                                        for _vc in list_active_vehicles():
                                            _dx = float(_vc.locX) - _ref[0]
                                            _dy = float(_vc.locY) - _ref[1]
                                            _dz = float(_vc.locZ) - _ref[2]
                                            _d2 = _dx*_dx + _dy*_dy + _dz*_dz
                                            if _best is None or _d2 < _best_d2:
                                                _best = _vc
                                                _best_d2 = _d2
                                        if _best is not None and _best_d2 < (100.0 * 100.0):
                                            _PLAYER_MOUNTED_VEHICLE[_aid] = int(_best.id)
                                            try:
                                                _best.switches = int(_best.switches) | 0x04
                                            except Exception as _bse:
                                                logger.debug(
                                                    f"[mount-detect] mounted "
                                                    f"bit err: {_bse!r}")
                                            logger.info(f"[mount-detect] player "
                                                        f"0x{_aid:08x} MOUNTED "
                                                        f"vehicle 0x{int(_best.id):08x} "
                                                        f"(xyz transitioned to "
                                                        f"vehicle-local, dist="
                                                        f"{_xz_m.sqrt(_best_d2):.1f}m)")
                                            try:
                                                await _finalize_vehicle_mount(
                                                    int(_aid),
                                                    int(_best.id),
                                                    live_avatars=_live_avatars,
                                                    _stamina_byte=_stamina_byte,
                                                    agent_bits_for=agent_bits_for)
                                            except Exception as _fmex:
                                                logger.warning(f"[mount-detect] "
                                                               f"mount finalize err: "
                                                               f"{_fmex!r}")
                                    elif (_new_mag > 1000.0
                                            and _cached_mount is not None):
                                        _PLAYER_MOUNTED_VEHICLE.pop(_aid, None)
                                        try:
                                            await _finalize_vehicle_dismount(
                                                int(_aid),
                                                int(_cached_mount),
                                                exit_xyz=_new_xyz,
                                                live_avatars=_live_avatars,
                                                conn=conn,
                                                _VEH_PARENT_FLOOR=(
                                                    _VEH_PARENT_FLOOR),
                                                _stamina_byte=_stamina_byte,
                                                agent_bits_for=agent_bits_for)
                                        except Exception as _fde:
                                            logger.warning(f"[mount-detect] cleanup "
                                                           f"err: {_fde!r}")
                                        try:
                                            await update_person_position(
                                                conn,
                                                int(_active_avatar_auid),
                                                float(_new_xyz[0]),
                                                float(_new_xyz[1]),
                                                float(_new_xyz[2]))
                                            _entry["_last_sql_pos_t"] = (
                                                __import__("time").monotonic())
                                        except Exception as _pp:
                                            logger.warning(f"[mount-detect] player "
                                                           f"SQL persist failed: {_pp!r}")
                                        logger.info(f"[mount-detect] player "
                                                    f"0x{_aid:08x} DISMOUNTED "
                                                    f"via magnitude "
                                                    f"(was 0x{_cached_mount:08x})")
                                except Exception as _mde:
                                    logger.warning(f"[mount-detect] err: {_mde!r}")

                                if _session is not None:
                                    _session.mark_position_dirty(
                                        float(_world[0]),
                                        float(_world[1]),
                                        float(_world[2]))
                                    _session.hot_state_suppressed_total += 1
                        if _world:
                            try:
                                _veh_id = _PLAYER_MOUNTED_VEHICLE.get(
                                    int(_active_avatar_auid))
                                if _veh_id is not None:
                                    _v = get_active_vehicle(int(_veh_id))
                                    if _v is not None:
                                        _sec_pos = (_dt.get("secondary_position")
                                                    if isinstance(_dt, dict)
                                                    else None)
                                        if _sec_pos is not None:
                                            _a400_v = int(
                                                _dt.get("auid_400") or 0
                                            ) & 0xFFFFFFFF
                                            if (_a400_v == 0 or _a400_v
                                                    == int(_veh_id) & 0xFFFFFFFF):
                                                try:
                                                    _v.locX = float(_sec_pos[0])
                                                    _v.locY = float(_sec_pos[1])
                                                    _v.locZ = float(_sec_pos[2])
                                                except Exception as _vpe:
                                                    logger.warning(
                                                        f"[scene]   vehicle "
                                                        f"pos update err: {_vpe!r}")
                                        _auid004 = (_dt.get("auid_004")
                                                    if isinstance(_dt, dict)
                                                    else None) or 0
                                        _auid400 = (_dt.get("auid_400")
                                                    if isinstance(_dt, dict)
                                                    else None) or 0
                                        _last_seen = _VEH_PARENT_WATCH.setdefault(
                                            int(_veh_id),
                                            {"auid_004": 0, "auid_400": 0,
                                             "ts_print": 0.0})
                                        import time as _pwt
                                        _now_pw = _pwt.monotonic()
                                        if ((int(_auid004) and
                                                int(_auid004) != _last_seen["auid_004"])
                                                or
                                            (int(_auid400) and
                                                int(_auid400) != _last_seen["auid_400"])):
                                            logger.info(f"[scene]   0x42 auid "
                                                        f"change for vehicle 0x{int(_veh_id):08x}: "
                                                        f"auid_004=0x{int(_auid004):08x} "
                                                        f"(was 0x{_last_seen['auid_004']:08x}) "
                                                        f"auid_400=0x{int(_auid400):08x} "
                                                        f"(was 0x{_last_seen['auid_400']:08x}) "
                                                        f"current_idp=0x{int(_v.idp):08x}")
                                            _last_seen["auid_004"] = int(_auid004)
                                            _last_seen["auid_400"] = int(_auid400)
                                            for _cand in (int(_auid400),
                                                          int(_auid004)):
                                                if not (_cand
                                                        and _cand != int(_v.idp)
                                                        and _cand != int(_veh_id)
                                                        and _cand != int(
                                                            _active_avatar_auid)):
                                                    continue
                                                if _cand not in _WORLD_ATOM_AUIDS:
                                                    logger.info(f"[scene] REPARENT rejected vehicle 0x{int(_veh_id):08x}: candidate 0x{_cand:08x} is not a world atom (prevents vehicle-to-vehicle parent loop)")
                                                    continue
                                                logger.info(f"[scene]   REPARENT "
                                                            f"vehicle 0x{int(_veh_id):08x}: "
                                                            f"idp 0x{int(_v.idp):08x} "
                                                            f"-> 0x{_cand:08x} "
                                                            f"(world atom)")
                                                _v.idp = int(_cand) & 0xFFFFFFFF
                                                break
                                        elif _now_pw - _last_seen["ts_print"] > 5.0:
                                            _last_seen["ts_print"] = _now_pw
                                            logger.debug(f"[scene]   0x42 vehicle "
                                                         f"watch (steady): auid_004="
                                                         f"0x{int(_auid004):08x} "
                                                         f"auid_400="
                                                         f"0x{int(_auid400):08x} "
                                                         f"idp=0x{int(_v.idp):08x}")
                                        try:
                                            await commit_vehicle(int(_veh_id),
                                                                 conn=conn)
                                        except Exception as _vce:
                                            logger.warning(f"[scene]   vehicle "
                                                           f"commit failed: {_vce!r}")
                                        try:
                                            _vpkt = build_da_vehicle_update(_v)
                                            _driver_auid = int(
                                                _active_avatar_auid) & 0xFFFFFFFF
                                            for _peer_auid, _peer_entry in list(
                                                    _live_avatars.items()):
                                                if int(_peer_auid) & 0xFFFFFFFF == _driver_auid:
                                                    continue
                                                _pw = _peer_entry.get("writer")
                                                if _pw is None or _pw.is_closing():
                                                    continue
                                                try:
                                                    await write_framed(_pw, _vpkt)
                                                except Exception as _vpe2:
                                                    logger.debug(
                                                        f"[scene]   vehicle push "
                                                        f"to 0x{_peer_auid:08x} "
                                                        f"failed: {_vpe2!r}")
                                        except Exception as _vbe:
                                            logger.warning(f"[scene]   vehicle "
                                                           f"broadcast failed: {_vbe!r}")
                                        logger.debug(f"[scene]   0x42 vehicle "
                                                     f"sync auid=0x{int(_veh_id):08x} "
                                                     f"xyz=({_v.locX:.1f},{_v.locY:.1f},"
                                                     f"{_v.locZ:.1f})")
                            except Exception as _vse:
                                logger.warning(f"[scene]   vehicle sync err: "
                                               f"{_vse!r}")
                        if _world:
                            try:
                                _self_auid = int(_active_avatar_auid)
                                _ts_e = _tock_state.setdefault(
                                    _self_auid,
                                    {"pose": 0x24,
                                     "last_minute": -1,
                                     "last_hour": -1})
                                _pose_now = int(_ts_e.get("pose", 0x24)) & 0xFF
                                _stam_now = int(_ts_e.get("stamina", 0x7F)) & 0xFF
                                _rot = _dt.get("rotation") if isinstance(_dt, dict) else None
                                if _rot and isinstance(_rot, (list, tuple)) and len(_rot) >= 3:
                                    _ts_e["last_rotation"] = (
                                        float(_rot[0]), float(_rot[1]),
                                        float(_rot[2]))
                                _rot_use = _ts_e.get(
                                    "last_rotation", (0.0, 0.0, 0.0))
                                import time as _sync_t
                                _sync_now = int(_sync_t.time() * 1000)
                                _poses_arr = _dt.get("poses") if isinstance(_dt, dict) else None
                                if _poses_arr and isinstance(_poses_arr, (list, tuple)):
                                    _ts_e["last_poses"] = bytes(
                                        int(p) & 0xFF for p in _poses_arr[:10])
                                _poses_bytes = _ts_e.get(
                                    "last_poses", bytes([_pose_now] * 10))
                                if len(_poses_bytes) < 10:
                                    _poses_bytes = (_poses_bytes
                                                     + bytes([_pose_now])
                                                     * (10 - len(_poses_bytes)))
                                _tilt_i16 = _dt.get("flag08_i16") if isinstance(_dt, dict) else None
                                if _tilt_i16 is not None:
                                    _ts_e["last_head_tilt_i16"] = int(_tilt_i16)
                                _sync_dacreature_flag = 0x00
                                _dacreature_payload = b""
                                _dacreature_payload += bytes([_stam_now])
                                _sync_pkt = (
                                    bytes([0x12])
                                    + struct.pack(">I", _self_auid)
                                    + struct.pack(">q", _sync_now)
                                    + bytes([0x08])
                                    + struct.pack(
                                        ">6f",
                                        float(_world[0]), float(_world[1]),
                                        float(_world[2]),
                                        float(_rot_use[0]),
                                        float(_rot_use[1]),
                                        float(_rot_use[2]))
                                    + bytes([0x00])
                                    + bytes([_sync_dacreature_flag])
                                    + _dacreature_payload
                                    + bytes([0x00])
                                    + bytes([0x08])
                                    + bytes([agent_bits_for(_self_auid)
                                             & 0x3F])
                                )
                                _peers = [
                                    (a, e) for a, e in _live_avatars.items()
                                    if a != _self_auid and e.get("writer")
                                    and not e["writer"].is_closing()]
                                for _peer_auid, _peer_e in _peers:
                                    try:
                                        await write_framed(
                                            _peer_e["writer"], _sync_pkt)
                                    except Exception as _se:
                                        logger.warning(f"[sync] push to "
                                                       f"0x{_peer_auid:08x} "
                                                       f"failed: {_se!r}")
                            except Exception as _bc_exc:
                                logger.warning(f"[sync] broadcast error "
                                               f"(non-fatal): {_bc_exc!r}")
                    except Exception as _dte:
                        logger.warning(f"[scene]   0x42 decode/persist error "
                                       f"(non-fatal): {_dte!r}")

                probe_entries = SCENE_PROBES.get(SCENE_PROBE_NAME, [])
                for trigger_op, builder in probe_entries:
                    if op == trigger_op:
                        try:
                            reply = builder() if callable(builder) else builder
                            if _inspect.isawaitable(reply):
                                reply = await reply
                        except Exception as _pe:
                            logger.warning("[scene]   probe build failed: " + repr(_pe))
                            continue
                        if reply:
                            await write_framed(writer, reply)
                            logger.info(f"[scene]   -> probe on 0x{op:02X}: {len(reply)}B")
            except Exception as _he:
                logger.warning("[scene]   handler error on 0x%02X: %r" % (op, _he))
    except asyncio.IncompleteReadError:
        import time as _t_fin
        _fin_t = _t_fin.monotonic() - _conn_t0
        if _last_rx_t is not None:
            _delta = _fin_t - _last_rx_t
            logger.info(f"[scene] {peer} closed (incomplete read) at "
                        f"t+{_fin_t:6.3f}s "
                        f"(Δ{_delta*1000:.1f}ms after last RX "
                        f"op=0x{_last_rx_op:02X})")
        else:
            logger.info(f"[scene] {peer} closed (incomplete read) at "
                        f"t+{_fin_t:6.3f}s (no RX before FIN)")
    except ConnectionResetError:
        import time as _t_rst
        _rst_t = _t_rst.monotonic() - _conn_t0
        if _last_rx_t is not None:
            _delta = _rst_t - _last_rx_t
            logger.info(f"[scene] {peer} reset at t+{_rst_t:6.3f}s "
                        f"(Δ{_delta*1000:.1f}ms after last RX "
                        f"op=0x{_last_rx_op:02X})")
        else:
            logger.info(f"[scene] {peer} reset at t+{_rst_t:6.3f}s "
                        f"(no RX before RST)")
    except Exception as e:  # noqa: BLE001
        logger.warning("[scene] %s error: %r" % (peer, e))
    finally:
        if _conn_tasks:
            _n_cancelled = 0
            for _t in _conn_tasks:
                if not _t.done():
                    _t.cancel()
                    _n_cancelled += 1
            if _n_cancelled:
                try:
                    await asyncio.gather(*_conn_tasks, return_exceptions=True)
                except Exception as _gxc:
                    logger.warning(f"[scene] {peer} per-conn task gather err "
                                   f"(non-fatal): {_gxc!r}")
            logger.info(f"[scene] {peer} per-conn task cleanup: "
                        f"cancelled {_n_cancelled}/{len(_conn_tasks)}")

        if _session is not None:
            try:
                _g2_n = _session.flush_to_queue(get_queue(), force=True)
                if _g2_n:
                    logger.info(f"[scene] {peer} G.2 final flush: "
                                f"{_g2_n} op(s) submitted "
                                f"(auid=0x{_session.player_auid:08x})")
            except Exception as _g2fe:
                logger.warning(f"[scene] {peer} G.2 final flush err "
                               f"(non-fatal): {_g2fe!r}")

        if _session is not None:
            try:
                detach_from_live_avatars(_live_avatars, _session)
            except Exception as _dxc:
                logger.warning(f"[scene] {peer} session detach err "
                               f"(non-fatal): {_dxc!r}")

        try:
            _deregister_auid = int(_active_avatar_auid)
            _bio_snapshot = {}
            _entry = _live_avatars.get(_deregister_auid)
            if _entry is not None and _entry.get("writer") is writer:
                _last_xyz = _entry.get("xyz")
                _live_avatars.pop(_deregister_auid, None)
                if _deregister_auid == 0x1:
                    try:
                        clear_synthetic_auid(0x1)
                        logger.info(f"[scene] {peer} cleared synth=0x1 from "
                                    f"_synthetic_auid_map (variant-B lock released)")
                    except Exception as _csa_e:
                        logger.warning(f"[scene] clear_synthetic_auid err "
                                       f"(non-fatal): {_csa_e!r}")
                logger.info(f"[scene] {peer} DEREGISTERED live avatar "
                            f"auid=0x{_deregister_auid:08x} "
                            f"(remaining live = {len(_live_avatars)})")
                _clear_init_ack(_deregister_auid)
                _bio_snapshot = dict(_tock_state.get(_deregister_auid) or {})
                try:
                    _tock_state.pop(_deregister_auid, None)
                    augear_states.pop(_deregister_auid, None)
                    logger.info(f"[scene] {peer} cleared _tock_state + "
                                f"_AUGEAR_STATES for auid="
                                f"0x{_deregister_auid:08x}")
                except Exception as _ce:
                    logger.warning(f"[scene] {peer} per-actor cleanup err: {_ce!r}")
                try:
                    _peer_host_cleanup = (
                        peer[0] if isinstance(peer, tuple) and peer else "")
                    _cleanup_ip_state_if_idle(
                        _live_avatars, _peer_host_cleanup,
                        scene_connect_n_by_ip=_scene_connect_n_by_ip,
                        variant_b_handled_by_ip=_variant_b_handled_by_ip,
                        force_closed_once_by_ip=force_closed_once_by_ip,
                        session_usernames_by_ip=session_usernames_by_ip)
                except Exception as _ipce:
                    logger.warning(f"[scene] {peer} per-IP cleanup err: "
                                   f"{_ipce!r}")
                for _peer_auid, _peer_entry in list(_live_avatars.items()):
                    _pw = _peer_entry.get("writer")
                    if _pw is None or _pw.is_closing():
                        continue
                    _builder = getattr(
                        _pw, "_scene_manifest_builder", None)
                    if _builder is None:
                        continue
                    try:
                        _mpkt = _builder()
                        await write_framed(_pw, _mpkt)
                        logger.info("[scene]   -> peer auid=0x%08x: "
                                    "manifest re-emit (%d bytes; "
                                    "removed=0x%08x)" % (
                                        _peer_auid, len(_mpkt),
                                        _deregister_auid))
                    except Exception as _me:
                        logger.warning("[scene]   peer manifest push err "
                                       "auid=0x%08x: %r" % (_peer_auid, _me))
                try:
                    await mark_offline(conn, _deregister_auid)
                    if _last_xyz:
                        await update_person_position(
                            conn,
                            _deregister_auid,
                            float(_last_xyz[0]),
                            float(_last_xyz[1]),
                            float(_last_xyz[2]))
                        logger.info(f"[scene] {peer} SQL persist "
                                    f"final position={_last_xyz}")
                    _bio = _bio_snapshot or _tock_state.get(
                        _deregister_auid)
                    if not _bio:
                        _bio = _entry.get("bio") if _entry else None
                    if _bio:
                        _bio_fields = {k: int(v) for k, v in _bio.items()
                                        if k in ("hp", "hunger",
                                                  "stamina", "pose")}
                        if _bio_fields:
                            await update_person_state(
                                conn, _deregister_auid, **_bio_fields)
                            logger.info(f"[scene] {peer} SQL persist "
                                        f"bio={_bio_fields}")
                except Exception as _we:
                    logger.warning(f"[scene] {peer} SQL flush error "
                                   f"(non-fatal): {_we!r}")
        except Exception as _de:
            logger.warning(f"[scene] {peer} deregister error: {_de!r}")
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as _wce:
            logger.debug(f"[scene] {peer} writer close err: {_wce!r}")
        if _announced_scene:
            logger.info(f"[scene] {peer} disconnected")
