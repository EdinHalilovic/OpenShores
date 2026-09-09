
from __future__ import annotations

import time

from openshores.core.logging import get_logger
from openshores.gameplay import conditions as _cx
from openshores.gameplay import gd_tables as _gd

logger = get_logger(__name__)


def _get_conditions(auid, *,
                    condition_states):
    return condition_states.setdefault(int(auid) & 0xFFFFFFFF, [])


def _add_condition(auid, ctype, severity=0, quality=0, strain=0,
                   source=0, dna=None, *,
                   condition_states) -> bool:
    conds = _get_conditions(auid, condition_states=condition_states)
    cond = _cx.Condition(ctype, severity=severity, quality=quality,
                         strain=strain, source=source, dna=dna)
    if not _cx.add_condition(conds, cond):
        return False
    logger.debug("0x%08x gained %s sev=%s q=%s",
                 int(auid) & 0xFFFFFFFF, cond.name, cond.severity,
                 cond.quality)
    return True


def _tick_conditions(auid, *,
                     condition_states,
                     tock_state) -> int:
    key = int(auid) & 0xFFFFFFFF
    conds = condition_states.get(key)
    if not conds:
        return 0
    entry = tock_state.setdefault(key, {})
    if not _cx.should_tick(entry.get("cond_tick_ms")):
        return 0
    entry["cond_tick_ms"] = int(time.time() * 1000)
    hp_delta, expired = _cx.tick(conds)
    for c in expired:
        logger.debug("0x%08x %s ran its course", key, c.name)
    return hp_delta


def _apply_weapon_conditions(victim_auid, weapon_cid, mode, damage,
                             attacker=0, dice=None, result=None,
                             weapon=None, *,
                             condition_states) -> int:
    if not damage:
        return 0
    conds = _get_conditions(victim_auid, condition_states=condition_states)
    quality = 0
    if result is not None and weapon is not None:
        eff1, eff2 = int(weapon.effect1), int(weapon.effect2)
        d1, d2 = int(result.damage1), int(result.damage2)
        quality = int(getattr(weapon, "quality", 0)) & 0xFF
        new = _cx.conditions_from_hit(
            eff1, d1, eff2, d2, quality,
            existing=conds, attacker=attacker, dice=dice)
        added = 0
        for c in new:
            if _cx.add_condition(conds, c):
                added += 1
                logger.debug("0x%08x gained %s sev=%s from cid %s "
                             "(effects %s/%s, slot damage %s/%s)",
                             int(victim_auid) & 0xFFFFFFFF, c.name,
                             c.severity, weapon_cid, eff1, eff2, d1, d2)
        return added
    try:
        row = _gd.load_commodities().get(int(weapon_cid) & 0xFFFF)
    except Exception:
        row = None
    if row is None:
        return 0
    _mode, eff1, _d1, eff2, _d2 = row.weapon_block(2 if int(mode) == 2 else 1)
    new = _cx.conditions_from_hit(
        eff1, damage, eff2, damage, quality,
        existing=conds, attacker=attacker, dice=dice)
    added = 0
    for c in new:
        if _cx.add_condition(conds, c):
            added += 1
            logger.debug("0x%08x gained %s sev=%s from cid %s "
                         "(effects %s/%s)",
                         int(victim_auid) & 0xFFFFFFFF, c.name, c.severity,
                         weapon_cid, eff1, eff2)
    return added


def _conditions_ailment_provider(player_auid, *,
                                 condition_states,
                                 ailment_poison,
                                 ailment_disease,
                                 ailment_paralysis,
                                 ailment_acid):
    mapping = {
        _cx.CON_POISON: ailment_poison,
        _cx.CON_DISEASE: ailment_disease,
        _cx.CON_PARALYSIS: ailment_paralysis,
        _cx.CON_ACID: ailment_acid,
    }
    out = []
    for c in condition_states.get(int(player_auid) & 0xFFFFFFFF, ()):
        kind = mapping.get(c.type)
        if kind is None:
            continue
        out.append((kind, c.severity >= 50, c.name))
    return out
