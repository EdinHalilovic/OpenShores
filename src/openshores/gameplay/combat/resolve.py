
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import person_combat as _pc
from openshores.gameplay.body_slots import (
    _weapon_ammo_cids as _hz_weapon_ammo_cids,
)
from openshores.gameplay.bio_bytes import _mins_to_full_grown_for_actor
from openshores.gameplay.dpbody_maxes import minutes_to_full_grown as _gt

logger = get_logger(__name__)


async def _body_weapon_for_actor(conn, actor_auid, slot, sub, *,
                                 dna_for_actor):
    try:
        dna = await dna_for_actor(conn, actor_auid)
        mtfg = await _mins_to_full_grown_for_actor(conn, actor_auid)
        growth_time = 0
        if mtfg:
            try:
                growth_time = int(_gt(bytes(dna)))
            except Exception as exc:
                logger.debug('[fire]   growth time off this DNA refused (%r).', exc)
                growth_time = 0
        return _pc.body_weapon(int(slot), dna, special=bool(sub),
                               mins_to_full_grown=mtfg,
                               growth_time=growth_time)
    except Exception as exc:
        logger.error(f"[fire]   body weapon build failed for slot {slot}: {exc!r}")
        return None


def _resolve_combat_hit(weapon_cid, type_id, mode, *, quality=0,
                        target_gear=None, dice=None, weapon=None):
    if weapon is None:
        ammo_cid = 0
        try:
            ammo_cid = int(_hz_weapon_ammo_cids(weapon_cid)[0]) & 0xFFFF
        except Exception as exc:
            logger.debug('[combat] no primary ammo cid for %r (%r).', weapon_cid, exc)
            ammo_cid = 0
        try:
            weapon = _pc.weapon_for_cursor(weapon_cid, type_id, mode,
                                           quality=quality, ammo_cid=ammo_cid)
        except Exception as exc:
            logger.error(f"[combat] weapon build failed for cid {weapon_cid}: {exc!r}")
            return None
    if weapon is None:
        return None
    worn = None
    if target_gear:
        try:
            worn = _pc.worn_from_gear(target_gear)
        except Exception as exc:
            logger.error(f"[combat] armour read failed: {exc!r}")
    try:
        res = _pc.target_attacked(worn, weapon, dice=dice)
    except Exception as exc:
        logger.error(f"[combat] staging failed: {exc!r}")
        return None
    return weapon, res, worn
