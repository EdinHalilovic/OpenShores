
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.gameplay.combat.damage import _apply_damage
from openshores.gameplay.creature_state import _build_creature_state_pkt
from openshores.gameplay.ground_snap import _AVATAR_HEIGHT_M, _ground_snap_radial
from openshores.gameplay.vehicles.atom_packet import (
    build_da_vehicle_atom,
    build_da_vehicle_update,
)
from openshores.gameplay.vehicles.combat import clear_last_damage_ms
from openshores.gameplay.vehicles.spawn import (
    commit_vehicle,
    despawn_vehicle,
    get_active_vehicle,
    spawn_vehicle,
)
from openshores.network.broadcast import _broadcast_to_peers
from openshores.network.vehicle_mount import (
    _EXPLOSION_SOUND_DEFAULT,
    _explosion_visual_for_vehicle,
    _finalize_vehicle_mount,
)
from openshores.protocol.atoms.person import _build_daperson_parent_update
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


async def _finalize_vehicle_dismount(player_auid: int,
                                     vehicle_auid: int,
                                     *,
                                     exit_xyz=None,
                                     live_avatars: dict,
                                     conn,
                                     _VEH_PARENT_FLOOR: dict,
                                     _stamina_byte,
                                     agent_bits_for) -> None:
    try:
        _vc = get_active_vehicle(int(vehicle_auid))
    except Exception:
        _vc = None
    if _vc is None:
        return
    try:
        _vc.switches = int(_vc.switches) & ~0x05
    except Exception as _se:
        logger.warning(f"[dismount] could not clear switches on vehicle "
                       f"0x{int(vehicle_auid):08x}: {_se!r}")
    if exit_xyz is not None:
        try:
            _gx, _gy, _gz = _ground_snap_radial(exit_xyz)
            _vc.locX = float(_gx)
            _vc.locY = float(_gy)
            _vc.locZ = float(_gz)
            try:
                _vc.vecX = 0.0
                _vc.vecY = 0.0
                _vc.vecZ = 0.0
                _vc.atRest = True
            except Exception as _pe_rest:
                logger.warning(f"[dismount] could not park vehicle "
                               f"0x{int(vehicle_auid):08x}: {_pe_rest!r}")
            try:
                import math as _pm_floor
                _pmag = _pm_floor.sqrt(_gx*_gx + _gy*_gy + _gz*_gz)
                if _pmag > 1.0:
                    _VEH_PARENT_FLOOR[int(_vc.idp) & 0xFFFFFFFF] = _pmag
            except Exception as _fe:
                logger.warning(f"[dismount] floor pin skipped: {_fe!r}")
            logger.info(f'[dismount] vehicle 0x{int(_vc.id):08x} parked at ({_vc.locX:.1f},{_vc.locY:.1f},{_vc.locZ:.1f}) (snapped {_AVATAR_HEIGHT_M:.1f}m below exit.')
        except Exception as _gex:
            logger.error(f"[dismount] ground-snap failed: {_gex!r}")
        try:
            await commit_vehicle(int(vehicle_auid), conn=conn)
        except Exception as _ce:
            logger.error(f"[dismount] commit err: {_ce!r}")
    try:
        _pkt = build_da_vehicle_update(_vc)
        _sent = await _broadcast_to_peers(_pkt, live_avatars or {})
        logger.info(f"[dismount] 0x1C broadcast -> {_sent} peer(s)")
    except Exception as _be:
        logger.error(f"[dismount] vehicle broadcast err: {_be!r}")

    try:
        _parent = int(_vc.idp) & 0xFFFFFFFF
        if _parent:
            _ppkt0 = _build_daperson_parent_update(
                int(player_auid), _parent,
                _stamina_byte=_stamina_byte, agent_bits_for=agent_bits_for)
            _sent = await _broadcast_to_peers(_ppkt0, live_avatars or {})
            logger.info(f"[dismount] DaPerson parent 0x{int(player_auid):08x} -> "
                  f"0x{_parent:08x} broadcast to {_sent} peer(s) (1/3)")

            async def _parent_retry():
                for _i in (2, 3):
                    try:
                        await asyncio.sleep(0.2)
                        _ppkt_i = _build_daperson_parent_update(
                            int(player_auid), _parent,
                            _stamina_byte=_stamina_byte,
                            agent_bits_for=agent_bits_for)
                        _s = await _broadcast_to_peers(
                            _ppkt_i, live_avatars or {})
                        logger.debug(f"[dismount] DaPerson parent retry "
                              f"({_i}/3) -> {_s} peer(s)")
                    except Exception as _re:
                        logger.error(f"[dismount] parent retry {_i} err: {_re!r}")

            asyncio.create_task(_parent_retry())
    except Exception as _pe:
        logger.error(f"[dismount] DaPerson parent update err: {_pe!r}")


async def grant_crafted_vehicle(actor_auid: int, commodity_id: int,
                                quality: int = 1, *, mount: bool = True,
                                conn,
                                _tock_state: dict,
                                _live_avatars: dict,
                                _DYNAMIC_SCENE_AUIDS: set,
                                _veh_note_ground_radius,
                                _stamina_byte,
                                agent_bits_for):
    actor = int(actor_auid) & 0xFFFFFFFF
    ent = (_tock_state.get(actor) or {})
    live = (_live_avatars.get(actor) or {})
    xyz = ent.get("xyz") or live.get("xyz")
    if not xyz:
        logger.error(f"[handcraft-veh] no live position for 0x{actor:08x}; "
              f"vehicle not placed")
        return None
    parent = None
    for _key in ("parent", "parent_auid", "parent_world", "AP", "world", "world_auid"):
        _val = ent.get(_key) or live.get(_key)
        if _val:
            try:
                parent = (int.from_bytes(bytes(_val), "big")
                          if isinstance(_val, (bytes, bytearray))
                          else int(_val)) & 0xFFFFFFFF
            except (TypeError, ValueError):
                continue
            break
    if not parent:
        logger.error(f"[handcraft-veh] no parent world for 0x{actor:08x}; "
              f"vehicle not placed")
        return None

    import math as _hm
    _x, _y, _z = (float(v) for v in tuple(xyz)[:3])
    _r = _hm.sqrt(_x * _x + _y * _y + _z * _z) or 1.0
    _lift = 5.0
    _spawn_xyz = (_x + _lift * _x / _r,
                  _y + _lift * _y / _r,
                  _z + _lift * _z / _r)
    _rot = ent.get("last_rotation") or live.get("last_rotation") or (0.0, 0.0, 0.0)

    _q = int(quality) & 0xFF
    _q = 1 if _q < 1 else (100 if _q > 100 else _q)
    try:
        _veh = await spawn_vehicle(
            commodity_id=int(commodity_id) & 0xFFFF,
            parent_id=parent,
            location=_spawn_xyz,
            rotation=tuple(float(v) for v in tuple(_rot)[:3]),
            name="",
            quality=_q,
            allegiance=actor,
            fuel=100,
            conn=conn,
        )
    except Exception as exc:
        logger.error(f"[handcraft-veh] spawn failed: {exc!r}")
        return None
    logger.info(f"[handcraft-veh] spawned id=0x{_veh.id:08x} cid=0x{_veh.cid:x} "
          f"q={_veh.qual} hp={_veh.hp} parent=0x{_veh.idp:08x} "
          f"loc=({_veh.locX:.1f}, {_veh.locY:.1f}, {_veh.locZ:.1f})")

    try:
        _note = _veh_note_ground_radius
        if callable(_note):
            _note(parent, _spawn_xyz)
    except Exception as exc:
        logger.warning(f"[handcraft-veh] floor-note skipped: {exc!r}")

    _DYNAMIC_SCENE_AUIDS.add(int(_veh.id))
    _writer = live.get("writer")
    if _writer is not None and not _writer.is_closing():
        try:
            _mb = getattr(_writer, "_scene_manifest_builder", None)
            if _mb:
                await write_framed(_writer, _mb())
            else:
                logger.warning("[handcraft-veh] no manifest builder on writer; "
                      "vehicle may be culled")
        except Exception as exc:
            logger.warning(f"[handcraft-veh] manifest re-emit failed: {exc!r}")
        try:
            await write_framed(_writer, build_da_vehicle_atom(_veh))
        except Exception as exc:
            logger.error(f"[handcraft-veh] atom emit failed: {exc!r}")
            return None

    try:
        _sent = await _broadcast_to_peers(build_da_vehicle_atom(_veh), _live_avatars)
        logger.info(f"[handcraft-veh] atom broadcast -> {_sent} peer(s)")
    except Exception as exc:
        logger.error(f"[handcraft-veh] atom broadcast err: {exc!r}")

    if mount:
        try:
            await _finalize_vehicle_mount(actor, int(_veh.id),
                                          live_avatars=_live_avatars,
                                          _stamina_byte=_stamina_byte,
                                          agent_bits_for=agent_bits_for)
        except Exception as exc:
            logger.error(f"[handcraft-veh] mount failed: {exc!r}")
    return int(_veh.id)


async def _destroy_vehicle_cascade(vc,
                                   killer_id: int,
                                   *,
                                   death_message: str = "",
                                   live_avatars: dict = None,
                                   weapon_cid: int = 0,
                                   weapon_quality: int = 0,
                                   conn,
                                   _live_avatars: dict,
                                   _PLAYER_MOUNTED_VEHICLE: dict,
                                   _PENDING_DISMOUNT: dict,
                                   _VEH_LAST_BROADCAST_POS: dict,
                                   _VEH_PARENT_WATCH: dict,
                                   _tock_state: dict,
                                   _DYNAMIC_SCENE_AUIDS: set,
                                   _build_world_atom_effect_pkt,
                                   next_effect_time_ms,
                                   _stamina_byte,
                                   agent_bits_for) -> None:
    if vc is None:
        return

    live_avatars = live_avatars or _live_avatars

    _vid = int(vc.id) & 0xFFFFFFFF
    _vparent = int(vc.idp) & 0xFFFFFFFF
    _vname = (vc.name or f"vehicle 0x{_vid:08x}")
    _origin = (float(vc.locX), float(vc.locY), float(vc.locZ))

    try:
        vc.hp = 0
        vc.switches = int(vc.switches) & ~0x05
        import time as _dt
        vc.timeDeath = int(_dt.time() * 1000)
        try:
            await commit_vehicle(_vid, conn=conn)
        except Exception as _ce:
            logger.error(f"[destroy] commit before delete err: {_ce!r}")
    except Exception as _se:
        logger.error(f"[destroy] state mutation err: {_se!r}")

    try:
        _final_pkt = build_da_vehicle_update(vc)
        _sent = await _broadcast_to_peers(_final_pkt, live_avatars)
        logger.info(f"[destroy] vehicle 0x{_vid:08x} final 0x1C broadcast -> "
              f"{_sent} peer(s) (hp=0, switches=0x{int(vc.switches):02x})")
    except Exception as _be:
        logger.error(f"[destroy] final 0x1C broadcast err: {_be!r}")

    try:
        _to_eject = [
            int(_pa) & 0xFFFFFFFF
            for _pa, _vi in list(_PLAYER_MOUNTED_VEHICLE.items())
            if int(_vi) & 0xFFFFFFFF == _vid
        ]
    except Exception:
        _to_eject = []
    for _player_auid in _to_eject:
        try:
            _PLAYER_MOUNTED_VEHICLE.pop(_player_auid, None)
            _PENDING_DISMOUNT.pop(_player_auid, None)
        except Exception as _fe:
            logger.warning(f"[destroy] mount-cache clear err for "
                           f"0x{_player_auid:08x}: {_fe!r}")
        try:
            if _vparent:
                _ppkt = _build_daperson_parent_update(
                    int(_player_auid), _vparent,
                    _stamina_byte=_stamina_byte, agent_bits_for=agent_bits_for)
                _ps = await _broadcast_to_peers(_ppkt, live_avatars)
                logger.info(f"[destroy] eject parent flip 0x{_player_auid:08x} "
                      f"-> 0x{_vparent:08x} broadcast to {_ps} peer(s)")
        except Exception as _ppe:
            logger.error(f"[destroy] eject parent flip err: {_ppe!r}")
        try:
            _eject_dmg = 9999
            _new_hp = _apply_damage(
                int(_player_auid), _eject_dmg,
                source=(f"vehicle-explosion:0x{_vid:08x}"
                        + (f":w{weapon_cid:#x}" if weapon_cid else "")),
                tock_state=_tock_state, agent_bits_for=agent_bits_for)
            _e_state = _tock_state.setdefault(
                int(_player_auid),
                {"pose": 0x24, "last_minute": -1,
                 "last_hour": -1, "hp": _new_hp})
            _e_state["pose"] = 0x20
            _e_state["hp"] = _new_hp
            try:
                _e_writer_entry = _live_avatars.get(int(_player_auid))
                _stam_now = (int(_e_state.get("stamina", 0x7F))
                             if isinstance(_e_state, dict) else 0x7F)
                _hunger_now = (int(_e_state.get("hunger", 0x320))
                               if isinstance(_e_state, dict) else 0x320)
                _cs_pkt = _build_creature_state_pkt(
                    int(_player_auid), hp=int(_new_hp), pose=0x20,
                    hunger=int(_hunger_now), stamina=int(_stam_now),
                    tock_state=_tock_state, agent_bits_for=agent_bits_for)
                await _broadcast_to_peers(_cs_pkt, live_avatars)
            except Exception as _csb:
                logger.error(f"[destroy] eject creature-state broadcast err: "
                      f"{_csb!r}")
            logger.info(f"[destroy] eject 0x{_player_auid:08x} knocked out "
                  f"(pose=0x20, hp={_new_hp})")
        except Exception as _kde:
            logger.error(f"[destroy] eject damage err: {_kde!r}")

    try:
        _ev = _explosion_visual_for_vehicle(vc)
        _es = int(_EXPLOSION_SOUND_DEFAULT) & 0xFF
        if _vparent:
            _fxp = _build_world_atom_effect_pkt(
                _vparent,
                origin_xyz=_origin,
                sound_type=_es,
                visual_type=_ev,
                next_effect_time_ms=next_effect_time_ms,
            )
            _fxs = await _broadcast_to_peers(_fxp, live_avatars)
            logger.info(f"[destroy] explosion VFX (visual=0x{_ev:02x}, "
                  f"sound=0x{_es:02x}) at "
                  f"({_origin[0]:.1f},{_origin[1]:.1f},{_origin[2]:.1f}) "
                  f"anchor=0x{_vparent:08x} -> {_fxs} peer(s)")
        else:
            logger.warning(f"[destroy] vehicle 0x{_vid:08x} has no parent. Skipping VFX broadcast")
    except Exception as _fxe:
        logger.error(f"[destroy] VFX broadcast err: {_fxe!r}")

    try:
        await despawn_vehicle(int(_vid), delete_row=True, conn=conn)
    except Exception as _dse:
        logger.error(f"[destroy] despawn err: {_dse!r}")
    clear_last_damage_ms(int(_vid))
    try:
        _VEH_LAST_BROADCAST_POS.pop(int(_vid), None)
        _VEH_PARENT_WATCH.pop(int(_vid), None)
    except Exception as _re:
        logger.warning(f"[destroy] registry clear err for 0x{_vid:08x}: {_re!r}")

    try:
        _DYNAMIC_SCENE_AUIDS.discard(int(_vid))
        for _peer_auid, _peer_entry in list(live_avatars.items()):
            _pw = _peer_entry.get("writer") if isinstance(
                _peer_entry, dict) else None
            if _pw is None or _pw.is_closing():
                continue
            _b = getattr(_pw, "_scene_manifest_builder", None)
            if _b is None:
                continue
            try:
                _mpkt = _b()
                await write_framed(_pw, _mpkt)
            except Exception as _mre:
                logger.warning(f"[destroy] manifest re-emit to peer "
                      f"0x{int(_peer_auid):08x} err: {_mre!r}")
        logger.info(f"[destroy] manifest re-emit (without 0x{_vid:08x}) sent to live peers. Should trigger client GC")
    except Exception as _mfe:
        logger.error(f"[destroy] manifest re-emit err: {_mfe!r}")

    logger.info(f"[destroy] vehicle 0x{_vid:08x} ({_vname}) DESTROYED by "
          f"0x{int(killer_id) & 0xFFFFFFFF:08x} weapon=0x{int(weapon_cid):x} "
          f"q={int(weapon_quality)} msg={death_message!r}")
