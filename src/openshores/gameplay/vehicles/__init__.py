
from __future__ import annotations

from .persistence import (
    Vehicle, ensure_schema, insert_vehicle, update_vehicle,
    load_vehicle, load_all_vehicles, load_vehicles_by_parent, delete_vehicle,
)

from .spawn import (
    SpotType, reserve_vehicle_id, peek_next_vehicle_id,
    spawn_vehicle, despawn_vehicle, commit_vehicle,
    get_active_vehicle, list_active_vehicles, active_vehicle_count,
    hydrate_from_db, clear_active_registry, find_parking_spot,
)

from .wire import (
    Flags1, Flags2, ActBits as WireActBits,
    OrdnanceSlot, TxOptions, RxResult,
    pack_davehicle_update, unpack_davehicle_update,
    compute_flags1, encode_flags2, decode_flags2,
)

from .beam_packets import (
    BeamPacketType, BeamCity, BeamCoordinate, BeamOver,
    BeamPlanet, BeamShip, BeamTransporter, AnyBeamPacket,
    encode_beam_packet, parse_beam_packet, apply_beam,
)

from .input import (
    ControlContext, VehicleRuntimeState,
    Switches, ActBits, ControlInputRecord,
    process_input, process_input_array,
    get_runtime, drop_runtime, clear_runtime_registry,
    is_launching, is_paralyzed, is_control_seat,
    can_pitch_and_roll, can_turn, has_light,
)

from .ticker import (
    tock, tock_all, tick, tick_all,
    reset_tick_clock, clear_tick_clock_registry,
    start_ticker_thread, stop_ticker_thread,
    FUEL_DRAIN_MS_PER_UNIT, DEFAULT_TOCK_INTERVAL_MS, DEFAULT_TICK_INTERVAL_MS,
)

from .physics import (
    Vec3, TickResult,
    DEFAULT_GRAVITY, SEA_LEVEL_AIR_DENSITY, REST_TIMEOUT_MS,
    FUZZY_ZERO_EPS, MAX_TICK_MS,
    wrap_angle, body_to_world,
    compute_acceleration, compute_drag, compute_gravity, compute_orientation_speed,
    tick_movement, tick_movement_v,
)

from .terrain import (
    TerrainQuery, NullTerrainQuery, CallbackTerrainQuery, NearbyAtom,
    set_terrain_query, get_terrain_query, reset_terrain_query,
    spherical_latlon_to_xyz,
)

from .collision import (
    move, is_obstacle, check_collision_against_launcher, movement_blocked,
)

from .ordnance import (
    Ordnance, TurretLoadout,
    can_fire, fired, reload, time_until_can_fire_ms,
    get_loadout, drop_loadout, clear_loadout_registry,
    pack_ordnance, unpack_ordnance,
)

from .combat import (
    AuCombatWeapon, AuCombatResult,
    WEAPONMODE, WEAPONEFFECT, WEAPONMODE_HULL, MODE_ARMOR_SLOT,
    WeaponMode, WeaponEffect, DbCommodityArmor,
    set_db_commodity_armor, get_db_commodity_armor, reset_armor_registry,
    combat_armor_effectiveness, target_attacked,
    set_dice_roller, reset_dice_roller, default_dice_roller,
    combat_apply_damage,
    get_last_damage_ms, clear_last_damage_ms,
    COND_BURNING, COND_PARALYZED, COND_ACID,
    has_condition, clear_conditions,
)

from .weapons import (
    DamageRecord, FireResult,
    fire_gun, fire_weapon, record_damage, get_killer_id,
    get_last_weapon_used_by,
    set_weapon_for_ammo, get_weapon_for_ammo,
    MAX_GUN_RANGE_M, DAMAGE_HISTORY_MAX,
)

from .hull_stress import (
    HullStressResult,
    hull_stress, test_hull_stress,
)

from .missile import (
    Missile, MissileTickResult,
    spawn_missile, despawn_missile,
    get_active_missile, list_active_missiles, active_missile_count,
    tick_missile, tick_all_missiles, clear_missile_registry,
    INITIAL_MISSILE_SPEED, MAX_MISSILE_LIFETIME_MS, MISSILE_IMPACT_RADIUS,
)

from .atom_packet import (
    OPCODE_DAVEHICLE,
    build_da_vehicle_atom,
    build_da_vehicle_update,
    build_da_vehicle_keepalive,
    build_scene_atoms,
)

from .vehicle_constants import (
    VehicleType, VEHICLE_NAMES,
    HULL_STRESS_LOWER, HULL_STRESS_UPPER, ATMO_DAMAGE_AIR_DENSITY,
    FALL_DISTANCE_THRESHOLD, SIGHT_RAY_MAX_DISTANCE, SCENE_RADIUS_SQ,
    CRIT_ARMOR_MULTIPLIER, CRIT_ROLL_THRESHOLD, JET_RUNWAY_TAKEOFF_SPEED,
    HULL_STRESS_TOLERANCE, CROSS_SECTIONAL_AREA, DRAG_COEFFICIENT,
    DENSITY, ORIENTATION_SPEED, ACCELERATION_TABLE, FRICTION_CONSTANTS,
    THROTTLE_CLAMPS, ORDNANCE_COOLDOWN_MS,
    ControlInput, HEAD_LOOK_ANGLES,
    MISSILE_THRUST_HEAVY, MISSILE_THRUST_LIGHT, MISSILE_DAMPING_RATE,
    PoliticalStance,
    is_enclosed_vehicle, has_headlight, blip_class_for_commodity,
)

__all__ = [
    "Vehicle", "ensure_schema", "insert_vehicle", "update_vehicle",
    "load_vehicle", "load_all_vehicles", "load_vehicles_by_parent",
    "delete_vehicle",
    "SpotType", "reserve_vehicle_id", "peek_next_vehicle_id",
    "spawn_vehicle", "despawn_vehicle", "commit_vehicle",
    "get_active_vehicle", "list_active_vehicles", "active_vehicle_count",
    "hydrate_from_db", "clear_active_registry", "find_parking_spot",
    "Flags1", "Flags2", "WireActBits",
    "OrdnanceSlot", "TxOptions", "RxResult",
    "pack_davehicle_update", "unpack_davehicle_update",
    "compute_flags1", "encode_flags2", "decode_flags2",
    "BeamPacketType", "BeamCity", "BeamCoordinate", "BeamOver",
    "BeamPlanet", "BeamShip", "BeamTransporter", "AnyBeamPacket",
    "encode_beam_packet", "parse_beam_packet", "apply_beam",
    "ControlContext", "VehicleRuntimeState",
    "Switches", "ActBits", "ControlInputRecord",
    "process_input", "process_input_array",
    "get_runtime", "drop_runtime", "clear_runtime_registry",
    "is_launching", "is_paralyzed", "is_control_seat",
    "can_pitch_and_roll", "can_turn", "has_light",
    "tock", "tock_all", "tick", "tick_all",
    "reset_tick_clock", "clear_tick_clock_registry",
    "start_ticker_thread", "stop_ticker_thread",
    "FUEL_DRAIN_MS_PER_UNIT", "DEFAULT_TOCK_INTERVAL_MS",
    "DEFAULT_TICK_INTERVAL_MS",
    "Vec3", "TickResult",
    "DEFAULT_GRAVITY", "SEA_LEVEL_AIR_DENSITY", "REST_TIMEOUT_MS",
    "FUZZY_ZERO_EPS", "MAX_TICK_MS",
    "wrap_angle", "body_to_world",
    "compute_acceleration", "compute_drag", "compute_gravity",
    "compute_orientation_speed",
    "tick_movement", "tick_movement_v",
    "TerrainQuery", "NullTerrainQuery", "CallbackTerrainQuery", "NearbyAtom",
    "set_terrain_query", "get_terrain_query", "reset_terrain_query",
    "spherical_latlon_to_xyz",
    "move", "is_obstacle", "check_collision_against_launcher",
    "movement_blocked",
    "Ordnance", "TurretLoadout",
    "can_fire", "fired", "reload", "time_until_can_fire_ms",
    "get_loadout", "drop_loadout", "clear_loadout_registry",
    "pack_ordnance", "unpack_ordnance",
    "AuCombatWeapon", "AuCombatResult",
    "WEAPONMODE", "WEAPONEFFECT", "WEAPONMODE_HULL", "MODE_ARMOR_SLOT",
    "WeaponMode", "WeaponEffect", "DbCommodityArmor",
    "set_db_commodity_armor", "get_db_commodity_armor", "reset_armor_registry",
    "combat_armor_effectiveness", "target_attacked",
    "set_dice_roller", "reset_dice_roller", "default_dice_roller",
    "combat_apply_damage",
    "get_last_damage_ms", "clear_last_damage_ms",
    "COND_BURNING", "COND_PARALYZED", "COND_ACID",
    "has_condition", "clear_conditions",
    "DamageRecord", "FireResult",
    "fire_gun", "fire_weapon", "record_damage", "get_killer_id",
    "get_last_weapon_used_by",
    "set_weapon_for_ammo", "get_weapon_for_ammo",
    "MAX_GUN_RANGE_M", "DAMAGE_HISTORY_MAX",
    "HullStressResult",
    "hull_stress", "test_hull_stress",
    "Missile", "MissileTickResult",
    "spawn_missile", "despawn_missile",
    "get_active_missile", "list_active_missiles", "active_missile_count",
    "tick_missile", "tick_all_missiles", "clear_missile_registry",
    "INITIAL_MISSILE_SPEED", "MAX_MISSILE_LIFETIME_MS", "MISSILE_IMPACT_RADIUS",
    "OPCODE_DAVEHICLE", "build_da_vehicle_atom",
    "build_da_vehicle_update", "build_da_vehicle_keepalive", "build_scene_atoms",
    "VehicleType", "VEHICLE_NAMES", "PoliticalStance", "ControlInput",
    "HULL_STRESS_LOWER", "HULL_STRESS_UPPER", "ATMO_DAMAGE_AIR_DENSITY",
    "FALL_DISTANCE_THRESHOLD", "SIGHT_RAY_MAX_DISTANCE", "SCENE_RADIUS_SQ",
    "CRIT_ARMOR_MULTIPLIER", "CRIT_ROLL_THRESHOLD", "JET_RUNWAY_TAKEOFF_SPEED",
    "HULL_STRESS_TOLERANCE", "CROSS_SECTIONAL_AREA", "DRAG_COEFFICIENT",
    "DENSITY", "ORIENTATION_SPEED", "ACCELERATION_TABLE", "FRICTION_CONSTANTS",
    "THROTTLE_CLAMPS", "ORDNANCE_COOLDOWN_MS",
    "MISSILE_THRUST_HEAVY", "MISSILE_THRUST_LIGHT", "MISSILE_DAMPING_RATE",
    "HEAD_LOOK_ANGLES",
    "is_enclosed_vehicle", "has_headlight", "blip_class_for_commodity",
]
