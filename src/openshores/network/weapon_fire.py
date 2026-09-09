
from __future__ import annotations

import time as _t

from openshores.core.heartbeat_watch import _note_0x18
from openshores.core.logging import get_logger
from openshores.database.repositories.person import read_person_position
from openshores.gameplay.body_slots import (
    _body_slot_name,
    _body_slot_of_cursor,
)
from openshores.gameplay.combat.damage import (
    _apply_damage,
    _combat_total_damage,
    _describe_weapon,
    _log_combat_hit,
)
from openshores.gameplay.combat.impact import (
    _classify_hit_surface,
    _compute_world_hit_point,
    _victim_world_xyz,
)
from openshores.gameplay.combat.resolve import (
    _body_weapon_for_actor,
    _resolve_combat_hit,
)
from openshores.gameplay.condition_states import _apply_weapon_conditions
from openshores.gameplay.damageable import is_damageable
from openshores.gameplay.gear_entry import _gear_quality_of
from openshores.gameplay.vehicles.atom_packet import build_da_vehicle_update
from openshores.gameplay.vehicles.combat import (
    WEAPONEFFECT as _VEFF,
    WEAPONMODE as _VMODE,
    AuCombatWeapon as _VAuWeapon,
    combat_apply_damage as _veh_combat_apply,
)
from openshores.gameplay.vehicles.spawn import (
    commit_vehicle,
    get_active_vehicle,
)
from openshores.gameplay.vehicles.weapons import (
    get_killer_id as _veh_killer_id,
    get_last_weapon_used_by as _veh_last_weapon,
)
from openshores.network.augear_refresh import _push_augear_refresh_for
from openshores.network.broadcast import _broadcast_to_peers
from openshores.network.npc_damage import _damage_npc_target
from openshores.network.player_effect import _push_player_effect
from openshores.network.skinning_ops import _skin_ground_carcass
from openshores.network.trigger_debounce import _LAST_FIRE_TS
from openshores.network.vehicle_lifecycle import _destroy_vehicle_cascade
from openshores.protocol.atoms.effect import _build_world_atom_effect_pkt
from openshores.protocol.atoms.item import _extract_cid_from_auitem_body
from openshores.protocol.atoms.weapon import (
    _weapon_damage_for_cid_mode,
    _weapon_range_for_cid_mode,
    _weapon_spec_for_cid,
)
from openshores.protocol.atoms.weapon_fx import (
    _WEAPONEFFECT_TO_STRIKE_VISUAL,
    _swing_fx_for_weapon,
)
from openshores.protocol.framing import write_framed
from openshores.world.sim_time_low import _current_sim_t_low

logger = get_logger(__name__)

_FIRE_DEBOUNCE_SEC = 0.30


async def _handle_fire_weapon_trigger(avatar_auid: int,
                                      target_auid: int = 0,
                                      aim_x: float = 0.0,
                                      aim_y: float = 0.0,
                                      writer=None, *,
                                      conn,
                                      _AUGEAR_STATES,
                                      actor_cursor,
                                      _live_avatars,
                                      _WORLD_ATOM_AUIDS,
                                      tock_state,
                                      condition_states,
                                      agent_bits_for,
                                      _stamina_byte,
                                      dna_for_actor,
                                      alloc_daitem_auid,
                                      _DROPPED_ITEMS,
                                      _DYNAMIC_SCENE_AUIDS,
                                      idle_bodies,
                                      story_npcs,
                                      story_atom_id,
                                      story_name,
                                      spawned_buildings,
                                      _CITIZEN_EMPIRE_OVERRIDE,
                                      anchor_full,
                                      anchor_low32,
                                      sim_time_state,
                                      next_effect_time_ms,
                                      _build_augear_only_daperson_update,
                                      _PLAYER_MOUNTED_VEHICLE,
                                      _PENDING_DISMOUNT,
                                      _VEH_LAST_BROADCAST_POS,
                                      _VEH_PARENT_WATCH,
                                      ) -> None:
    now = _t.monotonic()
    logger.debug(f"[fire] enter auid=0x{avatar_auid:08x} target=0x{target_auid:08x}")
    last = _LAST_FIRE_TS.get(avatar_auid, 0.0)
    if now - last < _FIRE_DEBOUNCE_SEC:
        logger.debug(f"[fire] debounce. Last fire {now - last:.3f}s ago < {_FIRE_DEBOUNCE_SEC}s")
        return
    _LAST_FIRE_TS[avatar_auid] = now

    if int(target_auid or 0) & 0xFFFFFFFF == int(avatar_auid) & 0xFFFFFFFF:
        logger.warning(f"[fire] SELF-TARGET refused: actor=0x{int(avatar_auid):08x} target_auid resolved to the firer.")
        return

    _auid_key = int(avatar_auid) & 0xFFFFFFFF
    _actor_cursor = actor_cursor.get(_auid_key)
    if _actor_cursor is not None:
        _cur_slot, _cur_sub, _cur_mode = (
            int(_actor_cursor[0]) & 0xFF,
            int(_actor_cursor[1]) & 0x0F,
            int(_actor_cursor[2]) & 0xFF,
        )
    else:
        _cur_slot = 9
        _cur_sub  = 0
        _cur_mode = 0
    _body_slot = _body_slot_of_cursor(_cur_slot)
    _body_weapon = None
    if _body_slot is not None:
        _body_weapon = await _body_weapon_for_actor(
            conn, avatar_auid, _body_slot, _cur_mode,
            dna_for_actor=dna_for_actor)
        if _body_weapon is None or not _body_weapon.armed:
            logger.info(f"[fire] auid=0x{avatar_auid:08x} body slot {_body_slot} (sub={_cur_mode}) is empty for this species. No attack")
            return
        logger.debug(f"[fire] auid=0x{avatar_auid:08x} cursor=({_cur_slot},"
                     f"{_cur_sub},{_cur_mode}) BODY {_body_slot_name(_body_slot)} "
                     f"{_describe_weapon(_body_weapon)} target=0x{target_auid:08x}")

    state = _AUGEAR_STATES.get(int(avatar_auid) & 0xFFFFFFFF) or []
    target_entry = None
    target_index = -1
    if _body_slot is not None:
        target_entry = [_cur_slot, 0, 0x08, b""]
    else:
        if not state:
            logger.debug(f"[fire] auid=0x{avatar_auid:08x} no gear state. Bail")
            return
        _cursor_holds = None
        for idx, entry in enumerate(state):
            if len(entry) < 4:
                continue
            if (int(entry[0]) & 0xFF) == _cur_slot and (int(entry[1]) & 0x0F) == _cur_sub:
                _cursor_holds = entry
                if int(entry[2]) & 0xFF in (0x08, 0x09, 0x0C):
                    target_entry = entry
                    target_index = idx
                break
        if _cursor_holds is not None and target_entry is None:
            logger.info(f'[fire] auid=0x{avatar_auid:08x} cursor ({_cur_slot},{_cur_sub}) holds typeId 0x{int(_cursor_holds[2]) & 255:02x}, which is not a weapon.')
            return
        if target_entry is None and _actor_cursor is None:
            for idx, entry in enumerate(state):
                if len(entry) < 4:
                    continue
                if int(entry[2]) & 0xFF in (0x08, 0x09, 0x0C):
                    target_entry = entry
                    target_index = idx
                    break
        if target_entry is None:
            if _actor_cursor is not None:
                logger.info(f'[fire] auid=0x{avatar_auid:08x} cursor ({_cur_slot},{_cur_sub},{_cur_mode}) is not a weapon.')
            else:
                logger.debug(f"[fire] auid=0x{avatar_auid:08x} no weapon in gear (cursor slot={_cur_slot} sub={_cur_sub} mode={_cur_mode}). Bail")
            return
        logger.debug(f"[fire] auid=0x{avatar_auid:08x} cursor=({_cur_slot},{_cur_sub},"
                     f"{_cur_mode}) weapon at slot {target_entry[0]}/sub{target_entry[1]} "
                     f"typeId=0x{target_entry[2]:02x} target=0x{target_auid:08x}")

    if int(target_entry[2]) & 0xFF == 0x09 and _cur_mode != 0:
        _gate_body = bytes(target_entry[3])
        if len(_gate_body) < 4:
            logger.warning(f"[fire] AuItemWeaponAmmo body too short ({len(_gate_body)} bytes). Bail")
            return
        _gate_ammo = _gate_body[-2] if _cur_mode == 2 else _gate_body[-4]
        if _gate_ammo == 0:
            logger.info(f"[fire] auid=0x{avatar_auid:08x} mode={_cur_mode} {('ammo2' if _cur_mode == 2 else 'ammo1')}=0. Fire blocked BEFORE damage (press R to reload)")
            return

    if _body_slot is not None:
        _weapon_cid = 0
        _weapon_range_m = float(_body_weapon.range_ or 1.0)
    else:
        _weapon_cid = _extract_cid_from_auitem_body(bytes(target_entry[3]))
        _weapon_range_m = _weapon_range_for_cid_mode(_weapon_cid, _cur_mode)
    _target_is_player = (int(target_auid) & 0xFFFFFFFF) in _live_avatars
    _target_is_world = (int(target_auid) & 0xFFFFFFFF) in _WORLD_ATOM_AUIDS
    _target_v = None
    try:
        _target_v = get_active_vehicle(int(target_auid) & 0xFFFFFFFF)
    except Exception as _vle:
        _target_v = None
        logger.error(f"[fire]   vehicle target lookup err: {_vle!r}")
    _target_is_vehicle = _target_v is not None
    _in_range = True
    if _target_is_player:
        _atk_pos = None
        _tgt_pos = None
        try:
            _atk_pos = await read_person_position(conn, int(avatar_auid))
            _tgt_pos = await read_person_position(conn, int(target_auid))
        except Exception as _re:
            logger.error(f"[fire] range check: pos read err {_re!r}")
        if _atk_pos and _tgt_pos:
            _dx = float(_atk_pos[0]) - float(_tgt_pos[0])
            _dy = float(_atk_pos[1]) - float(_tgt_pos[1])
            _dz = float(_atk_pos[2]) - float(_tgt_pos[2])
            _dist = (_dx*_dx + _dy*_dy + _dz*_dz) ** 0.5
            if _dist > _weapon_range_m:
                logger.info(f"[fire] auid=0x{avatar_auid:08x} out OF range (player target) dist={_dist:.2f}m > {_weapon_range_m:.2f}m (cid={_weapon_cid} mode={_cur_mode}). Swing only, no impact")
                _in_range = False
            else:
                logger.debug(f"[fire]   range ok: dist={_dist:.2f}m / "
                             f"max={_weapon_range_m:.2f}m")
        else:
            logger.warning(f"[fire]   range check skipped: missing pos "
                           f"(atk={_atk_pos!r} tgt={_tgt_pos!r})")
        if _in_range and int(target_auid) != int(avatar_auid):
            try:
                _combat = _resolve_combat_hit(
                    _weapon_cid, int(target_entry[2]) & 0xFF, _cur_mode,
                    quality=(0 if _body_slot is not None
                             else _gear_quality_of(target_entry)),
                    target_gear=_AUGEAR_STATES.setdefault(
                        int(target_auid) & 0xFFFFFFFF, []),
                    weapon=_body_weapon)
                if _combat is not None:
                    _cweapon, _cres, _cworn = _combat
                    _dmg = _combat_total_damage(_cres)
                    _log_combat_hit(
                        f"0x{int(avatar_auid):08x} -> "
                        f"0x{int(target_auid):08x} "
                        f"({_describe_weapon(_cweapon)})", _cres, _cworn)
                elif _body_weapon is not None:
                    _cweapon, _cres = _body_weapon, None
                    _lo, _hi = _body_weapon.damage_range(1)
                    _dmg = max(1, (_lo + _hi) // 2)
                else:
                    _cweapon = _cres = None
                    _dmg = _weapon_damage_for_cid_mode(
                        _weapon_cid,
                        int(target_entry[2]) & 0xFF,
                        _cur_mode)
                if _dmg > 0:
                    _new_hp = _apply_damage(
                        int(target_auid), _dmg,
                        source=f"fire:cid{_weapon_cid}/mode{_cur_mode}",
                        attacker=int(avatar_auid),
                        tock_state=tock_state,
                        agent_bits_for=agent_bits_for)
                    logger.info(f"[fire]   damage applied: "
                                f"attacker=0x{int(avatar_auid):08x} "
                                f"victim=0x{int(target_auid):08x} "
                                f"-{_dmg} hp -> {_new_hp}")
                    try:
                        _apply_weapon_conditions(
                            int(target_auid), _weapon_cid, _cur_mode, _dmg,
                            attacker=int(avatar_auid), result=_cres,
                            weapon=_cweapon,
                            condition_states=condition_states)
                    except Exception as _wcexc:
                        logger.error(f"[condition] weapon effect failed: {_wcexc!r}")
                elif _body_slot is not None:
                    logger.debug(f"[fire]   damage skipped: "
                                 f"{_body_slot_name(_body_slot)} rolled 0 hp "
                                 f"({_describe_weapon(_body_weapon)})")
                else:
                    logger.debug(f"[fire]   damage skipped: weapon spec "
                                 f"reports 0 hp (cid={_weapon_cid} "
                                 f"mode={_cur_mode})")
            except Exception as _de:
                logger.error(f"[fire]   damage apply err: {_de!r}")
    elif _target_is_vehicle:
        _atk_pos = None
        try:
            _atk_pos = await read_person_position(conn, int(avatar_auid))
        except Exception as _re:
            logger.error(f"[fire]   vehicle range: atk pos read err {_re!r}")
        if _atk_pos:
            _dx = float(_atk_pos[0]) - float(_target_v.locX)
            _dy = float(_atk_pos[1]) - float(_target_v.locY)
            _dz = float(_atk_pos[2]) - float(_target_v.locZ)
            _dist = (_dx*_dx + _dy*_dy + _dz*_dz) ** 0.5
            if _dist > _weapon_range_m:
                logger.info(f"[fire] auid=0x{avatar_auid:08x} out OF range (vehicle target) dist={_dist:.2f}m > {_weapon_range_m:.2f}m (cid={_weapon_cid} mode={_cur_mode}). Swing only, no impact")
                _in_range = False
            else:
                logger.debug(f"[fire]   vehicle range ok: dist={_dist:.2f}m / "
                             f"max={_weapon_range_m:.2f}m (target 0x"
                             f"{int(_target_v.id):08x} cid 0x{_target_v.cid:x})")
        else:
            logger.warning("[fire]   vehicle range check skipped: no atk pos")
        if _in_range:
            try:
                if _body_weapon is not None:
                    _lo, _hi = _body_weapon.damage_range(1)
                    _hp_dmg = max(1, (_lo + _hi) // 2)
                else:
                    _hp_dmg = _weapon_damage_for_cid_mode(
                        _weapon_cid,
                        int(target_entry[2]) & 0xFF,
                        _cur_mode)
                _typeid = int(target_entry[2]) & 0xFF
                _w_mode = int(_VMODE.CONTACT)
                _w_eff = int(_VEFF.KINETIC)
                if _typeid in (0x09, 0x0C) and _cur_mode != 0:
                    _w_mode = int(_VMODE.PROJECTILE)
                if _typeid == 0x0C:
                    _w_eff = int(_VEFF.ENERGY)
                elif _typeid == 0x09 and _cur_mode != 0:
                    _spec = _weapon_spec_for_cid(_weapon_cid) or {}
                    _primary = _spec.get("primary", {}) or {}
                    _snd = int(_primary.get("sound", 0)) & 0xFF
                    if _snd in (0x0D, 0x0E):
                        _w_eff = int(_VEFF.BURNING)
                _dc = max(1, int(_hp_dmg) * 2)
                _pierce_block = 0.25
                _pierce_absorb = 0.25
                _w = _VAuWeapon(
                    weapon_id=int(_weapon_cid) & 0xFFFF,
                    mode=_w_mode,
                    effect1=_w_eff,
                    dice_count_1=_dc,
                    dice_bonus_1=0,
                    pierce_block_1=_pierce_block,
                    pierce_absorb_1=_pierce_absorb,
                )
                _hit_pt = (float(_atk_pos[0]), float(_atk_pos[1]),
                           float(_atk_pos[2])) if _atk_pos else None
                _norm = (float(_target_v.locX), float(_target_v.locY),
                         float(_target_v.locZ))
                _res = _veh_combat_apply(
                    _target_v,
                    attacker_id=int(avatar_auid) & 0xFFFFFFFF,
                    weapon=_w,
                    hit_point=_hit_pt,
                    normal=_norm,
                )
                logger.info(f"[fire]   vehicle damage 0x"
                            f"{int(_target_v.id):08x}: -{_res.total_damage()} "
                            f"(absorbed={_res.primary_absorbed} "
                            f"blocked={_res.primary_blocked} "
                            f"crit={_res.critical_flag}) hp={_target_v.hp} "
                            f"switches=0x{int(_target_v.switches):02x}")
                try:
                    await commit_vehicle(int(_target_v.id), conn=conn)
                except Exception as _ce:
                    logger.error(f"[fire]   vehicle commit err: {_ce!r}")
                try:
                    _vpkt = build_da_vehicle_update(_target_v)
                    await _broadcast_to_peers(_vpkt, _live_avatars)
                except Exception as _vbe:
                    logger.error(f"[fire]   vehicle eager broadcast err: "
                                 f"{_vbe!r}")
                if _res.kill_confirmed:
                    logger.info(f"[fire] KILL confirmed on vehicle 0x{int(_target_v.id):08x}. Invoking destroy cascade")
                    try:
                        _killer = _veh_killer_id(_target_v) or int(
                            avatar_auid) & 0xFFFFFFFF
                        _w_cid, _w_q = _veh_last_weapon(
                            _target_v, _killer)
                        await _destroy_vehicle_cascade(
                            _target_v, _killer,
                            death_message=(
                                f"{_target_v.name or 'vehicle'} destroyed "
                                f"by weapon cid 0x{_weapon_cid:x}"),
                            live_avatars=_live_avatars,
                            weapon_cid=int(_w_cid),
                            weapon_quality=int(_w_q),
                            conn=conn,
                            _live_avatars=_live_avatars,
                            _PLAYER_MOUNTED_VEHICLE=_PLAYER_MOUNTED_VEHICLE,
                            _PENDING_DISMOUNT=_PENDING_DISMOUNT,
                            _VEH_LAST_BROADCAST_POS=_VEH_LAST_BROADCAST_POS,
                            _VEH_PARENT_WATCH=_VEH_PARENT_WATCH,
                            _tock_state=tock_state,
                            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                            _build_world_atom_effect_pkt=(
                                _build_world_atom_effect_pkt),
                            next_effect_time_ms=next_effect_time_ms,
                            _stamina_byte=_stamina_byte,
                            agent_bits_for=agent_bits_for,
                        )
                        logger.info(f"[fire] destroy cascade returned for 0x{int(_target_v.id):08x}")
                    except Exception as _dce:
                        logger.error(f"[fire]   destroy cascade err: {_dce!r}")
                elif _target_v.hp <= 0:
                    logger.warning(f"[fire] WARN vehicle 0x{int(_target_v.id):08x} hp={_target_v.hp} but kill_confirmed=False. Destroy cascade will not run.")
            except Exception as _vde:
                logger.error(f"[fire]   vehicle combat apply err: {_vde!r}")
    elif _target_is_world or int(target_auid) == 0:
        try:
            _aim_dist = (float(aim_x) ** 2
                         + float(aim_y) ** 2) ** 0.5
        except Exception:
            _aim_dist = 0.0
        if _aim_dist > _weapon_range_m:
            logger.info(f"[fire] auid=0x{avatar_auid:08x} out OF range (terrain) dist={_aim_dist:.2f}m > {_weapon_range_m:.2f}m (cid={_weapon_cid} mode={_cur_mode}). Swing only, no impact VFX")
            _in_range = False
        else:
            logger.debug(f"[fire]   terrain range ok: dist={_aim_dist:.2f}m / "
                         f"max={_weapon_range_m:.2f}m")
    elif (_cur_mode == 0 and _body_slot is None
          and await _skin_ground_carcass(
              int(target_auid), int(avatar_auid), _weapon_cid,
              _gear_quality_of(target_entry),
              alloc_daitem_auid=alloc_daitem_auid,
              _live_avatars=_live_avatars,
              _DROPPED_ITEMS=_DROPPED_ITEMS,
              _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
              world_atom_auids=_WORLD_ATOM_AUIDS)):
        pass
    elif await _damage_npc_target(conn, int(target_auid), int(avatar_auid),
                                  _weapon_cid, _cur_mode, _in_range,
                                  _weapon_range_m, weapon=_body_weapon,
                                  idle_bodies=idle_bodies,
                                  story_npcs=story_npcs,
                                  story_atom_id=story_atom_id,
                                  story_name=story_name,
                                  _live_avatars=_live_avatars,
                                  tock_state=tock_state,
                                  _CITIZEN_EMPIRE_OVERRIDE=(
                                      _CITIZEN_EMPIRE_OVERRIDE),
                                  alloc_daitem_auid=alloc_daitem_auid,
                                  _DROPPED_ITEMS=_DROPPED_ITEMS,
                                  _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                                  spawned_buildings=spawned_buildings):
        pass
    else:
        logger.info(f"[fire] target 0x{int(target_auid):08x} not player/vehicle/world/npc. No damage applied (_target_v={_target_v!r}, npc_registered={is_damageable(int(target_auid))})")
    if target_entry[2] == 0x09 and _cur_mode != 0:
        body = bytearray(target_entry[3])
        if len(body) < 4:
            logger.warning(f"[fire] AuItemWeaponAmmo body too short ({len(body)} bytes)")
            return
        ammo1 = body[-4]
        ammo2 = body[-2]
        if _cur_mode == 2:
            _slot_ammo = ammo2
            _slot_name = "ammo2"
        else:
            _slot_ammo = ammo1
            _slot_name = "ammo1"
        if _slot_ammo == 0:
            logger.info(f"[fire] auid=0x{avatar_auid:08x} mode={_cur_mode} {_slot_name}=0. Fire blocked (press R to reload)")
            return
        if _cur_mode == 2:
            body[-2] = max(0, ammo2 - 1)
            logger.debug(f"[fire] ammo2 (mode=2 sub=2) {ammo2} -> {body[-2]}")
        else:
            body[-4] = max(0, ammo1 - 1)
            logger.debug(f"[fire] ammo1 (mode={_cur_mode} sub=1) {ammo1} -> {body[-4]}")
        target_entry[3] = bytes(body)
        await _push_augear_refresh_for(
            avatar_auid, log_prefix="fire",
            _live_avatars=_live_avatars,
            _AUGEAR_STATES=_AUGEAR_STATES,
            _build_augear_only_daperson_update=_build_augear_only_daperson_update,
        )
    elif target_entry[2] == 0x09 and _cur_mode == 0:
        logger.debug("[fire] rifle-butt melee swing (mode=0, no ammo cost)")
    elif target_entry[2] == 0x08:
        logger.debug("[fire] melee weapon swing (no ammo cost)")

    try:
        _fx_typeId = int(target_entry[2]) & 0xFF
        if _body_slot is not None:
            _fx_cid = 0
            _fx_sound = (int(_body_weapon.qty) & 0xFF) or 0x5F
            _fx_visual = _swing_fx_for_weapon(0, 0)[1]
        else:
            _fx_cid = _extract_cid_from_auitem_body(bytes(target_entry[3]))
            _fx_sound, _fx_visual = _swing_fx_for_weapon(_fx_cid, _cur_mode)
        _fx_xyz = (0.0, 0.0, 0.0)
        await _push_player_effect(
            writer, int(avatar_auid),
            origin_xyz=_fx_xyz,
            sound_type=_fx_sound,
            visual_type=_fx_visual,
            _live_avatars=_live_avatars,
            anchor_full=anchor_full,
            anchor_low32=anchor_low32,
            sim_time_state=sim_time_state,
            next_effect_time_ms=next_effect_time_ms,
            _stamina_byte=_stamina_byte,
            agent_bits_for=agent_bits_for,
        )
        if _in_range and int(target_auid) != 0:
            _strike_eff = 0x0F
            if _body_slot is not None:
                _strike_eff = int(_body_weapon.effect1) & 0xFF
            elif target_entry[2] == 0x09:
                if _cur_mode == 0:
                    _strike_eff = 0x08
                else:
                    _spec = _weapon_spec_for_cid(
                        _extract_cid_from_auitem_body(
                            bytes(target_entry[3])))
                    _strike_eff = int(_spec.get("primary", {}).get(
                        "sound", 0x0D)) & 0xFF
            _strike_visual = _WEAPONEFFECT_TO_STRIKE_VISUAL.get(
                _strike_eff, 0x1B)
            if int(target_entry[2]) & 0xFF in (0x08, 0x09, 0x0C):
                _strike_visual = 0x14
            _strike_xyz = (0.0, float(aim_x), float(aim_y))
            _target_is_live_player = (
                (int(target_auid) & 0xFFFFFFFF) in _live_avatars)
            _target_is_world_atom = (
                (int(target_auid) & 0xFFFFFFFF) in _WORLD_ATOM_AUIDS)
            _hit_kind, _hit_world = _classify_hit_surface(
                target_auid, avatar_auid,
                world_atom_auids=_WORLD_ATOM_AUIDS,
                _live_avatars=_live_avatars,
                spawned_buildings=spawned_buildings,
                idle_bodies=idle_bodies,
                story_atom_id=story_atom_id,
                story_npcs=story_npcs)
            if _hit_world and int(_hit_world) not in _WORLD_ATOM_AUIDS:
                logger.warning(f'[fire-fx] world anchor 0x{int(_hit_world):08x} is not a world atom this client has ({[hex(a) for a in _WORLD_ATOM_AUIDS]}).')
                _hit_world = 0
            if _target_is_live_player:
                _fx_route = "daperson_target"
                _fx_anchor_auid = int(target_auid)
                _fx_anchor_label = "target (DaPerson)"
            elif _target_is_world_atom or _hit_world:
                _fx_route = "world_globe"
                _fx_anchor_auid = int(
                    target_auid if _target_is_world_atom else _hit_world)
                _fx_anchor_label = (
                    f"{_hit_kind} impact @ world 0x{_fx_anchor_auid:08x} "
                    f"(DaWorldGlobe, no rotation follow)")
                _atk = _live_avatars.get(
                    int(avatar_auid) & 0xFFFFFFFF)
                if (_atk
                        and _atk.get("live_pos") is not None
                        and _atk.get("live_rot") is not None):
                    try:
                        _world_hit = _compute_world_hit_point(
                            _atk["live_pos"], _atk["live_rot"],
                            float(aim_x), float(aim_y))
                        _strike_xyz = (float(_world_hit[0]),
                                       float(_world_hit[1]),
                                       float(_world_hit[2]))
                        logger.debug(f"[fire-fx] world-hit transform: "
                                     f"pos={_atk['live_pos']} "
                                     f"yaw={_atk['live_rot'][2]:.4f} "
                                     f"aim=({aim_x:.2f},{aim_y:.2f}) "
                                     f"-> hit={_strike_xyz}")
                    except Exception as _whe:
                        logger.error(f"[fire-fx] world-hit transform err: {_whe!r}. Falling back to player-local aim")
                else:
                    logger.debug(f"[fire-fx] world-hit transform skip: no cached live_pos/live_rot for 0x{int(avatar_auid):08x} (need a 0x42 tick first). Using raw aim offset")
                if _hit_kind not in ("terrain", "building", "unknown"):
                    _victim_xyz = _victim_world_xyz(
                        target_auid,
                        story_npcs=story_npcs,
                        idle_bodies=idle_bodies,
                        spawned_buildings=spawned_buildings)
                    if _victim_xyz is not None:
                        _strike_xyz = _victim_xyz
                        logger.debug(f"[fire-fx] {_hit_kind} impact re-anchored to "
                                     f"the victim's own position {_strike_xyz}")
            else:
                _fx_route = "daperson_attacker"
                _fx_anchor_auid = int(avatar_auid)
                _fx_anchor_label = (f"attacker ({_hit_kind} fallback — "
                                    "rotates with player)")
            logger.debug(f"[fire-fx] strike: effect=0x{_strike_eff:02x} -> "
                         f"visual=0x{_strike_visual:02x} origin={_strike_xyz} "
                         f"aim=({aim_x:.2f},{aim_y:.2f}) "
                         f"target=0x{int(target_auid):08x} "
                         f"anchor=0x{_fx_anchor_auid:08x} route={_fx_route} "
                         f"({_fx_anchor_label})")
            try:
                _attacker_entry = _live_avatars.get(
                    int(avatar_auid) & 0xFFFFFFFF)
                if _attacker_entry:
                    _lp = _attacker_entry.get("live_pos")
                    _lr = _attacker_entry.get("live_rot")
                    if _lp and _lr:
                        logger.debug(f"[fire-fx] attacker state: "
                                     f"pos=({_lp[0]:.2f},{_lp[1]:.2f},{_lp[2]:.2f}) "
                                     f"rot=({_lr[0]:.5f},{_lr[1]:.5f},{_lr[2]:.5f}) "
                                     f"aim=({aim_x:.3f},{aim_y:.3f})")
            except Exception as _prfe:
                logger.error(f"[fire-fx] pos-rot dump err: {_prfe!r}")
            _broadcast_writers = []
            try:
                for _pa, _pe in _live_avatars.items():
                    _pw = _pe.get("writer") if isinstance(_pe, dict) else None
                    if _pw is not None and _pw not in _broadcast_writers:
                        _broadcast_writers.append(_pw)
            except Exception as _be:
                logger.error(f"[fire-fx] broadcast enumerate err: {_be!r}")
            if writer is not None and writer not in _broadcast_writers:
                _broadcast_writers.append(writer)
            for _bw in _broadcast_writers:
                try:
                    if _fx_route == "world_globe":
                        try:
                            _sync_t_low = _note_0x18(
                                (_current_sim_t_low(anchor_full=anchor_full)
                                 or sim_time_state.get("last_0x18_t_low", 0)
                                 or anchor_low32),
                                "fire-fx-sync")
                            if _sync_t_low:
                                _sync_pkt = (bytes([0x18])
                                             + (_sync_t_low & 0xFFFFFFFF
                                                ).to_bytes(4, "big")
                                             + bytes([0x02]))
                                await write_framed(_bw, _sync_pkt)
                                sim_time_state["last_0x18_t_low"] = (
                                    _sync_t_low & 0xFFFFFFFF)
                        except Exception as _se:
                            logger.error(f"[fire-fx] world sync err: {_se!r}")
                        _wbody = _build_world_atom_effect_pkt(
                            _fx_anchor_auid,
                            origin_xyz=_strike_xyz,
                            sound_type=_fx_sound,
                            visual_type=_strike_visual,
                            next_effect_time_ms=next_effect_time_ms,
                        )
                        await write_framed(_bw, _wbody)
                        logger.debug(f"[fire-fx] world-anchor sent "
                                     f"to=0x{_fx_anchor_auid:08x} "
                                     f"len={len(_wbody)}B")
                    else:
                        await _push_player_effect(
                            _bw, _fx_anchor_auid,
                            origin_xyz=_strike_xyz,
                            sound_type=_fx_sound,
                            visual_type=_strike_visual,
                            _live_avatars=_live_avatars,
                            anchor_full=anchor_full,
                            anchor_low32=anchor_low32,
                            sim_time_state=sim_time_state,
                            next_effect_time_ms=next_effect_time_ms,
                            _stamina_byte=_stamina_byte,
                            agent_bits_for=agent_bits_for,
                        )
                except Exception as _bxe:
                    logger.error(f"[fire-fx] broadcast err: {_bxe!r}")
    except Exception as _fxe:
        logger.error(f"[fire-fx] effect emit failed: {_fxe!r}")
