
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.gameplay import damageable as _dmg
from openshores.gameplay import fauna_ai as _ai
from openshores.gameplay.bio_bytes import _DhDNA_from_bytes
from openshores.gameplay.combat.damage import _apply_damage
from openshores.gameplay.fauna_placement import _fauna_align
from openshores.gameplay.fauna_world import (
    _FAUNA_NEXT_IND,
    _FAUNA_WORLD_STATE,
    _fauna_ground,
)
from openshores.gameplay.worldgen.planet_fauna_gen import (
    _density_cap,
    roll_individuals as _roll_ind,
)
from openshores.network.broadcast import _broadcast_to_peers
from openshores.protocol.atoms.daanimal import (
    pack_animal_spawn as _pack_animal_spawn,
    pack_animal_update as _pack_upd,
)
from openshores.protocol.dhdna import AuDice as _DnaDice
from openshores.protocol.rng import AuDice as _AiDice

logger = get_logger(__name__)


async def _fauna_ai_tick(conn, writer, period_s: float, *,
                         _live_avatars,
                         _tock_state,
                         _DROPPED_ITEMS,
                         agent_bits_for) -> None:
    import time as _t

    _wander_dice = _AiDice(seed=0xFA0A)

    while True:
        await asyncio.sleep(period_s)
        try:
            animals = [d for d in _dmg.all_damageable()
                       if d.kind == _dmg.KIND_ANIMAL and d.alive and d.xyz]
        except Exception as exc:
            logger.error(f"[fauna-ai] registry read failed: {exc!r}")
            continue
        if not animals:
            continue
        now_s = _t.time()

        people_by_world = {}
        for _pauid, _pent in list(_live_avatars.items()):
            _ts = _tock_state.get(_pauid) or {}
            _pxyz = _ts.get("xyz") or _pent.get("xyz")
            if not _pxyz:
                continue
            _pw = _pent.get("parent_world")
            if isinstance(_pw, (bytes, bytearray)):
                _pw = int.from_bytes(bytes(_pw), "big")
            people_by_world.setdefault(int(_pw or 0), []).append(
                _ai.PersonView(auid=int(_pauid), xyz=tuple(_pxyz),
                               hp=int(_ts.get("hp", 46) or 0),
                               max_hp=int(_ts.get("max_hp", 46) or 46)))

        carcasses = [tuple(v["xyz"]) for v in _DROPPED_ITEMS.values()
                     if v.get("xyz")]

        for d in animals:
            people = people_by_world.get(int(d.world_auid or 0), [])
            try:
                dna = _DhDNA_from_bytes(d.dna) if d.dna else None
            except Exception as exc:
                logger.debug("[fauna-ai] no DhDNA view for 0x%08x (%r); it "
                             "behaves as a herbivore.", int(d.auid), exc)
                dna = None
            view = _ai.AnimalView(
                auid=d.auid,
                eco_role=(dna.eco_role() if dna is not None else
                          _ai.ECO_HERBIVORE),
                xyz=tuple(d.xyz), hp=d.hp, max_hp=d.max_hp, dna=dna,
                home_xyz=(tuple(d.home_xyz) if d.home_xyz else None),
                last_attack_s=float(getattr(d, "ai_last_attack_s", 0.0)))
            try:
                intent = _ai.decide(view, people, now_s, carcasses=carcasses,
                                    dice=_wander_dice)
            except Exception as exc:
                logger.error(f"[fauna-ai] decide failed for 0x{d.auid:08x}: {exc!r}")
                continue

            if intent.attack_damage and intent.attack_target:
                try:
                    _apply_damage(intent.attack_target, intent.attack_damage,
                                  source=f"animal 0x{d.auid:08x}",
                                  attacker=d.auid,
                                  tock_state=_tock_state,
                                  agent_bits_for=agent_bits_for)
                    d.ai_last_attack_s = now_s
                    logger.info(f"[fauna-ai] {_ai.describe(view, intent)}")
                except Exception as exc:
                    logger.error(f"[fauna-ai] attack failed: {exc!r}")

            if not (intent.moved or intent.pose is not None):
                continue
            if intent.move_to:
                d.xyz = await _fauna_ground(conn, intent.move_to, d.world_auid)
            try:
                pkt = _pack_upd(d.auid, xyz=d.xyz,
                                rotation=_fauna_align(
                                    d.xyz, float(intent.face_rad)),
                                hp=d.hp, pose=intent.pose)
                await _broadcast_to_peers(pkt, _live_avatars,
                                          parent_auid=d.world_auid,
                                          label="fauna")
            except Exception as exc:
                logger.error(f"[fauna-ai] emit failed for 0x{d.auid:08x}: {exc!r}")


async def _fauna_repopulate_tick(conn, period_s: float, *,
                                 _live_avatars,
                                 _tock_state,
                                 _DYNAMIC_SCENE_AUIDS) -> None:
    import time as _t

    while True:
        await asyncio.sleep(period_s)
        try:
            for world, st in list(_FAUNA_WORLD_STATE.items()):
                roster = st.get("roster") or []
                if not roster:
                    continue
                anchor = None
                for _pauid, _pent in list(_live_avatars.items()):
                    _pw = _pent.get("parent_world")
                    if isinstance(_pw, (bytes, bytearray)):
                        _pw = int.from_bytes(bytes(_pw), "big")
                    if int(_pw or 0) != world:
                        continue
                    _ts = _tock_state.get(_pauid) or {}
                    if _ts.get("xyz"):
                        anchor = tuple(_ts["xyz"])
                        break
                if anchor is None:
                    continue

                live = [d for d in _dmg.all_damageable()
                        if d.kind == _dmg.KIND_ANIMAL and d.alive
                        and int(d.world_auid or 0) == world]
                cap = min(int(st.get("max_total", 20)),
                          _density_cap(int(st.get("land_value", 50))))
                missing = cap - len(live)
                if missing <= 0:
                    continue

                dice = _DnaDice(seed=(world ^ int(_t.time())) & 0xFFFFFFFF)
                fresh = _roll_ind(
                    roster, spawn_anchor_xyz=anchor, dice=dice,
                    per_species=max(1, int(st.get("per_species", 3))),
                    max_total=missing,
                    jitter_m=float(st.get("jitter_m", 30.0)),
                    land_value=int(st.get("land_value", 50)))[:missing]
                if not fresh:
                    continue

                born = 0
                for ind in fresh:
                    key = (world, ind.species_idx & 0xFF)
                    idx = _FAUNA_NEXT_IND.get(key, 0)
                    _FAUNA_NEXT_IND[key] = idx + 1
                    if idx > 0xFFFF:
                        continue
                    auid = (0xC0000000 | ((ind.species_idx & 0xFF) << 16)
                            | (idx & 0xFFFF))
                    try:
                        pkt = _pack_animal_spawn(
                            auid=auid, parent_planet_auid=world,
                            dna_bytes=ind.dna.to_bytes(), xyz=ind.xyz,
                            rotation=_fauna_align(ind.xyz, float(ind.yaw_rad)),
                            hp=ind.hp, max_hp=ind.max_hp,
                            stamina=ind.stamina, pose=ind.pose, sex=ind.sex)
                        _DYNAMIC_SCENE_AUIDS.add(auid)
                        _dmg.register(auid, kind=_dmg.KIND_ANIMAL,
                                      name=f"Specie_{ind.species_idx:02x}"
                                           f"#{idx}",
                                      dna=ind.dna.to_bytes(),
                                      max_hp=int(ind.max_hp),
                                      world_auid=world, xyz=ind.xyz)
                        await _broadcast_to_peers(pkt, _live_avatars,
                                                  parent_auid=world,
                                                  label="fauna-repop")
                        born += 1
                    except Exception as exc:
                        logger.error(f"[fauna-repop] spawn 0x{auid:08x} failed: "
                                     f"{exc!r}")
                if born:
                    logger.info(f"[fauna-repop] world 0x{world:08x}: {len(live)}/"
                                f"{cap} alive -> spawned {born} near a player")
        except Exception as exc:
            logger.error(f"[fauna-repop] tick failed: {exc!r}")


def start_fauna_loops(conn, writer, conn_label, conn_tasks, *,
                      _live_avatars, _tock_state, _DROPPED_ITEMS,
                      _DYNAMIC_SCENE_AUIDS, agent_bits_for) -> None:
    try:
        _ai_period = 0.5
        conn_tasks.append(asyncio.create_task(
            _fauna_ai_tick(conn, writer, _ai_period,
                           _live_avatars=_live_avatars,
                           _tock_state=_tock_state,
                           _DROPPED_ITEMS=_DROPPED_ITEMS,
                           agent_bits_for=agent_bits_for)))
        logger.info(f'[scene]   -> {conn_label} fauna AI ticker started (every {_ai_period:.2f}s.')
        _repop_period = 60.0
        conn_tasks.append(asyncio.create_task(
            _fauna_repopulate_tick(conn, _repop_period,
                                   _live_avatars=_live_avatars,
                                   _tock_state=_tock_state,
                                   _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)))
        logger.info(f"[scene]   -> {conn_label} fauna repopulation "
                    f"ticker started (every {_repop_period:.0f}s, "
                    f"tops up to the live-animal cap near a player)")
    except Exception as _ai_exc:
        logger.error(f"[scene]   {conn_label}: fauna AI ticker start err: "
                     f"{_ai_exc!r}")
