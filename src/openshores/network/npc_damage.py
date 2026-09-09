
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.gameplay import damageable as _dmg
from openshores.gameplay.combat.damage import (
    _combat_total_damage,
    _describe_weapon,
    _log_combat_hit,
    _register_damageable_npcs,
)
from openshores.gameplay.combat.resolve import _resolve_combat_hit
from openshores.gameplay.condition_registry import _CONDITION_STATES
from openshores.gameplay.condition_states import _apply_weapon_conditions
from openshores.gameplay.dpbody_maxes import minutes_to_full_grown as _mtfg
from openshores.network.corpse import _on_npc_killed
from openshores.network.npc_state import _push_npc_state
from openshores.protocol.atoms.weapon import (
    _weapon_damage_for_cid_mode as _hz_weapon_damage_for_cid_mode,
)

logger = get_logger(__name__)


_DMG_UPGRADE_TRIED: set = set()


async def _damage_npc_target(conn, target_auid, attacker_auid, weapon_cid,
                             mode, in_range, weapon_range_m, weapon=None, *,
                             idle_bodies,
                             story_npcs,
                             story_atom_id,
                             story_name,
                             _live_avatars,
                             tock_state,
                             _CITIZEN_EMPIRE_OVERRIDE,
                             alloc_daitem_auid,
                             _DROPPED_ITEMS,
                             _DYNAMIC_SCENE_AUIDS,
                             spawned_buildings) -> bool:
    d = _dmg.get(target_auid)
    if d is None:
        if _dmg.is_damageable_candidate(target_auid, idle_bodies=idle_bodies,
                                        story_atom_id=story_atom_id,
                                        story_npcs=story_npcs):
            _register_damageable_npcs(idle_bodies=idle_bodies,
                                      story_npcs=story_npcs,
                                      story_atom_id=story_atom_id,
                                      story_name=story_name)
            d = _dmg.get(target_auid)
    elif not d.dna and int(target_auid) not in _DMG_UPGRADE_TRIED:
        _DMG_UPGRADE_TRIED.add(int(target_auid))
        if _dmg.is_damageable_candidate(target_auid, idle_bodies=idle_bodies,
                                        story_atom_id=story_atom_id,
                                        story_npcs=story_npcs):
            _register_damageable_npcs(idle_bodies=idle_bodies,
                                      story_npcs=story_npcs,
                                      story_atom_id=story_atom_id,
                                      story_name=story_name)
            d = _dmg.get(target_auid) or d
            if d.dna:
                logger.info(f"[damageable] 0x{int(target_auid):08x} ({d.name}) "
                            f"upgraded off its DNA: {d.hp}/{d.max_hp}")
    if d is None:
        return False
    if not in_range:
        logger.debug(f"[fire] npc 0x{target_auid:08x} ({d.name}) out OF range (max {weapon_range_m:.2f}m). Swing only")
        return True
    if not d.alive:
        logger.debug(f"[fire]   npc 0x{target_auid:08x} ({d.name}) is already dead")
        return True

    _combat = _resolve_combat_hit(weapon_cid, 0x09, mode, target_gear=None,
                                  weapon=weapon)
    if _combat is not None:
        _cweapon, _cres, _cworn = _combat
        dmg = _combat_total_damage(_cres)
        _log_combat_hit(f"0x{attacker_auid:08x} -> npc 0x{target_auid:08x} "
                        f"({_describe_weapon(_cweapon)})", _cres, _cworn)
    elif weapon is not None:
        _cweapon, _cres = weapon, None
        _lo, _hi = weapon.damage_range(1)
        dmg = max(1, (_lo + _hi) // 2)
    else:
        _cweapon = _cres = None
        dmg = _hz_weapon_damage_for_cid_mode(weapon_cid, 0x09, mode)
    if dmg <= 0:
        return True
    growth = None
    if d.dna:
        try:
            growth = _mtfg(d.dna)
        except Exception as exc:
            logger.debug("[fire]   growth time off 0x%08x's DNA refused (%r).", int(target_auid), exc)
            growth = None
    res = _dmg.damage(target_auid, dmg, attacker=attacker_auid,
                      growth_time=growth)
    if res is None:
        return False
    hp, died, _was_dead = res
    logger.debug(f"[fire]   npc damage: attacker=0x{attacker_auid:08x} "
                 f"victim=0x{target_auid:08x} ({d.kind} {d.name!r}) "
                 f"-{dmg} hp -> {hp}/{d.max_hp}")
    try:
        _apply_weapon_conditions(target_auid, weapon_cid, mode, dmg,
                                 attacker=attacker_auid, result=_cres,
                                 weapon=_cweapon,
                                 condition_states=_CONDITION_STATES)
    except Exception as exc:
        logger.error(f"[condition] npc weapon effect failed: {exc!r}")
    try:
        asyncio.create_task(_push_npc_state(d, _live_avatars=_live_avatars))
    except Exception as exc:
        logger.error(f"[npc-state] could not schedule the update: {exc!r}")
    if died:
        await _on_npc_killed(
            conn, d, attacker_auid, tock_state=tock_state,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            _live_avatars=_live_avatars,
            alloc_daitem_auid=alloc_daitem_auid,
            _DROPPED_ITEMS=_DROPPED_ITEMS,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
            story_npcs=story_npcs, idle_bodies=idle_bodies,
            spawned_buildings=spawned_buildings)
    return True
