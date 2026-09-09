
from __future__ import annotations

import enum
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Iterable

from openshores.core.logging import get_logger

from .persistence import Vehicle
from .spawn import get_active_vehicle, list_active_vehicles
from .terrain import get_terrain_query
from .vehicle_constants import (
    VehicleType,
    THROTTLE_CLAMPS,
    HEAD_LOOK_ANGLES,
    ControlInput,
    JET_RUNWAY_TAKEOFF_SPEED,
)

logger = get_logger(__name__)


class Switches:
    ENGINE_BIT      = 0x01
    HEADLIGHT_BIT   = 0x02
    COMBAT_BIT      = 0x04
    SYNC_BIT        = 0x08
    BIT4_TOGGLE     = 0x10
    SERVER_PRIVATE  = 0xE0


class ActBits:
    YAW_RIGHT             = 0x000100
    YAW_LEFT              = 0x000200
    PITCH_UP              = 0x000400
    PITCH_DOWN            = 0x000800
    ROLL_LEFT             = 0x001000
    ROLL_RIGHT            = 0x002000
    FIRE_MODE_TURRET0     = 0x040000
    TURRET1_DIRTY         = 0x080000
    TURRET2_DIRTY         = 0x100000
    HANDBRAKE_HOVER       = 0x180000
    ACTIVE_TURRET_FLAG    = 0x200000


class ControlContext(enum.IntEnum):
    IGNORED            = 0
    CLIENT_PREDICTION  = 1
    FULL_SERVER        = 2


@dataclass
class VehicleRuntimeState:
    launch_counter: int = 0
    launching_vessel: int = 0
    launch_progress: float = 0.0
    launch_start_ms: int = 0
    launch_vector: tuple[float, float, float] = (0.0, 0.0, 0.0)

    rot_pitch_strength: int = 0
    rot_roll_strength: int = 0
    rot_yaw_strength: int = 0

    ts_engine_toggled: int = 0
    ts_fire_mode: int = 0
    ts_handbrake: int = 0
    ts_pitch_input: int = 0
    ts_roll_input: int = 0
    ts_throttle_long: int = 0
    ts_strafe_x: int = 0
    ts_strafe_y: int = 0
    ts_throttle_vert: int = 0
    ts_yaw_input: int = 0

    active_turret: int = 0

    ts_hp_changed: int = 0

    paralyzed: bool = False

    fuel_drain_accumulator_ms: int = 0
    last_tock_ms: int = 0

    force_transform_pending: bool = False


_runtime: dict[int, VehicleRuntimeState] = {}
_runtime_lock = threading.Lock()


def get_runtime(vehicle_id: int) -> VehicleRuntimeState:
    vid = int(vehicle_id)
    with _runtime_lock:
        rt = _runtime.get(vid)
        if rt is None:
            rt = VehicleRuntimeState()
            _runtime[vid] = rt
        return rt


def drop_runtime(vehicle_id: int) -> bool:
    with _runtime_lock:
        return _runtime.pop(int(vehicle_id), None) is not None


def clear_runtime_registry() -> None:
    with _runtime_lock:
        _runtime.clear()


def is_launching(vehicle_id: int) -> bool:
    return get_runtime(vehicle_id).launch_counter != 0


def is_paralyzed(vehicle_id: int) -> bool:
    return get_runtime(vehicle_id).paralyzed


def is_control_seat(v: Vehicle, seat_idx: int) -> bool:
    _ = v
    return int(seat_idx) == 0


def can_pitch_and_roll(v: Vehicle) -> bool:
    rt = get_runtime(v.id)
    if rt.launch_counter != 0:
        return False
    if rt.paralyzed:
        return False
    q = get_terrain_query()
    pos = (v.locX, v.locY, v.locZ)
    cid = v.cid
    import math as _math
    speed = _math.sqrt(v.vecX**2 + v.vecY**2 + v.vecZ**2)
    on_ground = q.is_on_ground(v.idp, pos)
    if cid in (VehicleType.PLANE, VehicleType.HELICOPTER):
        return not on_ground
    if cid in (VehicleType.JET, VehicleType.DRONE, VehicleType.LANDER):
        if not on_ground:
            return True
        return bool(v.switches & Switches.ENGINE_BIT) and speed > JET_RUNWAY_TAKEOFF_SPEED
    if cid == VehicleType.BOAT:
        return q.is_in_water(v.idp, pos) and not on_ground
    return False


def can_turn(v: Vehicle) -> bool:
    rt = get_runtime(v.id)
    return rt.launch_counter == 0 and not rt.paralyzed


def has_light(v: Vehicle) -> bool:
    from .vehicle_constants import has_headlight
    return has_headlight(v.cid)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _clamp_throttle(v: Vehicle, raw: int, axis: str = "long") -> int:
    clamp = THROTTLE_CLAMPS.get(v.cid)
    if clamp is None:
        lo, hi = -10, 10
    else:
        lo, hi = clamp.minimum, clamp.maximum
    if axis == "lat":
        if v.cid in (VehicleType.PLANE, VehicleType.JET,
                     VehicleType.DRONE, VehicleType.LANDER):
            lo = -5
    elif axis == "vert":
        if v.cid in (VehicleType.PLANE, VehicleType.JET,
                     VehicleType.DRONE, VehicleType.LANDER):
            lo = -6
    if raw < lo: return lo
    if raw > hi: return hi
    return raw


def _set_rotation_request(v: Vehicle, rt: VehicleRuntimeState, *,
                          set_bit: int, clear_bit: int,
                          strength_attr: str, strength: int,
                          ts_attr: str) -> None:
    v.actBits = (v.actBits & ~clear_bit) | set_bit
    setattr(rt, strength_attr, int(strength))
    setattr(rt, ts_attr, _now_ms())


def _h_stop_all_thrust(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx): return False
    if not (v.throttle or v.throttleLateral or v.throttleLong or v.throttleVertical):
        return False
    if is_paralyzed(v.id): return False
    now = _now_ms()
    rt.ts_throttle_long = now
    rt.ts_strafe_x = now
    rt.ts_strafe_y = now
    rt.ts_throttle_vert = now
    v.throttle = v.throttleLateral = v.throttleLong = v.throttleVertical = 0
    return True


def _h_throttle_down(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_launching(v.id) or is_paralyzed(v.id):
        return False
    rt.ts_throttle_long = _now_ms()
    v.throttle = _clamp_throttle(v, v.throttle - 1, "long")
    return True


def _h_throttle_up(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_launching(v.id) or is_paralyzed(v.id):
        return False
    rt.ts_throttle_long = _now_ms()
    if v.cid in (VehicleType.TANK, VehicleType.SUB_IFV,
                 VehicleType.APC, VehicleType.TURRET):
        if v.throttle < 9:
            v.throttle = _clamp_throttle(v, v.throttle + 2, "long")
        elif v.throttle < 10:
            v.throttle = _clamp_throttle(v, v.throttle + 1, "long")
    else:
        v.throttle = _clamp_throttle(v, v.throttle + 1, "long")
    return True


def _h_throttle_max_plus(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_launching(v.id) or is_paralyzed(v.id):
        return False
    if v.cid in (VehicleType.PLANE, VehicleType.HELICOPTER, VehicleType.JET,
                 VehicleType.DRONE, VehicleType.LANDER, VehicleType.BOAT):
        if v.throttle < 10:
            v.throttle = 10
        rt.ts_throttle_long = _now_ms()
        return True
    clamp = THROTTLE_CLAMPS.get(v.cid)
    if clamp is None:
        v.throttle = max(int(v.throttle), 50)
    else:
        v.throttle = int(clamp.maximum)
    rt.ts_throttle_long = _now_ms()
    return True


def _h_throttle_max_minus(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_launching(v.id) or is_paralyzed(v.id):
        return False
    clamp = THROTTLE_CLAMPS.get(v.cid)
    if clamp is None: return False
    if v.throttle > clamp.minimum:
        v.throttle = clamp.minimum
    rt.ts_throttle_long = _now_ms()
    return True


def _h_throttle_set(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_launching(v.id) or is_paralyzed(v.id):
        return False
    rt.ts_throttle_long = _now_ms()
    v.throttle = _clamp_throttle(v, int(payload), "long")
    return True


def _h_strafe_y_down(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_launching(v.id) or is_paralyzed(v.id):
        return False
    rt.ts_strafe_y = _now_ms()
    v.throttleLateral = _clamp_throttle(v, v.throttleLateral - 1, "lat")
    v.switches &= 0xF7
    return True


def _h_strafe_y_up(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_launching(v.id) or is_paralyzed(v.id):
        return False
    rt.ts_strafe_y = _now_ms()
    v.throttleLateral = _clamp_throttle(v, v.throttleLateral + 1, "lat")
    return True


def _h_vertical_down(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_launching(v.id) or is_paralyzed(v.id):
        return False
    rt.ts_throttle_vert = _now_ms()
    v.throttleVertical = _clamp_throttle(v, v.throttleVertical - 1, "vert")
    return True


def _h_vertical_up(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_launching(v.id) or is_paralyzed(v.id):
        return False
    rt.ts_throttle_vert = _now_ms()
    v.throttleVertical = _clamp_throttle(v, v.throttleVertical + 1, "vert")
    return True


def _h_strafe_x_down(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_launching(v.id) or is_paralyzed(v.id):
        return False
    rt.ts_strafe_x = _now_ms()
    v.throttleLong = _clamp_throttle(v, v.throttleLong - 1, "strafe_x")
    return True


def _h_strafe_x_up(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_launching(v.id) or is_paralyzed(v.id):
        return False
    rt.ts_strafe_x = _now_ms()
    if v.cid in (VehicleType.TANK, VehicleType.SUB_IFV,
                 VehicleType.APC, VehicleType.TURRET):
        if v.throttleLong < 9:
            v.throttleLong = _clamp_throttle(v, v.throttleLong + 2, "strafe_x")
        elif v.throttleLong < 10:
            v.throttleLong = _clamp_throttle(v, v.throttleLong + 1, "strafe_x")
    else:
        v.throttleLong = _clamp_throttle(v, v.throttleLong + 1, "strafe_x")
    return True


def _h_seat_next(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.IGNORED: return False
    return True


def _h_seat_prev(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.IGNORED: return False
    return True


def _h_seat_direct(seat: int):
    def handler(v, rt, payload, ctx, seat_idx, person_id):
        if ctx == ControlContext.IGNORED: return False
        _ = seat
        return True
    return handler


def _h_yaw_right(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.IGNORED: return False
    if not is_control_seat(v, seat_idx) or not can_turn(v): return False
    _set_rotation_request(v, rt,
        set_bit=ActBits.YAW_RIGHT, clear_bit=ActBits.YAW_LEFT,
        strength_attr="rot_yaw_strength", strength=payload,
        ts_attr="ts_yaw_input",
    )
    return True


def _h_yaw_left(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.IGNORED: return False
    if not is_control_seat(v, seat_idx) or not can_turn(v): return False
    _set_rotation_request(v, rt,
        set_bit=ActBits.YAW_LEFT, clear_bit=ActBits.YAW_RIGHT,
        strength_attr="rot_yaw_strength", strength=payload,
        ts_attr="ts_yaw_input",
    )
    return True


def _h_pitch_down(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.IGNORED: return False
    if not is_control_seat(v, seat_idx) or not can_pitch_and_roll(v):
        return False
    _set_rotation_request(v, rt,
        set_bit=ActBits.PITCH_DOWN, clear_bit=ActBits.PITCH_UP,
        strength_attr="rot_pitch_strength", strength=payload,
        ts_attr="ts_pitch_input",
    )
    return True


def _h_pitch_up(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.IGNORED: return False
    if not is_control_seat(v, seat_idx) or not can_pitch_and_roll(v):
        return False
    _set_rotation_request(v, rt,
        set_bit=ActBits.PITCH_UP, clear_bit=ActBits.PITCH_DOWN,
        strength_attr="rot_pitch_strength", strength=payload,
        ts_attr="ts_pitch_input",
    )
    return True


def _h_roll_left(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.IGNORED: return False
    if not is_control_seat(v, seat_idx) or not can_pitch_and_roll(v):
        return False
    q = get_terrain_query()
    if q.is_on_ground(v.idp, (v.locX, v.locY, v.locZ)):
        return _h_yaw_right(v, rt, payload, ctx, seat_idx, person_id)
    _set_rotation_request(v, rt,
        set_bit=ActBits.ROLL_LEFT, clear_bit=ActBits.ROLL_RIGHT,
        strength_attr="rot_roll_strength", strength=payload,
        ts_attr="ts_roll_input",
    )
    return True


def _h_roll_right(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.IGNORED: return False
    if not is_control_seat(v, seat_idx) or not can_pitch_and_roll(v):
        return False
    q = get_terrain_query()
    if q.is_on_ground(v.idp, (v.locX, v.locY, v.locZ)):
        return _h_yaw_left(v, rt, payload, ctx, seat_idx, person_id)
    _set_rotation_request(v, rt,
        set_bit=ActBits.ROLL_RIGHT, clear_bit=ActBits.ROLL_LEFT,
        strength_attr="rot_roll_strength", strength=payload,
        ts_attr="ts_roll_input",
    )
    return True


def _h_fire_mode(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_paralyzed(v.id):
        return False
    rt.ts_fire_mode = _now_ms()
    if v.cid in (VehicleType.PLANE, VehicleType.HELICOPTER, VehicleType.JET,
                 VehicleType.DRONE, VehicleType.TANK, VehicleType.BOAT,
                 VehicleType.SUB_IFV, VehicleType.APC, VehicleType.TURRET,
                 VehicleType.LANDER):
        v.actBits |= ActBits.FIRE_MODE_TURRET0
    return True


def _h_handbrake(v, rt, payload, ctx, seat_idx, person_id):
    if not is_control_seat(v, seat_idx) or is_paralyzed(v.id):
        return False
    rt.ts_handbrake = _now_ms()
    if (v.cid in (VehicleType.PLANE, VehicleType.HELICOPTER, VehicleType.JET,
                  VehicleType.DRONE, VehicleType.BOAT, VehicleType.LANDER)):
        v.actBits |= ActBits.HANDBRAKE_HOVER
    return True


def _h_engine_toggle(v, rt, payload, ctx, seat_idx, person_id,
                     dice_roller=None):
    if ctx == ControlContext.CLIENT_PREDICTION:
        logger.debug("Vehicle %#010x engine toggle ignored: context is "
                     "client prediction (%d).", int(v.id), int(ctx))
        return False
    if not is_control_seat(v, seat_idx):
        logger.debug("Vehicle %#010x engine toggle ignored: seat %s is not a "
                     "control seat.", int(v.id), seat_idx)
        return False
    if is_launching(v.id):
        logger.debug("Vehicle %#010x engine toggle ignored: vehicle is "
                     "launching.", int(v.id))
        return False
    if is_paralyzed(v.id):
        logger.debug("Vehicle %#010x engine toggle ignored, pilot is paralyzed.", int(v.id))
        return False

    if dice_roller is None:
        dice_roller = lambda: random.randint(1, 2)

    _prev_switches = int(v.switches)
    if not (v.switches & Switches.ENGINE_BIT):
        if v.fuel <= 0:
            logger.debug("Vehicle %#010x engine will not start: fuel %d.",
                         int(v.id), int(v.fuel))
            return False
        if dice_roller() == 2:
            v.fuel = max(0, v.fuel - 1)
            rt.ts_engine_toggled = _now_ms()
        v.switches |= Switches.ENGINE_BIT
        logger.debug("Vehicle %#010x engine on: switches %#04x -> %#04x, "
                     "fuel %d.", int(v.id), _prev_switches, int(v.switches),
                     int(v.fuel))
    else:
        v.switches &= 0xF6
        logger.debug("Vehicle %#010x engine off: switches %#04x -> %#04x.",
                     int(v.id), _prev_switches, int(v.switches))

    rt.force_transform_pending = True
    return True


def _h_headlight(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.CLIENT_PREDICTION: return False
    if not is_control_seat(v, seat_idx): return False
    if not has_light(v): return False
    v.switches ^= Switches.HEADLIGHT_BIT
    return True


def _h_fire_gun(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.CLIENT_PREDICTION: return False
    if not is_control_seat(v, seat_idx) or is_paralyzed(v.id):
        return False
    v.actBits |= ActBits.FIRE_MODE_TURRET0
    rt.ts_fire_mode = _now_ms()
    return True


def _h_door_switch(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.CLIENT_PREDICTION: return False
    if not is_control_seat(v, seat_idx): return False
    return True


def _h_service(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.CLIENT_PREDICTION: return False
    return True


def _h_fire_weapon(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.CLIENT_PREDICTION: return False
    if not is_control_seat(v, seat_idx) or is_paralyzed(v.id):
        return False
    v.actBits |= ActBits.FIRE_MODE_TURRET0
    rt.ts_fire_mode = _now_ms()
    return True


def _h_at_rest_toggle(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.CLIENT_PREDICTION: return False
    if not is_control_seat(v, seat_idx): return False
    v.atRest = not v.atRest
    return True


def _h_bit4_toggle(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.CLIENT_PREDICTION: return False
    if not is_control_seat(v, seat_idx): return False
    v.switches ^= Switches.BIT4_TOGGLE
    return True


def _h_sync_toggle(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.CLIENT_PREDICTION: return False
    if not is_control_seat(v, seat_idx) or is_launching(v.id) or is_paralyzed(v.id):
        return False
    v.switches ^= Switches.SYNC_BIT
    if not (v.switches & Switches.SYNC_BIT):
        rt.force_transform_pending = True
    return True


def _h_request_launch(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.CLIENT_PREDICTION: return False
    if not is_control_seat(v, seat_idx): return False
    rt.launch_counter = 1
    rt.launch_start_ms = _now_ms()
    rt.launching_vessel = v.idp
    return True


def _h_request_recovery(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.CLIENT_PREDICTION: return False
    if not is_control_seat(v, seat_idx): return False
    rt.launch_counter = 0
    rt.launch_progress = 0.0
    return True


def _h_clear_mothership(v, rt, payload, ctx, seat_idx, person_id):
    if ctx == ControlContext.CLIENT_PREDICTION: return False
    if not is_control_seat(v, seat_idx): return False
    if v.motherShip == 0:
        return False
    v.motherShip = 0
    v.motherShipName = ""
    return True


def _h_head_look(angle: float):
    def handler(v, rt, payload, ctx, seat_idx, person_id):
        if ctx == ControlContext.IGNORED: return False
        _ = angle
        return True
    return handler


_DISPATCH: dict[int, callable] = {
    ControlInput.STOP_ALL_THRUST:    _h_stop_all_thrust,
    ControlInput.THROTTLE_DOWN:      _h_throttle_down,
    ControlInput.THROTTLE_UP:        _h_throttle_up,
    ControlInput.NEXT_SEAT:          _h_seat_next,
    ControlInput.PREV_SEAT:          _h_seat_prev,
    ControlInput.SEAT_0:             _h_seat_direct(0),
    ControlInput.SEAT_1:             _h_seat_direct(1),
    ControlInput.SEAT_2:             _h_seat_direct(2),
    ControlInput.SEAT_3:             _h_seat_direct(3),
    ControlInput.SEAT_4:             _h_seat_direct(4),
    ControlInput.SEAT_5:             _h_seat_direct(5),
    ControlInput.SEAT_6:             _h_seat_direct(6),
    ControlInput.SEAT_7:             _h_seat_direct(7),
    ControlInput.SEAT_8:             _h_seat_direct(8),
    ControlInput.SEAT_9:             _h_seat_direct(9),
    ControlInput.YAW_RIGHT:          _h_yaw_right,
    ControlInput.YAW_LEFT:           _h_yaw_left,
    ControlInput.FIRE_MODE_BIT:      _h_fire_mode,
    ControlInput.PITCH_DOWN:         _h_pitch_down,
    ControlInput.PITCH_UP:           _h_pitch_up,
    ControlInput.ROLL_LEFT:          _h_roll_left,
    ControlInput.ROLL_RIGHT:         _h_roll_right,
    ControlInput.STRAFE_Y_DOWN:      _h_strafe_y_down,
    ControlInput.STRAFE_Y_UP:        _h_strafe_y_up,
    ControlInput.VERTICAL_DOWN:      _h_vertical_down,
    ControlInput.VERTICAL_UP:        _h_vertical_up,
    ControlInput.HANDBRAKE_HOVER:    _h_handbrake,
    ControlInput.ENGINE_TOGGLE:      _h_engine_toggle,
    ControlInput.HEADLIGHT_TOGGLE:   _h_headlight,
    ControlInput.FIRE_GUN:           _h_fire_gun,
    ControlInput.DOOR_SWITCH:        _h_door_switch,
    ControlInput.THROTTLE_MAX_PLUS:  _h_throttle_max_plus,
    ControlInput.THROTTLE_MAX_MINUS: _h_throttle_max_minus,
    ControlInput.THROTTLE_SET:       _h_throttle_set,
    ControlInput.STRAFE_X_DOWN:      _h_throttle_down,
    ControlInput.STRAFE_X_UP:        _h_throttle_up,
    ControlInput.SERVICE:            _h_service,
    ControlInput.FIRE_WEAPON:        _h_fire_weapon,
    ControlInput.AT_REST_TOGGLE:     _h_at_rest_toggle,
    ControlInput.BIT4_TOGGLE:        _h_bit4_toggle,
    ControlInput.BIT3_TOGGLE:        _h_sync_toggle,
    ControlInput.REQUEST_LAUNCH:     _h_request_launch,
    ControlInput.REQUEST_RECOVERY:   _h_request_recovery,
    ControlInput.CLEAR_MOTHERSHIP:   _h_clear_mothership,
    ControlInput.HEAD_LOOK_BACK:     _h_head_look(HEAD_LOOK_ANGLES[ControlInput.HEAD_LOOK_BACK]),
    ControlInput.HEAD_LOOK_FORWARD:  _h_head_look(HEAD_LOOK_ANGLES[ControlInput.HEAD_LOOK_FORWARD]),
    ControlInput.HEAD_LOOK_RIGHT:    _h_head_look(HEAD_LOOK_ANGLES[ControlInput.HEAD_LOOK_RIGHT]),
    ControlInput.HEAD_LOOK_BACK_R:   _h_head_look(HEAD_LOOK_ANGLES[ControlInput.HEAD_LOOK_BACK_R]),
    ControlInput.HEAD_LOOK_RIGHT_F:  _h_head_look(HEAD_LOOK_ANGLES[ControlInput.HEAD_LOOK_RIGHT_F]),
    ControlInput.HEAD_LOOK_LEFT:     _h_head_look(HEAD_LOOK_ANGLES[ControlInput.HEAD_LOOK_LEFT]),
    ControlInput.HEAD_LOOK_BACK_L:   _h_head_look(HEAD_LOOK_ANGLES[ControlInput.HEAD_LOOK_BACK_L]),
    ControlInput.HEAD_LOOK_LEFT_F:   _h_head_look(HEAD_LOOK_ANGLES[ControlInput.HEAD_LOOK_LEFT_F]),
}

_EXPECTED_HANDLER_COUNT = 52
assert len(_DISPATCH) == _EXPECTED_HANDLER_COUNT, (
    f"Input dispatch has {len(_DISPATCH)} entries, expected {_EXPECTED_HANDLER_COUNT}"
)


def process_input(
    vehicle_id: int,
    control_id: int,
    payload: int = 0,
    *,
    person_id: int = 0,
    seat_idx: int = 0,
    context: int = ControlContext.FULL_SERVER,
) -> bool:
    v = get_active_vehicle(vehicle_id)
    if v is None:
        return False
    rt = get_runtime(vehicle_id)
    fn = _DISPATCH.get(int(control_id))
    if fn is None:
        return False
    try:
        return bool(fn(v, rt, int(payload), int(context), int(seat_idx),
                       int(person_id)))
    except Exception as exc:
        logger.error("Control %#04x handler failed: %r. Input dropped.",
                     int(control_id), exc)
        return False


@dataclass
class ControlInputRecord:
    control_id: int
    payload: int = 0


def process_input_array(
    vehicle_id: int,
    inputs: Iterable[ControlInputRecord],
    *,
    person_id: int = 0,
    seat_idx: int = 0,
    context: int = ControlContext.FULL_SERVER,
) -> int:
    count = 0
    for rec in inputs:
        if process_input(vehicle_id, rec.control_id, rec.payload,
                         person_id=person_id, seat_idx=seat_idx,
                         context=context):
            count += 1
    return count


def _selftest() -> None:
    raise NotImplementedError(
        "Retired")


if __name__ == "__main__":
    logger.info("vehicles.input self-test starting")
    _selftest()
    logger.info("vehicles.input self-test passed")
