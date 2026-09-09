
from __future__ import annotations

import functools
import inspect
import os as _os
import time as _time
from typing import Any, Callable, Iterable, Mapping

from openshores.core.accounts import default_store, ensure_default_account
from openshores.core.config import Config
from openshores.core.logging import configure, get_logger
from openshores.core.pid_file import install_pid_file
from openshores.database.blueprint_seed import seed_if_empty
from openshores.network.scene_probes import install_generated_probes
from openshores.core.wiring import bind, requirements
from openshores.database import journal as _persist_queue
from openshores.database import pool as _pool
from openshores.database.migrations.runner import init_db
from openshores.database.repositories.avatar_roster import _persons_that_exist
from openshores.database.repositories.bd_row import (_bd_row_by_auid,
                                                     _bd_rows_for_empire)
from openshores.database.repositories.bundle import build_bundle
from openshores.database.repositories.bundle_retarget import (
    _retarget_bundle_to_avatar)
from openshores.database.repositories.city_buildings import _city_identity
from openshores.database.repositories.demolish import (_demolish_db_lookup,
                                                       _demolish_delete_bd_row)
from openshores.database.repositories.person import (_resolve_person_id,
                                                     _session_login_ms)
from openshores.gameplay.actor_cursor import (_ACTOR_CURSOR, _ACTOR_CYCLE,
                                              _ACTOR_INDEX, _ACTOR_LAST_ADV)
from openshores.gameplay.agent_powers import agent_bits_for
from openshores.gameplay.agent_registry import (_AGENT_BITS,
                                               _AGENT_RANK,
                                               _DNA_OVERRIDE,
                                               _INDIGENOUS_DNA_BY_WORLD,
                                               _STORY_PROGRESS,
                                               _SYSTEM_GEN_HAB)
from openshores.gameplay.augear_registry import (_AUGEAR_STATES,
                                                 _get_augear)
from openshores.gameplay.avatar_dna import _dna_for_actor
from openshores.gameplay.avatar_picker import (_resolve_avatar_record,
                                               build_login_ok_reply)
from openshores.gameplay.avatar_registry import _live_avatars, _tock_state
from openshores.gameplay.bio_bytes import _stamina_byte
from openshores.gameplay.build_materials import effective_build_material
from openshores.gameplay.building_registry import (_BUILDING_KEEPALIVE_TASKS,
                                                   _SPAWNED_BUILDINGS)
from openshores.gameplay.city.sky import _make_is_dark
from openshores.gameplay.city.zone_cache import _ZONE_CACHE
from openshores.gameplay.city_founding import _find_city_for_building
from openshores.gameplay.city_info import _city_info_from_row
from openshores.gameplay.city_persist import (_city_buildings_blob_io,
                                              found_city,
                                              found_town_square)
from openshores.gameplay.city_registry import (_CITY_KEEPALIVE_TASKS, _CITY_SIM,
                                               _SPAWNED_CITIES)
from openshores.gameplay.city_sim_loops import (_city_development_loop,
                                                _city_sim_manager)
from openshores.gameplay.combat.damage import (_apply_damage,
                                               _register_damageable_npcs)
from openshores.gameplay.condition_registry import _CONDITION_STATES
from openshores.gameplay.dev_building import _design_reports_for, _dev_to_building
from openshores.gameplay.dispatch import OPCODE_HANDLERS
from openshores.gameplay.empire_state import (_CITIZEN_EMPIRE_OVERRIDE,
                                              _EMPIRE_ANNOUNCEMENTS,
                                              _EMPIRE_DIPLO_LOG,
                                              _EMPIRE_NAME_OVERRIDE,
                                              _EMPIRE_TAX_OVERRIDE,
                                              _PENDING_CITY_SURRENDERS,
                                              _PENDING_EMPIRE_INVITES,
                                              _WORLD_NAME_OVERRIDE)
from openshores.gameplay.fauna_placement import _fauna_align
from openshores.gameplay.fauna_world import (_FAUNA_NEXT_IND,
                                             _FAUNA_TERRAIN_CACHE,
                                             _FAUNA_WORLD_STATE, _fauna_ground)
from openshores.gameplay.gd_commodity_scan import (CONTAINER_CAPACITIES,
                                                   CONTAINER_CIDS, USE_FOOD_CIDS)
from openshores.gameplay.gear_slots import _can_hold_item
from openshores.gameplay.ground_registry import _DROPPED_ITEMS
from openshores.gameplay.ground_snap import _peer_upright_euler
from openshores.gameplay import industry_hooks as _industry_hooks
from openshores.gameplay.natives.heal import _nc_heal_hook
from openshores.gameplay.natives.village import _IDLE_BODIES
from openshores.gameplay.npc_body import (_install_native_conversation_hooks,
                                          _nc_hp_provider)
from openshores.gameplay.person_zone import _person_zone
from openshores.gameplay.planet_geo_store import (_gather_planet_roads,
                                                  _get_or_init_planet_geo)
from openshores.gameplay.scene_manifest import _DYNAMIC_SCENE_AUIDS
from openshores.gameplay.seachest_registry import _SEACHEST_STATES
from openshores.gameplay.selfie_state import _SELFIE_LAST_AT
from openshores.gameplay.starmap_cache import _get_starmap_blob
from openshores.gameplay.story_npc import TARGOSS_NAME, _atom_id, _NPCS
from openshores.gameplay.vehicle_registry import (_PENDING_DISMOUNT,
                                                  _PLAYER_MOUNTED_VEHICLE,
                                                  _VEH_LAST_BROADCAST_POS,
                                                  _VEH_PARENT_WATCH)
from openshores.gameplay.world_atoms import _WORLD_ATOM_AUIDS
from openshores.gameplay.worldgen import terrain as _terrain
from openshores.gameplay.worldgen import world_chain as _world_chain
from openshores.gameplay.worldgen import world_clock as _world_clock
from openshores.gameplay.worldgen.first_run import ensure_universe
from openshores.gameplay.worldgen.primeval_gen import HAB_RANDOM, gen_moon, gen_planet
from openshores.network import boot as _boot
from openshores.network.active_chat_writer import (_ACTIVE_CHAT_WRITER,
                                                   set_active_chat_writer)
from openshores.network.active_item import _active_advance, pb2_last_cursor
from openshores.network.agent import CHAT_DIRECT_HANDLERS as CHAT_DIRECT_HANDLERS_AGENT
from openshores.network.aucomm_dispatch import AUCOMM_HANDLERS
from openshores.network.augear_refresh import _push_augear_refresh_for
from openshores.network.broadcast import (_broadcast_to_peers,
                                          _force_scene_manifest_push,
                                          _MANIFEST_SUPPRESS)
from openshores.network.building_restore import _restore_persisted_buildings
from openshores.network.building_spawn import spawn_city_building
from openshores.network.chat_broadcast import _broadcast_AuCommChat
from openshores.network.chat_channel import connection as _chat_channel
from openshores.network.chat_empire_dispatch import CHAT_DIRECT_EMPIRE_HANDLERS
from openshores.network.chat_state import (_CHAT_UNKNOWN_COUNTS,
                                           _CHAT_UNKNOWN_PRINT_EVERY_N,
                                           _CHAT_UNKNOWN_PRINT_FIRST_N,
                                           _PENDING_CHAT_AUIDS)
from openshores.network.city_restore import _restore_persisted_cities
from openshores.network.construction_ops import on_chat_construction_op
from openshores.network.construction_work import apply_construction_labor
from openshores.network.demolish_ops import on_chat_demolish
from openshores.network.empire_mutation_dispatch import \
    CHAT_DIRECT_HANDLERS as CHAT_DIRECT_HANDLERS_EMPIRE_MUTATIONS
from openshores.network.empire_mutation_dispatch import loop_built_entries
from openshores.network.empire_policy_ops import _rebroadcast
from openshores.network.flag_spawn import spawn_world_flag
from openshores.network.forage import _execute_forage
from openshores.network.legacy_actor_globals import (_PARENT_WORLD_AUID,
                                                     _PLAYER_AUID)
from openshores.network.login_dispatch import _dispatch_login
from openshores.network.login_listener import handle_login
from openshores.network.mail_server import handle_mail
from openshores.network.manufacture_ops import _mfg_environment_loop
from openshores.network.pickup import _execute_pickup
from openshores.network.pickup_speculation import _pickup_speculation_loop
from openshores.network.planet_geo_resend import resend_planet_geo
from openshores.network.road_ticker import ensure_road_construction_ticker
from openshores.network.scene import connection as _scene_channel
from openshores.network.session_usernames import _session_usernames_by_ip
from openshores.network.state_dump import (_install_dump_state_signal_handler,
                                           dump_server_state)
from openshores.network.udp_server import _udp_start
from openshores.network.vehicle_lifecycle import (_finalize_vehicle_dismount,
                                                 grant_crafted_vehicle)
from openshores.network.vehicle_loops import _VEH_KEEPALIVE_TASKS
from openshores.network.vehicle_terrain import (_VEH_PARENT_FLOOR,
                                                _veh_note_ground_radius)
from openshores.network.weapon_fire import _handle_fire_weapon_trigger
from openshores.network.weapon_reload import _handle_reload_weapon_trigger
from openshores.protocol.atoms.daanimal import pack_animal_spawn
from openshores.protocol.atoms.person import _build_augear_only_daperson_update
from openshores.protocol.login_reply import _default_dna
from openshores.world.save_bundle import SaveBundle, SiblingGlobe
from openshores.world.sim_time import _bootstrap_sim_time_anchor
from openshores.world.sim_time_low import _next_effect_time_ms

logger = get_logger(__name__)


class RootError(Exception):
    pass


class UnboundDependencies(RootError):
    pass


class Registry:

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._gaps: dict[str, str] = {}


    def value(self, name: str, value: Any, *, also: Iterable[str] = ()) -> None:
        if _declares_dependencies(value) and self._blocked(name, value, also):
            return
        for n in (name, *also):
            self._fresh(n)
            self._values[n] = value

    def gap(self, name: str, reason: str, *, also: Iterable[str] = ()) -> None:
        for n in (name, *also):
            self._fresh(n)
            self._gaps[n] = reason

    def partial(self, name: str, fn: Callable[..., Any], *,
                positional: tuple = (),
                also: Iterable[str] = ()) -> None:
        if self._blocked(name, fn, also):
            return
        bound = functools.partial(
            fn, *positional,
            **{n: self._values[n] for n in requirements(fn)})
        self.value(name, bound, also=also)

    def pooled_partial(self, name: str, fn: Callable[..., Any], *,
                       pool: Any, conn_first: bool = False,
                       also: Iterable[str] = ()) -> None:
        if self._blocked(name, fn, also):
            return
        deps = {n: self._values[n] for n in requirements(fn) if n != "conn"}

        async def _on_its_own_connection(*args, **kwargs):
            async with pool.acquire() as conn:
                if conn_first:
                    return await fn(conn, *args, **deps, **kwargs)
                return await fn(*args, conn=conn, **deps, **kwargs)

        _on_its_own_connection.__name__ = getattr(fn, "__name__", name)
        _on_its_own_connection.__qualname__ = getattr(fn, "__qualname__", name)
        self.value(name, _on_its_own_connection, also=also)

    def _blocked(self, name: str, fn: Callable[..., Any],
                 also: Iterable[str]) -> bool:
        need = requirements(fn)
        unregistered = [d for d in need
                        if d not in self._values and d not in self._gaps]
        if unregistered:
            raise RootError(
                f"{name}: {_qual(fn)} declares "
                + ", ".join(repr(d) for d in unregistered)
                + f", which the composition root neither supplies nor records "
                  f"as a gap. Add {'them' if len(unregistered) > 1 else 'it'} "
                  f"to build_registry -- either a supplier or a gap(), never "
                  f"silence.")
        blocked = [d for d in need if d in self._gaps]
        if blocked:
            rest = ("" if len(blocked) == 1 else
                    f" (and {len(blocked) - 1} more of its declared names: "
                    f"{', '.join(blocked[1:])})")
            self.gap(name,
                     f"needs {blocked[0]}, which {self._gaps[blocked[0]]}"
                     + rest, also=also)
            return True
        return False

    def _fresh(self, name: str) -> None:
        if name in self._values or name in self._gaps:
            raise RootError(
                f'{name!r} is registered twice in the composition root.')


    def __contains__(self, name: str) -> bool:
        return name in self._values

    def get(self, name: str) -> Any:
        if name in self._values:
            return self._values[name]
        if name in self._gaps:
            raise UnboundDependencies(
                f"Cannot bind {name}: it {self._gaps[name]}")
        raise RootError(
            f"{name!r} is not registered in the composition root at all")

    def why(self, name: str) -> str:
        return self._gaps[name]

    def supplied(self) -> tuple[str, ...]:
        return tuple(sorted(self._values))

    def gaps(self) -> Mapping[str, str]:
        return dict(self._gaps)


def _qual(fn: Callable[..., Any]) -> str:
    return getattr(fn, "__qualname__", None) or repr(fn)


def _declares_dependencies(value: Any) -> bool:
    if not (inspect.isroutine(value) or isinstance(value, functools.partial)):
        return False
    return bool(requirements(value))


_IN_LEGACY_HANDLE_SCENE = (
    "is a local inside the legacy handle_scene, with no top-level "
    "definition in either tree")


def _legacy_global(where: str) -> str:
    return (f"is an unported legacy module global at {where}; it needs a "
            f"module to own it, as gameplay/avatar_registry.py owns "
            f"_live_avatars")


def _no_filled_bundle(attr: str, evidence: str) -> str:
    return (f"is `_SAVE.{attr}` under another spelling ({evidence}). "
            f"--check-wiring has no database, so no filled bundle exists; "
            f"serve fills one first and this binds on a real boot")


def _not_a_boot_value(attr: str, evidence: str, why: str) -> str:
    return (f"is `_SAVE.{attr}` under another spelling ({evidence}), and a "
            f"filled bundle does not make it bindable: {why}. Freezing the "
            f"scalar here would report green and be wrong")


def _no_boot_anchor(legacy_global: str) -> str:
    return (f"is the legacy global at {legacy_global}, computed at boot. "
            f"serve computes it and binds it on a real boot; --check-wiring "
            f"has no database to compute it from")

_DAITEM_AUID_BASE = 0x70000000

BOOT_ARGUMENTS: tuple[str, ...] = requirements(_boot.main)

WORLD_QUERY_VALUES: dict[str, Any] = {
    "SiblingGlobe": SiblingGlobe,
    "gen_planet": gen_planet,
    "gen_moon": gen_moon,
    "HAB_RANDOM": HAB_RANDOM,
    "wch": _world_chain,
    "wc": _world_clock,
    "tr": _terrain,
}


def _handler_of(entry: Any) -> Callable[..., Any]:
    return entry[-1] if isinstance(entry, tuple) else entry


def _rebuilt(entry: Any, route: Callable[..., Any]) -> Any:
    return entry[:-1] + (route,) if isinstance(entry, tuple) else route


def bind_family(handlers: Mapping[Any, Any], providers: Mapping[str, Any],
                *, expect: set) -> dict:
    routes = bind({k: _handler_of(v) for k, v in handlers.items()},
                  providers, expect=expect)
    return {k: _rebuilt(handlers[k], routes[k]) for k in routes}


FAMILIES: dict[str, Any] = {
    "OPCODE_HANDLERS": OPCODE_HANDLERS,
    "AUCOMM_HANDLERS": AUCOMM_HANDLERS,
    "CHAT_DIRECT_EMPIRE_HANDLERS": CHAT_DIRECT_EMPIRE_HANDLERS,
    "CHAT_DIRECT_HANDLERS_EMPIRE_MUTATIONS": CHAT_DIRECT_HANDLERS_EMPIRE_MUTATIONS,
    "CHAT_DIRECT_HANDLERS_AGENT": CHAT_DIRECT_HANDLERS_AGENT,
}


FAMILY_EXTRAS: dict[str, Callable[..., Mapping[Any, Any]]] = {
    "CHAT_DIRECT_HANDLERS_EMPIRE_MUTATIONS": loop_built_entries,
}


def family_requirements(name: str) -> tuple[str, ...]:
    need: set[str] = set()
    for entry in FAMILIES[name].values():
        need |= set(requirements(_handler_of(entry)))
    extra = FAMILY_EXTRAS.get(name)
    if extra is not None:
        need |= set(requirements(extra))
    return tuple(sorted(need))


def build_registry(*, config: Config, conn: Any, pool: Any,
                   save: SaveBundle | None,
                   anchor: tuple[int, int] | None) -> Registry:
    if isinstance(conn, _pool.RAW_CONNECTION_TYPES):
        raise TypeError(
            'build_registry was handed a raw asyncpg connection.')
    reg = Registry()

    def _boot_default(name: str, attr: str, evidence: str) -> None:
        if save is None:
            reg.gap(name, _no_filled_bundle(attr, evidence))
        else:
            reg.value(name, getattr(save, attr))

    def _boot_anchor(name: str, index: int, legacy_global: str,
                     *, also: Iterable[str] = ()) -> None:
        if anchor is None:
            reg.gap(name, _no_boot_anchor(legacy_global), also=also)
        else:
            reg.value(name, anchor[index], also=also)

    def _boot_seed(name: str, attr: str, evidence: str,
                   seed: Callable[[SaveBundle], Any],
                   *, also: Iterable[str] = ()) -> None:
        if save is None:
            reg.gap(name, _no_filled_bundle(attr, evidence), also=also)
        else:
            reg.value(name, seed(save), also=also)

    reg.value("conn", conn)
    reg.value("pool", pool)
    reg.value("PUBLIC_HOST", config.deployment.public_host)
    reg.value("report_dir", config.deployment.report_dir)
    reg.value("_live_avatars", _live_avatars, also=("live_avatars",))
    reg.value("_tock_state", _tock_state, also=("tock_state",))
    reg.value("_DROPPED_ITEMS", _DROPPED_ITEMS)
    reg.value("_DYNAMIC_SCENE_AUIDS", _DYNAMIC_SCENE_AUIDS)
    reg.value("_WORLD_ATOM_AUIDS", _WORLD_ATOM_AUIDS)
    reg.value("_VEH_KEEPALIVE_TASKS", _VEH_KEEPALIVE_TASKS)
    reg.value("_SPAWNED_CITIES", _SPAWNED_CITIES)
    reg.value("_CITY_KEEPALIVE_TASKS", _CITY_KEEPALIVE_TASKS)
    reg.value("_CITY_SIM", _CITY_SIM, also=("city_sim",))
    reg.value("_SPAWNED_BUILDINGS", _SPAWNED_BUILDINGS,
              also=("spawned_buildings",))
    reg.value("_BUILDING_KEEPALIVE_TASKS", _BUILDING_KEEPALIVE_TASKS)
    reg.value("_ZONE_CACHE", _ZONE_CACHE)
    reg.value("_PENDING_CHAT_AUIDS", _PENDING_CHAT_AUIDS)
    reg.value("_CHAT_UNKNOWN_COUNTS", _CHAT_UNKNOWN_COUNTS)
    reg.value("_CHAT_UNKNOWN_PRINT_FIRST_N", _CHAT_UNKNOWN_PRINT_FIRST_N)
    reg.value("_CHAT_UNKNOWN_PRINT_EVERY_N", _CHAT_UNKNOWN_PRINT_EVERY_N)
    reg.value("_MANIFEST_SUPPRESS", _MANIFEST_SUPPRESS,
              also=("manifest_suppress",))
    reg.value("_PLAYER_MOUNTED_VEHICLE", _PLAYER_MOUNTED_VEHICLE)
    reg.value("_PENDING_DISMOUNT", _PENDING_DISMOUNT)
    reg.value("_VEH_LAST_BROADCAST_POS", _VEH_LAST_BROADCAST_POS)
    reg.value("_VEH_PARENT_WATCH", _VEH_PARENT_WATCH)
    reg.value("_CITIZEN_EMPIRE_OVERRIDE", _CITIZEN_EMPIRE_OVERRIDE)
    reg.value("_EMPIRE_TAX_OVERRIDE", _EMPIRE_TAX_OVERRIDE)
    reg.value("_EMPIRE_NAME_OVERRIDE", _EMPIRE_NAME_OVERRIDE)
    reg.value("_EMPIRE_ANNOUNCEMENTS", _EMPIRE_ANNOUNCEMENTS)
    reg.value("_WORLD_NAME_OVERRIDE", _WORLD_NAME_OVERRIDE)
    reg.value("_EMPIRE_DIPLO_LOG", _EMPIRE_DIPLO_LOG)
    reg.value("_PENDING_CITY_SURRENDERS", _PENDING_CITY_SURRENDERS)
    reg.value("_PENDING_EMPIRE_INVITES", _PENDING_EMPIRE_INVITES)
    reg.value("_SELFIE_LAST_AT", _SELFIE_LAST_AT)
    reg.value("_CONDITION_STATES", _CONDITION_STATES,
              also=("condition_states",))
    reg.value("_session_usernames_by_ip", _session_usernames_by_ip,
              also=("session_usernames_by_ip",))
    reg.value("_session_login_ms", _session_login_ms,
              also=("session_login_ms",))
    reg.value("pb2_last_cursor", pb2_last_cursor)
    reg.value("CONTAINER_CIDS", CONTAINER_CIDS)
    reg.value("CONTAINER_CAPACITIES", CONTAINER_CAPACITIES)
    reg.value("USE_FOOD_CIDS", USE_FOOD_CIDS)
    reg.value("pack_animal_spawn", pack_animal_spawn)

    for _name, _value in WORLD_QUERY_VALUES.items():
        reg.value(_name, _value)

    reg.value("idle_bodies", _IDLE_BODIES, also=("natives_idle_bodies",))
    reg.value("story_npcs", _NPCS)
    reg.value("story_atom_id", _atom_id())
    reg.value("story_name", TARGOSS_NAME)

    reg.value("fauna_align", _fauna_align)
    reg.value("fauna_ground", _fauna_ground)
    reg.value("fauna_next_ind", _FAUNA_NEXT_IND)
    reg.value("fauna_terrain_cache", _FAUNA_TERRAIN_CACHE)
    reg.value("fauna_world_state", _FAUNA_WORLD_STATE)

    reg.value("scene_connect_n_by_ip", {}, also=("_scene_connect_n_by_ip",))
    reg.value("variant_b_handled_by_ip", {},
              also=("_variant_b_handled_by_ip",))
    reg.value("force_closed_once_by_ip", {})

    reg.value("_resolve_person_id", _resolve_person_id,
              also=("resolve_person_id",))
    reg.value("_peer_upright_euler", _peer_upright_euler,
              also=("peer_upright_euler",))
    reg.value("_broadcast_to_peers", _broadcast_to_peers,
              also=("broadcast_to_peers",))
    reg.value("_can_hold_item", _can_hold_item)
    reg.value("agent_bits_for",
              functools.partial(agent_bits_for, _AGENT_BITS))
    reg.value("effective_build_material", effective_build_material)
    reg.partial("hp_provider", _nc_hp_provider)
    reg.partial("apply_damage", _apply_damage)
    # conversation.heal_hook is the slot these get installed into and is None at
    # import. Bind that name and the doctor talks with no heal behind it.
    reg.partial("heal_hook", _nc_heal_hook)
    reg.value("industry_hooks", _industry_hooks)
    reg.value("handle_mail", handle_mail)

    reg.value("_AUGEAR_STATES", _AUGEAR_STATES, also=("augear_states",))
    reg.value("_get_augear", _get_augear)
    reg.value("_SEACHEST_STATES", _SEACHEST_STATES)
    reg.value("_ACTOR_CURSOR", _ACTOR_CURSOR, also=("actor_cursor",))
    reg.value("_ACTOR_INDEX", _ACTOR_INDEX, also=("actor_index",))
    reg.value("_ACTOR_CYCLE", _ACTOR_CYCLE, also=("actor_cycle",))
    reg.value("_ACTOR_LAST_ADV", _ACTOR_LAST_ADV, also=("actor_last_adv",))
    reg.value("_AGENT_BITS", _AGENT_BITS, also=("agent_bits",))
    reg.value("_AGENT_RANK", _AGENT_RANK, also=("agent_rank",))
    reg.value("_VEH_PARENT_FLOOR", _VEH_PARENT_FLOOR)
    reg.value("_veh_note_ground_radius", _veh_note_ground_radius)
    reg.value("_PLAYER_AUID", _PLAYER_AUID)
    reg.value("_PARENT_WORLD_AUID", _PARENT_WORLD_AUID)
    reg.value("set_active_chat_writer", set_active_chat_writer)
    reg.value("_ACTIVE_CHAT_WRITER", _ACTIVE_CHAT_WRITER)

    _daitem_auid_next = [_DAITEM_AUID_BASE]

    def alloc_daitem_auid() -> int:
        auid = _daitem_auid_next[0]
        _daitem_auid_next[0] = auid + 1
        return auid

    def raise_daitem_auid_floor(n: int) -> None:
        if n > _daitem_auid_next[0]:
            _daitem_auid_next[0] = n

    reg.value("alloc_daitem_auid", alloc_daitem_auid)
    reg.value("raise_daitem_auid_floor", raise_daitem_auid_floor)

    reg.value("_FIRST_FRAME_WAIT_SEC", 300.0)
    reg.value("_SHOW_ACKS", bool(config.deployment.show_acks))
    reg.value("SCENE_PROBE_NAME", str(config.deployment.scene_probe))

    reg.value("_SAVE", save if save is not None else SaveBundle(),
              also=("save", "bundle"))


    reg.gap("_manifest_refresh", _IN_LEGACY_HANDLE_SCENE)


    reg.gap("_conn_tasks",
            "is Session state, not a root binding: src/openshores/world/session.py:93 "
            "holds it and handle_scene hands each ticker its own connection's "
            "list. One list bound here would be shared by every connection")


    _boot_seed("last_avatar_dna", "person_dna24",
               "server_stub.py:9816 `_last_avatar_dna: bytes = "
               "bytes(_SAVE.person_dna24 or _default_dna())`",
               lambda s: bytes(s.person_dna24 or _default_dna()),
               also=("_last_avatar_dna",))
    _boot_seed("last_avatar_name", "person_name",
               "server_stub.py:9848 `_last_avatar_name: str = "
               "_SAVE.person_name`",
               lambda s: s.person_name,
               also=("_last_avatar_name",))
    _boot_default("name_long", "empire_name", "server_stub.py:7243")
    _boot_default("name_short", "empire_name_short", "server_stub.py:7244")
    _boot_default("capital_name", "capital_name", "server_stub.py:7245")
    _boot_anchor("anchor_full", 0, "server_stub.py:2781",
                 also=("sim_time_anchor_full",))


    _boot_anchor("anchor_low32", 1, "server_stub.py:2782")
    _effect_emit_state: dict = {"counter": 0}
    reg.value("effect_emit_state", _effect_emit_state)
    _sim_time_state: dict = {"last_0x18_t_low": 0}
    reg.value("sim_time_state", _sim_time_state)
    reg.value("_INDIGENOUS_DNA_BY_WORLD", _INDIGENOUS_DNA_BY_WORLD,
              also=("indigenous_dna_by_world",))
    reg.value("_SYSTEM_GEN_HAB", _SYSTEM_GEN_HAB, also=("system_gen_hab",))
    reg.value("_STORY_PROGRESS", _STORY_PROGRESS, also=("story_progress",))
    reg.value("_DNA_OVERRIDE", _DNA_OVERRIDE, also=("dna_override",))

    reg.partial("gather_planet_roads", _gather_planet_roads,
                positional=(conn,))
    reg.partial("get_or_init_planet_geo", _get_or_init_planet_geo,
                positional=(conn,))
    if "anchor_full" in reg and "anchor_low32" in reg:
        _anchor_full = reg.get("anchor_full")
        _anchor_low32 = reg.get("anchor_low32")

        def next_effect_time_ms() -> int:
            return _next_effect_time_ms(
                anchor_full=_anchor_full,
                anchor_low32=_anchor_low32,
                last_0x18_t_low=_sim_time_state["last_0x18_t_low"],
                effect_emit_state=_effect_emit_state)

        reg.value("next_effect_time_ms", next_effect_time_ms)
    else:
        reg.gap("next_effect_time_ms",
                f"needs anchor_full, which {reg.why('anchor_full')}")

    reg.partial("_stamina_byte", _stamina_byte)
    reg.partial("_build_augear_only_daperson_update",
                _build_augear_only_daperson_update)
    reg.partial("_push_augear_refresh_for", _push_augear_refresh_for)
    reg.partial("_city_info_from_row", _city_info_from_row)
    reg.value("_dev_to_building", _dev_to_building)
    reg.value("_design_reports_for", _design_reports_for)
    reg.value("_city_buildings_blob_io", _city_buildings_blob_io,
              also=("city_buildings_blob_io",))
    reg.value("_city_identity", _city_identity)
    reg.value("found_city", found_city)
    reg.value("found_town_square", found_town_square)
    reg.value("_bd_row_by_auid", _bd_row_by_auid)
    reg.value("_bd_rows_for_empire", _bd_rows_for_empire)
    reg.value("_demolish_db_lookup", _demolish_db_lookup)
    reg.value("_demolish_delete_bd_row", _demolish_delete_bd_row)
    reg.value("_find_city_for_building", _find_city_for_building)
    reg.value("_persons_that_exist", _persons_that_exist,
              also=("persons_that_exist",))
    reg.partial("_make_is_dark", _make_is_dark)
    reg.partial("_person_zone", _person_zone, positional=(conn,))
    reg.partial("_resolve_avatar_record", _resolve_avatar_record,
                also=("resolve_avatar_record",))
    reg.partial("_dna_for_actor", _dna_for_actor, also=("dna_for_actor",))
    reg.partial("build_login_ok_reply", build_login_ok_reply)
    reg.partial("_rebroadcast", _rebroadcast)
    reg.partial("_hz_active_advance", _active_advance, positional=(conn,))
    reg.partial("_force_scene_manifest_push", _force_scene_manifest_push,
                also=("force_scene_manifest_push",))
    reg.partial("_broadcast_AuCommChat", _broadcast_AuCommChat)
    reg.partial("_register_damageable_npcs", _register_damageable_npcs,
                also=("register_damageable_npcs",))
    reg.partial("resend_planet_geo", resend_planet_geo)
    reg.partial("_finalize_vehicle_dismount", _finalize_vehicle_dismount)
    reg.partial("grant_crafted_vehicle", grant_crafted_vehicle)
    reg.partial("_handle_fire_weapon_trigger", _handle_fire_weapon_trigger)
    reg.partial("_handle_reload_weapon_trigger", _handle_reload_weapon_trigger)
    reg.partial("on_chat_construction_op", on_chat_construction_op)
    reg.partial("apply_construction_labor", apply_construction_labor)
    reg.partial("on_chat_demolish", on_chat_demolish)
    reg.partial("ensure_road_construction_ticker",
                ensure_road_construction_ticker)
    reg.partial("spawn_city_building", spawn_city_building)
    reg.partial("spawn_world_flag", spawn_world_flag)

    reg.partial("retarget_bundle_to_avatar", _retarget_bundle_to_avatar,
                positional=(conn, reg.get("_SAVE")),
                also=("_retarget_bundle_to_avatar",))

    reg.partial("_execute_pickup", _execute_pickup)
    reg.partial("_execute_forage", _execute_forage)

    reg.partial("_dispatch_login", _dispatch_login, positional=(conn,))
    reg.partial("handle_login", handle_login)
    reg.partial("dump_server_state", dump_server_state)

    reg.partial("_pickup_speculation_loop", _pickup_speculation_loop)
    reg.pooled_partial("_restore_persisted_cities", _restore_persisted_cities,
                       pool=pool)
    reg.pooled_partial("_restore_persisted_buildings",
                       _restore_persisted_buildings, pool=pool)
    reg.pooled_partial("_city_sim_manager", _city_sim_manager,
                       pool=pool, conn_first=True)
    reg.pooled_partial("_city_development_loop", _city_development_loop,
                       pool=pool, conn_first=True)
    reg.pooled_partial("_mfg_environment_loop", _mfg_environment_loop,
                       pool=pool)
    reg.partial("_install_native_conversation_hooks",
                _install_native_conversation_hooks)
    reg.partial("_install_dump_state_signal_handler",
                _install_dump_state_signal_handler)
    reg.partial("_udp_start", _udp_start)
    reg.partial("_get_starmap_blob", _get_starmap_blob)

    for _family in FAMILIES:
        _absent = [n for n in family_requirements(_family) if n not in reg]
        if _absent:
            reg.gap(_family,
                    f"needs {_absent[0]}, which {reg.why(_absent[0])} "
                    f"({len(_absent)} of its declared names are unsupplied: "
                    f"{', '.join(_absent)})")
            continue
        _providers = {n: reg.get(n)
                      for n in family_requirements(_family)}
        _table = FAMILIES[_family]
        _extra = FAMILY_EXTRAS.get(_family)
        if _extra is not None:
            _table = {**_table,
                      **_extra(**{n: _providers[n]
                                  for n in requirements(_extra)})}
        reg.value(_family, bind_family(
            _table, _providers, expect=set(_table)))

    reg.partial("handle_scene", _scene_channel.handle_scene, positional=(conn,))

    reg.partial("handle_chat", _chat_channel.handle_chat)
    return reg


def routing_tables(reg: Registry) -> dict[str, dict]:
    unbound = {n: reg.why(n) for n in FAMILIES if n not in reg}
    if unbound:
        raise UnboundDependencies(
            f"{len(unbound)} of {len(FAMILIES)} dispatch families cannot be "
            f"bound:\n  " + "\n  ".join(f"{n}: {why}"
                                        for n, why in sorted(unbound.items())))
    return {n: reg.get(n) for n in FAMILIES}


def unbound_boot_arguments(reg: Registry) -> dict[str, str]:
    return {n: reg.why(n) for n in BOOT_ARGUMENTS if n not in reg}


def boot_arguments(reg: Registry) -> dict[str, Any]:
    unbound = unbound_boot_arguments(reg)
    if unbound:
        raise UnboundDependencies(report(reg))
    return {n: reg.get(n) for n in BOOT_ARGUMENTS}


def report(reg: Registry) -> str:
    families = {n: reg.why(n) for n in FAMILIES if n not in reg}
    args = unbound_boot_arguments(reg)
    lines = [
        f"the composition root is incomplete: "
        f"{len(args)} of {len(BOOT_ARGUMENTS)} arguments to "
        f"network.boot.main and {len(families)} of {len(FAMILIES)} dispatch "
        f"families cannot be bound.",
        "",
        "network.boot.main:",
    ]
    for name in BOOT_ARGUMENTS:
        lines.append(f"  {'GAP  ' if name in args else 'bound'} {name}"
                     + (f": it {args[name]}" if name in args else ""))
    lines.append("")
    lines.append("dispatch families:")
    for name in FAMILIES:
        lines.append(f"  {'GAP  ' if name in families else 'bound'} {name}"
                     + (f": it {families[name]}" if name in families
                        else f" ({len(reg.get(name))} route(s))"))
    return "\n".join(lines)


FIRST_RUN_UNIVERSE_AUID = 116
FIRST_RUN_GALAXY_AUID = 117

FIRST_RUN_UNIVERSE_NAME = "Open Shores"

FIRST_RUN_ACCOUNT = "admin"

FIRST_RUN_GALAXY = "ShoresOfHazeron"
FIRST_RUN_SECTOR_RADIUS = 1

MAPS_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                         "galaxy_maps")


async def first_run(config: Config, conn) -> None:
    await init_db(conn)
    await ensure_universe(
        conn,
        universe_auid=FIRST_RUN_UNIVERSE_AUID,
        universe_name=FIRST_RUN_UNIVERSE_NAME,
        galaxy_auid=FIRST_RUN_GALAXY_AUID,
        galaxy_name=FIRST_RUN_GALAXY,
        galaxy_seed=config.gameplay.galaxy_seed,
        sector_radius=FIRST_RUN_SECTOR_RADIUS,
        maps_dir=MAPS_DIR,
        created_ms=int(_time.time() * 1000))
    ensure_default_account(default_store(), username=FIRST_RUN_ACCOUNT)
    await seed_if_empty(conn)


async def fill_bundle(conn) -> SaveBundle:
    save = SaveBundle()
    await build_bundle(conn, save,
                       **{n: WORLD_QUERY_VALUES[n]
                          for n in requirements(build_bundle)})
    return save


async def bootstrap_anchor(conn, save: SaveBundle) -> tuple[int, int]:
    pair = await _bootstrap_sim_time_anchor(
        conn, whereabouts_auid=save.whereabouts_auid)
    return pair if pair is not None else (0, 0)


async def shutdown() -> None:
    try:
        await _persist_queue.stop_queue()
    except Exception as exc:                            # noqa: BLE001
        logger.error('[persist] queue shutdown failed: %r.', exc)
    try:
        await _pool.terminate_all()
    except Exception as exc:                            # noqa: BLE001
        logger.error('[db] closing the connection pool failed: %r.', exc)


async def serve(config: Config) -> None:
    configure(config.deployment.log_level)
    try:
        install_pid_file(config.deployment.pid_file)
        pool = await _pool.connect(config.deployment.database_url)
        async with pool.acquire() as conn:
            await first_run(config, conn)
            save = await fill_bundle(conn)
            anchor = await bootstrap_anchor(conn, save)
        # A provider, not one connection. The listeners below are called once per
        # client socket and asyncpg allows one operation per connection, so sharing
        # one raises InterfaceError as soon as two players overlap.
        _task_conn = _pool.task_connection(pool)
        reg = build_registry(config=config, conn=_task_conn,
                             pool=pool, save=save, anchor=anchor)
        kwargs = boot_arguments(reg)
        _empire_names = ("name_long", "name_short", "capital_name",
                         "_EMPIRE_NAME_OVERRIDE", "_EMPIRE_TAX_OVERRIDE")
        _have = set(reg.supplied())
        _missing = [_n for _n in _empire_names if _n not in _have]
        _empire = (None if _missing else
                   {"conn": _task_conn,
                    **{_n: reg.get(_n) for _n in _empire_names}})
        _n_probes = install_generated_probes(empire=_empire)
        if _missing:
            logger.info('[root] %d generated scene probes installed; the 74 dg_empire_* ones are unavailable (%s unbound).',
                        _n_probes, ", ".join(_missing))
        else:
            logger.info('[root] %d generated scene probes installed (--probe selects one.', _n_probes)
        logger.info("[root] dispatch families bound: %s",
                    ", ".join(f"{k}={len(v)}"
                              for k, v in routing_tables(reg).items()))
        await _boot.main(config, **kwargs)
    finally:
        await shutdown()
