from __future__ import annotations

import time as _t

from openshores.core.logging import get_logger
from openshores.gameplay import gear_wear as _gw_reload
from openshores.gameplay.body_slots import (
    _ammo_capacity_for_cid,
    _weapon_ammo_cids,
)
from openshores.network.augear_refresh import _push_augear_refresh_for
from openshores.network.trigger_debounce import _LAST_RELOAD_TS
from openshores.protocol.atoms.item import _extract_cid_from_auitem_body

logger = get_logger(__name__)

_RELOAD_DEBOUNCE_SEC = 0.50


async def _handle_reload_weapon_trigger(avatar_auid: int,
                                        writer=None, *,
                                        _AUGEAR_STATES,
                                        actor_cursor,
                                        _live_avatars,
                                        _build_augear_only_daperson_update,
                                        ) -> None:
    now = _t.monotonic()
    last = _LAST_RELOAD_TS.get(avatar_auid, 0.0)
    if now - last < _RELOAD_DEBOUNCE_SEC:
        return
    _LAST_RELOAD_TS[avatar_auid] = now

    state = _AUGEAR_STATES.get(int(avatar_auid) & 0xFFFFFFFF) or []
    if not state:
        logger.debug(f"[reload] auid=0x{avatar_auid:08x} no gear state")
        return
    logger.debug(f"[reload] auid=0x{avatar_auid:08x} gear contents ({len(state)} entries):")
    for idx, entry in enumerate(state):
        if len(entry) < 4:
            logger.debug(f"[reload]   [{idx}] malformed (len={len(entry)})")
            continue
        _eb = bytes(entry[3])
        _ecid = _extract_cid_from_auitem_body(_eb)
        logger.debug(f"[reload]   [{idx}] slot={entry[0]} sub={entry[1]} "
                     f"typeId=0x{int(entry[2])&0xFF:02x} cid={_ecid} "
                     f"bodylen={len(_eb)}")
    _ak = int(avatar_auid) & 0xFFFFFFFF
    _cur = actor_cursor.get(_ak) or (9, 0, 0)
    _cur_slot, _cur_sub = int(_cur[0]) & 0xFF, int(_cur[1]) & 0x0F
    weapon_idx = -1
    for idx, entry in enumerate(state):
        if len(entry) < 4 or int(entry[2]) != 0x09:
            continue
        if (int(entry[0]) & 0xFF) == _cur_slot and (int(entry[1]) & 0x0F) == _cur_sub:
            weapon_idx = idx
            break
    if weapon_idx == -1:
        for idx, entry in enumerate(state):
            if len(entry) >= 4 and int(entry[2]) == 0x09:
                weapon_idx = idx
                logger.info(f'[reload] cursor ({_cur_slot},{_cur_sub}) holds no weapon.')
                break
    if weapon_idx == -1:
        logger.debug(f"[reload] auid=0x{avatar_auid:08x} no AuItemWeaponAmmo equipped")
        return

    weapon_entry = state[weapon_idx]
    body = bytearray(weapon_entry[3])
    if len(body) < 4:
        logger.warning(f"[reload] weapon body too short ({len(body)} bytes)")
        return
    _wcid = _extract_cid_from_auitem_body(bytes(body)) & 0xFFFF

    _cap1, _cap2 = _ammo_capacity_for_cid(_wcid)
    if not _cap1 and not _cap2:
        logger.debug(f'[reload] auid=0x{avatar_auid:08x} weapon cid={_wcid} has no magazine (melee).')
        return

    _ammo1_cid, _ammo2_cid = _weapon_ammo_cids(_wcid)
    _accepted = {c for c in (_ammo1_cid, _ammo2_cid) if c}
    ammo_idx = -1
    for idx, entry in enumerate(state):
        if len(entry) < 4 or int(entry[2]) != 0x07:
            continue
        _mcid = _extract_cid_from_auitem_body(bytes(entry[3])) & 0xFFFF
        if not _accepted:
            ammo_idx = idx
            logger.info(f"[reload] weapon cid={_wcid} has no recorded ammo cid; "
                        f"accepting magazine cid={_mcid} unchecked")
            break
        if _mcid in _accepted:
            ammo_idx = idx
            break
    if ammo_idx == -1:
        logger.info(f"[reload] auid=0x{avatar_auid:08x} no magazine matching cid(s) {sorted(_accepted) or 'any'} for weapon cid={_wcid}. No ammunition loaded.")
        return

    _mag_entry = state[ammo_idx]
    _mag_body = bytes(_mag_entry[3])
    _mag_cid = _extract_cid_from_auitem_body(_mag_body) & 0xFFFF
    try:
        _mag_q = int(_gw_reload.quality(_mag_body)) & 0xFF
    except Exception as _mqe:
        logger.warning(f'[reload] magazine cid={_mag_cid} quality unreadable ({_mqe!r}).')
        _mag_q = 0x3D
    body[-4] = _cap1 & 0xFF
    body[-3] = _mag_q
    body[-2] = _cap2 & 0xFF
    body[-1] = _mag_q
    weapon_entry[3] = bytes(body)
    state.pop(ammo_idx)
    logger.info(f"[reload] auid=0x{avatar_auid:08x} weapon cid={_wcid} "
                f"(slot {weapon_entry[0]} sub {weapon_entry[1]}) loaded "
                f"{_cap1}/{_cap2} rounds Q{_mag_q} from magazine cid={_mag_cid}")
    await _push_augear_refresh_for(
        avatar_auid, log_prefix="reload",
        _live_avatars=_live_avatars,
        _AUGEAR_STATES=_AUGEAR_STATES,
        _build_augear_only_daperson_update=_build_augear_only_daperson_update,
    )
