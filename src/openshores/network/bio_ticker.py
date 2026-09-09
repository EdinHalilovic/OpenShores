
from __future__ import annotations

import asyncio
import struct

from openshores.core.logging import get_logger
from openshores.database.journal import get_queue
from openshores.database.repositories.person import read_person_state
from openshores.gameplay.combat.kill_reputation import _award_kill_reputation
from openshores.gameplay.condition_states import _tick_conditions
from openshores.gameplay.dpbody_maxes import max_stamina as _dna_stam
from openshores.gameplay.food import _hunger_i16
from openshores.gameplay.stamina import _apply_stamina_modifiers
from openshores.network.death_respawn import _start_death_respawn
from openshores.protocol.dna_decoder import decode_species as _decode_species
from openshores.protocol.framing import write_framed
from openshores.world.session import state_flush_ticker as _g2_flusher

logger = get_logger(__name__)


_POSE_RATES = {
    0x16: -2,
    0x19: -4, 0x25: -4, 0x2B: -4,
    0x21: -1,
    0x1B:  4, 0x26:  4,
    0x28:  5,
    0x2D:  6,
    0x10:  7, 0x4A:  7,
}
for _p in (
        0x24,
        0x56, 0x57, 0x5A, 0x5B, 0x5E, 0x5F,
        0x62, 0x63, 0x66, 0x67, 0x6A, 0x6B,
        0x6F, 0x70, 0x73, 0x74, 0x77, 0x78,
        0x7B, 0x7C, 0x7F, 0x80, 0x84, 0x85, 0x87):
    _POSE_RATES.setdefault(_p, 8)
for _p in (
        *range(0x03, 0x0F + 1),
        0x23, 0x37, 0x39, 0x3A, 0x3B, 0x3C,
        0x3D, 0x3E, 0x3F,
        0x40, 0x41, 0x42, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49,
        0x54, 0x55, 0x58, 0x59, 0x5C, 0x5D,
        0x60, 0x61, 0x64, 0x65, 0x68, 0x69,
        0x6D, 0x6E, 0x71, 0x72, 0x75, 0x76,
        0x79, 0x7A, 0x7D, 0x7E, 0x81, 0x82, 0x83, 0x86):
    _POSE_RATES.setdefault(_p, 9)
for _p in (0x20, 0x6C, *range(0x4C, 0x53 + 1)):
    _POSE_RATES.setdefault(_p, 10)
for _p in (0x2A, 0x35, 0x4B):
    _POSE_RATES.setdefault(_p, 3)
del _p


async def _bio_ticker(w, target_auid, *,
                      conn,
                      _bio_tick_rate,
                      _POSE_RATES,
                      _conn_tasks,
                      _session,
                      _SAVE,
                      tock_state,
                      condition_states,
                      live_avatars,
                      get_augear,
                      agent_bits_for,
                      _CITIZEN_EMPIRE_OVERRIDE,
                      alloc_daitem_auid,
                      _DROPPED_ITEMS,
                      _DYNAMIC_SCENE_AUIDS,
                      world_atom_auids):
    import time as _bt_time
    _STAMINA_MAX_FALLBACK = 0x7F
    _stamina_max = _STAMINA_MAX_FALLBACK
    _persist_every = 10
    _persist_counter = 0
    _last_sql_bio = (None, None, None)
    _seed_state = await read_person_state(conn, target_auid) or {}
    _stamina_max = int(_seed_state.get("max_stamina") or 0)
    _stam_src = "db"
    if not _stamina_max:
        _dna_seed = _seed_state.get("dna")
        if _dna_seed:
            try:
                _stamina_max = int(_dna_stam(bytes(_dna_seed)))
                _stam_src = "dna"
            except Exception as _sexc:
                logger.warning(f"[bio-tock]   MaxStamina from DNA failed: "
                               f"{_sexc!r}")
    if not _stamina_max:
        _stamina_max = _STAMINA_MAX_FALLBACK
        _stam_src = "fallback"
    _stamina_max = max(1, min(255, _stamina_max))
    _ts_init = tock_state.setdefault(
        int(target_auid),
        {"pose": 0x24, "last_minute": -1, "last_hour": -1})
    _seed_hunger = _seed_state.get("hunger")
    _ts_init.setdefault(
        "hunger",
        int(_seed_hunger) if _seed_hunger is not None
        else int(_ts_init.get("max_hunger") or 0) or 100)
    _ts_init.setdefault(
        "stamina",
        int(_seed_state.get("stamina") or _stamina_max))
    _ts_init.setdefault(
        "hp",
        int(_seed_state.get("hp")
            or int(_SAVE.person_hit_points)
            or 46))
    _db_max_hp = _seed_state.get("max_hp")
    _ts_init["max_hp"] = max(1, int(
        _db_max_hp if _db_max_hp is not None
        else (int(_SAVE.person_hit_points) or 46)))
    _ts_init["max_stamina"] = _stamina_max
    _db_max_hunger = _seed_state.get("max_hunger")
    _ts_init["max_hunger"] = max(1, int(
        _db_max_hunger if _db_max_hunger is not None
        else _ts_init["max_hp"] * 2))
    _ts_init.setdefault("xp",        int(_seed_state.get("xp")         or 0))
    _ts_init.setdefault("bank",       float(_seed_state.get("bank")     or 0.0))
    _ts_init.setdefault("reputation", int(_seed_state.get("reputation") or 0))
    _ts_init.setdefault("islefty",    int(_seed_state.get("islefty")    or 0))
    if _seed_state.get("sex") is not None:
        _ts_init.setdefault("sex", int(_seed_state["sex"]))
    _db_dna = _seed_state.get("dna")
    if _db_dna and len(_db_dna) == 24:
        try:
            _species_str = _decode_species(_db_dna)
        except Exception as _dexc:
            logger.debug(f"[bio-tock]   species decode failed: {_dexc!r}")
            _species_str = "(decode error)"
        _ts_init.setdefault("dna",     bytes(_db_dna))
        _ts_init.setdefault("species", _species_str)
    else:
        _species_str = "(no dna)"
    logger.info(f"[bio-tock]   auid=0x{target_auid:08x} initialized "
                f"in-memory model: hp={_ts_init['hp']} "
                f"hunger={_ts_init['hunger']} "
                f"stamina={_ts_init['stamina']} "
                f"max_hp={_ts_init['max_hp']} "
                f"max_stamina={_stamina_max} (from {_stam_src}) "
                f"max_hunger={_ts_init['max_hunger']} "
                f"xp={_ts_init['xp']} bank={_ts_init['bank']:.2f} "
                f"rep={_ts_init['reputation']} "
                f"species={_species_str!r}")
    _last_sql_bio = (
        int(_seed_state.get("hp"))   if _seed_state.get("hp")   is not None else None,
        int(_seed_state.get("hunger")) if _seed_state.get("hunger") is not None else None,
        int(_seed_state.get("stamina")) if _seed_state.get("stamina") is not None else None,
    )
    try:
        while not w.is_closing():
            await asyncio.sleep(_bio_tick_rate)
            try:
                _ts_entry = tock_state[int(target_auid)]
                _h = int(_ts_entry.get("hunger", 0))
                _s = int(_ts_entry.get("stamina", _stamina_max))
                _hp = int(_ts_entry.get("hp", 46))
                _max_hp = int(_ts_entry.get("max_hp") or
                    max(1, int(_SAVE.person_hit_points) or 46))
                _max_hunger = int(_ts_entry.get("max_hunger")
                                  or _max_hp * 2)
                _stamina_max = int(_ts_entry.get("max_stamina")
                                   or _stamina_max)
                _ts_entry = tock_state.setdefault(
                    int(target_auid),
                    {"pose": 0x24,
                     "last_minute": -1,
                     "last_hour": -1})
                _cur_pose = _ts_entry.get("pose", 0x24) & 0xFF
                _rate = _POSE_RATES.get(_cur_pose, 0)
                _rate = _apply_stamina_modifiers(
                    target_auid, _rate,
                    gear=get_augear(target_auid),
                    tock_state=tock_state,
                    live_avatars=live_avatars)
                _new_s = _s
                _bio_mult = 1.0
                if _rate < 0:
                    if _s > 0:
                        _step = max(1, int(round(
                            -_rate * _bio_mult)))
                        _new_s = max(0, _s - _step)
                elif _rate > 0 and _bio_mult > 0:
                    if _h > 0 and _s < _stamina_max:
                        _step = max(1, int(round(
                            (_stamina_max * _rate / 100.0)
                            * _bio_mult)))
                        _new_s = min(_stamina_max, _s + _step)
                _now_min = int(_bt_time.time() // 60)
                _new_h = _h
                if (_now_min != _ts_entry.get("last_minute", -1)
                    and (_now_min & 1) != 0):
                    _step_h = max(1, _max_hunger // 0x28)
                    _new_h = max(0, _h - _step_h)
                    _ts_entry["last_minute"] = _now_min
                _now_hr = int(_bt_time.time() // 3600)
                _new_hp = _hp
                if _now_hr != _ts_entry.get("last_hour", -1):
                    _ts_entry["last_hour"] = _now_hr
                    if _new_h <= 0:
                        _new_hp = max(-30, _hp - 2)
                    elif 0 < _hp < _max_hp:
                        _new_hp = min(_max_hp, _hp + 1)
                try:
                    _cond_hp = _tick_conditions(
                        target_auid,
                        condition_states=condition_states,
                        tock_state=tock_state)
                    if _cond_hp:
                        _new_hp = max(-30, _new_hp + _cond_hp)
                        logger.info(f"[condition] 0x{target_auid:08x} "
                                    f"conditions cost {-_cond_hp} hp "
                                    f"-> {_new_hp}")
                except Exception as _cexc:
                    logger.error(f"[condition] tick failed: {_cexc!r}")
                _ts_entry["hunger"] = _new_h
                _ts_entry["stamina"] = _new_s
                _ts_entry["hp"] = _new_hp
                _death_threshold = -15
                if (_new_hp <= _death_threshold
                        and not _ts_entry.get("dying")):
                    try:
                        _killer = _ts_entry.get("last_attacker")
                        if _killer:
                            await _award_kill_reputation(
                                conn, target_auid, _killer,
                                tock_state=tock_state,
                                _CITIZEN_EMPIRE_OVERRIDE=(
                                    _CITIZEN_EMPIRE_OVERRIDE))
                        _ts_entry.pop("last_attacker", None)
                        _ts_entry.pop("last_attacker_ms", None)
                    except Exception as _kexc:
                        logger.error(f"[kill-rep] attribution failed: "
                                     f"{_kexc!r}")
                    _conn_tasks.append(_start_death_respawn(
                        w, target_auid,
                        _ts_entry=_ts_entry,
                        _SAVE=_SAVE,
                        tock_state=tock_state,
                        alloc_daitem_auid=alloc_daitem_auid,
                        _live_avatars=live_avatars,
                        _DROPPED_ITEMS=_DROPPED_ITEMS,
                        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
                        world_atom_auids=world_atom_auids))
                _cur_bio = (int(_new_hp), int(_new_h), int(_new_s))
                if _session is not None:
                    if _cur_bio != _last_sql_bio:
                        _session.mark_bio_dirty(
                            hp=_cur_bio[0],
                            hunger=_cur_bio[1],
                            stamina=_cur_bio[2])
                        _last_sql_bio = _cur_bio
                        _session.hot_state_suppressed_total += 1
                else:
                    _persist_counter += 1
                    if (_persist_counter >= _persist_every
                        and _cur_bio != _last_sql_bio):
                        _queue = get_queue()
                        if _queue is not None:
                            _queue.submit(
                                "update_person_state",
                                target_auid,
                                hp=_cur_bio[0],
                                hunger=_cur_bio[1],
                                stamina=_cur_bio[2])
                        _last_sql_bio = _cur_bio
                        _persist_counter = 0
                        if _queue is not None:
                            _queue.submit("flush_online_time", target_auid)
                if (_new_s != _s or _new_h != _h
                    or _new_hp != _hp):
                    logger.debug(f"[bio-tock]   auid=0x{target_auid:08x} "
                                 f"pose=0x{_cur_pose:02x} "
                                 f"rate={_rate:+d}/s  "
                                 f"hp {_hp}->{_new_hp}  "
                                 f"hunger {_h}->{_new_h}  "
                                 f"stamina {_s}->{_new_s}")
                _h, _s, _hp = _new_h, _new_s, _new_hp
                try:
                    import time as _bt_lp_time
                    _now_ms = int(_bt_lp_time.time() * 1000)
                    _hp_clamped = max(-30, min(0x7fff,
                                                int(_new_hp)))
                    _min_pkt = (
                        bytes([0x12])
                        + struct.pack(">I", int(target_auid))
                        + struct.pack(">q", _now_ms)
                        + bytes([0x00])
                        + bytes([0x00])
                        + bytes([0x04])
                        + struct.pack(">h", _hp_clamped)
                        + bytes([int(_new_s) & 0xFF])
                        + bytes([0x00])
                        + bytes([0x0C])
                        + struct.pack(
                            ">H",
                            _hunger_i16(
                                int(target_auid), _new_h,
                                _tock_state=tock_state))
                        + bytes([agent_bits_for(
                            int(target_auid)) & 0x3F])
                    )
                    await write_framed(w, _min_pkt)
                except Exception as _lpe:
                    logger.error(f"[bio-tock]   live-push "
                                 f"error: {_lpe!r}")
            except Exception as _bte:
                logger.error(f"[bio-tick]   error (continuing): "
                             f"{_bte!r}")
    except Exception as _bx:
        logger.info(f"[bio-tick]   ended: {_bx!r}")


def start_bio_ticker(writer, _conn_label, _active_avatar_auid, *,
                     conn,
                     _conn_tasks,
                     _session,
                     _SAVE,
                     tock_state,
                     condition_states,
                     live_avatars,
                     get_augear,
                     agent_bits_for,
                     _CITIZEN_EMPIRE_OVERRIDE,
                     alloc_daitem_auid,
                     _DROPPED_ITEMS,
                     _DYNAMIC_SCENE_AUIDS,
                     world_atom_auids) -> None:
    _bio_tick_rate = 1.0
    _hunger_rate = 1
    _stamina_rate = 5
    _bio_target_auid = int(_active_avatar_auid)
    _conn_tasks.append(asyncio.create_task(_bio_ticker(
        writer, _bio_target_auid,
        conn=conn,
        _bio_tick_rate=_bio_tick_rate,
        _POSE_RATES=_POSE_RATES,
        _conn_tasks=_conn_tasks,
        _session=_session,
        _SAVE=_SAVE,
        tock_state=tock_state,
        condition_states=condition_states,
        live_avatars=live_avatars,
        get_augear=get_augear,
        agent_bits_for=agent_bits_for,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
        alloc_daitem_auid=alloc_daitem_auid,
        _DROPPED_ITEMS=_DROPPED_ITEMS,
        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
        world_atom_auids=world_atom_auids)))
    if _session is not None:
        _conn_tasks.append(asyncio.create_task(
            _g2_flusher(_session, writer, get_queue())))
        logger.info(f"[scene]   {_conn_label}: G.2 state "
                    f"flush ticker started")
    logger.info(f"[scene]   -> {_conn_label} bio ticker started "
                f"(every {_bio_tick_rate:.0f}s wallclock: "
                f"hunger -={_hunger_rate}, stamina +={_stamina_rate})")
