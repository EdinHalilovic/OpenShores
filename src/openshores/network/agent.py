
from __future__ import annotations

import asyncio as _aio
import math
import struct
from typing import Optional, Tuple

import asyncpg

from openshores.core.config import Deployment
from openshores.core.logging import get_logger
from openshores.database.repositories.agent import (
    _system_of_globe,
    globe_row_for_fauna,
    is_walkable_globe,
)
from openshores.database.repositories.person import update_person_state
from openshores.database.repositories.world import _fauna_terrain_for_world
from openshores.gameplay import damageable as _dmg
from openshores.gameplay.agent_powers import (
    BIT_INVINCIBLE,
    BIT_INVISIBLE,
    BIT_POWERS,
    RANK_AGENT,
    RANK_NAMES,
    _actor_entry,
    agent_bits_for,
    describe_bits,
    is_agent,
    rank_for,
    resolve_actor,
    set_agent_bits,
)
from openshores.gameplay.fauna_placement import _FAUNA_BODY_OFFSET
from openshores.gameplay.gear_slots import _add_gear_item
from openshores.gameplay.natives import village as _nat
from openshores.gameplay.worldgen.planet_fauna_gen import (
    is_planet_habitable,
    roll_individuals,
    roll_planet_roster,
)
from openshores.protocol.atoms.aucomm import (
    AUCOMM_TYPE_CHAT,
    AUCOMM_TYPE_CHAT_CONTINUED,
    AUCOMM_TYPE_THOUGHT,
    CHAT_CHANNEL_SCOPE,
    CHAT_CHANNEL_TABLE,
    CHAT_TEXT_LIMIT,
    SYSTEM_CHANNEL,
    SYSTEM_SENDER_AUID,
    SYSTEM_SENDER_NAME,
    build_chat_aucomm_v4,
)
from openshores.protocol.atoms.person import (
    _build_daperson_xform_update,
    build_agent_bits_daperson_update,
)
from openshores.protocol.framing import write_framed
from openshores.protocol.rng import AuDice
from openshores.protocol.scene_init import build_scene_world_redirect
from openshores.protocol.stream import QDS
from openshores.world.chat_writer import _chat_only_writer

logger = get_logger(__name__)


_OPCODE_DOC = """
op    slot (class)                     body
0x34  LoadShipDesign (Design)          u32 blueprintRef, u8 1
0x50  RequestCityLastReport (Env)      u8 0
0x50  RequestCityHistoryReport (Env)   u8 1
0x77  RecoverShip (Ship)               u8 0x0B
0xB4  ToggleAgentBits (Power)          u8 bits
0xB5  Drain/FillCapacitor (Ship)       u8 sub(0=drain,1=fill), i8 pct
0xB6  ScuttleShip/ToggleOwnership      u8 sub(0=scuttle+QString, 1=toggle)
0xBB  encounter / ship-load            u8 sub, u32 arg
0xBC  environment                      u8 sub, i8 arg
0xBD  ChangeSystemGenHab (Env)         u8 (1=No, 2=Yes)
0xBE  teleport to atom                 AuId target, u8 withRide, u8 limbo
0xBF  teleport to long/lat             AuGlobeLLF ll(2xf32), u8 withRide
0xC1  kill animals (Enc)               u8 (0=domestic, 1=wild)
0xC2  MakeItem (Power)                 i16 cid, u8 q, u32 count, i8 galaxy,
                                       AuPoint coord, i8 dest
0xC5  Refuel/Repair (Ship)             i8 fuelQuality (0 = repair)
0xC6  ResetStory (Power)               i32 storyId
0xC7  ChangeMyDNA (Power)              (bare)
0xC8  SummonPerson                     AuId target, u8 withTheirRide
"""


async def notify(live_avatars: dict, actor_auid: int, text: str) -> bool:
    if not text:
        return False
    actor_auid = resolve_actor(live_avatars, actor_auid)
    entry = live_avatars.get(actor_auid) if actor_auid else None
    if entry is None:
        logger.debug("No live entry for 0x%08x, so it is not told: %s",
                     actor_auid, text)
        return False
    w = _chat_only_writer(entry)
    if w is None:
        logger.debug("0x%08x has no chat writer, so it is not told: %s",
                     actor_auid, text)
        return False
    if w.is_closing():
        return False
    idx = CHAT_CHANNEL_TABLE.index(SYSTEM_CHANNEL)
    scope = CHAT_CHANNEL_SCOPE[idx]
    type_byte = (AUCOMM_TYPE_CHAT if len(text) < CHAT_TEXT_LIMIT
                 else AUCOMM_TYPE_CHAT_CONTINUED)
    tail = QDS()
    tail.write_qstring(text)
    pkt = build_chat_aucomm_v4(
        type_byte=type_byte, body_after_parent=tail.getvalue(),
        sender_auid_int=SYSTEM_SENDER_AUID,
        sender_name=SYSTEM_SENDER_NAME,
        target_auid_int=actor_auid,
        channel_index=idx, scope=scope)
    await write_framed(w, pkt)
    logger.debug("-> 0x%08x: %s", actor_auid, text)
    return True


async def notify_thought(live_avatars: dict, actor_auid: int,
                         text: str) -> bool:
    if not text:
        return False
    actor_auid = resolve_actor(live_avatars, actor_auid)
    entry = live_avatars.get(actor_auid) if actor_auid else None
    if entry is None:
        logger.debug("No live entry for 0x%08x, so the thought is dropped: %s",
                     actor_auid, text)
        return False
    w = _chat_only_writer(entry)
    if w is None:
        logger.debug("0x%08x has no chat writer, so the thought is dropped: "
                     "%s", actor_auid, text)
        return False
    if w.is_closing():
        return False
    idx = CHAT_CHANNEL_TABLE.index("Thoughts")
    scope = CHAT_CHANNEL_SCOPE[idx]
    flags = 0x4F
    tail = QDS()
    tail.write_qstring(text)
    pkt = build_chat_aucomm_v4(
        type_byte=AUCOMM_TYPE_THOUGHT,
        body_after_parent=tail.getvalue(),
        sender_auid_int=actor_auid,
        sender_name=entry.get("name") or "",
        target_auid_int=1,
        channel_index=idx, scope=scope,
        flags_byte=flags, range_byte=0x00)
    await write_framed(w, pkt)
    logger.debug("Thought -> 0x%08x: %s", actor_auid, text)
    return True


def _gate(live_avatars: dict, agent_rank: dict, actor_auid: int, what: str,
          need: int = RANK_AGENT) -> bool:
    actor_auid = resolve_actor(live_avatars, actor_auid)
    if not actor_auid:
        logger.warning("%s is refused: no actor could be resolved for the "
                       "chat frame that asked for it.", what)
        return False
    """Rank check. The client will not show the button below Agent, but the
    wire is not the UI — anything can send a chat frame, so re-check here.
    Mirrors DaPerson::IsOnLineAsAgent's nesting (Architect > Programmer >
    Agent)."""
    r = rank_for(agent_rank, actor_auid)
    if r >= need:
        return True
    logger.warning("%s is refused: 0x%08x has rank %d and needs %d (%s).",
                   what, int(actor_auid) & 0xFFFFFFFF, r, need,
                   RANK_NAMES.get(need, need))
    return False


_UNIMPLEMENTED = {
    0x34: "Load/Publicize spacecraft design (Design tab)",
    0x77: "Recover Ship (Spacecraft tab)",
    0xB5: "Drain/Fill Capacitor (Spacecraft tab)",
    0xB6: "Scuttle Ship / Toggle Company-vs-Fleet (Spacecraft tab)",
    0xC5: "Refuel / Repair (Spacecraft tab)",
}


async def push_agent_bits(live_avatars: dict, agent_bits: dict,
                          actor_auid: int, *,
                          broadcast_to_peers) -> int:
    actor = int(actor_auid) & 0xFFFFFFFF
    entry = _actor_entry(live_avatars, actor)
    if entry is None:
        return 0
    bits = agent_bits_for(agent_bits, actor)
    pkt = build_agent_bits_daperson_update(struct.pack(">I", actor), bits)
    parent = entry.get("parent_world")
    if isinstance(parent, (bytes, bytearray)):
        parent = int.from_bytes(bytes(parent), "big")
    n = await broadcast_to_peers(
        pkt, live_avatars,
        parent_auid=int(parent) if parent else None,
        label="agent-bits")
    logger.info("Agent bits 0x%02x for 0x%08x went to %d client(s).",
                bits, actor, n)
    return int(n or 0)


async def on_toggle_agent_bits(payload: bytes, actor_auid: int, *,
                               live_avatars: dict,
                               agent_bits: dict,
                               agent_rank: dict,
                               pb2_last_cursor: dict,
                               broadcast_to_peers) -> None:
    if not _gate(live_avatars, agent_rank, actor_auid, "ToggleAgentBits"):
        return
    if len(payload) < 2:
        logger.warning('A 0xB4 ToggleAgentBits body is %dB, too short to carry the bits.', len(payload))
        return
    bits = payload[1] & 0x3F
    set_agent_bits(agent_bits, actor_auid, bits,
                   live_avatars=live_avatars, pb2_last_cursor=pb2_last_cursor)
    rank = rank_for(agent_rank, actor_auid)
    label = RANK_NAMES.get(rank, "Player")
    logger.info("0xB4 SetAgentBits actor=0x%08x bits=0x%02x powers=%d (%s)",
                int(actor_auid) & 0xFFFFFFFF, bits,
                int(bool(bits & BIT_POWERS)), describe_bits(bits))
    await push_agent_bits(live_avatars, agent_bits, actor_auid,
                          broadcast_to_peers=broadcast_to_peers)
    who = label if (bits & BIT_POWERS) else "Player"
    await notify(live_avatars, actor_auid,
                 f"Agent Settings: {who}, {describe_bits(bits)}")


ENCOUNTER_SUBS = {
    0: ("Animal Encounter", True),
    1: ("Pirate Station", False),
    2: ("Pirate Ship", False),
    3: ("Aerial Animal Encounter", True),
    4: ("Load Officer", False),
    5: ("Load Crew", False),
    6: ("Load Troops", False),
    7: ("Load Passengers", False),
    8: ("Pirate Equip", False),
    9: ("Monster Encounter", True),
    10: ("Indigenous Encounter", True),
}

ANIMAL_FAIL = {
    1: "No animals spawned. Animal encounters are disabled.",
    2: "No animals spawned. No creature or thing is present in the area.",
    3: "No animals spawned. The terrain is not in anyone's scene.",
    4: "No animals spawned. I am not on a planet.",
    5: "No animals spawned. Planet cannot have animals.",
    6: "No animals spawned. Planet does not have animals.",
    7: "No animals spawned. Person online not found in the area.",
    8: "No animals spawned. Maximum animal population is already present.",
    9: "No animals spawned. A development exists at the chosen spawn location.",
    10: "No animals spawned. Terrain area has no aerial creatures at this "
        "time of day.",
}


async def on_encounter(payload: bytes, actor_auid: int, *,
                       conn: asyncpg.Connection,
                       live_avatars: dict,
                       agent_rank: dict,
                       fauna_world_state: dict,
                       fauna_next_ind: dict,
                       fauna_terrain_cache: dict,
                       _DYNAMIC_SCENE_AUIDS: set,
                       indigenous_dna_by_world: dict,
                       tock_state: dict,
                       fauna_ground,
                       fauna_align,
                       pack_animal_spawn,
                       dna_for_actor,
                       register_damageable_npcs,
                       broadcast_to_peers) -> None:
    if not _gate(live_avatars, agent_rank, actor_auid, "Encounter"):
        return
    if len(payload) < 6:
        logger.warning('A 0xBB Encounter body is %dB, too short to carry a sub-code and argument.', len(payload))
        return
    sub = payload[1]
    arg = struct.unpack(">I", payload[2:6])[0]
    name, done = ENCOUNTER_SUBS.get(sub, (f"unknown sub {sub}", False))
    logger.info("0xBB %s sub=%d arg=0x%08x actor=0x%08x",
                name, sub, arg, int(actor_auid) & 0xFFFFFFFF)
    if not done:
        await notify(live_avatars, actor_auid,
                     f"{name} is not implemented on this server.")
        return
    if sub in (0, 3):
        await _spawn_animal_encounter(
            conn, live_avatars, actor_auid, aerial=(sub == 3),
            fauna_world_state=fauna_world_state,
            fauna_next_ind=fauna_next_ind,
            fauna_terrain_cache=fauna_terrain_cache,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
            tock_state=tock_state,
            fauna_ground=fauna_ground, fauna_align=fauna_align,
            pack_animal_spawn=pack_animal_spawn,
            broadcast_to_peers=broadcast_to_peers)
    elif sub == 9:
        await notify(live_avatars, actor_auid,
                     "Monster encounters require a spacecraft, which this "
                     "server does not simulate.")
    elif sub == 10:
        await _indigenous_encounter(
            conn, live_avatars, actor_auid,
            fauna_world_state=fauna_world_state,
            fauna_terrain_cache=fauna_terrain_cache,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
            indigenous_dna_by_world=indigenous_dna_by_world,
            dna_for_actor=dna_for_actor,
            register_damageable_npcs=register_damageable_npcs,
            broadcast_to_peers=broadcast_to_peers)


async def _roll_roster_for_world(conn: asyncpg.Connection, world_int: int, st,
                                 *, fauna_world_state: dict):
    globe_row = await globe_row_for_fauna(conn, world_int)
    if not globe_row:
        logger.info("0x%08x is not an a_WorldGlobe (gas giant / ring?), so it "
                    "has no fauna.", world_int)
        return [], st
    if not is_planet_habitable(globe_row):
        logger.info("0x%08x is not habitable (zone=%r atm=%r water=%r), so no "
                    "roster is rolled.", world_int, globe_row["orbitZone"],
                    globe_row["atmType"], globe_row["water"])
        return [], st
    roster = roll_planet_roster(globe_row, planet_auid=world_int, force=False)
    if not roster:
        return [], st
    st = dict(st or {})
    st.setdefault("roster", roster)
    st.setdefault("jitter_m", 30.0)
    st.setdefault("land_value", 50)
    st.setdefault("max_total", 20)
    st.setdefault("per_species", 3)
    fauna_world_state[world_int] = st
    logger.info("Rolled a fauna roster on demand for 0x%08x: %d species.",
                world_int, len(roster))
    return roster, st


async def _spawn_animal_encounter(conn: asyncpg.Connection,
                                  live_avatars: dict, actor_auid: int, *,
                                  aerial: bool,
                                  fauna_world_state: dict,
                                  fauna_next_ind: dict,
                                  fauna_terrain_cache: dict,
                                  _DYNAMIC_SCENE_AUIDS: set,
                                  tock_state: dict,
                                  fauna_ground,
                                  fauna_align,
                                  pack_animal_spawn,
                                  broadcast_to_peers) -> None:
    entry = _actor_entry(live_avatars, actor_auid)
    if entry is None:
        await notify(live_avatars, actor_auid, ANIMAL_FAIL[7])
        return
    world = entry.get("parent_world")
    if not world:
        await notify(live_avatars, actor_auid, ANIMAL_FAIL[4])
        return
    world_int = (int.from_bytes(world, "big") if isinstance(world, (bytes, bytearray))
                 else int(world)) & 0xFFFFFFFF
    anchor = entry.get("xyz")
    if not anchor:
        anchor = (tock_state.get(int(actor_auid) & 0xFFFFFFFF) or {}).get("xyz")
    if not anchor:
        await notify(live_avatars, actor_auid, ANIMAL_FAIL[2])
        return
    st = fauna_world_state.get(world_int)
    roster = (st or {}).get("roster") or []
    if not roster:
        roster, st = await _roll_roster_for_world(
            conn, world_int, st, fauna_world_state=fauna_world_state)
    if not roster:
        await notify(live_avatars, actor_auid, ANIMAL_FAIL[5])
        return

    def _flies(e) -> bool:
        return bool(e.dna.can_fly())
    subset = [e for e in roster if _flies(e) == bool(aerial)]
    if not subset:
        await notify(live_avatars, actor_auid,
                     ANIMAL_FAIL[10] if aerial else ANIMAL_FAIL[5])
        return

    import time as _t
    want = 3
    dice = AuDice(seed=(world_int ^ int(_t.time())) & 0xFFFFFFFF)
    fresh = roll_individuals(
        subset, spawn_anchor_xyz=tuple(anchor), dice=dice,
        per_species=max(1, want // max(1, len(subset))) or 1,
        max_total=want,
        jitter_m=float((st or {}).get("jitter_m", 30.0)),
        land_value=int((st or {}).get("land_value", 50)))[:want]
    if not fresh:
        await notify(live_avatars, actor_auid, ANIMAL_FAIL[2])
        return

    _terr, _size = await _fauna_terrain_for_world(conn, world_int,
                                                  cache=fauna_terrain_cache)
    if _terr and _size:
        for ind in fresh:
            ind.xyz = await fauna_ground(conn, ind.xyz, world_int)
        logger.debug("Projected %d spawn point(s) onto terrain "
                     "(world=0x%08x size=%s offset=%.2f).",
                     len(fresh), world_int, _size, _FAUNA_BODY_OFFSET)
    else:
        logger.warning("World 0x%08x has no terrain to project onto "
                       "(terrain=%s size=%s), so animals may spawn below "
                       "ground.", world_int, bool(_terr), _size)

    born = 0
    for ind in fresh:
        key = (world_int, ind.species_idx & 0xFF)
        idx = fauna_next_ind.get(key, 0)
        fauna_next_ind[key] = idx + 1
        if idx > 0xFFFF:
            continue
        auid = (0xC0000000 | ((ind.species_idx & 0xFF) << 16) | (idx & 0xFFFF))
        try:
            pkt = pack_animal_spawn(
                auid=auid, parent_planet_auid=world_int,
                dna_bytes=ind.dna.to_bytes(), xyz=ind.xyz,
                rotation=fauna_align(ind.xyz, ind.yaw_rad),
                hp=ind.hp, max_hp=ind.max_hp, stamina=ind.stamina,
                pose=ind.pose, sex=ind.sex)
            _DYNAMIC_SCENE_AUIDS.add(auid)
            _dmg.register(auid, kind=_dmg.KIND_ANIMAL,
                          name=f"Specie_{ind.species_idx:02x}#{idx}",
                          dna=ind.dna.to_bytes(), max_hp=int(ind.max_hp),
                          world_auid=world_int, xyz=ind.xyz)
            await broadcast_to_peers(pkt, live_avatars,
                                     parent_auid=world_int,
                                     label="agent-encounter")
            born += 1
        except Exception as exc:                        # noqa: BLE001
            logger.warning("Spawn err on 0x%08x: %r", auid, exc)
    logger.info("%sencounter on world 0x%08x spawned %d/%d near %s.",
                "aerial " if aerial else "", world_int, born, len(fresh),
                tuple(anchor))
    if not born:
        await notify(live_avatars, actor_auid, ANIMAL_FAIL[2])
        return
    await notify(live_avatars, actor_auid, f"{born} animals spawned.")


_AGENT_VILLAGES: dict = {}

_NATIVE_BLOCK = 0x1000


def _free_native_auid_base(_DYNAMIC_SCENE_AUIDS: set):
    taken = set()
    taken |= {int(a) & 0xFFFFFFFF for a in _nat._IDLE_BODIES}
    taken |= {int(a) & 0xFFFFFFFF for a in _DYNAMIC_SCENE_AUIDS}
    base0 = int(_nat.NATIVE_AUID_BASE) & 0xFFFFFFFF
    for n in range(1, 256):
        cand = (base0 + n * _NATIVE_BLOCK) & 0xFFFFFFFF
        if not any((cand + i) in taken for i in range(_NATIVE_BLOCK)):
            return cand
    return None


async def _indigenous_encounter(conn: asyncpg.Connection, live_avatars: dict,
                                actor_auid: int, *,
                                fauna_world_state: dict,
                                fauna_terrain_cache: dict,
                                _DYNAMIC_SCENE_AUIDS: set,
                                indigenous_dna_by_world: dict,
                                dna_for_actor,
                                register_damageable_npcs,
                                broadcast_to_peers) -> None:
    entry = _actor_entry(live_avatars, actor_auid)
    if entry is None or not entry.get("xyz"):
        await notify(live_avatars, actor_auid,
                     "You must be on the terrain of a planet.")
        return
    world = entry.get("parent_world")
    world_int = ((int.from_bytes(bytes(world), "big")
                  if isinstance(world, (bytes, bytearray)) else int(world or 0))
                 & 0xFFFFFFFF)
    anchor = entry.get("xyz")
    if not world_int or not anchor:
        await notify(live_avatars, actor_auid,
                     "You must be on the terrain of a planet.")
        return

    _st0 = fauna_world_state.get(world_int)
    roster = (_st0 or {}).get("roster") or []
    if not roster:
        roster, _st0 = await _roll_roster_for_world(
            conn, world_int, _st0, fauna_world_state=fauna_world_state)
    if not roster:
        await notify(live_avatars, actor_auid,
                     "No indigenous spawned. Terrain is not habitable.")
        return

    made = int(_AGENT_VILLAGES.get(world_int, 0))
    cap = 4
    if made >= cap:
        await notify(live_avatars, actor_auid,
                     f"{made} villages already placed on this world "
                     f"(cap {cap}). Restart the server to reset.")
        return

    base = _free_native_auid_base(_DYNAMIC_SCENE_AUIDS)
    if base is None:
        logger.warning("No free native AuId block is left on 0x%08x.",
                       world_int)
        await notify(live_avatars, actor_auid,
                     "No indigenous spawned. No free atom ids.")
        return

    dna = indigenous_dna_by_world.get(world_int)
    if not dna:
        dna = await dna_for_actor(conn, int(actor_auid) & 0xFFFFFFFF)
    if not dna or len(bytes(dna)) != 24:
        dna = _nat.DNA_DEFAULT_HUMAN

    terrain, size = await _fauna_terrain_for_world(conn, world_int,
                                                  cache=fauna_terrain_cache)
    if not size:
        terrain = None
    dist = float(_nat.DEFAULT_CENTRE_OFFSET_FT)

    entries = _nat.build_native_entries(
        world_auid=world_int,
        anchor_xyz=tuple(anchor),
        dna24=bytes(dna),
        seed=(world_int & 0x7FFFFFFF) or 1,
        terrain=terrain,
        size=size,
        centre_offset_ft=dist,
        auid_base=base,
        register_idle=True,
        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS,
    )
    if not entries:
        await notify(live_avatars, actor_auid, "No indigenous spawned.")
        return

    sent = 0
    for _label, pkt in entries:
        try:
            await broadcast_to_peers(pkt, live_avatars,
                                     parent_auid=world_int,
                                     label="agent-village")
            sent += 1
        except Exception as exc:                        # noqa: BLE001
            logger.warning("Village atom %s not broadcast: %r", _label, exc)
    n_hurt = register_damageable_npcs()

    _AGENT_VILLAGES[world_int] = made + 1
    logger.info("Indigenous village #%d on 0x%08x: %d bodies from base "
                "0x%08x, %d pushed, %d damageable, anchor=%s dist=%sft",
                made + 1, world_int, len(entries), base, sent, n_hurt,
                tuple(anchor), dist)
    await notify(live_avatars, actor_auid,
                 f"Indigenous encounter: {len(entries)} villagers spawned.")


async def on_kill_animals(payload: bytes, actor_auid: int, *,
                          live_avatars: dict, agent_rank: dict) -> None:
    if not _gate(live_avatars, agent_rank, actor_auid, "KillAnimals"):
        return
    if len(payload) < 2:
        logger.warning("A 0xC1 KillAnimals body is %dB, too short to carry a "
                       "kind; refused.", len(payload))
        return
    wild = bool(payload[1])
    kind = "wild" if wild else "domestic"
    killed = 0
    for d in list(_dmg.all_damageable()):
        if getattr(d, "kind", None) != _dmg.KIND_ANIMAL:
            continue
        if getattr(d, "hp", 0) <= 0:
            continue
        if not wild:
            continue
        try:
            _dmg.damage(int(d.auid), int(getattr(d, "max_hp", 100)) + 1,
                        attacker=int(actor_auid) & 0xFFFFFFFF)
            killed += 1
        except Exception as exc:                        # noqa: BLE001
            logger.warning("Kill err on 0x%08x: %r", int(d.auid), exc)
    logger.info("0xC1 KillAnimals kind=%s killed=%d actor=0x%08x",
                kind, killed, int(actor_auid) & 0xFFFFFFFF)
    if not wild:
        await notify(live_avatars, actor_auid,
                     "No domestic animals in your scene. This server has no "
                     "domestic animal model yet.")
    else:
        await notify(live_avatars, actor_auid,
                     f"{killed} wild animals killed.")


ENV_SUBS = {
    0: "Regenerate Ground Cover",
    1: "Regenerate Shrubbery",
    2: "Regenerate Trees",
    3: "Set Indigenous DNA of Zone to Mine",
    4: "Clear Indigenous DNA of Zone",
    5: "Clear Rat DNA",
    6: "Set Citizen DNA of City to Mine",
}

ZONE_NAMES = {0: "polar", 1: "temperate", 2: "tropical"}


async def on_environment(payload: bytes, actor_auid: int, *,
                         conn: asyncpg.Connection,
                         live_avatars: dict,
                         agent_rank: dict,
                         fauna_world_state: dict,
                         indigenous_dna_by_world: dict,
                         city_sim: dict,
                         dna_for_actor) -> None:
    if not _gate(live_avatars, agent_rank, actor_auid, "Environment"):
        return
    if len(payload) < 3:
        logger.warning('A 0xBC Environment body is %dB, too short to carry a sub-code and argument.', len(payload))
        return
    sub = payload[1]
    arg = struct.unpack(">b", payload[2:3])[0]
    name = ENV_SUBS.get(sub, f"unknown sub {sub}")
    logger.info("0xBC %s sub=%d arg=%d actor=0x%08x",
                name, sub, arg, int(actor_auid) & 0xFFFFFFFF)

    if sub == 5:
        await notify(live_avatars, actor_auid,
                     "Clear Rat DNA is a spacecraft function, which this "
                     "server does not simulate.")
        return
    if sub in (0, 1, 2):
        await _regen_plants(live_avatars, actor_auid, sub, arg,
                            fauna_world_state=fauna_world_state)
        return
    if sub == 6:
        await _set_citizen_dna(conn, live_avatars, actor_auid,
                               city_sim=city_sim,
                               dna_for_actor=dna_for_actor)
        return
    if sub in (3, 4):
        await _set_indigenous_dna(
            conn, live_avatars, actor_auid, clear=(sub == 4),
            indigenous_dna_by_world=indigenous_dna_by_world,
            dna_for_actor=dna_for_actor)
        return
    await notify(live_avatars, actor_auid,
                 f"{name} is not implemented on this server.")


async def _regen_plants(live_avatars: dict, actor_auid: int, sub: int,
                        zone: int, *, fauna_world_state: dict) -> None:
    kind = {0: "ground cover plants", 1: "shrubbery", 2: "trees"}[sub]
    zname = ZONE_NAMES.get(zone, str(zone))
    entry = _actor_entry(live_avatars, actor_auid)
    if entry is None or not entry.get("xyz"):
        await notify(live_avatars, actor_auid,
                     f"You must be on the terrain of a planet to regenerate "
                     f"{kind}.")
        return
    world = entry.get("parent_world")
    world_int = ((int.from_bytes(world, "big")
                  if isinstance(world, (bytes, bytearray)) else int(world or 0))
                 & 0xFFFFFFFF)
    dropped = False
    if world_int in fauna_world_state:
        fauna_world_state.pop(world_int, None)
        dropped = True
    logger.info("Regenerating %s in the %s zone of 0x%08x; roster cache "
                "dropped=%s", kind, zname, world_int, dropped)
    await notify(live_avatars, actor_auid,
                 f"The DNA of the {kind} in the {zname} zone of this world "
                 f"will be regenerated. Players in this area, including you, "
                 f"must restart Shores of Hazeron to see the change.")


async def _set_citizen_dna(conn: asyncpg.Connection, live_avatars: dict,
                           actor_auid: int, *,
                           city_sim: dict, dna_for_actor) -> None:
    entry = _actor_entry(live_avatars, actor_auid)
    if entry is None:
        await notify(live_avatars, actor_auid,
                     "You must be in a development of a city to change "
                     "citizen DNA.")
        return
    dna = await dna_for_actor(conn, int(actor_auid) & 0xFFFFFFFF)
    if not dna:
        await notify(live_avatars, actor_auid, "Your DNA could not be read.")
        return
    city_id, info = (None, None)
    for cid, inf in list(city_sim.items()):
        city_id, info = cid, inf
        break
    if info is None:
        await notify(live_avatars, actor_auid,
                     "You must be in a development of a city to change "
                     "citizen DNA.")
        return
    info["worker_dna"] = bytes(dna)
    name = info.get("name") or f"City_{city_id:08x}"
    logger.info("Citizen DNA of city 0x%08x (%s) now matches the actor's "
                "(%dB).", int(city_id), name, len(dna))
    await notify(live_avatars, actor_auid,
                 f"The citizen DNA in {name} will change to match your DNA.")


async def _set_indigenous_dna(conn: asyncpg.Connection, live_avatars: dict,
                              actor_auid: int, *,
                              clear: bool, indigenous_dna_by_world: dict,
                              dna_for_actor) -> None:
    entry = _actor_entry(live_avatars, actor_auid)
    if entry is None or not entry.get("xyz"):
        await notify(live_avatars, actor_auid,
                     "You must be on the terrain of a planet to change "
                     "indigenous DNA.")
        return
    world = entry.get("parent_world")
    world_int = ((int.from_bytes(world, "big")
                  if isinstance(world, (bytes, bytearray)) else int(world or 0))
                 & 0xFFFFFFFF)
    store = indigenous_dna_by_world
    if clear:
        store.pop(world_int, None)
        logger.info("Indigenous DNA cleared for world 0x%08x.", world_int)
        await notify(live_avatars, actor_auid,
                     "The indigenous DNA in your current zone of this world "
                     "will be cleared, like it was never set.")
        return
    dna = await dna_for_actor(conn, int(actor_auid) & 0xFFFFFFFF)
    if not dna:
        await notify(live_avatars, actor_auid, "Your DNA could not be read.")
        return
    store[world_int] = bytes(dna)
    logger.info("Indigenous DNA of world 0x%08x set (%dB).",
                world_int, len(dna))
    await notify(live_avatars, actor_auid,
                 "The indigenous DNA in your current zone of this world will "
                 "change to match your DNA.")


async def on_change_system_gen_hab(payload: bytes, actor_auid: int, *,
                                   live_avatars: dict,
                                   agent_rank: dict,
                                   system_gen_hab: dict) -> None:
    if not _gate(live_avatars, agent_rank, actor_auid, "ChangeSystemGenHab"):
        return
    if len(payload) < 2:
        logger.warning('A 0xBD ChangeSystemGenHab body is %dB, too short to carry an answer.', len(payload))
        return
    homeworld = (payload[1] == 2)
    entry = _actor_entry(live_avatars, actor_auid)
    world = (entry or {}).get("parent_world")
    world_int = ((int.from_bytes(world, "big")
                  if isinstance(world, (bytes, bytearray)) else int(world or 0))
                 & 0xFFFFFFFF)
    system_gen_hab[world_int] = bool(homeworld)
    logger.info("0xBD GenHab world=0x%08x homeworld=%s",
                world_int, homeworld)
    await notify(live_avatars, actor_auid,
                 f"System recorded as {'a homeworld' if homeworld else 'not a homeworld'} "
                 f"system. Refresh your star map data to see survey changes.")


async def on_city_report(payload: bytes, actor_auid: int, *,
                         live_avatars: dict,
                         agent_rank: dict,
                         lookup_city_for_report,
                         write_city_report_html) -> None:
    if not _gate(live_avatars, agent_rank, actor_auid, "CityReport"):
        return
    if len(payload) < 2:
        logger.warning("A 0x50 CityReport body is %dB, too short to carry a "
                       "sub-code; refused.", len(payload))
        return
    history = bool(payload[1])
    req_id = 0
    if len(payload) >= 6:
        req_id = struct.unpack(">I", payload[2:6])[0]
    city_id, info = await lookup_city_for_report(req_id)
    logger.info("0x50 CityReport history=%s req=0x%08x -> city=%s",
                history, req_id,
                city_id and f"0x{int(city_id):08x}")
    if info is None:
        await notify(live_avatars, actor_auid,
                     "No response. Check the city id, or stand in the city.")
        return
    reports = info.get("reports") or []
    if not reports:
        await notify(live_avatars, actor_auid,
                     f"{info.get('name', 'City')} has produced no reports yet.")
        return
    wanted = reports if history else reports[-1:]
    write_city_report_html(int(city_id), info,
                           (info.get("last_report") or {}).get("html", ""))
    await notify(live_avatars, actor_auid,
                 f"{info.get('name', 'City')}: {len(wanted)} report"
                 f"{'s' if len(wanted) != 1 else ''} sent to your mail.")


MAKE_DEST_INVENTORY = 0
MAKE_DEST_CITY = 1
MAKE_DEST_SHIP = 2
MAKE_DEST_ONE = 3

MAKE_DEST_NAMES = {
    MAKE_DEST_INVENTORY: "inventory",
    MAKE_DEST_CITY: "city inventory",
    MAKE_DEST_SHIP: "ship cargo",
    MAKE_DEST_ONE: "one item/vehicle",
}


async def on_make_item(payload: bytes, actor_auid: int, *,
                       live_avatars: dict,
                       agent_rank: dict,
                       city_sim: dict,
                       get_augear,
                       pack_auitem_seed_body,
                       push_augear_refresh_for) -> None:
    if not _gate(live_avatars, agent_rank, actor_auid, "MakeItem"):
        return
    if len(payload) < 9:
        logger.warning("A 0xC2 MakeItem body is %dB, too short to carry a "
                       "commodity; refused.", len(payload))
        return
    cid = struct.unpack_from(">h", payload, 1)[0]
    quality = payload[3]
    count = struct.unpack_from(">I", payload, 4)[0]
    try:
        galaxy = struct.unpack_from(">b", payload, 8)[0]
        coord = struct.unpack_from(">ddd", payload, 9)
        dest = struct.unpack_from(">b", payload, 33)[0]
    except Exception:
        galaxy, coord, dest = 0, (0.0, 0.0, 0.0), MAKE_DEST_INVENTORY
    actor = int(actor_auid) & 0xFFFFFFFF
    cap = 10000 if dest in (MAKE_DEST_CITY, MAKE_DEST_SHIP) else 10
    if dest == MAKE_DEST_ONE:
        count = 1
    count = max(1, min(int(count), cap))
    logger.info("0xC2 MakeItem actor=0x%08x cid=%d q=%d count=%d dest=%s "
                "galaxy=%s coord=%s", actor, cid, quality, count,
                MAKE_DEST_NAMES.get(dest, dest), galaxy, coord)

    if dest == MAKE_DEST_SHIP:
        await notify(live_avatars, actor_auid,
                     "Make Ship Cargo needs a spacecraft, which this server "
                     "does not simulate.")
        return
    if dest == MAKE_DEST_CITY:
        await _make_into_city(live_avatars, actor_auid, cid, quality, count,
                              city_sim=city_sim)
        return

    augear = get_augear(actor)
    made = 0
    for _ in range(count):
        body = pack_auitem_seed_body(0x01, int(cid),
                                     quality=int(quality) & 0xFF)
        slot, sub = _add_gear_item(augear, 0x01, bytes(body))
        if slot is None:
            break
        made += 1
    if made:
        await push_augear_refresh_for(actor, log_prefix="agent")
    logger.info("Made %d/%d of cid=%d into inventory.", made, count, cid)
    if made < count:
        await notify(live_avatars, actor_auid,
                     f"Made {made} of {count}. I have no room to carry more.")
    else:
        await notify(live_avatars, actor_auid, f"Made {made} item(s).")


async def _make_into_city(live_avatars: dict, actor_auid: int, cid: int,
                          quality: int, count: int, *,
                          city_sim: dict) -> None:
    city_id, info = (None, None)
    for _cid, _inf in list(city_sim.items()):
        city_id, info = _cid, _inf
        break
    if info is None:
        await notify(live_avatars, actor_auid, "You are not in a city.")
        return
    inv = info.setdefault("inventory", {})
    key = int(cid)
    cur = int(inv.get(key, 0))
    inv[key] = cur + int(count)
    logger.info("City 0x%08x inventory cid=%d %d -> %d",
                int(city_id), cid, cur, inv[key])
    await notify(live_avatars, actor_auid,
                 f"Added {count} to the inventory of "
                 f"{info.get('name', 'your city')}.")


STORY_NAMES = {
    1: "Veil of Targoss", 2: "Falla's Embrace", 3: "Getting Started",
    4: "Rocket Training", 5: "Caroler", 6: "Relic - A Package Arrives",
    7: "Relic - Dangerous Exchange", 8: "Relic - Beacon",
}


async def on_reset_story(payload: bytes, actor_auid: int, *,
                         live_avatars: dict,
                         agent_rank: dict,
                         story_progress: dict) -> None:
    if not _gate(live_avatars, agent_rank, actor_auid, "ResetStory"):
        return
    if len(payload) < 5:
        logger.warning('A 0xC6 ResetStory body is %dB, too short to carry a script id.', len(payload))
        return
    story = struct.unpack(">i", payload[1:5])[0]
    actor = int(actor_auid) & 0xFFFFFFFF
    name = STORY_NAMES.get(story, f"script {story}")
    cleared = False
    if story_progress.pop((actor, story), None) is not None:
        cleared = True
    logger.info("0xC6 ResetStory actor=0x%08x story=%d (%s) cleared=%s",
                actor, story, name, cleared)
    await notify(live_avatars, actor_auid,
                 f"Story reset: {name}. The avatar no longer has a record of "
                 f"starting or finishing it.")


async def on_change_my_dna(payload: bytes, actor_auid: int, *,
                           conn: asyncpg.Connection,
                           live_avatars: dict,
                           agent_rank: dict,
                           dna_override: dict,
                           dna_for_actor) -> None:
    if not _gate(live_avatars, agent_rank, actor_auid, "ChangeMyDNA"):
        return
    actor = int(actor_auid) & 0xFFFFFFFF
    blob = bytes(payload[1:])
    if not blob:
        dna = await dna_for_actor(conn, actor)
        logger.info("0xC7 ChangeMyDNA actor=0x%08x QUERY (%dB current)",
                    actor, len(dna) if dna else 0)
        await notify(live_avatars, actor_auid,
                     "DNA read. Use the My DNA dialog to change it.")
        return
    dna_override[actor] = blob
    logger.info("0xC7 ChangeMyDNA actor=0x%08x apply %dB %s",
                actor, len(blob), blob[:16].hex())
    await notify(live_avatars, actor_auid,
                 "Your DNA has been changed. Restart Shores of Hazeron to "
                 "see the change.")


async def teleport_scope(conn: asyncpg.Connection, current_globe: int,
                         dest_globe: int) -> str:
    cur = int(current_globe or 0) & 0xFFFFFFFF
    dst = int(dest_globe or 0) & 0xFFFFFFFF
    if not dst or dst == cur:
        return "same-planet"
    if not cur:
        return "cross-system"
    s_cur = await _system_of_globe(conn, cur)
    s_dst = await _system_of_globe(conn, dst)
    if s_cur and s_dst and s_cur == s_dst:
        return "same-system"
    return "cross-system"


async def reparent_via_manifest(live_avatars: dict, agent_bits: dict,
                                actor_auid: int, new_parent: int, xyz,
                                *, label: str = "agent",
                                manifest_suppress: set,
                                force_scene_manifest_push,
                                peer_upright_euler,
                                _stamina_byte,
                                broadcast_to_peers) -> bool:
    actor = int(actor_auid) & 0xFFFFFFFF
    new_parent = int(new_parent or 0) & 0xFFFFFFFF
    entry = _actor_entry(live_avatars, actor)
    if entry is None or not new_parent:
        return False
    w = entry.get("writer")
    if w is None:
        logger.warning("0x%08x has no scene writer, so it cannot be "
                       "reparented.", actor)
        return False


    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    sup = manifest_suppress
    sup.add(actor)
    try:
        n = await force_scene_manifest_push(
            reason=f"{label}: drop 0x{actor:08x} for reparent")
        logger.info('A manifest without 0x%08x went to %d client(s).', actor, n)
        await _aio.sleep(0.35)
    finally:
        sup.discard(actor)

    await force_scene_manifest_push(reason=f"{label}: relist 0x{actor:08x}")

    pkt = None
    _pb2 = entry.get("pb2")
    _tc = entry.get("time_created")
    if _pb2 and _tc is not None:
        import time as _rt
        pkt = (
            bytes([0x12])
            + struct.pack(">I", actor)
            + struct.pack(">q", int(_rt.time() * 1000))
            + bytes([0x0B])
            + struct.pack(">I", new_parent)
            + struct.pack(">q", int(_tc))
            + struct.pack(">ffffff", x, y, z,
                          *peer_upright_euler((x, y, z)))
            + bytes(_pb2)
            + b"\x00" * 16
        )
        logger.debug("Re-adding 0x%08x as a FULL body (%dB, pb2=%dB).",
                     actor, len(pkt), len(_pb2))
    else:
        logger.warning("0x%08x has no cached pb2 (pb2=%s time_created=%r), so "
                       "the reparent falls back to the transform delta and "
                       "the avatar will arrive without a body.",
                       actor, bool(_pb2), _tc)
    if pkt is None:
        pkt = _build_daperson_xform_update(
            player_auid=actor, parent_auid=new_parent, x=x, y=y, z=z,
            agent_bits=agent_bits_for(agent_bits, actor),
            _stamina_byte=_stamina_byte)
    await write_framed(w, pkt)
    await broadcast_to_peers(pkt, live_avatars)
    logger.info("%s: reparented 0x%08x under 0x%08x at (%.1f,%.1f,%.1f)",
                label, actor, new_parent, x, y, z)
    return True


async def teleport_actor(conn: asyncpg.Connection, live_avatars: dict,
                         agent_bits: dict, actor_auid: int, xyz,
                         globe_auid: int = 0, *, label: str = "agent",
                         manifest_suppress: set,
                         force_scene_manifest_push,
                         peer_upright_euler,
                         _stamina_byte,
                         retarget_bundle_to_avatar,
                         broadcast_to_peers) -> bool:
    actor = int(actor_auid) & 0xFFFFFFFF
    entry = _actor_entry(live_avatars, actor)
    if entry is None:
        return False
    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    globe_auid = int(globe_auid or 0) & 0xFFFFFFFF
    _cur = entry.get("parent_world") or entry.get("AP") or 0
    if isinstance(_cur, (bytes, bytearray)):
        _cur = int.from_bytes(bytes(_cur), "big")
    _cur = int(_cur or 0) & 0xFFFFFFFF
    scope = await teleport_scope(conn, _cur, globe_auid)

    if globe_auid:
        await update_person_state(conn, actor, idp=globe_auid,
                                  locX=x, locY=y, locZ=z,
                                  vecX=0, vecY=0, vecZ=0, atRest=1)
    else:
        await update_person_state(conn, actor,
                                  locX=x, locY=y, locZ=z,
                                  vecX=0, vecY=0, vecZ=0, atRest=1)

    sess = entry.get("session")
    if sess is not None:
        sess.mark_position_dirty(x, y, z, parent_world=globe_auid or 0)
    entry["xyz"] = (x, y, z)
    if globe_auid:
        entry["parent_world"] = globe_auid.to_bytes(4, "big")

    if globe_auid:
        await retarget_bundle_to_avatar(actor)

    _dest_parent = int(globe_auid or _cur) & 0xFFFFFFFF

    if scope == "cross-system":
        _w = entry.get("writer")
        if _w is None:
            logger.warning('%s: 0x%08x is going cross-system with no scene writer.', label, actor)
            return True
        deployment = Deployment.from_env()
        _redir = build_scene_world_redirect(
            server_name=deployment.public_host,
            port=deployment.scene_port,
            world_state=2,
            account_id_lo=_dest_parent,
            account_id_hi=0,
            extra=0)
        await write_framed(_w, _redir)
        logger.info('%s: CROSS-SYSTEM 0x22 redirect to world 0x%08x (%dB).',
                    label, _dest_parent, len(_redir))
        return True

    ok = await reparent_via_manifest(
        live_avatars, agent_bits, actor, globe_auid or _cur, (x, y, z),
        label=f"{label}[{scope}]",
        manifest_suppress=manifest_suppress,
        force_scene_manifest_push=force_scene_manifest_push,
        peer_upright_euler=peer_upright_euler,
        _stamina_byte=_stamina_byte,
        broadcast_to_peers=broadcast_to_peers)
    if ok:
        return True
    logger.info('%s: 0x%08x was not reparented.', label, actor)
    return True


async def move_actor_to_xyz(live_avatars: dict, agent_bits: dict,
                            actor_auid: int, xyz, parent_world: int = 0,
                            *, label: str = "agent",
                            _stamina_byte,
                            broadcast_to_peers) -> bool:
    actor = int(actor_auid) & 0xFFFFFFFF
    entry = _actor_entry(live_avatars, actor)
    if entry is None:
        logger.warning("No live entry for 0x%08x, so it cannot be moved.",
                       actor)
        return False

    x, y, z = (float(xyz[0]), float(xyz[1]), float(xyz[2]))
    if not parent_world:
        pw = entry.get("parent_world") or entry.get("AP") or 0
        if isinstance(pw, (bytes, bytearray)):
            pw = int.from_bytes(bytes(pw), "big")
        parent_world = int(pw or 0) & 0xFFFFFFFF

    sess = entry.get("session")
    if sess is not None:
        sess.mark_position_dirty(x, y, z, parent_world=parent_world)
    entry["xyz"] = (x, y, z)
    if parent_world:
        entry["parent_world"] = parent_world
    pkt = _build_daperson_xform_update(
        player_auid=actor, parent_auid=parent_world, x=x, y=y, z=z,
        agent_bits=agent_bits_for(agent_bits, actor),
        _stamina_byte=_stamina_byte)
    w = entry.get("writer")
    if w is None:
        logger.warning("0x%08x has no scene writer, so the move is not "
                       "pushed.", actor)
        return False
    await write_framed(w, pkt)
    n = await broadcast_to_peers(pkt, live_avatars)
    logger.info("%s: moved 0x%08x to (%.1f,%.1f,%.1f) parent=0x%08x "
                "(+%d peer(s))", label, actor, x, y, z, parent_world, n)
    return True


async def _apply_arrival_bits(live_avatars: dict, agent_bits: dict,
                              agent_rank: dict, actor_auid: int, *,
                              pb2_last_cursor: dict,
                              broadcast_to_peers) -> int:
    if not is_agent(agent_rank, actor_auid):
        logger.debug("Arrival bits skipped for 0x%08x: not an agent (the "
                     "engine grants these to arriving AGENTS only).",
                     int(actor_auid) & 0xFFFFFFFF)
        return agent_bits_for(agent_bits, actor_auid)
    bits = agent_bits_for(agent_bits, actor_auid) | BIT_INVISIBLE | BIT_INVINCIBLE
    bits = set_agent_bits(agent_bits, actor_auid, bits,
                          live_avatars=live_avatars,
                          pb2_last_cursor=pb2_last_cursor)
    await push_agent_bits(live_avatars, agent_bits, actor_auid,
                          broadcast_to_peers=broadcast_to_peers)
    return bits


async def on_teleport_atom(payload: bytes, actor_auid: int, *,
                           conn: asyncpg.Connection,
                           live_avatars: dict,
                           agent_bits: dict,
                           agent_rank: dict,
                           pb2_last_cursor: dict,
                           manifest_suppress: set,
                           force_scene_manifest_push,
                           peer_upright_euler,
                           _stamina_byte,
                           retarget_bundle_to_avatar,
                           lookup_city_for_report,
                           broadcast_to_peers) -> None:
    if not _gate(live_avatars, agent_rank, actor_auid, "Teleport"):
        return
    if len(payload) < 7:
        logger.warning("A 0xBE Teleport body is %dB, too short to carry a "
                       "target; refused.", len(payload))
        return
    target = struct.unpack(">I", payload[1:5])[0]
    with_ride = bool(payload[5])
    limbo = bool(payload[6])
    actor = int(actor_auid) & 0xFFFFFFFF
    what = ("Limbo Rescue" if limbo else
            ("Go to Destination With My Ride" if with_ride
             else "Go to Destination"))
    logger.info("0xBE %s actor=0x%08x target=0x%08x withRide=%s limbo=%s",
                what, actor, target, with_ride, limbo)
    await _move_actor_to_atom(
        conn, live_avatars, agent_bits, agent_rank, actor_auid, target,
        with_ride, what,
        pb2_last_cursor=pb2_last_cursor,
        manifest_suppress=manifest_suppress,
        force_scene_manifest_push=force_scene_manifest_push,
        peer_upright_euler=peer_upright_euler,
        _stamina_byte=_stamina_byte,
        retarget_bundle_to_avatar=retarget_bundle_to_avatar,
        lookup_city_for_report=lookup_city_for_report,
        broadcast_to_peers=broadcast_to_peers)


async def on_summon(payload: bytes, actor_auid: int, *,
                    conn: asyncpg.Connection,
                    live_avatars: dict,
                    agent_bits: dict,
                    agent_rank: dict,
                    pb2_last_cursor: dict,
                    manifest_suppress: set,
                    force_scene_manifest_push,
                    peer_upright_euler,
                    _stamina_byte,
                    retarget_bundle_to_avatar,
                    broadcast_to_peers) -> None:
    if not _gate(live_avatars, agent_rank, actor_auid, "Summon"):
        return
    if len(payload) < 6:
        logger.warning("A 0xC8 Summon body is %dB, too short to carry a "
                       "target; refused.", len(payload))
        return
    target = struct.unpack(">I", payload[1:5])[0]
    with_ride = bool(payload[5])
    actor = int(actor_auid) & 0xFFFFFFFF
    logger.info("0xC8 SummonAvatar actor=0x%08x target=0x%08x withRide=%s",
                actor, target, with_ride)
    dest = _actor_entry(live_avatars, actor)
    if dest is None or not dest.get("xyz"):
        await notify(live_avatars, actor_auid, "Your own location is unknown.")
        return
    victim = live_avatars.get(target)
    if victim is None:
        await notify(live_avatars, actor_auid,
                     f"Avatar 0x{target:08x} is not on line. After 3 minutes "
                     f"the agent teleport is redirected to a capital city.")
        return
    _pw = dest.get("parent_world") or dest.get("AP") or 0
    if isinstance(_pw, (bytes, bytearray)):
        _pw = int.from_bytes(bytes(_pw), "big")
    ok = await teleport_actor(
        conn, live_avatars, agent_bits, target, tuple(dest["xyz"]),
        globe_auid=int(_pw or 0), label="agent:Summon",
        manifest_suppress=manifest_suppress,
        force_scene_manifest_push=force_scene_manifest_push,
        peer_upright_euler=peer_upright_euler,
        _stamina_byte=_stamina_byte,
        retarget_bundle_to_avatar=retarget_bundle_to_avatar,
        broadcast_to_peers=broadcast_to_peers)
    if not ok:
        await notify(live_avatars, actor_auid,
                     "The summon could not be delivered.")
        return
    await _apply_arrival_bits(live_avatars, agent_bits, agent_rank, target,
                              pb2_last_cursor=pb2_last_cursor,
                              broadcast_to_peers=broadcast_to_peers)
    await notify(live_avatars, target, "You have been summoned by an agent.")
    await notify(live_avatars, actor_auid,
                 f"Summoned {victim.get('name') or f'0x{target:08x}'}. "
                 f"They must re-enter the world to arrive.")


async def on_teleport_longlat(payload: bytes, actor_auid: int, *,
                              conn: asyncpg.Connection,
                              live_avatars: dict,
                              agent_bits: dict,
                              agent_rank: dict,
                              pb2_last_cursor: dict,
                              manifest_suppress: set,
                              force_scene_manifest_push,
                              peer_upright_euler,
                              _stamina_byte,
                              retarget_bundle_to_avatar,
                              broadcast_to_peers) -> None:
    if not _gate(live_avatars, agent_rank, actor_auid, "TeleportLongLat"):
        return
    if len(payload) < 10:
        logger.warning('A 0xBF GoToLongLat body is %dB, too short to carry a longitude and latitude.', len(payload))
        return
    lon, lat = struct.unpack(">ff", payload[1:9])
    with_ride = bool(payload[9])
    actor = int(actor_auid) & 0xFFFFFFFF
    logger.info("0xBF GoToLongLat actor=0x%08x lon=%.4f lat=%.4f withRide=%s",
                actor, lon, lat, with_ride)
    entry = _actor_entry(live_avatars, actor)
    if entry is None:
        await notify(live_avatars, actor_auid, "You are not in a scene.")
        return
    xyz = _longlat_to_xyz(entry, lon, lat)
    if xyz is None:
        await notify(live_avatars, actor_auid,
                     "You must be on a world to use longitude/latitude.")
        return
    if not await teleport_actor(
            conn, live_avatars, agent_bits, actor, xyz,
            label="agent:GoToLongLat",
            manifest_suppress=manifest_suppress,
            force_scene_manifest_push=force_scene_manifest_push,
            peer_upright_euler=peer_upright_euler,
            _stamina_byte=_stamina_byte,
            retarget_bundle_to_avatar=retarget_bundle_to_avatar,
            broadcast_to_peers=broadcast_to_peers):
        await notify(live_avatars, actor_auid,
                     "The teleport could not be delivered.")
        return
    await _apply_arrival_bits(live_avatars, agent_bits, agent_rank, actor,
                              pb2_last_cursor=pb2_last_cursor,
                              broadcast_to_peers=broadcast_to_peers)
    await notify(live_avatars, actor_auid,
                 f"Teleported to {lon:.4f}, {lat:.4f}.")


def _longlat_to_xyz(entry, lon: float, lat: float
                    ) -> Optional[Tuple[float, float, float]]:
    cur = entry.get("xyz")
    if not cur:
        return None
    r = math.sqrt(sum(float(c) * float(c) for c in cur))
    if r <= 0.0:
        return None
    la = float(lat)
    lo = float(lon)
    return (r * math.cos(la) * math.cos(lo),
            r * math.cos(la) * math.sin(lo),
            r * math.sin(la))


async def teleport_to_world(conn: asyncpg.Connection, live_avatars: dict,
                            agent_bits: dict, agent_rank: dict,
                            actor_auid: int, globe_auid: int,
                            *, label: str = "agent-teleport",
                            pb2_last_cursor: dict,
                            manifest_suppress: set,
                            force_scene_manifest_push,
                            peer_upright_euler,
                            _stamina_byte,
                            retarget_bundle_to_avatar,
                            broadcast_to_peers) -> bool:
    actor = int(actor_auid) & 0xFFFFFFFF
    globe = int(globe_auid) & 0xFFFFFFFF
    entry = _actor_entry(live_avatars, actor)
    if entry is None:
        return False
    if not await is_walkable_globe(conn, globe):
        await notify(live_avatars, actor_auid,
                     f"Destination 0x{globe:08x} is not a world this server "
                     f"can build a scene on.")
        return False
    if not await teleport_actor(
            conn, live_avatars, agent_bits, actor, (0.0, 0.0, 0.0),
            globe_auid=globe, label=label,
            manifest_suppress=manifest_suppress,
            force_scene_manifest_push=force_scene_manifest_push,
            peer_upright_euler=peer_upright_euler,
            _stamina_byte=_stamina_byte,
            retarget_bundle_to_avatar=retarget_bundle_to_avatar,
            broadcast_to_peers=broadcast_to_peers):
        await notify(live_avatars, actor_auid,
                     "The scene rebuild failed. Re-enter the world to arrive.")
        return False
    await _apply_arrival_bits(live_avatars, agent_bits, agent_rank, actor,
                              pb2_last_cursor=pb2_last_cursor,
                              broadcast_to_peers=broadcast_to_peers)
    name, system = f"0x{globe:08x}", ""
    await notify(live_avatars, actor_auid,
                 f"Teleported to {name}"
                 f"{f' in {system}' if system else ''}. "
                 f"You arrive invisible.")
    return True


async def _move_actor_to_atom(conn: asyncpg.Connection, live_avatars: dict,
                              agent_bits: dict, agent_rank: dict,
                              actor_auid: int, target: int, with_ride: bool,
                              what: str, *,
                              pb2_last_cursor: dict,
                              manifest_suppress: set,
                              force_scene_manifest_push,
                              peer_upright_euler,
                              _stamina_byte,
                              retarget_bundle_to_avatar,
                              lookup_city_for_report,
                              broadcast_to_peers) -> None:
    actor = int(actor_auid) & 0xFFFFFFFF
    entry = _actor_entry(live_avatars, actor)
    if entry is None:
        await notify(live_avatars, actor_auid, "You are not in a scene.")
        return
    dest_entry = live_avatars.get(int(target) & 0xFFFFFFFF)
    if dest_entry is not None and dest_entry.get("xyz"):
        _pw = dest_entry.get("parent_world") or dest_entry.get("AP") or 0
        if isinstance(_pw, (bytes, bytearray)):
            _pw = int.from_bytes(bytes(_pw), "big")
        _dx, _dy, _dz = dest_entry["xyz"]
        ok = await teleport_actor(
            conn, live_avatars, agent_bits, actor,
            (float(_dx) + 1.5, _dy, _dz),
            globe_auid=int(_pw or 0), label=f"agent:{what}",
            manifest_suppress=manifest_suppress,
            force_scene_manifest_push=force_scene_manifest_push,
            peer_upright_euler=peer_upright_euler,
            _stamina_byte=_stamina_byte,
            retarget_bundle_to_avatar=retarget_bundle_to_avatar,
            broadcast_to_peers=broadcast_to_peers)
        if not ok:
            await notify(live_avatars, actor_auid,
                         "The teleport could not be delivered.")
            return
        await _apply_arrival_bits(live_avatars, agent_bits, agent_rank, actor,
                                  pb2_last_cursor=pb2_last_cursor,
                                  broadcast_to_peers=broadcast_to_peers)
        await notify(live_avatars, actor_auid,
                     f"Teleport set to {dest_entry.get('name') or 'the avatar'}. "
                     f"Re-enter the world to arrive.")
        return
    city_id, info = await lookup_city_for_report(int(target) & 0xFFFFFFFF)
    if info is not None:
        xyz = info.get("xyz") or info.get("location")
        if xyz:
            ok = await teleport_actor(
                conn, live_avatars, agent_bits, actor, tuple(xyz),
                label=f"agent:{what}",
                manifest_suppress=manifest_suppress,
                force_scene_manifest_push=force_scene_manifest_push,
                peer_upright_euler=peer_upright_euler,
                _stamina_byte=_stamina_byte,
                retarget_bundle_to_avatar=retarget_bundle_to_avatar,
                broadcast_to_peers=broadcast_to_peers)
            if not ok:
                await notify(live_avatars, actor_auid,
                             "The teleport could not be delivered.")
                return
            await _apply_arrival_bits(
                live_avatars, agent_bits, agent_rank, actor,
                pb2_last_cursor=pb2_last_cursor,
                broadcast_to_peers=broadcast_to_peers)
            await notify(live_avatars, actor_auid,
                         f"Teleport set to {info.get('name', 'the city')}. "
                         f"Re-enter the world to arrive.")
            return
    if await is_walkable_globe(conn, int(target)):
        await teleport_to_world(
            conn, live_avatars, agent_bits, agent_rank, actor_auid,
            int(target), label=f"agent:{what}",
            pb2_last_cursor=pb2_last_cursor,
            manifest_suppress=manifest_suppress,
            force_scene_manifest_push=force_scene_manifest_push,
            peer_upright_euler=peer_upright_euler,
            _stamina_byte=_stamina_byte,
            retarget_bundle_to_avatar=retarget_bundle_to_avatar,
            broadcast_to_peers=broadcast_to_peers)
        return
    logger.info("%s: destination 0x%08x was not found (not an on-line "
                "avatar, not a simulated city, not a walkable globe).",
                what, int(target))
    await notify(live_avatars, actor_auid,
                 f"Destination 0x{int(target):08x} was not found. After 3 "
                 f"minutes the agent teleport is redirected to the capital "
                 f"city of a randomly selected empire.")


async def on_unimplemented(payload: bytes, actor_auid: int, *,
                           live_avatars: dict) -> None:
    op = payload[0] if payload else 0
    what = _UNIMPLEMENTED.get(op, f"opcode 0x{op:02X}")
    logger.info("0x%02X %s: decoded, not implemented (len=%dB) %s",
                op, what, len(payload), payload[:32].hex())
    await notify(live_avatars, actor_auid,
                 f"{what} is not implemented on this server.")


CHAT_DIRECT_HANDLERS: dict = {
    0xB4: ("ToggleAgentBits", on_toggle_agent_bits),
    0xBB: ("AgentEncounter", on_encounter),
    0xBC: ("AgentEnvironment", on_environment),
    0xBD: ("ChangeSystemGenHab", on_change_system_gen_hab),
    0xBF: ("AgentTeleportLongLat", on_teleport_longlat),
    0xC1: ("AgentKillAnimals", on_kill_animals),
    0xC6: ("AgentResetStory", on_reset_story),
    0xC7: ("AgentChangeMyDNA", on_change_my_dna),
    0xC8: ("AgentSummon", on_summon),
    0x77: ("AgentRecoverShip", on_unimplemented),
    0xB5: ("AgentCapacitor", on_unimplemented),
    0xB6: ("AgentScuttle", on_unimplemented),
    0xC5: ("AgentRefuelRepair", on_unimplemented),
}


def describe() -> str:
    live = sorted(k for k, v in CHAT_DIRECT_HANDLERS.items()
                  if v[1] is not on_unimplemented)
    inert = sorted(k for k, v in CHAT_DIRECT_HANDLERS.items()
                   if v[1] is on_unimplemented)
    return (f"[agent] {len(live)} live opcodes "
            f"({', '.join(f'0x{o:02X}' for o in live)}); "
            f"{len(inert)} decoded-only "
            f"({', '.join(f'0x{o:02X}' for o in inert)})")
