
from __future__ import annotations

import time

from openshores.core.logging import get_logger
from openshores.gameplay import damageable as _dmg
from openshores.gameplay import person_combat as _pc

logger = get_logger(__name__)


def _describe_weapon(weapon) -> str:
    if weapon is None:
        return "no weapon"
    bits = []
    for slot in (1, 2):
        eff = weapon.effect1 if slot == 1 else weapon.effect2
        if not eff:
            continue
        lo, hi = weapon.damage_range(slot)
        if hi <= 0:
            continue
        bits.append(f"{_pc.EFFECT_NAMES.get(eff, eff)} {lo}-{hi}hp")
    if not bits:
        return "no damage"
    return (f"{_pc.MODE_NAMES.get(weapon.mode, weapon.mode)} "
            + " + ".join(bits))


def _combat_total_damage(res) -> int:
    return int(res.damage1) + int(res.damage2)


def _log_combat_hit(tag, res, worn):
    absorbed = int(res.absorbed1) + int(res.absorbed2)
    blocked = int(res.blocked1) + int(res.blocked2)
    bits = [f"dealt {_combat_total_damage(res)}"]
    if absorbed:
        bits.append(f"absorbed {absorbed}")
    if blocked:
        bits.append(f"blocked {blocked}")
    if res.critical:
        bits.append("CRIT")
    if worn:
        bits.append(f"{len(worn)} armour piece(s)")
    logger.debug("%s: %s", tag, ", ".join(bits))


def _register_damageable_npcs(*,
                              idle_bodies,
                              story_npcs,
                              story_atom_id,
                              story_name) -> int:
    n = 0
    for auid, body in (idle_bodies or {}).items():
        _dmg.register(auid, kind=_dmg.KIND_NATIVE,
                      name=body.get("label", ""),
                      dna=body.get("dna"),
                      mins_to_full_grown=body.get("mins_to_full_grown", 0),
                      world_auid=body.get("world_auid", 0),
                      xyz=(body.get("xyz") or body.get("home_xyz")))
        n += 1
    _t_states = list((story_npcs or {}).values())
    if _t_states:
        for _st in _t_states:
            _dmg.register(int(_st.get("auid") or story_atom_id),
                          kind=_dmg.KIND_STORY,
                          name=_st.get("name") or story_name,
                          dna=_st.get("dna"),
                          world_auid=int(_st.get("world") or 0),
                          xyz=_st.get("xyz"))
            n += 1
    else:
        _dmg.register(story_atom_id, kind=_dmg.KIND_STORY,
                      name=story_name)
        n += 1
    if n:
        logger.info("%d NPC(s) registered as hurtable", n)
    return n


def _apply_damage(auid, amount, source: str = "unknown", attacker=None, *,
                  tock_state,
                  agent_bits_for) -> int:
    try:
        _auid = int(auid)
        _amt = int(amount)
    except (TypeError, ValueError):
        return 0
    if _amt == 0:
        return int(tock_state.get(_auid, {}).get("hp", 0))
    entry = tock_state.get(_auid)
    if entry is None:
        logger.debug("0x%08x has no bio state yet; ignoring %d from %s "
                     "(seeding here would ship hunger 0 forever)",
                     _auid, _amt, source)
        return 0
    if attacker is not None and _amt > 0:
        _att = int(attacker) & 0xFFFFFFFF
        if _att and _att != (_auid & 0xFFFFFFFF):
            entry["last_attacker"] = _att
            entry["last_attacker_ms"] = int(time.time() * 1000)
    _AGENT_DAMAGE_IMMUNE = 0x22
    if _amt > 0:
        _bits = agent_bits_for(_auid)
        if _bits & _AGENT_DAMAGE_IMMUNE:
            _cur = int(entry.get("hp", 46))
            logger.debug("0x%08x immune (agent bits 0x%02x & 0x22). Ignored %d from %s (hp stays %d)",
                         _auid, _bits, _amt, source, _cur)
            return _cur
    old_hp = int(entry.get("hp", 46))
    _max_hp_clamp = int(entry.get("max_hp") or 0)
    new_hp = max(-30, old_hp - _amt)
    if _max_hp_clamp > 0:
        new_hp = min(new_hp, _max_hp_clamp)
    entry["hp"] = new_hp
    if _amt > 0:
        logger.debug("0x%08x hp %d->%d (-%d from %s)",
                     _auid, old_hp, new_hp, _amt, source)
    else:
        logger.debug("0x%08x healed, hp %d->%d (+%d from %s)",
                     _auid, old_hp, new_hp, -_amt, source)
    return new_hp
