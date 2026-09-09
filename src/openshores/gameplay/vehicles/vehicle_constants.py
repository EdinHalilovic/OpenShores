
from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Optional


class VehicleType(enum.IntEnum):

    PLANE       = 0x06
    HELICOPTER  = 0x07
    JET         = 0x08
    DRONE       = 0x09
    TANK        = 0x1C
    UNK_0x36    = 0x36
    UNK_0x46    = 0x46
    UNK_0x47    = 0x47
    BOAT        = 0x4D
    SUB_IFV     = 0x52
    UNK_0x67    = 0x67
    APC         = 0x68
    SHUTTLE     = 0x84
    TURRET      = 0x85
    LANDER      = 0xE7


VEHICLE_NAMES: dict[int, str] = {
    VehicleType.PLANE:      "Plane",
    VehicleType.HELICOPTER: "Helicopter",
    VehicleType.JET:        "Jet",
    VehicleType.DRONE:      "Drone",
    VehicleType.TANK:       "Tank",
    VehicleType.BOAT:       "Boat",
    VehicleType.SUB_IFV:    "SubIFV",
    VehicleType.APC:        "APC",
    VehicleType.SHUTTLE:    "Shuttle",
    VehicleType.TURRET:     "Turret",
    VehicleType.LANDER:     "Lander",
}


class PoliticalStance(enum.IntEnum):
    FRIENDLY     = 0
    NEUTRAL      = 1
    ENEMY        = 2
    SAME_EMPIRE  = 3
    OVERLORD     = 4


HULL_STRESS_LOWER: float = 1.0

HULL_STRESS_UPPER: float = 1.2

ATMO_DAMAGE_AIR_DENSITY: float = 0.95

FALL_DISTANCE_THRESHOLD: float = 1.0

SIGHT_RAY_MAX_DISTANCE: float = 100.0

SCENE_RADIUS_SQ: float = 2.75e9

CRIT_ARMOR_MULTIPLIER: float = 0.5

CRIT_ROLL_THRESHOLD: int = 95

JET_RUNWAY_TAKEOFF_SPEED: float = 73.333333333333


HULL_STRESS_TOLERANCE: dict[int, float] = {
    VehicleType.PLANE:      250.0,
    VehicleType.HELICOPTER: 1000.0,
    VehicleType.JET:        800.0,
    VehicleType.DRONE:      600.0,
    VehicleType.TANK:       450.0,
    VehicleType.BOAT:       400.0,
    VehicleType.SUB_IFV:    350.0,
    VehicleType.APC:        500.0,
    VehicleType.SHUTTLE:    150.0,
    VehicleType.TURRET:     300.0,
    VehicleType.LANDER:     850.0,
}


@dataclass(frozen=True)
class Dimensions:
    x: float
    y: float
    z: float


CROSS_SECTIONAL_AREA: dict[int, Dimensions] = {
    VehicleType.PLANE:      Dimensions(125.0,  45.0, 250.0),
    VehicleType.HELICOPTER: Dimensions(170.0,  16.0, 170.0),
    VehicleType.JET:        Dimensions(131.0,  60.0, 350.0),
    VehicleType.LANDER:     Dimensions(131.0,  60.0, 350.0),
    VehicleType.DRONE:      Dimensions(250.0, 120.0, 700.0),
    VehicleType.TANK:       Dimensions(208.0,  55.0, 153.0),
    VehicleType.SUB_IFV:    Dimensions(208.0,  55.0, 153.0),
    VehicleType.BOAT:       Dimensions(167.0,  73.0, 200.0),
    VehicleType.APC:        Dimensions(208.0,  60.0, 153.0),
    VehicleType.SHUTTLE:    Dimensions( 80.0,  40.0, 249.0),
    VehicleType.TURRET:     Dimensions( 13.7,   2.85,  4.28),
}
_DIMENSIONS_DEFAULT: Dimensions = Dimensions(1.0, 1.0, 1.0)


DRAG_COEFFICIENT: dict[int, float] = {
    VehicleType.PLANE:      1.39e-3,
    VehicleType.HELICOPTER: 1.83e-3,
    VehicleType.JET:        6.51e-4,
    VehicleType.LANDER:     6.51e-4,
    VehicleType.DRONE:      3.55e-4,
    VehicleType.TANK:       9.22e-4,
    VehicleType.BOAT:       1.21e-4,
    VehicleType.SUB_IFV:    1.97e-5,
    VehicleType.APC:        1.96e-5,
    VehicleType.SHUTTLE:    4.34e-4,
    VehicleType.TURRET:     1.37e-3,
}
DRAG_COEFFICIENT_DEFAULT: float = 0.04132


DENSITY: dict[int, float] = {
    VehicleType.PLANE:      22.619,
    VehicleType.HELICOPTER: 24.881,
    VehicleType.JET:        27.369,
    VehicleType.DRONE:      27.369,
    VehicleType.SHUTTLE:     1.295,
    VehicleType.TURRET:     76.667,
    VehicleType.LANDER:     29.857,
}
DENSITY_DEFAULT: float = 62.316

GROUND_MASS_DIVISOR: float = 70.629


ORIENTATION_SPEED: dict[int, float] = {
    VehicleType.PLANE:      math.pi / 4,
    VehicleType.JET:        math.pi / 4,
    VehicleType.DRONE:      math.pi / 4,
    VehicleType.LANDER:     math.pi / 4,
    VehicleType.TANK:       math.pi / 4,
    VehicleType.BOAT:       math.pi / 4,
    VehicleType.SHUTTLE:    math.pi / 4,
    VehicleType.HELICOPTER: math.pi,
    VehicleType.SUB_IFV:    1.0471975512,
    VehicleType.APC:        1.0471975512,
    VehicleType.TURRET:     math.pi / 2,
}
ORIENTATION_SPEED_DEFAULT: float = math.pi / 2


@dataclass(frozen=True)
class AccelTable:
    forward: Optional[float] = None
    reverse: Optional[float] = None
    surface: Optional[float] = None
    submerged: Optional[float] = None
    water_divisor: Optional[float] = None
    sub_thrust: Optional[float] = None
    sub_reverse: Optional[float] = None
    inside_ship_speed_cap: Optional[float] = None
    wind_multiplier: Optional[float] = None
    wind_divisor: Optional[float] = None


ACCELERATION_TABLE: dict[int, AccelTable] = {
    VehicleType.HELICOPTER: AccelTable(
        forward=767.0,
        reverse=-767.0,
    ),
    VehicleType.DRONE: AccelTable(
        forward=600.0,
        reverse=-600.0,
    ),
    VehicleType.TANK: AccelTable(
        forward=32.2666666667,
        reverse=-32.2666666667,
        surface=36.6666666667,
        submerged=9.1666666667,
        water_divisor=2.9333333333,
    ),
    VehicleType.BOAT: AccelTable(
        forward=8.8,
        reverse=-8.8,
        sub_thrust=1023.0,
        sub_reverse=-1023.0,
    ),
    VehicleType.SUB_IFV: AccelTable(
        forward=19.5555555556,
        reverse=-19.5555555556,
        surface=183.3333333333,
        submerged=61.1111111111,
        water_divisor=7.3333333333,
    ),
    VehicleType.APC: AccelTable(
        forward=19.5555555556,
        reverse=-19.5555555556,
        surface=176.0,
        submerged=58.6666666667,
        water_divisor=5.8666666667,
    ),
    VehicleType.SHUTTLE: AccelTable(
        wind_multiplier=6.8444444444,
        wind_divisor=10.0,
    ),
    VehicleType.TURRET: AccelTable(
        forward=34.2222222222,
        reverse=-34.2222222222,
        surface=139.3333333333,
        submerged=69.6666666667,
        water_divisor=7.3333333333,
    ),
}

ROCKET_INSIDE_SHIP_SPEED: float = 96.875

BOAT_DEPTH_SHALLOW: float = 0.25
BOAT_DEPTH_DEEP: float    = 0.30


FRICTION_CONSTANTS: dict[str, float] = {
    "base_50":               50.0,
    "epsilon_2":              2.0,
    "ground_medium_20":      20.0,
    "water_surface_15":      15.0,
    "high_75":               75.0,
    "OnGround8_mod_30":      30.0,
    "high_150":             150.0,
    "atmos_drag_075":         0.75,
    "medium_low_4":           4.0,
    "medium_8":               8.0,
    "very_low_05":            0.5,
    "low_5":                  5.0,
    "low_med_6":              6.0,
    "treaded_60":            60.0,
    "med_high_40":           40.0,
    "water_friction_25":     25.0,
    "hover_ground_9":         9.0,
    "OnGround5_mod_35":      35.0,
    "submerged_depth_80":    80.0,
    "OnGround6_mod_7":        7.0,
    "tank_OnGround8_11":     11.0,
    "sub_OnGround1_14":      14.0,
    "sub_OnGround8_16":      16.0,
    "shallow_boat_13":       13.0,
    "deep_boat_18":          18.0,
    "tiny_3":                 3.0,
}


@dataclass(frozen=True)
class ThrottleClamp:
    minimum: int
    maximum: int


THROTTLE_CLAMPS: dict[int, ThrottleClamp] = {
    VehicleType.PLANE:      ThrottleClamp(-10, 10),
    VehicleType.JET:        ThrottleClamp(-10, 10),
    VehicleType.DRONE:      ThrottleClamp(-10, 10),
    VehicleType.LANDER:     ThrottleClamp(-10, 10),
    VehicleType.HELICOPTER: ThrottleClamp(-2, 10),
    VehicleType.TANK:       ThrottleClamp(-9, 10),
    VehicleType.BOAT:       ThrottleClamp(-9, 10),
    VehicleType.SUB_IFV:    ThrottleClamp(-9, 10),
    VehicleType.APC:        ThrottleClamp(-9, 10),
    VehicleType.SHUTTLE:    ThrottleClamp(-9, 10),
    VehicleType.TURRET:     ThrottleClamp(-8, 10),
}


ORDNANCE_COOLDOWN_MS: dict[int, int] = {
    0x0B: 332,
    0x132: 332, 0x133: 332, 0x134: 332,
    0x0C: 500,
    0x140: 500, 0x141: 500, 0x142: 500, 0x143: 500, 0x144: 500,
    0x37: 600,
    0x12B: 600,
    0x12F: 600,
    0x44: 800,
    0x12A: 800,
    0x12E: 800,
    0x38: 1000,
    0x12C: 1000,
    0x130: 1000,
    0x43: 400,
    0x129: 400,
    0x12D: 400,
    0x135: 400, 0x136: 400, 0x137: 400, 0x138: 400, 0x139: 400,
    0x13A: 400, 0x13B: 400, 0x13C: 400, 0x13D: 400, 0x13E: 400,
}


class ControlInput(enum.IntEnum):

    STOP_ALL_THRUST     = 0x00
    THROTTLE_DOWN       = 0x01
    THROTTLE_UP         = 0x02
    STRAFE_Y_DOWN       = 0x16
    STRAFE_Y_UP         = 0x17
    VERTICAL_DOWN       = 0x18
    VERTICAL_UP         = 0x19
    STRAFE_X_DOWN       = 0x2B
    STRAFE_X_UP         = 0x2C
    THROTTLE_MAX_PLUS   = 0x20
    THROTTLE_MAX_MINUS  = 0x21
    THROTTLE_SET        = 0x22

    NEXT_SEAT           = 0x03
    PREV_SEAT           = 0x04
    SEAT_0              = 0x05
    SEAT_1              = 0x06
    SEAT_2              = 0x07
    SEAT_3              = 0x08
    SEAT_4              = 0x09
    SEAT_5              = 0x0A
    SEAT_6              = 0x0B
    SEAT_7              = 0x0C
    SEAT_8              = 0x0D
    SEAT_9              = 0x0E

    YAW_RIGHT           = 0x0F
    YAW_LEFT            = 0x10
    PITCH_DOWN          = 0x12
    PITCH_UP            = 0x13
    ROLL_LEFT           = 0x14
    ROLL_RIGHT          = 0x15

    FIRE_MODE_BIT       = 0x11
    HANDBRAKE_HOVER     = 0x1A
    ENGINE_TOGGLE       = 0x1B
    HEADLIGHT_TOGGLE    = 0x1C
    FIRE_GUN            = 0x1E
    DOOR_SWITCH         = 0x1F
    SERVICE             = 0x2D
    FIRE_WEAPON         = 0x2E
    AT_REST_TOGGLE      = 0x2F
    BIT4_TOGGLE         = 0x30
    BIT3_TOGGLE         = 0x31
    REQUEST_LAUNCH      = 0x32
    REQUEST_RECOVERY    = 0x33
    CLEAR_MOTHERSHIP    = 0x34

    HEAD_LOOK_BACK      = 0x23
    HEAD_LOOK_FORWARD   = 0x24
    HEAD_LOOK_RIGHT     = 0x25
    HEAD_LOOK_BACK_R    = 0x26
    HEAD_LOOK_RIGHT_F   = 0x27
    HEAD_LOOK_LEFT      = 0x28
    HEAD_LOOK_BACK_L    = 0x29
    HEAD_LOOK_LEFT_F    = 0x2A


HEAD_LOOK_ANGLES: dict[int, float] = {
    ControlInput.HEAD_LOOK_BACK:      math.pi,
    ControlInput.HEAD_LOOK_FORWARD:   0.0,
    ControlInput.HEAD_LOOK_RIGHT:     math.pi / 2,
    ControlInput.HEAD_LOOK_BACK_R:    3 * math.pi / 4,
    ControlInput.HEAD_LOOK_RIGHT_F:   math.pi / 4,
    ControlInput.HEAD_LOOK_LEFT:     -math.pi / 2,
    ControlInput.HEAD_LOOK_BACK_L:   -3 * math.pi / 4,
    ControlInput.HEAD_LOOK_LEFT_F:   -math.pi / 4,
}


MISSILE_THRUST_HEAVY: float = 1639.0
MISSILE_THRUST_LIGHT: float = 3278.0
MISSILE_DAMPING_RATE: float = -2.0

MISSILE_AMMO_HEAVY: frozenset[int] = frozenset({
    0x38, 0x44, 0x12A, 0x12C, 0x12E, 0x130,
})
MISSILE_AMMO_LIGHT: frozenset[int] = frozenset({
    0x43, 0x129, 0x12D,
})
MISSILE_AMMO_VACUUM_OR_BH: frozenset[int] = frozenset({
    0x38, 0x44, 0x12A, 0x12C, 0x12E, 0x130,
    0x43, 0x129, 0x12D,
})
MISSILE_AMMO_PARENT_FLAG_GATED: frozenset[int] = frozenset({
    0x37, 0x12B, 0x12F,
})
MISSILE_AMMO_DRONE_BOMBLET: frozenset[int] = frozenset({
    0x132, 0x133, 0x134, 0x0B,
})


_ENCLOSED_COMMODITIES: frozenset[int] = frozenset({
    VehicleType.PLANE,
    VehicleType.HELICOPTER,
    VehicleType.JET,
    VehicleType.DRONE,
    VehicleType.BOAT,
    VehicleType.SUB_IFV,
    VehicleType.APC,
    VehicleType.LANDER,
})


def is_enclosed_vehicle(commodity_id: int) -> bool:
    return commodity_id in _ENCLOSED_COMMODITIES


_HEADLIGHT_COMMODITIES: frozenset[int] = frozenset({
    VehicleType.PLANE,
    VehicleType.HELICOPTER,
    VehicleType.TANK,
    VehicleType.APC,
    VehicleType.SUB_IFV,
})


def has_headlight(commodity_id: int) -> bool:
    return commodity_id in _HEADLIGHT_COMMODITIES


_BLIP_AIRCRAFT: frozenset[int] = frozenset({
    VehicleType.PLANE, VehicleType.JET, VehicleType.DRONE, VehicleType.LANDER,
    VehicleType.HELICOPTER,
})
_BLIP_GROUND: frozenset[int] = frozenset({
    VehicleType.TANK, VehicleType.SUB_IFV, VehicleType.APC, VehicleType.TURRET,
})
_BLIP_BOAT: frozenset[int] = frozenset({
    VehicleType.BOAT, VehicleType.SHUTTLE,
})


def blip_class_for_commodity(commodity_id: int) -> Optional[str]:
    if commodity_id in _BLIP_AIRCRAFT:
        return "aircraft"
    if commodity_id in _BLIP_GROUND:
        return "ground"
    if commodity_id in _BLIP_BOAT:
        return "boat"
    return None


def _self_check() -> None:
    assert len(HULL_STRESS_TOLERANCE) == 11, \
        f"Expected 11 hull tolerances, got {len(HULL_STRESS_TOLERANCE)}"
    assert HULL_STRESS_TOLERANCE[VehicleType.HELICOPTER] == 1000.0
    assert ORIENTATION_SPEED[VehicleType.HELICOPTER] == math.pi
    assert CRIT_ARMOR_MULTIPLIER == 0.5
    assert CRIT_ROLL_THRESHOLD == 95
    for cid, cd in DRAG_COEFFICIENT.items():
        assert 0 < cd < 1, f"Cd for {cid:#x} out of range: {cd}"
    assert MISSILE_THRUST_LIGHT == 2 * MISSILE_THRUST_HEAVY, \
        "Light missile should be exactly 2x heavy (1639 vs 3278)"
    assert len(FRICTION_CONSTANTS) == 26, \
        f"Expected 26 friction constants, got {len(FRICTION_CONSTANTS)}"
    assert len(HEAD_LOOK_ANGLES) == 8


_self_check()


TODO_DLL_CONSTANTS = """
Still-symbolic values requiring binary extraction (Phase 4+ fidelity):

1. AuCombatWeapon mode-7 fields beyond what was lifted in S11.2. The struct
   layout itself is known (0x40 bytes), but the binary's damage-mode lookup
   tables (e.g. weapon[+0x14] dice count for mode 7 by weapon type) need
   per-weapon-type dump from DbCommodity.

2. HasLight per-commodity table: ProcessControlInput case 0x1C gates on this,
   but the per-type predicate body wasn't fully lifted. has_headlight() above
   is a reasonable approximation.

3. CanTurn predicate: gates YAW_RIGHT / YAW_LEFT. Probably consults paralysis
   and launch state, plus vehicle-type-specific roll capability.

4. The PostProcessVelocity / ClampVelocity virtual slots (TickMovement step 2
   tail). Per-commodity terminal velocity caps -- needed for byte-exact
   physics. Sprint 12 noted these as "small DLL dump" follow-up.

5. The full Acceleration switch's gating constants (engine-bit, atmosphere,
   in-water, on-ground branches). Sprint 12 captured the 40+ DAT_* values
   under simple names in ACCELERATION_TABLE here, but the per-case selection
   logic that decides which one applies needs to be reproduced in
   physics.py (Phase 4). The binary's switch structure was decompiled but
   not transcribed.

6. DbCommodity armor stat block. Sprint 11 S11.3 documented offsets +0x9c
   through +0xb8 but the actual per-commodity armor values come from the
   runtime commodity DB (packet 0x2B). The solo server's existing commodity
   loader needs vehicle-relevant rows populated.
"""
