
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.world import _fauna_terrain_for_world
from openshores.gameplay import damageable as _fauna_dmg
from openshores.gameplay.fauna_placement import (
    _FAUNA_BODY_OFFSET,
    _fauna_align,
)
from openshores.gameplay.natives.village import project_to_terrain as _proj
from openshores.gameplay.worldgen.planet_fauna_gen import (
    ensure_schema as _fauna_ensure_schema,
    is_planet_habitable as _fauna_is_habitable,
    register_species as _fauna_register_species,
    roll_individuals as _roll_individuals,  # type: ignore
    roll_planet_roster as _fauna_roll_roster,
)
from openshores.protocol.atoms.daanimal import (
    pack_animal_spawn as _pack_animal_spawn,
)
from openshores.protocol.dhdna import AuDice as _DnaDice

logger = get_logger(__name__)


_FAUNA_TERRAIN_CACHE: dict = {}


async def _fauna_ground(conn, xyz, world_auid):
    terrain, size = await _fauna_terrain_for_world(
        conn, world_auid, cache=_FAUNA_TERRAIN_CACHE)
    if not (terrain and size):
        return tuple(float(v) for v in xyz)
    try:
        return _proj(tuple(xyz), terrain, int(size),
                     body_offset=_FAUNA_BODY_OFFSET)
    except Exception as exc:
        logger.debug('[fauna] terrain projection on 0x%08x refused (%r).',
                     int(world_auid) & 0xFFFFFFFF, exc)
        return tuple(float(v) for v in xyz)


_FAUNA_WORLD_STATE: dict = {}

_FAUNA_NEXT_IND: dict = {}


async def _build_fauna_entries(conn, planet_auid_int, save, atm_type,
                               atm_dens, water, spawn_xyz, *,
                               _DYNAMIC_SCENE_AUIDS):
    globe_row = {
        "id":         planet_auid_int,
        "orbitZone":  bytes([int(save.planet_zone or 0) & 0xff]),
        "atmType":    bytes([int(atm_type or 0) & 0xff]),
        "atmDensity": bytes([int(atm_dens or 0) & 0xff]),
        "water":      bytes([int(water or 0) & 0xff]),
    }
    hab = _fauna_is_habitable(globe_row)
    if not hab:
        logger.info(f'[fauna] planet not habitable (zone={int(save.planet_zone or 0)} atm={atm_type} water={water}).')
        return []
    roster = _fauna_roll_roster(globe_row,
                                planet_auid=planet_auid_int, force=False)
    per_species = 3
    max_total = 20
    jitter = 30.0
    logger.info(f"[fauna] habitable={hab} force=False roster={len(roster)} "
                f"per-species={per_species} cap={max_total} jitter={jitter:.1f}m")
    try:
        await _fauna_ensure_schema(conn)
    except Exception as exc:
        logger.error(f"[fauna] ensure_schema fail: {exc!r}")
    for sp_idx, entry in enumerate(roster):
        name = f"Specie_{sp_idx:02x}_{planet_auid_int:06x}"
        try:
            await _fauna_register_species(conn, entry.dna, name,
                                          creator_id=int(save.person_auid))
        except Exception as exc:
            logger.error(f"[fauna]   z_Specie register fail: {exc!r}")
    dice = _DnaDice(seed=planet_auid_int or 1)
    individuals = _roll_individuals(
        roster,
        spawn_anchor_xyz=spawn_xyz,
        dice=dice,
        per_species=per_species,
        max_total=max_total,
        jitter_m=jitter,
        land_value=50)
    _FAUNA_WORLD_STATE[int(planet_auid_int) & 0xFFFFFFFF] = {
        "roster": roster,
        "land_value": 50,
        "max_total": max_total,
        "per_species": per_species,
        "jitter_m": jitter,
    }

    entries = []
    _fauna_registered = 0
    for ind in individuals:
        sp_name = f"Specie_{ind.species_idx:02x}_{planet_auid_int:06x}"
        auid = (0xC0000000
                | ((ind.species_idx & 0xff) << 16)
                | (ind.individual_idx & 0xffff))
        _k = (int(planet_auid_int) & 0xFFFFFFFF, ind.species_idx & 0xFF)
        _FAUNA_NEXT_IND[_k] = max(_FAUNA_NEXT_IND.get(_k, 0),
                                  (ind.individual_idx & 0xFFFF) + 1)
        try:
            _fauna_dmg.register(
                auid, kind=_fauna_dmg.KIND_ANIMAL,
                name=f"{sp_name}#{ind.individual_idx}",
                dna=ind.dna.to_bytes(),
                max_hp=int(ind.max_hp),
                world_auid=planet_auid_int,
                xyz=ind.xyz)
            _fauna_registered += 1
        except Exception as _frx:
            logger.error(f"[fauna]   damageable register failed for "
                         f"0x{auid:08x}: {_frx!r}")
        _DYNAMIC_SCENE_AUIDS.add(auid)
        pkt = _pack_animal_spawn(
            auid=auid,
            parent_planet_auid=planet_auid_int,
            dna_bytes=ind.dna.to_bytes(),
            xyz=ind.xyz,
            rotation=_fauna_align(ind.xyz, float(ind.yaw_rad)),
            hp=ind.hp, max_hp=ind.max_hp,
            stamina=ind.stamina, pose=ind.pose,
            sex=ind.sex)
        entries.append(
            (f"DaAnimal/{sp_name}#{ind.individual_idx}", pkt))
    if _fauna_registered:
        logger.info(f"[fauna] {_fauna_registered} animal(s) registered as "
                    f"huntable (kill -> carcass -> skin).")
    return entries
