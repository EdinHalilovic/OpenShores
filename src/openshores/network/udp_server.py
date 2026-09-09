
from __future__ import annotations

import asyncio
import struct as _udp_struct

from openshores.core.config import Deployment
from openshores.core.logging import get_logger
from openshores.gameplay.vehicles.atom_packet import (
    build_da_vehicle_keepalive,
    build_da_vehicle_update,
)
from openshores.gameplay.vehicles.input import process_input
from openshores.gameplay.vehicles.spawn import (
    commit_vehicle,
    get_active_vehicle,
)
from openshores.network.flag_claim import _maybe_flag_claim
from openshores.network.recall_home import _execute_recall_home
from openshores.network.udp_resolve import _actor_from_udp_addr
from openshores.network.vehicle_mount import _finalize_vehicle_mount
from openshores.protocol.control_input import _udp_decode_0x37
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


_UDP_TRANSPORT = None
_UDP_HOLD: dict = {}
_UDP_LAST_PICKUP_AT: float = 0.0
_UDP_LAST_PICKUP_BY_ACTOR: dict = {}
_UDP_DEBUG = False


_FLAG_CLAIM_CANDIDATE_SEEN: set = set()

_UDP_RESOLVE_LOGGED: set = set()


async def _udp_maybe_pickup(target, actor_auid=0, action=0, arg=0,
                             hit_target=0, aim_x=0.0, aim_y=0.0,
                             *, conn, _live_avatars, _DROPPED_ITEMS,
                             _WORLD_ATOM_AUIDS, _PLAYER_MOUNTED_VEHICLE,
                             _PENDING_DISMOUNT, _finalize_vehicle_dismount,
                             _execute_pickup, _execute_forage,
                             _handle_fire_weapon_trigger,
                             _handle_reload_weapon_trigger, _SAVE,
                             _CITIZEN_EMPIRE_OVERRIDE, alloc_daitem_auid,
                             _tock_state, _DYNAMIC_SCENE_AUIDS, agent_bits,
                             agent_bits_for, manifest_suppress,
                             force_scene_manifest_push, peer_upright_euler,
                             _stamina_byte, retarget_bundle_to_avatar,
                             broadcast_to_peers):
    global _UDP_LAST_PICKUP_AT
    import time as _t
    now = _t.monotonic()
    debounce = 0.6
    _pickup_actor = int(actor_auid) & 0xFFFFFFFF

    if int(action) == 0x73:
        logger.info(f'[udp-disp] CI 0x73 Fire Weapon -> actor=0x{int(actor_auid):08x} '
                    f'hit_target=0x{int(hit_target):08x} aim=({aim_x:.2f},{aim_y:.2f})')
        try:
            await _handle_fire_weapon_trigger(int(actor_auid),
                                              target_auid=int(hit_target),
                                              aim_x=float(aim_x),
                                              aim_y=float(aim_y))
        except Exception as exc:
            logger.warning(f"[udp-disp] fire dispatch raised: {exc!r}")
        return

    if int(action) == 0x89:
        logger.info(f'[udp-disp] CI 0x89 Reload -> actor=0x{int(actor_auid):08x}')
        try:
            await _handle_reload_weapon_trigger(int(actor_auid))
        except Exception as exc:
            logger.warning(f"[udp-disp] reload dispatch raised: {exc!r}")
        return

    is_pickup = bool(_DROPPED_ITEMS) and target in _DROPPED_ITEMS
    is_forage = target in _WORLD_ATOM_AUIDS

    _veh_target = None
    _actor_id = int(actor_auid) & 0xFFFFFFFF
    try:
        _tgt_int = int(target) & 0xFFFFFFFF
        if get_active_vehicle(_tgt_int) is not None:
            _veh_target = _tgt_int
            try:
                _vmnt = get_active_vehicle(_tgt_int)
                if (_vmnt is not None and not (int(_vmnt.switches) & 0x04)):
                    _vmnt.switches = int(_vmnt.switches) | 0x04
                    logger.info(f"[udp-disp] vehicle 0x{_tgt_int:08x} "
                                f"switches |= 0x04 (mounted/armed)")
            except Exception as _swx:
                logger.debug(f"[udp-disp] mounted-bit set skipped: {_swx!r}")
            if _PLAYER_MOUNTED_VEHICLE.get(_actor_id) != _tgt_int:
                _PLAYER_MOUNTED_VEHICLE[_actor_id] = _tgt_int
                logger.info(f"[udp-disp] player 0x{_actor_id:08x} now "
                            f"driving vehicle 0x{_tgt_int:08x}")
                try:
                    await _finalize_vehicle_mount(
                        _actor_id, _tgt_int,
                        live_avatars=_live_avatars,
                        _stamina_byte=_stamina_byte,
                        agent_bits_for=agent_bits_for)
                except Exception as _fmex:
                    logger.warning(f"[udp-disp] mount finalize err: {_fmex!r}")
        elif _tgt_int == _actor_id:
            _cached = _PLAYER_MOUNTED_VEHICLE.get(_actor_id)
            if _cached and get_active_vehicle(_cached) is not None:
                _veh_target = _cached
    except Exception as _vlex:
        logger.warning(f"[udp-disp] vehicle-lookup err: {_vlex!r}")
        _veh_target = None
    if _veh_target is not None:
        try:
            _arg_u16 = int(arg) & 0xFFFF
            _ci_from_arg = (_arg_u16 >> 8) & 0xFF
            _ci_payload  = _arg_u16 & 0xFF
            _ci_action   = int(action) & 0xFF

            _is_idle_poll = (_arg_u16 == 0 and _ci_action == 0x00)
            _v_pre = get_active_vehicle(_veh_target)
            _thr_before = (int(_v_pre.throttle)
                           if _v_pre is not None else None)
            if _is_idle_poll:
                _ci_handled = False
            else:
                _ci_handled = process_input(
                    _veh_target, _ci_action, _arg_u16,
                    person_id=int(actor_auid) & 0xFFFFFFFF)
                if _ci_handled:
                    _ci_from_arg = _ci_action
                    _ci_payload = _arg_u16
            _v_post = get_active_vehicle(_veh_target)
            _thr_after = (int(_v_post.throttle)
                          if _v_post is not None else None)
            if (_thr_before is not None and _thr_after is not None
                    and _thr_before != _thr_after):
                logger.info(f"[throttle-diag] target=0x{_veh_target:08x} "
                            f"thr {_thr_before}->{_thr_after} "
                            f"action=0x{_ci_action:02x} "
                            f"arg=0x{_arg_u16:04x} "
                            f"ctrl(primary)=0x{_ci_from_arg:02x} "
                            f"payload(primary)=0x{_ci_payload:02x} "
                            f"idle={_is_idle_poll} handled={_ci_handled} "
                            f"actor=0x{int(actor_auid) & 0xFFFFFFFF:08x}")
            logger.debug(f"[udp-disp] vehicle CI: target=0x{_veh_target:08x} "
                         f"wrapper=0x{_ci_action:02x} ctrl=0x{_ci_from_arg:02x} "
                         f"payload=0x{_ci_payload:02x} handled={_ci_handled}")
            _door_dismount = False
            if (_ci_handled and _ci_from_arg == 0x1F
                    and _veh_target == _PLAYER_MOUNTED_VEHICLE.get(
                        int(actor_auid) & 0xFFFFFFFF)):
                _aid_d = int(actor_auid) & 0xFFFFFFFF
                _PENDING_DISMOUNT[_aid_d] = int(_veh_target)
                _PLAYER_MOUNTED_VEHICLE.pop(_aid_d, None)
                logger.info(f"[udp-disp] DOOR_SWITCH dismount: player "
                            f"0x{_aid_d:08x} leaving vehicle "
                            f"0x{int(_veh_target):08x} (position snapshot "
                            f"pending next 0x42)")
                try:
                    await _finalize_vehicle_dismount(
                        _aid_d, int(_veh_target),
                        exit_xyz=None,
                        live_avatars=_live_avatars)
                except Exception as _fdex:
                    logger.warning(f"[udp-disp] door-dismount cleanup err: "
                                   f"{_fdex!r}")
                _door_dismount = True
            if _ci_handled and not _door_dismount:
                _PREDICTED_CIS = (
                    0x00, 0x01, 0x02,
                    0x0F, 0x10,
                    0x12, 0x13, 0x14, 0x15,
                    0x16, 0x17, 0x18, 0x19,
                    0x20, 0x21, 0x22,
                    0x23, 0x24, 0x25, 0x26,
                    0x27, 0x28, 0x29, 0x2A,
                    0x2B, 0x2C,
                )
                _ci_is_predicted = (_ci_from_arg in _PREDICTED_CIS)
                _driver_auid_b = int(actor_auid) & 0xFFFFFFFF
                _v = get_active_vehicle(_veh_target)
                if _v is not None:
                    try:
                        _upkt = build_da_vehicle_update(_v)
                        _PREDICTED_CIS = (
                            0x00, 0x01, 0x02,
                            0x0F, 0x10,
                            0x12, 0x13, 0x14, 0x15,
                            0x16, 0x17, 0x18, 0x19,
                            0x20, 0x21, 0x22,
                            0x23, 0x24, 0x25, 0x26,
                            0x27, 0x28, 0x29, 0x2A,
                            0x2B, 0x2C,
                        )
                        _ci_is_predicted = (_ci_from_arg in _PREDICTED_CIS)
                        _driver_auid_b = int(actor_auid) & 0xFFFFFFFF
                        _driver_pkt = (None if _ci_is_predicted
                                       else build_da_vehicle_keepalive(_v))
                        for _peer_auid, _peer_entry in list(
                                _live_avatars.items()):
                            _is_self = (int(_peer_auid) & 0xFFFFFFFF
                                        == _driver_auid_b)
                            _pkt_to_send = _upkt
                            if _is_self:
                                if _driver_pkt is None:
                                    continue
                                _pkt_to_send = _driver_pkt
                            _pw = _peer_entry.get("writer")
                            if _pw is None or _pw.is_closing():
                                continue
                            try:
                                await write_framed(_pw, _pkt_to_send)
                            except Exception as _be:
                                logger.debug(f"[udp-disp] broadcast err to "
                                             f"0x{_peer_auid:08x}: {_be!r}")
                        try:
                            await commit_vehicle(_veh_target, conn=conn)
                        except Exception as _ce:
                            logger.warning(f"[udp-disp] commit err: {_ce!r}")
                    except Exception as _bex:
                        logger.warning(f"[udp-disp] update build err: {_bex!r}")
                return
            if _door_dismount:
                return
        except Exception as _vpe:
            logger.error(f"[udp-disp] vehicle process_input err: {_vpe!r}")

    if (int(action) & 0xFF) == 0x97:
        try:
            await _execute_recall_home(int(actor_auid) or int(target),
                    conn=conn, live_avatars=_live_avatars,
                    agent_bits=agent_bits, manifest_suppress=manifest_suppress,
                    force_scene_manifest_push=force_scene_manifest_push,
                    peer_upright_euler=peer_upright_euler, _stamina_byte=_stamina_byte,
                    retarget_bundle_to_avatar=retarget_bundle_to_avatar,
                    broadcast_to_peers=broadcast_to_peers)
        except Exception as _rc:
            logger.warning(f"[recall] handler err: {_rc!r}")
        return

    if not is_pickup and not is_forage:
        try:
            if await _maybe_flag_claim(actor_auid, action, arg, target,
                                       hit_target, aim_x, aim_y,
                                       _FLAG_CLAIM_CANDIDATE_SEEN=_FLAG_CLAIM_CANDIDATE_SEEN,
                                       conn=conn, _live_avatars=_live_avatars,
                                       _SAVE=_SAVE,
                                       _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
                                       alloc_daitem_auid=alloc_daitem_auid, _tock_state=_tock_state,
                                       _DROPPED_ITEMS=_DROPPED_ITEMS, _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS):
                return
        except Exception as _fce:
            logger.warning(f"[flag-claim] handler err: {_fce!r}")
        _key = (int(target) & 0xFFFFFFFF, int(action) & 0xFF)
        _dumped = getattr(_udp_maybe_pickup, "_dumped", None)
        if _dumped is None:
            _dumped = set()
            _udp_maybe_pickup._dumped = _dumped
        _first = _key not in _dumped
        if _first:
            _dumped.add(_key)
        if _first:
            logger.info(f"[udp-disp] unhandled target=0x{target:08x} action=0x{action:02x} arg=0x{arg:04x} hit=0x{hit_target:08x} aim=({aim_x:.2f},{aim_y:.2f}) first")
        elif int(action) & 0xFF == 0x60 and int(arg) & 0xFFFF == 0:
            pass
        else:
            logger.debug(f"[udp-disp] unhandled target=0x{target:08x} action=0x{action:02x} arg=0x{arg:04x} hit=0x{hit_target:08x} aim=({aim_x:.2f},{aim_y:.2f})")
        if _UDP_HOLD:
            _UDP_HOLD.clear()
        return

    _last_pu = _UDP_LAST_PICKUP_BY_ACTOR.get(_pickup_actor, 0.0)
    if now - _last_pu < debounce:
        return
    _UDP_LAST_PICKUP_BY_ACTOR[_pickup_actor] = now
    _UDP_LAST_PICKUP_AT = now
    _UDP_HOLD.clear()

    if is_pickup:
        logger.info('[udp-disp] immediate target=0x%08x -> pickup' % target)
        try:
            await _execute_pickup(target, source='udp',
                                  actor_auid=int(actor_auid))
        except Exception as exc:
            logger.warning('[udp-disp] _execute_pickup raised: %r' % (exc,))
    else:
        logger.info('[udp-disp] immediate target=0x%08x -> forage '
                    '(action=%d arg=0x%04x)' % (target, action, arg))
        try:
            await _execute_forage(target, action=int(action),
                                  arg=int(arg),
                                  actor_auid=int(actor_auid))
        except Exception as exc:
            logger.warning('[udp-disp] _execute_forage raised: %r' % (exc,))


class _UdpCtrlProto(asyncio.DatagramProtocol):
    def __init__(self,
                 *, conn, _live_avatars, _DROPPED_ITEMS, _WORLD_ATOM_AUIDS,
                 _PLAYER_MOUNTED_VEHICLE, _PENDING_DISMOUNT,
                 _finalize_vehicle_dismount, _execute_pickup, _execute_forage,
                 _handle_fire_weapon_trigger, _handle_reload_weapon_trigger,
                 _SAVE, _CITIZEN_EMPIRE_OVERRIDE,
                 alloc_daitem_auid, _tock_state, _DYNAMIC_SCENE_AUIDS,
                 agent_bits, agent_bits_for, manifest_suppress,
                 force_scene_manifest_push, peer_upright_euler, _stamina_byte,
                 retarget_bundle_to_avatar, broadcast_to_peers,
                 _hz_active_advance):
        self._live_avatars = _live_avatars
        self._WORLD_ATOM_AUIDS = _WORLD_ATOM_AUIDS
        self._hz_active_advance = _hz_active_advance
        self._dispatch_kw = dict(
            conn=conn, _live_avatars=_live_avatars,
            _DROPPED_ITEMS=_DROPPED_ITEMS,
            _WORLD_ATOM_AUIDS=_WORLD_ATOM_AUIDS,
            _PLAYER_MOUNTED_VEHICLE=_PLAYER_MOUNTED_VEHICLE,
            _PENDING_DISMOUNT=_PENDING_DISMOUNT,
            _finalize_vehicle_dismount=_finalize_vehicle_dismount,
            _execute_pickup=_execute_pickup, _execute_forage=_execute_forage,
            _handle_fire_weapon_trigger=_handle_fire_weapon_trigger,
            _handle_reload_weapon_trigger=_handle_reload_weapon_trigger,
            _SAVE=_SAVE,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            alloc_daitem_auid=alloc_daitem_auid, _tock_state=_tock_state,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS, agent_bits=agent_bits,
            agent_bits_for=agent_bits_for,
            manifest_suppress=manifest_suppress,
            force_scene_manifest_push=force_scene_manifest_push,
            peer_upright_euler=peer_upright_euler,
            _stamina_byte=_stamina_byte,
            retarget_bundle_to_avatar=retarget_bundle_to_avatar,
            broadcast_to_peers=broadcast_to_peers)

    def connection_made(self, transport):
        global _UDP_TRANSPORT
        _UDP_TRANSPORT = transport
        sock = transport.get_extra_info("socket")
        try:
            host, port = sock.getsockname()
        except Exception:
            host, port = ("?", "?")
        logger.info(f"[udp-ctrl] listening on {host}:{port}")

    def datagram_received(self, data, addr):
        try:
            if len(data) < 8:
                return
            session_id = _udp_struct.unpack_from(">I", data, 0)[0]
            payload_size = _udp_struct.unpack_from(">I", data, 4)[0]
            if payload_size > len(data) - 8:
                return
            payload = data[8:8 + payload_size]
            if not payload:
                return
            decoded = _udp_decode_0x37(payload)
            try:
                _ai_action = int(decoded.get('action', 0))
                _ai_actor = _actor_from_udp_addr(addr, fallback_sid=session_id,
                        _live_avatars=self._live_avatars,
                        _UDP_RESOLVE_LOGGED=_UDP_RESOLVE_LOGGED)
                if _ai_actor != (int(session_id) & 0xFFFFFFFF):
                    logger.info(f'[active-item] sid override 0x{int(session_id):08x} '
                                f'-> 0x{_ai_actor:08x} via {addr[0]!r}')
                if _ai_action == 0x95:
                    logger.info(f'[active-item] UDP 0x37 action=0x95 '
                                f'SelectNext (kind=0x{decoded.get("kind", 0):02x}) '
                                f'actor=0x{_ai_actor:08x}')
                    asyncio.get_running_loop().create_task(
                        self._hz_active_advance(+1, actor_auid=_ai_actor))
                elif _ai_action == 0x96:
                    logger.info(f'[active-item] UDP 0x37 action=0x96 '
                                f'SelectPrev (kind=0x{decoded.get("kind", 0):02x}) '
                                f'actor=0x{_ai_actor:08x}')
                    asyncio.get_running_loop().create_task(
                        self._hz_active_advance(-1, actor_auid=_ai_actor))
            except Exception as _ai_we:
                logger.warning(f'[active-item] 0x37 wheel-hook err: {_ai_we!r}')
            tgt_d = int(decoded.get('target', 0))
            if tgt_d:
                if tgt_d in self._WORLD_ATOM_AUIDS:
                    logger.debug('[forage-raw] target=0x%08x flags=0x%02x '
                                 'kind=0x%02x action=%d arg=0x%04x sid=0x%08x '
                                 'plen=%d hex=%s' % (
                                     tgt_d,
                                     int(decoded.get('flags', 0)),
                                     int(decoded.get('kind', 0)),
                                     int(decoded.get('action', 0)),
                                     int(decoded.get('arg', 0)) & 0xFFFF,
                                     int(session_id),
                                     len(payload),
                                     payload.hex()))
                try:
                    _ud_actor = _actor_from_udp_addr(
                        addr, fallback_sid=session_id,
                        _live_avatars=self._live_avatars,
                        _UDP_RESOLVE_LOGGED=_UDP_RESOLVE_LOGGED)
                    asyncio.get_running_loop().create_task(
                        _udp_maybe_pickup(tgt_d,
                                          actor_auid=int(_ud_actor),
                                          action=int(decoded.get('action', 0)),
                                          arg=int(decoded.get('arg', 0)),
                                          hit_target=int(decoded.get('hit_target', 0)),
                                          aim_x=float(decoded.get('aim_x', 0.0)),
                                          aim_y=float(decoded.get('aim_y', 0.0)),
                                          **self._dispatch_kw))
                except RuntimeError as _nl:
                    logger.debug(f'[udp-ctrl] no running loop to dispatch on: '
                                 f'{_nl!r}')
        except Exception as exc:
            logger.error(f"[udp-ctrl] dgram err: {exc!r}")

    def error_received(self, exc):
        pass

    def connection_lost(self, exc):
        global _UDP_TRANSPORT
        _UDP_TRANSPORT = None
        if exc:
            logger.warning(f"[udp-ctrl] lost: {exc!r}")


async def _udp_start(
        *, conn, _live_avatars, _DROPPED_ITEMS, _WORLD_ATOM_AUIDS,
        _PLAYER_MOUNTED_VEHICLE, _PENDING_DISMOUNT,
        _finalize_vehicle_dismount, _execute_pickup, _execute_forage,
        _handle_fire_weapon_trigger, _handle_reload_weapon_trigger,
        _SAVE, _CITIZEN_EMPIRE_OVERRIDE, alloc_daitem_auid,
        _tock_state, _DYNAMIC_SCENE_AUIDS, agent_bits, agent_bits_for,
        manifest_suppress, force_scene_manifest_push, peer_upright_euler,
        _stamina_byte, retarget_bundle_to_avatar, broadcast_to_peers,
        _hz_active_advance):
    global _UDP_TRANSPORT
    if _UDP_TRANSPORT is not None:
        return
    deployment = Deployment.from_env()
    SCENE_PORT = deployment.scene_port
    _bind_host = "0.0.0.0"
    loop = asyncio.get_running_loop()
    try:
        await loop.create_datagram_endpoint(
            lambda: _UdpCtrlProto(
                conn=conn, _live_avatars=_live_avatars, _DROPPED_ITEMS=_DROPPED_ITEMS,
                _WORLD_ATOM_AUIDS=_WORLD_ATOM_AUIDS,
                _PLAYER_MOUNTED_VEHICLE=_PLAYER_MOUNTED_VEHICLE,
                _PENDING_DISMOUNT=_PENDING_DISMOUNT,
                _finalize_vehicle_dismount=_finalize_vehicle_dismount,
                _execute_pickup=_execute_pickup, _execute_forage=_execute_forage,
                _handle_fire_weapon_trigger=_handle_fire_weapon_trigger,
                _handle_reload_weapon_trigger=_handle_reload_weapon_trigger,
                _SAVE=_SAVE,
                _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
                alloc_daitem_auid=alloc_daitem_auid, _tock_state=_tock_state,
                _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS, agent_bits=agent_bits,
                agent_bits_for=agent_bits_for, manifest_suppress=manifest_suppress,
                force_scene_manifest_push=force_scene_manifest_push,
                peer_upright_euler=peer_upright_euler, _stamina_byte=_stamina_byte,
                retarget_bundle_to_avatar=retarget_bundle_to_avatar,
                broadcast_to_peers=broadcast_to_peers,
                _hz_active_advance=_hz_active_advance),
            local_addr=(_bind_host, SCENE_PORT))
    except Exception as exc:
        logger.error(f"[udp-ctrl] bind failed on UDP {SCENE_PORT}: {exc!r}")


