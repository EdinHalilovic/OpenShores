
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.database.journal import get_queue
from openshores.gameplay.containers import (
    _container_add_nested,
    _container_pop_nested,
    _is_container_cid,
    _upgrade_to_container,
)
from openshores.gameplay.food import _food_value, _is_food_cid
from openshores.gameplay.gear_entry import _augear_apply_move, _augear_pop
from openshores.gameplay.gear_slots import (
    SLOT_CAPS,
    SLOT_NAMES,
    _next_sub_index,
    _slot_count,
)
from openshores.gameplay.use_action_tables import (
    USE_DRINK_CIDS,
    USE_STAMINA_RESET_CIDS,
    USE_TOGGLEABLE_CIDS,
)
from openshores.network.chat_binding import _chat_writer_auid
from openshores.network.creature_state import _push_creature_state
from openshores.network.daitem_lifecycle import _daitem_lifecycle
from openshores.protocol.atoms.daitem_drop import _build_daitem_drop_packet
from openshores.protocol.atoms.gear import (
    _pack_au_gear,
    _reinscribe_body,
    _set_item_message,
    _set_item_picture,
)
from openshores.protocol.atoms.item_seed import _pack_auitem_seed_body
from openshores.protocol.atoms.item_state import (
    _flip_auitemstate_switched_on,
    _read_auitem_cid_from_body,
    _upgrade_to_auitemstate,
)
from openshores.protocol.framing import write_framed
from openshores.protocol.stream import QDS

logger = get_logger(__name__)


_INV_OPS = (0x57, 0x5d, 0x5f, 0x60, 0x66, 0x67, 0x69)


async def handle_inventory_op(
        payload: bytes, op: int, peer, writer, *,
        _live_avatars: dict, _PENDING_CHAT_AUIDS: list,
        _PLAYER_AUID: bytes, _DROPPED_ITEMS: dict,
        _DYNAMIC_SCENE_AUIDS: set, _PARENT_WORLD_AUID, _SAVE,
        _tock_state: dict, alloc_daitem_auid, _get_augear,
        _can_hold_item, _build_augear_only_daperson_update,
        agent_bits_for, CONTAINER_CIDS, CONTAINER_CAPACITIES,
        USE_FOOD_CIDS) -> None:
    s = QDS(payload); s.read_u8()
    logger.info(f"[chat] <- {peer} op=0x{op:02X} "
                f"len={len(payload)}: {payload.hex()}")
    src_slot = s.read_u8()
    src_sub_raw = s.read_u8()
    src_path = []
    if src_sub_raw & 0x80:
        src_path_count = s.read_u8()
        for _ in range(src_path_count):
            src_path.append(s.read_u8())
    src_sub = src_sub_raw & 0x0F
    _actor_auid_int = _chat_writer_auid(
        writer, live_avatars=_live_avatars,
        _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS)
    if not _actor_auid_int and _PLAYER_AUID:
        _actor_auid_int = int.from_bytes(_PLAYER_AUID, "big")
    _actor_auid_bytes = (
        _actor_auid_int.to_bytes(4, "big")
        if _actor_auid_int else b"")
    _actor_entry = _live_avatars.get(_actor_auid_int) or {}
    _actor_writer = _actor_entry.get("writer")
    _actor_augear = (_get_augear(_actor_auid_int)
                     if _actor_auid_int else [])

    action = "?"
    removed_item = None
    extra = ""

    if op == 0x57:
        action = "DropGearItem"
        if int(src_slot) not in SLOT_CAPS:
            removed_item = None
            extra = (" [REJECT: src_slot=%d out of "
                     "valid range 1..9]" % int(src_slot))
        else:
            removed_item = _augear_pop(
                _actor_augear, src_slot, src_sub)
        _drop_parent = (_actor_entry.get("parent_world")
                        if isinstance(_actor_entry, dict)
                        else None) or _PARENT_WORLD_AUID
        if (removed_item is not None
                and _drop_parent
                and _actor_writer is not None
                and not _actor_writer.is_closing()):
            try:
                _player_auid_int = _actor_auid_int
                _av_entry = _actor_entry
                _xyz = _av_entry.get(
                    "xyz") or _SAVE.person_position or (0.0, 0.0, 0.0)
                _new_auid_int = alloc_daitem_auid()
                if int(removed_item[2]) == 0x0E:
                    _drop_body = _pack_auitem_seed_body(
                        typeId=0x0E,
                        cid=0 & 0xFFFF or 130,
                        byte14=5 & 0xFF,
                        quality=0x3D & 0xFF,
                        name="",
                        for_world=True,
                    )
                else:
                    _drop_body = bytes(removed_item[3])
                _drop_pkt = _build_daitem_drop_packet(
                    item_auid_int=_new_auid_int,
                    parent_auid=_drop_parent,
                    xyz=_xyz,
                    item_typeId=int(removed_item[2]),
                    item_body=_drop_body,
                )
                import time as _drop_t
                _drop_now_ms = int(_drop_t.time() * 1000)
                _av_rot = (
                    _av_entry.get("last_rotation")
                    or _tock_state.get(
                        _player_auid_int, {})
                       .get("last_rotation")
                    or (0.0, 0.0, 0.0))
                _drop_pkt = _build_daitem_drop_packet(
                    item_auid_int=_new_auid_int,
                    parent_auid=_drop_parent,
                    xyz=_xyz,
                    item_typeId=int(removed_item[2]),
                    item_body=_drop_body,
                    rotation=_av_rot,
                    time_created_ms=_drop_now_ms,
                )
                _DYNAMIC_SCENE_AUIDS.add(_new_auid_int)
                _DROPPED_ITEMS[_new_auid_int] = {
                    "parent": _drop_parent,
                    "xyz": tuple(float(v) for v in _xyz),
                    "typeId": int(removed_item[2]),
                    "body": bytes(_drop_body),
                    "rotation": tuple(float(v) for v in _av_rot),
                    "time_created_ms": _drop_now_ms,
                }
                try:
                    _queue = get_queue()
                    _ok_sql = _queue is not None and _queue.submit(
                        "dropped_item_insert",
                        auid=_new_auid_int,
                        parent_auid=int.from_bytes(
                            _drop_parent, "big"),
                        xyz=_xyz,
                        rotation=_av_rot,
                        type_id=int(removed_item[2]),
                        body=bytes(_drop_body),
                        time_created_ms=_drop_now_ms,
                    )
                    if _ok_sql:
                        logger.debug(f"[chat]   SQL: persisted "
                                     f"a_Item id=0x{_new_auid_int:08x}")
                except Exception as _sqe:               # noqa: BLE001
                    logger.warning(f"[chat]   SQL persist "
                                   f"failed: {_sqe!r}")
                try:
                    _builder = getattr(
                        _actor_writer,
                        "_scene_manifest_builder", None)
                    if _builder:
                        _manifest_pkt = _builder()
                        await write_framed(
                            _actor_writer,
                            _manifest_pkt)
                        logger.debug(f"[chat]   -> scene 0x18 "
                                     f"manifest re-emit "
                                     f"({len(_manifest_pkt)}B, "
                                     f"includes new auid="
                                     f"0x{_new_auid_int:08x})")
                except Exception as _me:                # noqa: BLE001
                    logger.warning(f"[chat]   manifest re-emit "
                                   f"failed: {_me!r}")
                await write_framed(
                    _actor_writer, _drop_pkt)
                for _peer_auid, _peer_entry in list(
                        _live_avatars.items()):
                    if _peer_auid == _actor_auid_int:
                        continue
                    _pw = _peer_entry.get("writer")
                    if _pw is None or _pw.is_closing():
                        continue
                    try:
                        _pb = getattr(
                            _pw,
                            "_scene_manifest_builder",
                            None)
                        if _pb:
                            _pm = _pb()
                            await write_framed(_pw, _pm)
                        await write_framed(_pw, _drop_pkt)
                        logger.debug("[chat]   -> peer "
                                     "auid=0x%08x: drop "
                                     "broadcast (manifest+"
                                     "0x11 %dB)" % (
                                         _peer_auid,
                                         len(_drop_pkt)))
                    except Exception as _pe:            # noqa: BLE001
                        logger.warning("[chat]   peer drop "
                                       "push err auid=0x%08x: "
                                       "%r" % (_peer_auid, _pe))
                asyncio.create_task(
                    _daitem_lifecycle(_new_auid_int))
                logger.info(f"[chat]   -> scene 0x11 DaItem "
                            f"spawn auid=0x{_new_auid_int:08x} "
                            f"parent={_drop_parent.hex()} "
                            f"xyz=({_xyz[0]:.2f}, {_xyz[1]:.2f}, "
                            f"{_xyz[2]:.2f}) "
                            f"rot=({_av_rot[0]:.2f}, "
                            f"{_av_rot[1]:.2f}, {_av_rot[2]:.2f}) "
                            f"typeId="
                            f"0x{int(removed_item[2]):02X} "
                            f"len={len(_drop_pkt)}B "
                            f"keepalive=ON")
            except Exception as _de:                    # noqa: BLE001
                logger.warning(f"[chat]   DaItem world-spawn "
                               f"failed: {_de!r}")
    elif op == 0x60:
        flag = s.read_u8()
        if src_path:
            parent_entry = next(
                (e for e in _actor_augear
                 if int(e[0]) == int(src_slot)
                 and int(e[1]) == int(src_sub)),
                None)
            if parent_entry is None:
                action = (
                    "MoveGearItemFromContainer "
                    f"src=(slot={src_slot}, "
                    f"sub={src_sub}, path={src_path}) "
                    "[no parent]")
                if flag == 1:
                    try: s.read_u8()
                    except Exception: pass              # noqa: BLE001
                else:
                    try: s.read_u8(); s.read_u8()
                    except Exception: pass              # noqa: BLE001
            elif int(parent_entry[2]) not in (0x0B, 0x12):
                action = (
                    "MoveGearItemFromContainer "
                    f"src=(slot={src_slot}, "
                    f"sub={src_sub}, path={src_path}) "
                    f"[parent typeId="
                    f"0x{int(parent_entry[2]):02X} not "
                    "a container]")
                if flag == 1:
                    try: s.read_u8()
                    except Exception: pass              # noqa: BLE001
                else:
                    try: s.read_u8(); s.read_u8()
                    except Exception: pass              # noqa: BLE001
            else:
                key = int(src_path[0]) & 0xFF
                try:
                    pop_result = _container_pop_nested(
                        bytes(parent_entry[3]), key)
                except Exception as _pe:                # noqa: BLE001
                    pop_result = None
                    logger.warning("[chat]   container pop "
                                   "err: %r" % (_pe,))
                if pop_result is None:
                    action = (
                        "MoveGearItemFromContainer "
                        f"src=(slot={src_slot}, "
                        f"sub={src_sub}, path="
                        f"{src_path}) "
                        f"[key {key} not in container]")
                    if flag == 1:
                        try: s.read_u8()
                        except Exception: pass          # noqa: BLE001
                    else:
                        try: s.read_u8(); s.read_u8()
                        except Exception: pass          # noqa: BLE001
                else:
                    popped_tid, popped_body, new_parent_body = pop_result
                    parent_entry[3] = new_parent_body
                    if flag == 1:
                        dst_slot = s.read_u8()
                        new_sub = _next_sub_index(
                            _actor_augear, int(dst_slot))
                        if new_sub is None:
                            re_added = (
                                _container_add_nested(
                                    new_parent_body,
                                    (0, 0, popped_tid,
                                     popped_body)))
                            if re_added is not None:
                                parent_entry[3] = re_added
                            action = (
                                "MoveGearItemFromContainer "
                                f"flag=1 dst_slot="
                                f"{dst_slot} [REJECT: "
                                f"slot {dst_slot} full]")
                        else:
                            _actor_augear.append(
                                [int(dst_slot) & 0xFF,
                                 new_sub & 0x0F,
                                 popped_tid,
                                 popped_body])
                            ok = True
                            action = (
                                "MoveGearItemFromContainer "
                                f"flag=1 dst_slot="
                                f"{dst_slot} sub="
                                f"{new_sub} "
                                f"(popped key={key} "
                                f"typeId=0x"
                                f"{popped_tid:02X})")
                    else:
                        dst_slot = s.read_u8()
                        dst_sub  = s.read_u8()
                        collision = next(
                            (e for e in _actor_augear
                             if int(e[0]) == int(dst_slot)
                             and int(e[1]) == int(dst_sub)),
                            None)
                        if collision is not None:
                            re_added = (
                                _container_add_nested(
                                    new_parent_body,
                                    (0, 0, popped_tid,
                                     popped_body)))
                            if re_added is not None:
                                parent_entry[3] = re_added
                            action = (
                                "MoveGearItemFromContainer "
                                f"flag=0 dst=(slot="
                                f"{dst_slot}, sub="
                                f"{dst_sub}) [REJECT: "
                                f"position occupied]")
                        else:
                            _actor_augear.append(
                                [int(dst_slot) & 0xFF,
                                 int(dst_sub) & 0x0F,
                                 popped_tid,
                                 popped_body])
                            ok = True
                            action = (
                                "MoveGearItemFromContainer "
                                f"flag=0 dst=(slot="
                                f"{dst_slot}, sub="
                                f"{dst_sub}) "
                                f"(popped key={key} "
                                f"typeId=0x"
                                f"{popped_tid:02X})")
        elif flag == 1:
            dst_slot = s.read_u8()
            action = ("MoveGearItemToSlot "
                      f"flag=1 dst_slot={dst_slot}")
            src_entry = next(
                (e for e in _actor_augear
                 if int(e[0]) == int(src_slot)
                 and int(e[1]) == int(src_sub)),
                None)
            if src_entry is None:
                ok = False
                extra = (" [no matching src entry; "
                         f"slots={[e[0] for e in _actor_augear]}]")
            elif int(dst_slot) not in SLOT_CAPS:
                ok = False
                extra = (" [REJECT: dst_slot=%d out of "
                         "valid range 1..9]" % int(dst_slot))
            elif int(dst_slot) == int(src_slot):
                ok = False
                extra = " [REJECT: dst == src no-op]"
            else:
                _ok_type, _why = _can_hold_item(
                    int(dst_slot),
                    int(src_entry[2]), bytes(src_entry[3]))
                if not _ok_type:
                    ok = False
                    extra = " [REJECT: %s]" % _why
                elif (_slot_count(_actor_augear, int(dst_slot))
                      >= SLOT_CAPS[int(dst_slot)]):
                    ok = False
                    extra = (" [REJECT: dst slot %d (%s) "
                             "already full, cap=%d]" % (
                                 int(dst_slot),
                                 SLOT_NAMES[int(dst_slot)],
                                 SLOT_CAPS[int(dst_slot)]))
                else:
                    ok = _augear_apply_move(
                        _actor_augear, src_slot, src_sub,
                        int(dst_slot))
                    if not ok:
                        extra = " [apply_move returned False]"
                    else:
                        _moved = next(
                            (e for e in _actor_augear
                             if int(e[0]) == int(dst_slot)
                             and int(e[1]) == int(src_sub)),
                            None)
                        if _moved is not None:
                            _moved_cid = (
                                _read_auitem_cid_from_body(
                                    bytes(_moved[3])))
                            if (int(_moved[2]) == 0x01
                                    and _moved_cid in
                                        CONTAINER_CIDS):
                                _new_tid, _new_body = (
                                    _upgrade_to_container(
                                        _moved[2],
                                        _moved[3],
                                        CONTAINER_CAPACITIES=(
                                            CONTAINER_CAPACITIES)))
                                _moved[2] = _new_tid
                                _moved[3] = _new_body
                                logger.info(
                                    "[chat]   0x60 "
                                    "promoted "
                                    "cid=0x%04X to "
                                    "AuItemBox"
                                    " (typeId 0x12) "
                                    "on equip"
                                    % _moved_cid)
                            elif (int(_moved[2]) == 0x01
                                    and _moved_cid in
                                    USE_TOGGLEABLE_CIDS):
                                _new_tid, _new_body = (
                                    _upgrade_to_auitemstate(
                                        _moved[2],
                                        _moved[3],
                                        switched_on=1))
                                _moved[2] = _new_tid
                                _moved[3] = _new_body
                                logger.info(
                                    "[chat]   0x60 "
                                    "promoted "
                                    "cid=0x%04X to "
                                    "AuItemState "
                                    "(typeId 0x06, "
                                    "switched_on=1) "
                                    "for "
                                    "head-replacement"
                                    " / light-toggle"
                                    % _moved_cid)
        else:
            dst_slot = s.read_u8()
            dst_sub  = s.read_u8()
            _dst_entry = next(
                (e for e in _actor_augear
                 if int(e[0]) == int(dst_slot)
                 and int(e[1]) == int(dst_sub)),
                None)
            _dst_typeId = (int(_dst_entry[2])
                           if _dst_entry else 0)
            _dst_cid = (
                _read_auitem_cid_from_body(
                    bytes(_dst_entry[3]))
                if _dst_entry else 0)
            ok = False
            if (_dst_entry is not None
                    and _dst_typeId == 0x01
                    and _is_container_cid(
                        _dst_cid, CONTAINER_CIDS=CONTAINER_CIDS)):
                _new_tid, _new_body = (
                    _upgrade_to_container(
                        _dst_typeId,
                        _dst_entry[3],
                        CONTAINER_CAPACITIES=CONTAINER_CAPACITIES))
                _dst_entry[2] = _new_tid
                _dst_entry[3] = _new_body
                _dst_typeId   = _new_tid
                logger.info("[chat]   0x60 promoted "
                            "cid=0x%04X to AuItemBox "
                            "(typeId 0x12) on first drag"
                            % _dst_cid)
            if _dst_typeId in (0x0B, 0x12):
                _src_entry_p = next(
                    (e for e in _actor_augear
                     if int(e[0]) == int(src_slot)
                     and int(e[1]) == int(src_sub)),
                    None)
                if _src_entry_p is None:
                    action = (
                        "MoveGearItemToItem "
                        f"flag=0 dst=(slot={dst_slot}"
                        f", sub={dst_sub}) "
                        "[no source entry]")
                else:
                    try:
                        _new_dst_body = (
                            _container_add_nested(
                                bytes(_dst_entry[3]),
                                _src_entry_p))
                    except Exception as _ce:            # noqa: BLE001
                        logger.warning("[chat]   0x60 "
                                       "container nest err: "
                                       "%r" % (_ce,))
                        _new_dst_body = None
                    if _new_dst_body is None:
                        action = (
                            "MoveGearItemToItem "
                            f"flag=0 dst=(slot="
                            f"{dst_slot}, sub="
                            f"{dst_sub}) [REJECT: "
                            "container full or "
                            "malformed]")
                    else:
                        _augear_pop(
                            _actor_augear,
                            int(src_slot),
                            int(src_sub))
                        _dst_entry[3] = _new_dst_body
                        ok = True
                        action = (
                            "MoveGearItemToItem "
                            f"flag=0 dst=(slot="
                            f"{dst_slot}, sub="
                            f"{dst_sub}) NESTED "
                            f"(dst.cid=0x{_dst_cid:04X})")
            else:
                action = (
                    "MoveGearItemToItem "
                    f"flag=0 dst=(slot={dst_slot}"
                    f", sub={dst_sub}) "
                    "[REJECT: dst is not a "
                    "container (cid=0x"
                    f"{_dst_cid:04X}, typeId="
                    f"0x{_dst_typeId:02X}); add "
                    "cid to "
                    "HZ_CONTAINER_CIDS_EXTRA if "
                    "this should be a container]")
    elif op == 0x69:
        _src_entry = next(
            (e for e in _actor_augear
             if int(e[0]) == int(src_slot)
             and int(e[1]) == int(src_sub)),
            None)
        if _src_entry is None:
            action = "UseGearItem [no matching entry]"
            extra = (" slots="
                     f"{[e[0] for e in _actor_augear]}")
        else:
            _src_typeId = int(_src_entry[2])
            _src_body   = bytes(_src_entry[3])
            _src_cid    = _read_auitem_cid_from_body(
                _src_body)
            _src_quality = 0x3D
            if _is_food_cid(_src_cid, USE_FOOD_CIDS=USE_FOOD_CIDS):
                _player_auid_int = _actor_auid_int
                _ts = _tock_state.setdefault(
                    _player_auid_int,
                    {"pose": 0x24,
                     "last_minute": -1,
                     "last_hour": -1})
                _live_max_hp = _ts.get("max_hp")
                if _live_max_hp:
                    _max_hp = int(_live_max_hp)
                else:
                    _max_hp = max(1, int(_SAVE.person_hit_points) or 46)
                _max_hunger = int(
                    _ts.get("max_hunger") or (_max_hp * 2))
                _food_pts = _food_value(
                    _src_cid, _src_quality, USE_FOOD_CIDS=USE_FOOD_CIDS)
                _h_old = int(_ts.get("hunger", 0))
                _h_new = min(_max_hunger,
                             _h_old + _food_pts)
                _ts["hunger"] = _h_new
                _stamina_max = int(
                    _ts.get("max_stamina") or 0x7F)
                _s_old = int(_ts.get(
                    "stamina", _stamina_max))
                if _src_cid in USE_STAMINA_RESET_CIDS:
                    _s_new = _stamina_max
                else:
                    _s_new = _s_old
                _ts["stamina"] = _s_new
                _food_name = USE_FOOD_CIDS.get(
                    _src_cid, ("?", 0))[0]
                _verb = ("drank"
                         if _src_cid in USE_DRINK_CIDS
                         else "ate")
                action = (f"UseGearItem ({_verb} "
                          f"{_food_name})")
                extra = (f" cid=0x{_src_cid:04X} "
                         f"food_pts={_food_pts} "
                         f"hunger {_h_old}->{_h_new} "
                         f"stamina {_s_old}->{_s_new}")
                removed_item = _augear_pop(
                    _actor_augear,
                    int(src_slot), int(src_sub))
                try:
                    _queue = get_queue()
                    if _queue is not None:
                        _queue.submit(
                            "update_person_state",
                            _player_auid_int,
                            hunger=_h_new,
                            stamina=_s_new)
                except Exception as _eat_sql_exc:       # noqa: BLE001
                    logger.warning(f"[chat]   Eat SQL flush "
                                   f"failed (non-fatal): "
                                   f"{_eat_sql_exc!r}")
                try:
                    _eat_pose = int(_ts.get("pose", 0x24))
                    _eat_hp = int(_ts.get("hp", 46))
                    if (_actor_writer is not None
                            and not _actor_writer.is_closing()):
                        await _push_creature_state(
                            _actor_writer,
                            _player_auid_int,
                            hp=_eat_hp,
                            pose=_eat_pose,
                            hunger=_h_new,
                            stamina=_s_new,
                            tock_state=_tock_state,
                            agent_bits_for=agent_bits_for)
                        logger.debug(f"[chat]   eat IMMEDIATE "
                                     f"DaPerson push: "
                                     f"auid=0x{_player_auid_int:08x} "
                                     f"hp={_eat_hp} pose=0x{_eat_pose:02x} "
                                     f"hunger={_h_new} stamina={_s_new}")
                except Exception as _eat_push_exc:      # noqa: BLE001
                    logger.warning(f"[chat]   eat immediate "
                                   f"hunger push failed "
                                   f"(non-fatal): "
                                   f"{_eat_push_exc!r}")
            elif (_src_typeId == 0x06
                  or _src_cid in USE_TOGGLEABLE_CIDS):
                if _src_typeId != 0x06:
                    _new_tid, _new_body0 = (
                        _upgrade_to_auitemstate(
                            _src_typeId,
                            _src_body,
                            switched_on=0))
                    _src_entry[2] = _new_tid
                    _src_entry[3] = _new_body0
                    _src_typeId   = _new_tid
                    _src_body     = _new_body0
                    logger.info(
                        "[chat]   0x69 promoted "
                        "cid=0x%04X to AuItemState "
                        "on first Use (was "
                        "typeId 0x01)" % _src_cid)
                _new_body, _new_st, _old_st = (
                    _flip_auitemstate_switched_on(
                        _src_body))
                _src_entry[3] = _new_body
                _name_hint = USE_TOGGLEABLE_CIDS.get(
                    _src_cid,
                    f"item 0x{_src_cid:04X}")
                action = (f"UseGearItem (toggle "
                          f"{_name_hint})")
                extra = (
                    f" cid=0x{_src_cid:04X} "
                    f"switched_on {_old_st}->{_new_st}"
                )
            else:
                action = "UseGearItem [no-op]"
                extra = (
                    f" cid=0x{_src_cid:04X} "
                    f"typeId=0x{_src_typeId:02X} "
                    "(unrecognised; no engine effect)"
                )
    elif op == 0x5d:
        text = s.read_qstring()
        action = f"InscribeGearItem text={text!r}"
        _insc_entry = next(
            (e for e in _actor_augear
             if int(e[0]) == int(src_slot)
             and int(e[1]) == int(src_sub)),
            None)
        if _insc_entry is None:
            logger.warning(f"[chat]   0x5d no gear entry at "
                           f"slot={src_slot} sub={src_sub}")
        else:
            _insc_before = bytes(_insc_entry[3])
            _insc_entry[3] = _reinscribe_body(
                _insc_before, text)
            logger.info(f"[chat]   0x5d inscribed cid="
                        f"{_read_auitem_cid_from_body(_insc_before)}"
                        f" at slot={src_slot} sub={src_sub}: "
                        f"{len(_insc_before)}B -> "
                        f"{len(_insc_entry[3])}B")
    elif op == 0x5f:
        text = s.read_qstring()
        action = f"SetMessage text={text!r}"
        _msg_entry = next(
            (e for e in _actor_augear
             if int(e[0]) == int(src_slot)
             and int(e[1]) == int(src_sub)),
            None)
        if _msg_entry is None:
            logger.warning(f"[chat]   0x5f no gear entry at "
                           f"slot={src_slot} sub={src_sub}")
        elif int(_msg_entry[2]) != 0x11:
            logger.warning(f"[chat] 0x5f item at slot={src_slot} sub={src_sub} is typeId 0x{int(_msg_entry[2]):02x}, not 0x11 AuItemStateMessage. SetMessage is a no-op on the base class, ignoring")
        else:
            _msg_entry[3] = _set_item_message(
                bytes(_msg_entry[3]), text)
            logger.info(f"[chat]   0x5f message set on 0x11 item "
                        f"at slot={src_slot} sub={src_sub}")
    elif op == 0x66:
        seed = s.read_u8()
        action = f"SetFlowerPot seed=0x{seed:02X}"
    elif op == 0x67:
        url   = s.read_qstring()
        b1    = s.read_u8()
        b2    = s.read_u8()
        action = (f"SetPictureFrame url={url!r} "
                  f"hidden={b1} rotate={b2}")
        _pic_entry = next(
            (e for e in _actor_augear
             if int(e[0]) == int(src_slot)
             and int(e[1]) == int(src_sub)),
            None)
        if _pic_entry is None:
            logger.warning(f"[chat]   0x67 no gear entry at "
                           f"slot={src_slot} sub={src_sub}")
        elif int(_pic_entry[2]) != 0x10:
            logger.warning(f"[chat] 0x67 item at slot={src_slot} sub={src_sub} is typeId 0x{int(_pic_entry[2]):02x}, not 0x10 AuItemPicture. The engine's dynamic_cast fails here too, ignoring")
        else:
            _pic_entry[3] = _set_item_picture(
                bytes(_pic_entry[3]), url,
                url_hidden=bool(b1), rotate=bool(b2))
            logger.info(f"[chat]   0x67 picture set on 0x10 item "
                        f"at slot={src_slot} sub={src_sub} "
                        f"hidden={bool(b1)} rotate={bool(b2)}")

    logger.info(f"[chat]   0x{op:02X} {action} "
                f"src=(slot={src_slot}, sub={src_sub})"
                f"{extra}")
    if removed_item is not None:
        logger.info(f"[chat]     popped entry: slot="
                    f"{removed_item[0]} sub={removed_item[1]} "
                    f"typeId=0x{removed_item[2]:02X}")

    if (not _actor_auid_bytes
            or _actor_writer is None
            or _actor_writer.is_closing()):
        logger.warning("[chat]   skip reply: actor_auid=0x%08x "
                       "writer=%r" % (
                           _actor_auid_int, _actor_writer))
    else:
        new_aug = _pack_au_gear([
            (e[0], e[1], e[2], e[3])
            for e in _actor_augear
        ])
        reply = _build_augear_only_daperson_update(
            _actor_auid_bytes, new_aug)
        try:
            await write_framed(_actor_writer, reply)
            logger.info("[chat]   -> scene 0x12 "
                        "DaPerson(AuGear delta) "
                        "len=%dB slots=%r actor=0x%08x" % (
                            len(reply),
                            [e[0] for e in _actor_augear],
                            _actor_auid_int))
            if _actor_auid_int:
                try:
                    _queue = get_queue()
                    if _queue is not None:
                        _queue.submit(
                            "update_person_state",
                            _actor_auid_int,
                            inv=bytes(new_aug))
                        logger.debug("[chat]   SQL inv persisted "
                                     "len=%d for auid=0x%08x" % (
                                         len(new_aug),
                                         _actor_auid_int))
                except Exception as _spx:               # noqa: BLE001
                    logger.warning("[chat]   SQL inv persist "
                                   "failed: %r" % (_spx,))
        except Exception as _se:                        # noqa: BLE001
            logger.warning("[chat]   scene-writer push "
                           "failed: %r" % (_se,))
