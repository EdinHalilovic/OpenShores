
from __future__ import annotations

import struct

from openshores.core.logging import get_logger
from openshores.database.journal import get_queue
from openshores.gameplay.gear_slots import _add_gear_item
from openshores.gameplay.vehicles.atom_packet import build_da_vehicle_atom
from openshores.gameplay.vehicles.spawn import spawn_vehicle
from openshores.network.chat_binding import _chat_writer_auid
from openshores.network.vehicle_loops import _davehicle_keepalive_start
from openshores.protocol.atoms.gear import (
    _apply_weapon_typeid_migration,
    _pack_au_gear,
)
from openshores.protocol.atoms.item_seed import _pack_auitem_seed_body
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


async def handle_make_commodity(
        payload: bytes, writer, *, _live_avatars: dict,
        _PENDING_CHAT_AUIDS: list, _PLAYER_AUID: bytes,
        _DYNAMIC_SCENE_AUIDS: set, _tock_state: dict, conn,
        _get_augear, _build_augear_only_daperson_update,
        _veh_note_ground_radius) -> None:
    if len(payload) < 34:
        logger.warning(f"[chat]   0xC2 short frame "
                       f"len={len(payload)}; ignoring")
        return
    try:
        commodity_id = struct.unpack(
            ">H", payload[1:3])[0]
        quality      = payload[3]
        quantity     = struct.unpack(
            ">I", payload[4:8])[0]
        galaxy       = payload[8]
        where        = payload[33]
    except Exception as _ce:                            # noqa: BLE001
        logger.warning(f"[chat]   0xC2 decode error: {_ce!r}")
        return

    logger.info(f"[chat]   0xC2 MakeCommodity "
                f"commodity={commodity_id} "
                f"quality={quality} qty={quantity} "
                f"galaxy=0x{galaxy:02x} where={where}")

    _actor_auid_int = _chat_writer_auid(
        writer, live_avatars=_live_avatars,
        _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS)
    if not _actor_auid_int and _PLAYER_AUID:
        _actor_auid_int = int.from_bytes(
            _PLAYER_AUID, "big")
    if not _actor_auid_int:
        logger.warning("[chat]   0xC2 no bound actor; ignoring")
        return
    _actor_auid_bytes = (
        _actor_auid_int.to_bytes(4, "big"))
    _actor_entry = _live_avatars.get(
        _actor_auid_int) or {}
    _actor_writer = _actor_entry.get("writer")
    _actor_augear = _get_augear(_actor_auid_int)

    _VEHICLE_CIDS = frozenset({
        6, 7, 8, 9, 0x1c, 0x36, 0x46, 0x47, 0x4d,
        0x52, 0x67, 0x68, 0x84, 0x85, 0xe7,
        0x156, 0x15d,
    })
    if commodity_id in _VEHICLE_CIDS:
        if commodity_id in (0x156, 0x15d):
            logger.info(f"[chat]   0xC2 commodity={commodity_id:#x} "
                        f"is an empire-creation special, deferred")
            return
        def _resolve_auid(val):
            if isinstance(val, int):
                return val & 0xFFFFFFFF
            if isinstance(val, (bytes, bytearray)):
                try:
                    return int.from_bytes(val[:4], "big")
                except Exception:                       # noqa: BLE001
                    return 0
            return 0
        _veh_parent = _resolve_auid(_actor_entry.get("parent_world"))
        if _veh_parent == 0:
            try:
                _veh_parent = _resolve_auid(_AW)        # noqa: F821
            except Exception:                           # noqa: BLE001
                _veh_parent = 0
        if _veh_parent == 0:
            try:
                _veh_parent = int(_planet_auid_int) & 0xFFFFFFFF  # noqa: F821
            except Exception:                           # noqa: BLE001
                _veh_parent = 0
        _veh_xyz = _actor_entry.get("xyz")
        if (not isinstance(_veh_xyz, (tuple, list)) or
                len(_veh_xyz) != 3):
            try:
                _veh_xyz = _robert_xyz_v65              # noqa: F821
            except NameError:
                _veh_xyz = (0.0, 0.0, 0.0)
        try:
            _ts_av = _tock_state.get(_actor_auid_int, {})
            _player_rot = _ts_av.get("last_rotation")
        except Exception:                               # noqa: BLE001
            _player_rot = None
        import math as _vsm
        _vx, _vy, _vz = (float(_veh_xyz[0]),
                         float(_veh_xyz[1]),
                         float(_veh_xyz[2]))
        _vr = _vsm.sqrt(_vx * _vx + _vy * _vy + _vz * _vz)
        if _vr < 1e-6:
            _vnx, _vny, _vnz = 0.0, 1.0, 0.0
            _vr = 1.0
        else:
            _vnx, _vny, _vnz = _vx/_vr, _vy/_vr, _vz/_vr
        _vex, _vey, _vez = -_vnz, 0.0, _vnx
        _velen = _vsm.sqrt(_vex*_vex + _vey*_vey + _vez*_vez)
        if _velen < 1e-6:
            _vex, _vey, _vez = 1.0, 0.0, 0.0
        else:
            _vex, _vey, _vez = _vex/_velen, _vey/_velen, _vez/_velen
        _vnnx = _vny*_vez - _vnz*_vey
        _vnny = _vnz*_vex - _vnx*_vez
        _vnnz = _vnx*_vey - _vny*_vex
        _vyaw = float(_player_rot[2]) if (_player_rot and
                isinstance(_player_rot, (list, tuple)) and
                len(_player_rot) >= 3) else 0.0
        _vyaw_off = -0.95
        _vyaw_sign = -1.0
        _vtheta = _vyaw_sign * _vyaw + _vyaw_off
        _vctheta = _vsm.cos(_vtheta)
        _vstheta = _vsm.sin(_vtheta)
        _vfx = _vctheta * _vnnx + _vstheta * _vex
        _vfy = _vctheta * _vnny + _vstheta * _vey
        _vfz = _vctheta * _vnnz + _vstheta * _vez
        _lift_m = 5.0
        _fwd_m = -20.0
        _spawn_xyz = (
            _vx + _lift_m * _vnx + _fwd_m * _vfx,
            _vy + _lift_m * _vny + _fwd_m * _vfy,
            _vz + _lift_m * _vnz + _fwd_m * _vfz,
        )
        logger.debug(f"[chat]   0xC2 pose: player=({_vx:.1f},{_vy:.1f},{_vz:.1f}) "
                     f"|p|={_vr:.1f} yaw={_vyaw:.3f} "
                     f"normal=({_vnx:.3f},{_vny:.3f},{_vnz:.3f}) "
                     f"fwd=({_vfx:.3f},{_vfy:.3f},{_vfz:.3f}) "
                     f"-> spawn=({_spawn_xyz[0]:.1f},"
                     f"{_spawn_xyz[1]:.1f},{_spawn_xyz[2]:.1f})")
        if (_player_rot and
                isinstance(_player_rot, (list, tuple)) and
                len(_player_rot) >= 3):
            _spawn_rot = (
                float(_player_rot[0]),
                float(_player_rot[1]),
                float(_player_rot[2]),
            )
        else:
            _spawn_rot = (
                _vsm.atan2(-_vx, _vz),
                _vsm.asin(max(-1.0, min(1.0, _vy / _vr))),
                0.0,
            )
        _q = int(quality) & 0xFF
        if _q < 1: _q = 1
        if _q > 100: _q = 100
        try:
            _new_veh = await spawn_vehicle(
                commodity_id=int(commodity_id),
                parent_id=int(_veh_parent) & 0xFFFFFFFF,
                location=_spawn_xyz,
                rotation=_spawn_rot,
                name="",
                quality=_q,
                allegiance=int(_actor_auid_int) & 0xFFFFFFFF,
                fuel=100,
                conn=conn,
            )
            logger.info(f"[chat]   0xC2 spawned vehicle: "
                        f"id=0x{_new_veh.id:08x} cid=0x{_new_veh.cid:x} "
                        f"q={_new_veh.qual} hp={_new_veh.hp} "
                        f"parent=0x{_new_veh.idp:x} "
                        f"loc=({_new_veh.locX:.1f}, "
                        f"{_new_veh.locY:.1f}, "
                        f"{_new_veh.locZ:.1f})")
            try:
                _note = _veh_note_ground_radius
                if _note is not None:
                    _note(int(_veh_parent) & 0xFFFFFFFF,
                          _spawn_xyz)
            except Exception as _floor_exc:             # noqa: BLE001
                logger.warning(f"[chat]   0xC2 floor-note skipped: "
                               f"{_floor_exc!r}")
            try:
                _veh_pkt = build_da_vehicle_atom(_new_veh)
                if (_actor_writer is not None
                        and not _actor_writer.is_closing()):
                    _DYNAMIC_SCENE_AUIDS.add(int(_new_veh.id))
                    try:
                        _vb = getattr(_actor_writer,
                            "_scene_manifest_builder", None)
                        if _vb:
                            _mpkt = _vb()
                            await write_framed(_actor_writer, _mpkt)
                            logger.debug(f"[chat]   0xC2 -> scene 0x18 "
                                         f"manifest pre-emit ({len(_mpkt)}B; "
                                         f"added=0x{int(_new_veh.id):08x})")
                        else:
                            logger.warning("[chat]   0xC2 no manifest builder "
                                           "on writer; vehicle may be culled")
                    except Exception as _mee:           # noqa: BLE001
                        logger.warning(f"[chat]   0xC2 manifest re-emit "
                                       f"failed: {_mee!r}")
                    await write_framed(_actor_writer, _veh_pkt)
                    logger.info(f"[chat]   0xC2 broadcast: "
                                f"sent {len(_veh_pkt)}B 0x1C atom "
                                f"to spawner (auid=0x{_actor_auid_int:x})")
                    _v4_sent = 0
                    for _peer_auid, _peer_entry in list(
                            _live_avatars.items()):
                        if int(_peer_auid) == int(_actor_auid_int):
                            continue
                        _pw = (_peer_entry.get("writer")
                               if isinstance(_peer_entry, dict)
                               else None)
                        if _pw is None or _pw.is_closing():
                            continue
                        try:
                            _pb = getattr(
                                _pw,
                                "_scene_manifest_builder",
                                None)
                            if _pb is not None:
                                _pmpkt = _pb()
                                await write_framed(
                                    _pw, _pmpkt)
                            await write_framed(
                                _pw, _veh_pkt)
                            _v4_sent += 1
                        except Exception as _v4e:       # noqa: BLE001
                            logger.warning(f"[chat]   0xC2 V.4 "
                                           f"peer push err "
                                           f"auid=0x{int(_peer_auid):08x}: "
                                           f"{_v4e!r}")
                    if _v4_sent:
                        logger.info(f"[chat]   0xC2 V.4 "
                                    f"broadcast: pushed atom "
                                    f"+ manifest to "
                                    f"{_v4_sent} peer(s)")
                    _davehicle_keepalive_start(
                        int(_new_veh.id), _live_avatars=_live_avatars)
                else:
                    logger.warning('[chat]   0xC2 broadcast: no active writer for peer.')
            except Exception as _bce:                   # noqa: BLE001
                logger.warning(f"[chat] 0xC2 broadcast failed (non-fatal): {_bce!r}")
        except Exception as _vse:                       # noqa: BLE001
            logger.warning(f"[chat] 0xC2 vehicle spawn failed: {_vse!r}")
        return

    if where in (1, 2):
        _qty = max(1, min(10, int(quantity)))
        _added = []
        _full = False
        for _i in range(_qty):
            _body = _pack_auitem_seed_body(
                typeId=0x01,
                cid=int(commodity_id) & 0xFFFF,
                byte14=5,
                quality=int(quality) & 0xFF,
                name="",
            )
            _slot, _sub = _add_gear_item(
                _actor_augear, 0x01, _body)
            if _slot is None:
                _full = True
                break
            _added.append((_slot, _sub))
        logger.info(f"[chat]   0xC2 added {len(_added)}/"
                    f"{_qty} item(s) to gear; slots="
                    f"{_added}"
                    + (" [REJECT: gear full]"
                       if _full else ""))
        if _added:
            try:
                _apply_weapon_typeid_migration(
                    _actor_augear,
                    source=f"0xC2:cid{commodity_id}")
            except Exception as _wte:                   # noqa: BLE001
                logger.warning(f"[chat] 0xC2 weapon typeId migration failed (non-fatal): {_wte!r}")

        if (_added and _actor_writer is not None
                and not _actor_writer.is_closing()):
            try:
                new_aug = _pack_au_gear([
                    (e[0], e[1], e[2], e[3])
                    for e in _actor_augear
                ])
                reply = (
                    _build_augear_only_daperson_update(
                        _actor_auid_bytes, new_aug))
                await write_framed(_actor_writer, reply)
                logger.info(f"[chat]   0xC2 -> AuGear refresh "
                            f"({len(reply)}B; "
                            f"{len(_actor_augear)} slot(s))")
                try:
                    _queue = get_queue()
                    if _queue is not None:
                        _queue.submit(
                            "update_person_state",
                            _actor_auid_int,
                            inv=bytes(new_aug))
                        logger.debug("[chat]   0xC2 SQL inv "
                                     "persisted len=%d for "
                                     "auid=0x%08x" % (
                                         len(new_aug),
                                         _actor_auid_int))
                except Exception as _spc:               # noqa: BLE001
                    logger.warning("[chat]   0xC2 SQL "
                                   "persist failed: "
                                   f"{_spc!r}")
            except Exception as _re:                    # noqa: BLE001
                logger.warning(f"[chat]   0xC2 reply push "
                               f"failed: {_re!r}")
    else:
        logger.info(f"[chat]   0xC2 where={where} not yet "
                    f"supported (3=City, 4=Cargo, 5..8="
                    f"combo packs)")
