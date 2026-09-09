
from __future__ import annotations

import struct as _struct
import time as _time_active_item

from openshores.core.logging import get_logger
from openshores.gameplay.avatar_dna import _dna_for_actor
from openshores.gameplay.bio_bytes import (
    _DEFAULT_ACTIVE_CYCLE,
    _mins_to_full_grown_for_actor,
    _stamina_byte,
)
from openshores.gameplay.body_weapons import _body_weapons_from_dna
from openshores.protocol.atoms.gear import _unpack_au_gear
from openshores.protocol.framing import encode_size

logger = get_logger(__name__)


pb2_last_cursor = {}


async def _dynamic_cycle_from_inventory(conn, actor_auid: int = 0, *,
                                        _live_avatars: dict,
                                        _AUGEAR_STATES: dict,
                                        agent_bits_for,
                                        resolve_avatar_record,
                                        last_avatar_dna: bytes):
    visible_slots = {1, 4, 7, 8, 9}
    cycle = []
    seen = set()
    if int(actor_auid) != 0:
        _iter_auids = [int(actor_auid) & 0xFFFFFFFF]
    else:
        _iter_auids = list(_live_avatars.keys())
    for auid in _iter_auids:
        entries = None
        try:
            live_state = _AUGEAR_STATES.get(int(auid) & 0xFFFFFFFF)
            if live_state:
                entries = list(live_state)
        except Exception as _lse:
            logger.debug(f'[active-item] live AuGear for auid=0x{auid:08x} unreadable ({_lse!r}).')
        if not entries:
            pb2 = _live_avatars.get(auid, {}).get('pb2')
            if not pb2:
                continue
            last = pb2_last_cursor.get(id(pb2)) or (9, 0, 0)
            ab_default = agent_bits_for(actor_auid)
            marker_a = bytes([ab_default, last[0], last[1], last[2]])
            marker_b = bytes([ab_default | 0x80, last[0], last[1],
                              last[2]])
            idx = pb2.find(marker_a)
            if idx < 0:
                idx = pb2.find(marker_b)
            if idx < 0:
                continue
            try:
                entries = _unpack_au_gear(pb2[idx+4:])
            except Exception as _e:
                logger.warning(f'[active-item] dynamic cycle parse failed for '
                               f'auid=0x{auid:08x}: {_e!r}')
                continue
        for e in entries:
            slottype = int(e[0]) & 0xFF
            sub = int(e[1]) & 0x0F
            typeId = int(e[2]) & 0xFF
            if typeId == 0:
                continue
            if slottype not in visible_slots:
                continue
            if typeId in (0x08, 0x09, 0x0C):
                key = (slottype, sub, 0)
                if key not in seen:
                    seen.add(key)
                    cycle.append((slottype, sub, 0))
                if typeId in (0x09, 0x0C):
                    key = (slottype, sub, 1)
                    if key not in seen:
                        seen.add(key)
                        cycle.append((slottype, sub, 1))
            else:
                key = (slottype, sub, 0)
                if key in seen:
                    continue
                seen.add(key)
                cycle.append((slottype, sub, 0))
        break

    body_list = _body_weapons_from_dna(
        await _dna_for_actor(conn, actor_auid,
                             resolve_avatar_record=resolve_avatar_record,
                             last_avatar_dna=last_avatar_dna),
        await _mins_to_full_grown_for_actor(conn, actor_auid))
    for st_signed, st_sub in body_list:
        slot_byte = int(st_signed) & 0xFF
        key = (slot_byte, 0, int(st_sub) & 0xFF)
        if key not in seen:
            seen.add(key)
            cycle.append(key)
    return cycle


async def _active_advance(conn, direction=1, actor_auid: int = 0, *,
                          _live_avatars: dict,
                          _AUGEAR_STATES: dict,
                          _tock_state: dict,
                          actor_cursor: dict,
                          actor_index: dict,
                          actor_cycle: dict,
                          actor_last_adv: dict,
                          agent_bits_for,
                          resolve_avatar_record,
                          last_avatar_dna: bytes):
    _auid_key = int(actor_auid) & 0xFFFFFFFF if int(actor_auid) else 0
    now = _time_active_item.monotonic()
    _last_adv = actor_last_adv.get(_auid_key, 0.0)
    if now - _last_adv < 0.25:
        return
    actor_last_adv[_auid_key] = now
    _dyn = await _dynamic_cycle_from_inventory(
        conn, actor_auid=_auid_key, _live_avatars=_live_avatars,
        _AUGEAR_STATES=_AUGEAR_STATES, agent_bits_for=agent_bits_for,
        resolve_avatar_record=resolve_avatar_record,
        last_avatar_dna=last_avatar_dna)
    if _dyn:
        actor_cycle[_auid_key] = _dyn
    cycle = actor_cycle.get(_auid_key, _DEFAULT_ACTIVE_CYCLE)
    n = len(cycle)
    if n == 0:
        logger.warning(f'[active-item] cycle is empty for actor=0x{_auid_key:08x}.')
        return
    _idx = actor_index.get(_auid_key, 0)
    _idx = (_idx + direction) % n
    actor_index[_auid_key] = _idx
    _slot, _sub, _mode = cycle[_idx]
    actor_cursor[_auid_key] = (_slot, _sub, _mode)
    logger.debug(f'[active-item] cursor -> '
                 f'(slot={_slot}, sub={_sub}, mode={_mode}) '
                 f'idx={_idx}/{n} actor=0x{_auid_key:08x} '
                 f'cycle={cycle}')
    try:
        _splice_cursor_into_cached_pb2(
            actor_auid=int(actor_auid), _live_avatars=_live_avatars,
            actor_cursor=actor_cursor, agent_bits_for=agent_bits_for)
    except Exception as _e:
        logger.warning(f'[active-item] splice error: {_e!r}')
    try:
        _send_active_cursor_update(
            actor_auid=int(actor_auid), _live_avatars=_live_avatars,
            _tock_state=_tock_state, actor_cursor=actor_cursor,
            agent_bits_for=agent_bits_for)
    except Exception as _e:
        logger.warning(f'[active-item] reemit error: {_e!r}')


def _splice_cursor_into_cached_pb2(actor_auid: int = 0, *,
                                   _live_avatars: dict,
                                   actor_cursor: dict,
                                   agent_bits_for):
    _ab_default = agent_bits_for(actor_auid)
    _ab_with_80 = _ab_default | 0x80
    if int(actor_auid) != 0:
        _ak = int(actor_auid) & 0xFFFFFFFF
        _cur = actor_cursor.get(_ak) or (9, 0, 0)
        new_cursor = bytes([
            int(_cur[0]) & 0xFF,
            int(_cur[1]) & 0x0F,
            int(_cur[2]) & 0xFF,
        ])
        _peers_iter = [(_ak, _live_avatars.get(_ak, {}))]
    else:
        _cur = actor_cursor.get(0) or (9, 0, 0)
        new_cursor = bytes([
            int(_cur[0]) & 0xFF,
            int(_cur[1]) & 0x0F,
            int(_cur[2]) & 0xFF,
        ])
        _peers_iter = list(_live_avatars.items())
    for auid, peer in _peers_iter:
        pb2 = peer.get('pb2')
        if not pb2:
            continue
        key = id(pb2)
        last = pb2_last_cursor.get(key)
        if last is None:
            last = (9, 0, 0)
        last_marker_no80 = bytes([_ab_default, last[0], last[1], last[2]])
        last_marker_80   = bytes([_ab_with_80, last[0], last[1], last[2]])
        idx = pb2.find(last_marker_no80)
        if idx < 0:
            idx = pb2.find(last_marker_80)
        if idx < 0:
            logger.warning(f'[active-item] splice: cursor marker not found in '
                           f'pb2 for auid=0x{auid:08x} '
                           f'(last={last}, ab=0x{_ab_default:02x})')
            continue
        new_pb2 = pb2[:idx+1] + new_cursor + pb2[idx+4:]
        if len(new_pb2) != len(pb2):
            logger.warning(f'[active-item] splice: length mismatch '
                           f'old={len(pb2)} new={len(new_pb2)}')
            continue
        peer['pb2'] = new_pb2
        pb2_last_cursor[id(new_pb2)] = (
            new_cursor[0], new_cursor[1], new_cursor[2])
        logger.debug(f'[active-item] splice: pb2 cursor for auid=0x{auid:08x} '
                     f'@offset 0x{idx+1:x}: '
                     f'{last} -> ({new_cursor[0]}, {new_cursor[1]}, '
                     f'{new_cursor[2]})')


def _send_active_cursor_update(actor_auid: int = 0, *,
                               _live_avatars: dict,
                               _tock_state: dict,
                               actor_cursor: dict,
                               agent_bits_for):
    if not _live_avatars:
        return
    if int(actor_auid) != 0:
        _key = int(actor_auid) & 0xFFFFFFFF
        _ent = _live_avatars.get(_key)
        if _ent is None:
            return
        _cur = actor_cursor.get(_key) or (9, 0, 0)
        cursor_payload = bytes([
            int(_cur[0]) & 0xFF,
            int(_cur[1]) & 0x0F,
            int(_cur[2]) & 0xFF,
        ])
        _peers_iter = [(_key, _ent)]
    else:
        _cur = actor_cursor.get(0) or (9, 0, 0)
        cursor_payload = bytes([
            int(_cur[0]) & 0xFF,
            int(_cur[1]) & 0x0F,
            int(_cur[2]) & 0xFF,
        ])
        _peers_iter = list(_live_avatars.items())
    for _peer_auid, _peer in _peers_iter:
        _w = _peer.get('writer')
        _ap = _peer.get('AP')
        _pb2 = _peer.get('pb2')
        _stamina = _stamina_byte(int(_peer_auid), _tock_state=_tock_state)
        if _w is None or _ap is None:
            continue
        try:
            _now_ms = int(_time_active_item.time() * 1000.0)
            body = (
                bytes([0x12])
                + _ap
                + _struct.pack('>q', _now_ms)
                + bytes([0x00])
                + bytes([0x00])
                + bytes([0x00])
                + bytes([_stamina])
                + bytes([0x00])
                + bytes([0x28])
                + bytes([agent_bits_for(int(_peer_auid)) & 0x3F])
                + cursor_payload
                + b'\x00' * 16
            )
            framed = encode_size(len(body)) + body
            _w.write(framed)
            logger.debug(f'[active-item] reemit -> peer auid=0x{_peer_auid:08x} '
                         f'(minimal cursor, {len(framed)}B, stamina=0x{_stamina:02x})')
        except Exception as _ee:
            logger.warning(f'[active-item] reemit to 0x{_peer_auid:08x} '
                           f'failed: {_ee!r}')
