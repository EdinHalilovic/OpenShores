
from __future__ import annotations

WORLD_UNITS_PER_METRE = 3.280839895013123
ONE_METRE = WORLD_UNITS_PER_METRE
TWO_METRES = 2.0 * WORLD_UNITS_PER_METRE

FIXED_SPAWN_RADIUS_INDUSTRIES = frozenset({0x22, 0x3E, 0x55, 0x59, 0x81})

TOWN_SQUARE_INDUSTRY = 1
MILITARY_FLAG_INDUSTRY = 10
GARRISON_SPAWN_INDUSTRIES = frozenset({TOWN_SQUARE_INDUSTRY,
                                       MILITARY_FLAG_INDUSTRY})

MAX_TROOPS_PER_DEVLL = 1


def max_worker_spawn_radius(industry_id, terrain_level_radius=0.0):
    if int(industry_id) in FIXED_SPAWN_RADIUS_INDUSTRIES:
        return TWO_METRES
    return float(terrain_level_radius) - ONE_METRE


class GarrisonSpawn:

    __slots__ = ("flag_index", "location", "industry_id", "radius")

    def __init__(self, flag_index, location, industry_id, radius):
        self.flag_index = flag_index
        self.location = location
        self.industry_id = industry_id
        self.radius = radius

    def __repr__(self):
        return ("GarrisonSpawn(flag=%d, industry=0x%02x, radius=%.3f)"
                % (self.flag_index, self.industry_id, self.radius))

    def __eq__(self, other):
        return (isinstance(other, GarrisonSpawn)
                and self.flag_index == other.flag_index
                and self.location == other.location
                and self.industry_id == other.industry_id
                and abs(self.radius - other.radius) < 1e-9)


def plan_garrison_spawns(garrison_troops, flags, building_at, troops_at,
                         terrain_radius_at=None):
    pool = int(garrison_troops)
    spawns = []
    if pool <= 0 or not flags:
        return spawns, pool

    target_empire = flags[0].get("empire")

    for idx, flag in enumerate(flags):
        if pool <= 0:
            break
        if flag.get("empire") != target_empire:
            continue
        loc = flag.get("location")
        b = building_at(loc)
        if not b or b.get("destroyed"):
            continue
        industry = int(b.get("industry_id", 0))
        if industry not in GARRISON_SPAWN_INDUSTRIES:
            continue
        if int(troops_at(loc) or 0) >= MAX_TROOPS_PER_DEVLL:
            continue
        tr = 0.0
        if terrain_radius_at is not None:
            tr = float(terrain_radius_at(loc) or 0.0)
        spawns.append(GarrisonSpawn(idx, loc, industry,
                                    max_worker_spawn_radius(industry, tr)))
        pool -= 1
    return spawns, pool


def take_garrison_troop(state):
    n = int(getattr(state, "garrison_troops", 0) or 0)
    if n == 0:
        return False
    state.garrison_troops = n - 1
    return True


ENCOUNTER_SPAWNED = 0
ENCOUNTER_DISABLED = 1
ENCOUNTER_NOT_IN_CITY = 2
ENCOUNTER_NO_CITY_FOUND = 3
ENCOUNTER_NO_LOCATION = 4
ENCOUNTER_NO_POPULATION = 5
ENCOUNTER_CROWDED = 6
ENCOUNTER_PLAYER_FLAG = 7
ENCOUNTER_IN_WATER = 8
ENCOUNTER_UNDER_ATTACK = 9

AMBIENT_CROWD_FACTOR = 10.0

ENCOUNTER_RADIUS_WORLD = 164.042

ORDER_CHANCE_NUM = 0x684
ORDER_CHANCE_DEN = 10000

CITIZEN_ORDER_GO_TO_TARGET = 8


def crowd_cap(ambient_light: float) -> int:
    import math as _m
    return int(_m.ceil(float(ambient_light) * AMBIENT_CROWD_FACTOR))


def encounter_plan(*, enabled=True, in_city_or_bd=True, city_found=True,
                   player_flag=False, in_water=False, under_attack=False,
                   population=0, citizens_present=0, citizens_nearby=0,
                   ambient_light=0.0, roll_1d3=1, have_location=True):
    if not enabled:
        return 0, ENCOUNTER_DISABLED
    if not in_city_or_bd:
        return 0, ENCOUNTER_NOT_IN_CITY
    if player_flag:
        return 0, ENCOUNTER_PLAYER_FLAG
    if in_water:
        return 0, ENCOUNTER_IN_WATER
    if under_attack:
        return 0, ENCOUNTER_UNDER_ATTACK
    if not city_found:
        return 0, ENCOUNTER_NO_CITY_FOUND
    available = int(population) - int(citizens_present)
    if available < 1:
        return 0, ENCOUNTER_NO_POPULATION
    if crowd_cap(ambient_light) < int(citizens_nearby):
        return 0, ENCOUNTER_CROWDED
    if not have_location:
        return 0, ENCOUNTER_NO_LOCATION
    return max(0, min(int(roll_1d3), available)), ENCOUNTER_SPAWNED


def wants_order(roll_1_10000: int, player_inside_building: bool = False,
                citizen_inside_building: bool = False) -> bool:
    if player_inside_building or citizen_inside_building:
        return False
    return int(roll_1_10000) < ORDER_CHANCE_NUM


def add_garrison_troop(state) -> int:
    n = int(getattr(state, "garrison_troops", 0) or 0) + 1
    state.garrison_troops = n
    return n
