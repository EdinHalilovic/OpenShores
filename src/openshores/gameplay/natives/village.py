from __future__ import annotations

import math
import struct
from typing import List, NamedTuple, Optional, Sequence, Tuple

from openshores.core.logging import get_logger
from openshores.database.repositories.native import save_growth
from openshores.protocol.rng import AuDice

from openshores.gameplay.native_atom import (          # noqa: E402
    ATOM_TAG_CIT_INDIGENOUS,
    BASEFLAGS_FULL,
    DNA_DEFAULT_HUMAN,
    POSE_SPAWNED_NATIVE,
    ROLE_ADULT,
    ROLE_CHILD,
    ROLE_DOCTOR,
    ROLE_ELDER,
    build_cit_indigenous,
)

logger = get_logger(__name__)


FEET_PER_METRE = 3.280839895013123
GREETER_SPACING_FT = 4.0
ELDER_OFFSET_FT = 32.80839895013123
TENT_RING_BASE_FT = 29.52755905511811
DEG_TO_RAD = 0.017453292519943295
HALF_PI = 1.5707963267948966

DEFAULT_CENTRE_OFFSET_FT = 0.0


VILLAGE_MIN_FT = 246.06299212598424
VILLAGE_MAX_FT = 574.1469816272966


VILLAGE_PROBE_TRIES = 10

VILLAGE_DIST_SIDES = 328
VILLAGE_DIST_MOD = 246

VILLAGE_BEARING_SIDES = 360

MIN_DRY_LAND_ALT_FT = 1.0

FORBIDDEN_ZONE_RADIUS_FT = 328.083989501312

CITY_AMBIENT_LIGHT_MAX = 0.009999999776482582
WORLDTEX_TYPE_CITY_LIGHTS = 0x1C

DEVELOPMENT_CLEAR_FT = 656.167979002624

LIVE_UNIT_CLEAR_FT2 = 60546.99609399206
LIVE_UNIT_CLEAR_FT = 246.06299212598424

ARBITRARY_AXIS_EPS = 0.015625

SITE_DICE_SALT = 0x51DE517E

COMMODITY_FIRE = 0x156
COMMODITY_TEPEE = 0x157

POP_MIN, POP_MAX = 3, 13

NATIVE_AUID_BASE = 0x7B000000


def _clamp_pop(pop: int) -> int:
    while pop > POP_MAX:
        pop //= 2
    return max(pop, POP_MIN)


def roll_population(dice: AuDice) -> int:
    return _clamp_pop(dice.roll(2, 4, 2))


def plan_village(dice: AuDice, pop: Optional[int] = None
                 ) -> List[Tuple[int, float, float]]:
    if pop is None:
        pop = roll_population(dice)
    pop = _clamp_pop(int(pop))

    roster: List[Tuple[int, float, float]] = [
        (ROLE_ADULT, 0.0, 0.0),
        (ROLE_ADULT, GREETER_SPACING_FT, 0.0),
    ]

    for i in range(max(pop - 2, 0)):
        if i == 0:
            roster.append((ROLE_ELDER, ELDER_OFFSET_FT, HALF_PI))
        elif i == 1 and pop > 3:
            dist = float(dice.roll(1, 2, 6))
            bearing = dice.roll(1, 360) * DEG_TO_RAD
            roster.append((ROLE_DOCTOR, dist, bearing))
        else:
            dist = float(dice.roll(1, 12, 7))
            bearing = dice.roll(1, 360) * DEG_TO_RAD
            role = ROLE_CHILD if dice.roll(1, 3) == 1 else ROLE_ADULT
            roster.append((role, dist, bearing))
    return roster


def plan_tepee_ring(pop: int) -> List[Tuple[float, float]]:
    count = int(pop) // 2
    if count <= 0:
        return []
    return [(TENT_RING_BASE_FT, i * (2.0 * math.pi / count))
            for i in range(count)]


def _offset_xyz(anchor: Sequence[float], dist_ft: float, bearing_rad: float
                ) -> Tuple[float, float, float]:
    ax, ay, az = float(anchor[0]), float(anchor[1]), float(anchor[2])
    r = math.sqrt(ax * ax + ay * ay + az * az)
    if r <= 0.0:
        return (ax + dist_ft * math.cos(bearing_rad),
                ay + dist_ft * math.sin(bearing_rad), az)
    ux, uy, uz = ax / r, ay / r, az / r
    ex, ey = -uy, ux
    en = math.hypot(ex, ey)
    if en < 1e-9:
        ex, ey, en = 1.0, 0.0, 1.0
    ex, ey, ez = ex / en, ey / en, 0.0
    nx = uy * ez - uz * ey
    ny = uz * ex - ux * ez
    nz = ux * ey - uy * ex
    c, s = math.cos(bearing_rad), math.sin(bearing_rad)
    px = ax + dist_ft * (c * nx + s * ex)
    py = ay + dist_ft * (c * ny + s * ey)
    pz = az + dist_ft * (c * nz + s * ez)
    pn = math.sqrt(px * px + py * py + pz * pz) or 1.0
    return (px * r / pn, py * r / pn, pz * r / pn)


BODY_ORIGIN_ABOVE_GROUND = 2.95


def project_to_terrain(xyz: Sequence[float],
                       terrain: Sequence[float],
                       size: int,
                       body_offset: float = BODY_ORIGIN_ABOVE_GROUND
                       ) -> Tuple[float, float, float]:
    from openshores.gameplay.worldgen.terrain import terrain_altitude_msl
    from openshores.gameplay.worldgen.world_gen import globe_radius_units

    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    r = math.sqrt(x * x + y * y + z * z)
    if r <= 0.0:
        return (x, y, z)
    try:
        t = tuple(float(v) for v in terrain)
        if len(t) != 6:
            return (x, y, z)
        lat = math.asin(max(-1.0, min(1.0, z / r)))
        lon = math.atan2(y, x)
        alt = terrain_altitude_msl(t, int(size), lat, lon)
        target = globe_radius_units(int(size)) + alt + float(body_offset)
    except Exception as exc:
        logger.warning('Terrain projection unavailable (%r).',
                       exc)
        return (x, y, z)
    if not math.isfinite(target) or target <= 0.0:
        return (x, y, z)
    s = target / r
    return (x * s, y * s, z * s)


def gravity_align_euler(xyz: Sequence[float],
                        heading_rad: float = 0.0
                        ) -> Tuple[float, float, float]:
    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    r = math.sqrt(x * x + y * y + z * z)
    if r <= 0.0:
        return (0.0, 0.0, float(heading_rad))
    ux, uy, uz = x / r, y / r, z / r

    ry = math.atan2(ux, math.hypot(uy, uz))
    rx = math.atan2(-uy, uz)

    if (1.0 + uz) < 1e-12:
        rz = 0.0
    else:
        rz = math.atan2(ux * uy, uy * uy + uz * (1.0 + uz))
    return (rx, ry, rz + float(heading_rad))


_TAU = 2.0 * math.pi


def _wrap_pi(a: float) -> float:
    a = math.fmod(float(a) + math.pi, _TAU)
    if a <= 0.0:
        a += _TAU
    return a - math.pi


def body_axes(rx: float, ry: float, rz: float
              ) -> Tuple[Tuple[float, float, float],
                         Tuple[float, float, float],
                         Tuple[float, float, float]]:
    sa, ca = math.sin(rx), math.cos(rx)
    sb, cb = math.sin(ry), math.cos(ry)
    sc, cc = math.sin(rz), math.cos(rz)
    c0 = (cb, sa * sb, -ca * sb)
    c1 = (0.0, ca, sa)
    c2 = (sb, -sa * cb, ca * cb)
    right = (cc * c0[0] + sc * c1[0],
             cc * c0[1] + sc * c1[1],
             cc * c0[2] + sc * c1[2])
    forward = (-sc * c0[0] + cc * c1[0],
               -sc * c0[1] + cc * c1[1],
               -sc * c0[2] + cc * c1[2])
    return (right, forward, c2)


def heading_to_face(xyz: Sequence[float],
                    target_xyz: Sequence[float],
                    default: float = 0.0) -> float:
    rx, ry, rz = gravity_align_euler(xyz)
    right0, fwd0, up = body_axes(rx, ry, rz)

    dx = float(target_xyz[0]) - float(xyz[0])
    dy = float(target_xyz[1]) - float(xyz[1])
    dz = float(target_xyz[2]) - float(xyz[2])
    radial = dx * up[0] + dy * up[1] + dz * up[2]
    dx -= radial * up[0]
    dy -= radial * up[1]
    dz -= radial * up[2]
    n = math.sqrt(dx * dx + dy * dy + dz * dz)
    if n < 1e-9:
        return float(default)
    dx, dy, dz = dx / n, dy / n, dz / n

    alpha = dx * right0[0] + dy * right0[1] + dz * right0[2]
    beta = dx * fwd0[0] + dy * fwd0[1] + dz * fwd0[2]
    return math.atan2(-alpha, beta)


def _f32(v: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(v)))[0]


def arbitrary_axis(v: Sequence[float]) -> Optional[Tuple[float, float, float]]:
    x, y, z = float(v[0]), float(v[1]), float(v[2])
    if abs(x) >= ARBITRARY_AXIS_EPS or abs(y) >= ARBITRARY_AXIS_EPS:
        ax, ay, az = -y, x, 0.0
    else:
        ax, ay, az = z, 0.0, -x
    n = math.sqrt(ax * ax + ay * ay + az * az)
    if n == 0.0:
        return None
    return (ax / n, ay / n, az / n)


def tangent_basis(anchor_xyz: Sequence[float]
                  ) -> Optional[Tuple[Tuple[float, float, float],
                                      Tuple[float, float, float],
                                      Tuple[float, float, float]]]:
    ax, ay, az = (float(anchor_xyz[0]), float(anchor_xyz[1]),
                  float(anchor_xyz[2]))
    r = math.sqrt(ax * ax + ay * ay + az * az)
    if r <= 0.0:
        return None
    up = (ax / r, ay / r, az / r)
    a = arbitrary_axis(up)
    if a is None:
        return None
    b = (up[1] * a[2] - up[2] * a[1],
         up[2] * a[0] - up[0] * a[2],
         up[0] * a[1] - up[1] * a[0])
    return (up, a, b)


def ll_of_loc(xyz: Sequence[float]) -> Tuple[float, float]:
    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    lon = _f32(math.atan2(y, x))
    lat = _f32(math.atan2(z, math.hypot(x, y)))
    lat = max(-HALF_PI, min(HALF_PI, float(lat)))
    lon = float(lon)
    while lon < -math.pi:
        lon += 2.0 * math.pi
    while lon > math.pi:
        lon -= 2.0 * math.pi
    return (lat, lon)


def elevate_loc_msl(xyz: Sequence[float], alt_ft: float, size: int
                    ) -> Tuple[float, float, float]:
    from openshores.gameplay.worldgen.world_gen import globe_radius_units
    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    r = math.sqrt(x * x + y * y + z * z)
    if r <= 0.0:
        return (x, y, z)
    s = (globe_radius_units(int(size)) + float(alt_ft)) / r
    return (x * s, y * s, z * s)


def city_ambient_light(lat: float, lon: float,
                       worldtex_type: int = WORLDTEX_TYPE_CITY_LIGHTS
                       ) -> Optional[float]:
    return None


def development_within(lat: float, lon: float,
                       radius_ft: float = DEVELOPMENT_CLEAR_FT
                       ) -> Optional[bool]:
    return None


def live_unit_within(xyz: Sequence[float],
                     radius2_ft2: float = LIVE_UNIT_CLEAR_FT2,
                     live_units: Optional[Sequence[Sequence[float]]] = None
                     ) -> Optional[bool]:
    if live_units is None:
        return None
    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    limit = float(radius2_ft2)
    for u in live_units:
        dx = x - float(u[0])
        dy = y - float(u[1])
        dz = z - float(u[2])
        if (dx * dx + dy * dy + dz * dz) < limit:
            return True
    return False


class VillageSpot(NamedTuple):
    lat: float
    lon: float
    alt_ft: float
    xyz: Tuple[float, float, float]
    dist_ft: float
    bearing_rad: float
    attempts: int
    unchecked: Tuple[str, ...]


_WARNED: set = set()


def _warn_once(key: str, msg: str) -> None:
    if key not in _WARNED:
        _WARNED.add(key)
        logger.warning("%s", msg)


def choose_village_location(anchor_xyz: Sequence[float],
                            terrain: Sequence[float],
                            size: int,
                            *,
                            seed: int = 1,
                            dice: Optional[AuDice] = None,
                            tries: int = VILLAGE_PROBE_TRIES,
                            dist_override_ft: Optional[float] = None,
                            live_units: Optional[Sequence[Sequence[float]]]
                            = None,
                            quiet: bool = False,
                            ) -> Optional[VillageSpot]:
    from openshores.gameplay.worldgen.terrain import terrain_altitude_msl

    centre_p = elevate_loc_msl(anchor_xyz, 0.0, size)
    basis = tangent_basis(centre_p)
    if basis is None:
        return None
    _up, a_vec, b_vec = basis
    ax, ay, az = centre_p

    if dice is None:
        dice = AuDice((int(seed) ^ SITE_DICE_SALT) & 0xFFFFFFFF)
    t = tuple(float(v) for v in terrain)
    if len(t) != 6:
        raise ValueError("Terrain must be six floats, got %d" % len(t))

    unchecked: List[str] = []
    rejected: List[str] = []
    for attempt in range(1, int(tries) + 1):
        dist = float(dice.roll(1, VILLAGE_DIST_SIDES, VILLAGE_DIST_MOD))
        deg = dice.roll(1, VILLAGE_BEARING_SIDES)
        if dist_override_ft is not None and float(dist_override_ft) > 0.0:
            dist = float(dist_override_ft)
        theta = deg * DEG_TO_RAD
        c, s = math.cos(theta), math.sin(theta)
        px = ax + a_vec[0] * (dist * c) + b_vec[0] * (dist * s)
        py = ay + a_vec[1] * (dist * c) + b_vec[1] * (dist * s)
        pz = az + a_vec[2] * (dist * c) + b_vec[2] * (dist * s)

        lat, lon = ll_of_loc((px, py, pz))

        alt = terrain_altitude_msl(t, int(size), lat, lon)
        if not (alt >= MIN_DRY_LAND_ALT_FT):
            rejected.append("wet")
            continue


        light = city_ambient_light(lat, lon)
        if light is None:
            if "city_ambient_light" not in unchecked:
                unchecked.append("city_ambient_light")
        elif not (light <= CITY_AMBIENT_LIGHT_MAX):
            rejected.append("citylight")
            continue

        devel = development_within(lat, lon, DEVELOPMENT_CLEAR_FT)
        if devel is None:
            if "development_within" not in unchecked:
                unchecked.append("development_within")
        elif devel:
            rejected.append("development")
            continue

        q = elevate_loc_msl((px, py, pz), alt, size)
        near = live_unit_within(q, LIVE_UNIT_CLEAR_FT2, live_units)
        if near is None:
            if "live_unit_within" not in unchecked:
                unchecked.append("live_unit_within")
        elif near:
            rejected.append("unit")
            continue

        if unchecked and not quiet:
            _warn_once(
                "unchecked:" + ",".join(unchecked),
                "ChooseVillageLocation port: %d of its 5 rejection "
                "clauses are NOT modelled and were skipped (%s). Each of them "
                "is a no-op on a world with no cities, no developments and no "
                "nearby fauna -- see the stub block in this module."
                % (len(unchecked), ", ".join(unchecked)))
        return VillageSpot(lat=lat, lon=lon, alt_ft=float(alt), xyz=q,
                           dist_ft=dist, bearing_rad=theta, attempts=attempt,
                           unchecked=tuple(unchecked))

    if not quiet:
        logger.warning('ChooseVillageLocation found no site in %d probes (%s).',
                       int(tries),
                       ", ".join(rejected) or "no reason recorded")
    return None


_VILLAGE_CENTRES: dict = {}
_VILLAGE_CENTRES_LAST: dict = {}


def _centre_key(anchor_xyz: Sequence[float], offset_ft: Optional[float],
                bearing_rad: float) -> tuple:
    return (round(float(anchor_xyz[0]), 6), round(float(anchor_xyz[1]), 6),
            round(float(anchor_xyz[2]), 6),
            None if offset_ft is None else round(float(offset_ft), 6),
            round(float(bearing_rad), 9))


def clear_village_centres() -> None:
    _VILLAGE_CENTRES.clear()
    _VILLAGE_CENTRES_LAST.clear()


def centre_offset_override_ft(explicit: Optional[float] = None
                              ) -> Optional[float]:
    if explicit is not None:
        try:
            v = float(explicit)
        except (TypeError, ValueError):
            v = 0.0
        if v > 0.0:
            return v
        if v < 0.0:
            return None
    return None


def village_site(anchor_xyz: Sequence[float],
                 centre_offset_ft: Optional[float] = None,
                 centre_bearing_rad: float = 0.0,
                 *,
                 terrain: Optional[Sequence[float]] = None,
                 size: Optional[int] = None,
                 seed: int = 1,
                 live_units: Optional[Sequence[Sequence[float]]] = None,
                 ) -> Tuple[Tuple[float, float, float], Optional[VillageSpot]]:
    override = centre_offset_override_ft(centre_offset_ft)
    bare = _centre_key(anchor_xyz, override, centre_bearing_rad)
    key = bare + (int(seed) & 0xFFFFFFFF,)

    if terrain is None or size is None:
        hit = _VILLAGE_CENTRES.get(key)
        if hit is None:
            hit = _VILLAGE_CENTRES_LAST.get(bare)
        if hit is not None:
            return hit
        fallback_ft = override if override is not None else VILLAGE_MIN_FT
        _warn_once(
            "centre-no-terrain",
            "no terrain data for the village site search -- falling "
            "back to a flat %.1f ft offset from the anchor. This is NOT the "
            "engine's ChooseVillageLocation (0x18067a4b0); the camp may land "
            "in the sea." % fallback_ft)
        return (_offset_xyz(anchor_xyz, fallback_ft,
                            float(centre_bearing_rad)), None)

    spot = choose_village_location(
        anchor_xyz, terrain, int(size), seed=seed,
        dist_override_ft=override, live_units=live_units)
    if spot is None:
        fallback_ft = override if override is not None else VILLAGE_MIN_FT
        logger.warning('Village site search failed; placing the camp at a flat %.1f ft instead.', fallback_ft)
        out = (_offset_xyz(anchor_xyz, fallback_ft, float(centre_bearing_rad)),
               None)
        _VILLAGE_CENTRES[key] = out
        _VILLAGE_CENTRES_LAST[bare] = out
        return out

    centre = project_to_terrain(spot.xyz, terrain, int(size))
    out = (centre, spot)
    _VILLAGE_CENTRES[key] = out
    _VILLAGE_CENTRES_LAST[bare] = out
    return out


def village_centre_xyz(anchor_xyz: Sequence[float],
                       centre_offset_ft: Optional[float] = None,
                       centre_bearing_rad: float = 0.0,
                       *,
                       terrain: Optional[Sequence[float]] = None,
                       size: Optional[int] = None,
                       seed: int = 1,
                       live_units: Optional[Sequence[Sequence[float]]] = None,
                       ) -> Tuple[float, float, float]:
    return village_site(anchor_xyz, centre_offset_ft, centre_bearing_rad,
                        terrain=terrain, size=size, seed=seed,
                        live_units=live_units)[0]


HEADING_DICE_SALT = 0x5A17C0DE
IDLE_DICE_SALT = 0x1D1E5EED

HEADING_JITTER_DEG = 30


def plan_village_headings(placements: Sequence[Tuple[int, int, str,
                                                     Tuple[float, float, float]]],
                          centre_xyz: Sequence[float],
                          anchor_xyz: Sequence[float],
                          seed: int = 1) -> List[float]:
    dice = AuDice((int(seed) ^ HEADING_DICE_SALT) & 0xFFFFFFFF)
    span = 2 * HEADING_JITTER_DEG + 1
    out: List[float] = []
    for idx, (_auid, _role, _label, xyz) in enumerate(placements):
        target = anchor_xyz if idx < 2 else centre_xyz
        h = heading_to_face(xyz, target,
                            default=dice.roll(1, 360) * DEG_TO_RAD)
        h += dice.roll(1, span, -(HEADING_JITTER_DEG + 1)) * DEG_TO_RAD
        out.append(_wrap_pi(h))
    return out


def plan_native_placements(anchor_xyz: Sequence[float],
                           pop: Optional[int] = None,
                           seed: int = 1,
                           auid_base: int = NATIVE_AUID_BASE,
                           register_manifest: bool = True,
                           centre_offset_ft: Optional[float] = None,
                           centre_bearing_rad: float = 0.0,
                           terrain: Optional[Sequence[float]] = None,
                           size: Optional[int] = None,
                           *,
                           _DYNAMIC_SCENE_AUIDS: set,
                           ) -> List[Tuple[int, int, str, Tuple[float, float, float]]]:
    dice = AuDice(seed)
    centre = village_centre_xyz(anchor_xyz, centre_offset_ft,
                                centre_bearing_rad,
                                terrain=terrain, size=size, seed=seed)
    _on_ground = (lambda p: project_to_terrain(p, terrain, size)) \
        if (terrain is not None and size is not None) else (lambda p: p)
    if terrain is None or size is None:
        logger.warning('No terrain data supplied.')

    out: List[Tuple[int, int, str, Tuple[float, float, float]]] = []
    for idx, (role, dist_ft, bearing) in enumerate(plan_village(dice, pop)):
        auid = (auid_base + idx) & 0xFFFFFFFF
        out.append((auid, role, _ROLE_LABEL[role],
                    _on_ground(_offset_xyz(centre, dist_ft, bearing))))
        if register_manifest:
            _DYNAMIC_SCENE_AUIDS.add(auid)
    return out


def native_display_name(role: int) -> str:
    return _ROLE_PLACEHOLDER_NAME[role]


def build_native_entries(world_auid: int,
                         anchor_xyz: Sequence[float],
                         dna24: bytes = DNA_DEFAULT_HUMAN,
                         pop: Optional[int] = None,
                         seed: int = 1,
                         auid_base: int = NATIVE_AUID_BASE,
                         now_ms: Optional[int] = None,
                         base_flags: int = BASEFLAGS_FULL,
                         register_manifest: bool = True,
                         terrain: Optional[Sequence[float]] = None,
                         size: Optional[int] = None,
                         centre_offset_ft: Optional[float] = None,
                         register_idle: bool = True,
                         *,
                         _DYNAMIC_SCENE_AUIDS: set,
                         ) -> List[Tuple[str, bytes]]:
    import time as _t
    if now_ms is None:
        now_ms = int(_t.time() * 1000)
    if len(dna24) != 24:
        raise ValueError("Worker DNA must be 24 bytes, got %d" % len(dna24))

    placements = plan_native_placements(
        anchor_xyz, pop=pop, seed=seed, auid_base=auid_base,
        register_manifest=register_manifest,
        centre_offset_ft=centre_offset_ft,
        terrain=terrain, size=size,
        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
    centre = village_centre_xyz(anchor_xyz, centre_offset_ft,
                                terrain=terrain, size=size, seed=seed)
    headings = plan_village_headings(placements, centre, anchor_xyz, seed=seed)

    entries: List[Tuple[str, bytes]] = []
    for (auid, role, label, (x, y, z)), heading in zip(placements, headings):
        rx, ry, rz = gravity_align_euler((x, y, z), heading)
        mins = seed_mins_to_full_grown(dna24, role)
        pkt = build_cit_indigenous(
            atom_id=auid,
            parent_id=int(world_auid),
            now_ms=now_ms,
            x=x, y=y, z=z,
            rx=rx, ry=ry, rz=rz,
            name=_ROLE_PLACEHOLDER_NAME[role],
            role=role,
            dna=dna24,
            scale_byte=mins,
            pose=POSE_SPAWNED_NATIVE,
            base_flags=base_flags,
            tag=ATOM_TAG_CIT_INDIGENOUS,
        )
        entries.append((f"DaCitIndigenous/{label}", pkt))
        if register_idle:
            register_idle_body(
                auid=auid, role=role, label=label,
                world_auid=int(world_auid), home_xyz=(x, y, z),
                heading=heading, dna24=dna24, seed=seed,
                terrain=terrain, size=size, base_flags=base_flags,
                mins_to_full_grown=mins)
    return entries


BODY_AGILITY_DEFAULT = 5

IDLE_TURN_RATE_SCALE = 0.5

IDLE_TURN_CHANCE_DENOM = 3

IDLE_TURN_SIDES = 361
IDLE_TURN_MOD = -181

IDLE_THINK_SEC = 6.0

HEAD_TILT_SIDES = 11
HEAD_TILT_MOD = -6

HEAD_TILT_LIMIT_RAD = 0.6981316804885864

IDLE_EMIT_EPS_RAD = 0.004


def turn_rate_rad_per_sec(agility: int = BODY_AGILITY_DEFAULT,
                          idle: bool = True) -> float:
    rate = ((float(int(agility) & 0xF) + 1.0) / 6.0) * math.pi
    return rate * (IDLE_TURN_RATE_SCALE if idle else 1.0)


_IDLE_BODIES: dict = {}


def register_idle_body(auid: int, role: int, label: str, world_auid: int,
                       home_xyz: Sequence[float], heading: float,
                       dna24: bytes, seed: int = 1, tilt: float = 0.0,
                       terrain: Optional[Sequence[float]] = None,
                       size: Optional[int] = None,
                       base_flags: int = BASEFLAGS_FULL,
                       agility: int = BODY_AGILITY_DEFAULT,
                       mins_to_full_grown: Optional[int] = None) -> None:
    auid = int(auid) & 0xFFFFFFFF
    if mins_to_full_grown is None:
        mins_to_full_grown = seed_mins_to_full_grown(dna24, role)
    _IDLE_BODIES[auid] = {
        "role": int(role),
        "label": str(label),
        "world_auid": int(world_auid) & 0xFFFFFFFF,
        "home": (float(home_xyz[0]), float(home_xyz[1]), float(home_xyz[2])),
        "dna": bytes(dna24),
        "base_flags": int(base_flags),
        "terrain": (tuple(float(v) for v in terrain)
                    if terrain is not None else None),
        "size": (int(size) if size is not None else None),
        "dice": AuDice((int(seed) ^ IDLE_DICE_SALT ^ auid) & 0xFFFFFFFF),
        "turn_rate": turn_rate_rad_per_sec(agility, idle=True),
        "heading": float(heading),
        "pending_turn": 0.0,
        "tilt": float(tilt),
        "next_think": None,
        "last_t": None,
        "sent_heading": float(heading),
        "sent_tilt": float(tilt),
        "mins_to_full_grown": max(0, min(255, int(mins_to_full_grown))),
        "growth_due": None,
    }


def clear_idle_bodies(auids: Optional[Sequence[int]] = None) -> None:
    if auids is None:
        _IDLE_BODIES.clear()
        return
    for a in auids:
        _IDLE_BODIES.pop(int(a) & 0xFFFFFFFF, None)


GROWTH_TICK_SEC = 60.0

GROWTH_ROLE = ROLE_CHILD


def initial_mins_to_full_grown(dna24: bytes, role: int) -> int:
    if int(role) != GROWTH_ROLE:
        return 0
    from openshores.gameplay.dpbody_maxes import minutes_to_full_grown
    return ((int(minutes_to_full_grown(bytes(dna24))) + 1) >> 1) & 0xFF


def seed_mins_to_full_grown(dna24: bytes, role: int) -> int:
    return initial_mins_to_full_grown(dna24, role)


def growth_tick(now_s: Optional[float] = None) -> List[Tuple[int, int]]:
    if not _IDLE_BODIES:
        return []
    import time as _t
    now = float(_t.monotonic() if now_s is None else now_s)

    grown: List[Tuple[int, int]] = []
    for auid, b in _IDLE_BODIES.items():
        mins = int(b.get("mins_to_full_grown") or 0)
        if mins <= 0:
            continue
        due = b.get("growth_due")
        if due is None:
            b["growth_due"] = now + GROWTH_TICK_SEC
            continue
        if now < due:
            continue
        steps = int((now - due) // GROWTH_TICK_SEC) + 1
        b["growth_due"] = due + steps * GROWTH_TICK_SEC
        mins = max(0, mins - steps)
        b["mins_to_full_grown"] = mins
        grown.append((auid, mins))
    return grown


def _body_transform(b: dict) -> Tuple[Tuple[float, float, float],
                                      Tuple[float, float, float], float]:
    pos = b["home"] if b.get("xyz") is None else b["xyz"]
    if b.get("terrain") is not None and b.get("size") is not None:
        pos = project_to_terrain(pos, b["terrain"], b["size"])
    return (pos, gravity_align_euler(pos, b["heading"]),
            float(b.get("tilt") or 0.0))


async def _persist_growth(conn, grown: Sequence[Tuple[int, int]]) -> None:
    if not grown:
        return
    try:
        await _save_growth_rows(conn, grown)
    except Exception as exc:                        # noqa: BLE001
        _warn_once("growth-persist",
                   "[natives] growth timers are not being persisted (%r) -- "
                   "villagers will re-age from their stored value on the "
                   "next restart" % (exc,))


async def _save_growth_rows(conn, grown: Sequence[Tuple[int, int]]) -> None:
    await save_growth(conn, grown)


def idle_transforms(now_s: Optional[float] = None
                    ) -> List[Tuple[int, Tuple[float, float, float],
                                    Tuple[float, float, float], float]]:
    if not _IDLE_BODIES:
        return []
    import time as _t
    now = float(_t.monotonic() if now_s is None else now_s)

    moved: List[Tuple[int, Tuple[float, float, float],
                      Tuple[float, float, float], float]] = []
    for auid, b in _IDLE_BODIES.items():
        _p = b.get("pose")
        if _p is not None and 0x12 <= int(_p) <= 0x15:
            continue
        last = b["last_t"]
        b["last_t"] = now
        dt = 0.0 if last is None else max(0.0, min(now - last, 1.0))

        if b["next_think"] is None or now >= b["next_think"]:
            b["next_think"] = now + IDLE_THINK_SEC
            dice = b["dice"]
            step_deg = dice.roll(1, HEAD_TILT_SIDES, HEAD_TILT_MOD)
            if step_deg != 0:
                t = b["tilt"] + step_deg * DEG_TO_RAD
                b["tilt"] = max(-HEAD_TILT_LIMIT_RAD,
                                min(HEAD_TILT_LIMIT_RAD, t))
            if dice.roll(1, IDLE_TURN_CHANCE_DENOM) == 1:
                b["pending_turn"] = _wrap_pi(
                    dice.roll(1, IDLE_TURN_SIDES, IDLE_TURN_MOD) * DEG_TO_RAD)

        pend = b["pending_turn"]
        if pend != 0.0 and dt > 0.0:
            step = b["turn_rate"] * dt
            if abs(pend) <= step:
                b["heading"] = _wrap_pi(b["heading"] + pend)
                b["pending_turn"] = 0.0
            else:
                step = math.copysign(step, pend)
                b["heading"] = _wrap_pi(b["heading"] + step)
                b["pending_turn"] = pend - step

        pos = b["home"]
        if b["terrain"] is not None and b["size"] is not None:
            pos = project_to_terrain(pos, b["terrain"], b["size"])
        b["xyz"] = pos

        d_hdg = abs(_wrap_pi(b["heading"] - b["sent_heading"]))
        d_tilt = abs(b["tilt"] - b["sent_tilt"])
        if d_hdg < IDLE_EMIT_EPS_RAD and d_tilt < IDLE_EMIT_EPS_RAD:
            continue
        b["sent_heading"] = b["heading"]
        b["sent_tilt"] = b["tilt"]
        moved.append((auid, pos, gravity_align_euler(pos, b["heading"]),
                      b["tilt"]))
    return moved


async def build_native_idle_entries(conn,
                                   now_ms: Optional[int] = None,
                                   now_s: Optional[float] = None,
                                   ) -> List[Tuple[str, int, bytes]]:
    import time as _t
    if now_ms is None:
        now_ms = int(_t.time() * 1000)

    moved = idle_transforms(now_s)
    grown = growth_tick(now_s)
    await _persist_growth(conn, grown)

    pending: List[Tuple[int, Tuple[float, float, float],
                        Tuple[float, float, float], float]] = list(moved)
    seen = {rec[0] for rec in pending}
    for auid, _mins in grown:
        if auid in seen:
            continue
        b = _IDLE_BODIES.get(auid)
        if b is None:
            continue
        xyz, rot, tilt = _body_transform(b)
        pending.append((auid, xyz, rot, tilt))
        seen.add(auid)

    out: List[Tuple[str, int, bytes]] = []
    for auid, xyz, (rx, ry, rz), tilt in pending:
        b = _IDLE_BODIES.get(auid)
        if b is None:
            continue
        b["xyz"] = (float(xyz[0]), float(xyz[1]), float(xyz[2]))
        b["rot"] = (float(rx), float(ry), float(rz))
        pkt = build_cit_indigenous(
            atom_id=auid,
            parent_id=b["world_auid"],
            now_ms=now_ms,
            x=xyz[0], y=xyz[1], z=xyz[2],
            rx=rx, ry=ry, rz=rz,
            head_tilt=tilt,
            name=_ROLE_PLACEHOLDER_NAME[b["role"]],
            role=b["role"],
            dna=b["dna"],
            hunger=(b["hp"] if b.get("hp") is not None else 1000),
            scale_byte=int(b.get("mins_to_full_grown") or 0),
            pose=(b["pose"] if b.get("pose") is not None
                  else POSE_SPAWNED_NATIVE),
            base_flags=b["base_flags"],
            tag=ATOM_TAG_CIT_INDIGENOUS,
        )
        out.append((f"DaCitIndigenous/{b['label']}", auid, pkt))
    return out


_ROLE_PLACEHOLDER_NAME = {
    ROLE_ADULT: "Native",
    ROLE_CHILD: "Native Child",
    ROLE_ELDER: "Native",
    ROLE_DOCTOR: "Native",
}
_ROLE_LABEL = {
    ROLE_ADULT: "Adult",
    ROLE_CHILD: "Child",
    ROLE_ELDER: "Elder",
    ROLE_DOCTOR: "Doctor",
}


if __name__ == "__main__":
    import asyncio as _asyncio

    d = AuDice(12345)
    pop = roll_population(d)
    roster = plan_village(d, pop)
    logger.info("Population %d (clamped to %d..%d)",
                pop, POP_MIN, POP_MAX)
    logger.info("Roster size %d = 2 greeters + %d villagers",
                len(roster), pop - 2)
    for role, dist, bearing in roster:
        logger.info("  %-7s %7.2f ft  %6.1f deg",
                    _ROLE_LABEL[role], dist, math.degrees(bearing))
    logger.info("Tepees %d (pop // 2)", len(plan_tepee_ring(pop)))

    ents = build_native_entries(
        world_auid=0xC9228A1A, anchor_xyz=(-6670.6, -18225.7, 19944.7),
        pop=pop, seed=12345, now_ms=0, register_manifest=False,
        register_idle=False, _DYNAMIC_SCENE_AUIDS=set())
    logger.info("Atoms %d, %d bytes total",
                len(ents), sum(len(b) for _, b in ents))
    assert all(b[0] == ATOM_TAG_CIT_INDIGENOUS for _, b in ents)
    assert len(ents) == len(roster)
    logger.info("First atom %s", ents[0][1].hex())

    def _mat(rx, ry, rz):
        ca, sa = math.cos(rx), math.sin(rx)
        cb, sb = math.cos(ry), math.sin(ry)
        cc, sc = math.cos(rz), math.sin(rz)
        Rx = [[1, 0, 0], [0, ca, -sa], [0, sa, ca]]
        Ry = [[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]]
        Rz = [[cc, -sc, 0], [sc, cc, 0], [0, 0, 1]]
        def mm(A, B):
            return [[sum(A[i][k] * B[k][j] for k in range(3))
                     for j in range(3)] for i in range(3)]
        return mm(mm(Rx, Ry), Rz)

    def _col(M, j):
        return (M[0][j], M[1][j], M[2][j])

    def _dot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    R_GLOBE = 27961.7
    probes = []
    for lat in (0.0, 12.5, 45.0, 78.0, 89.999, -33.3, -89.999):
        for lon in (0.0, 37.0, 128.0, -95.5):
            la, lo = math.radians(lat), math.radians(lon)
            probes.append((R_GLOBE * math.cos(la) * math.cos(lo),
                           R_GLOBE * math.cos(la) * math.sin(lo),
                           R_GLOBE * math.sin(la)))
    probes += [(0.0, 0.0, R_GLOBE), (0.0, 0.0, -R_GLOBE),
               (R_GLOBE, 0.0, 0.0), (0.0, R_GLOBE, 0.0)]

    worst_axes = 0.0
    for p in probes:
        for h in (0.0, 0.5, -2.1, 3.0):
            rx, ry, rz = gravity_align_euler(p, h)
            M = _mat(rx, ry, rz)
            for got, j in zip(body_axes(rx, ry, rz), (0, 1, 2)):
                want = _col(M, j)
                worst_axes = max(worst_axes,
                                 max(abs(g - w) for g, w in zip(got, want)))
    logger.info("body_axes vs matrix product   max err %.3e", worst_axes)
    assert worst_axes < 1e-12

    worst_tilt = 0.0
    for p in probes:
        n = math.sqrt(sum(c * c for c in p))
        up = tuple(c / n for c in p)
        for h in (0.0, 0.1, 1.0, -1.0, math.pi, -math.pi / 2, 2.9999):
            rx, ry, rz = gravity_align_euler(p, h)
            zc = _col(_mat(rx, ry, rz), 2)
            worst_tilt = max(worst_tilt, abs(math.degrees(
                math.acos(max(-1.0, min(1.0, _dot(zc, up)))))))
    logger.info("Tilt from local vertical max %.3e deg (over %d points x 7 headings)", worst_tilt, len(probes))
    assert worst_tilt < 1e-9, "A heading must not tip the body"

    worst_face = 0.0
    for p in probes:
        for brg in (0.0, 1.0, 2.5, -2.0, math.pi):
            for dist in (4.0, 32.8, 500.0):
                tgt = _offset_xyz(p, dist, brg)
                tgt = (tgt[0] * 1.001, tgt[1] * 1.001, tgt[2] * 1.001)
                h = heading_to_face(p, tgt)
                rx, ry, rz = gravity_align_euler(p, h)
                fwd = _col(_mat(rx, ry, rz), 1)
                n = math.sqrt(sum(c * c for c in p))
                up = tuple(c / n for c in p)
                d = [tgt[i] - p[i] for i in range(3)]
                rad = _dot(d, up)
                d = [d[i] - rad * up[i] for i in range(3)]
                dn = math.sqrt(sum(c * c for c in d))
                d = [c / dn for c in d]
                worst_face = max(worst_face, abs(math.degrees(math.acos(
                    max(-1.0, min(1.0, _dot(fwd, d)))))))
    logger.info("heading_to_face aiming error  max %.3e deg", worst_face)
    assert worst_face < 1e-4

    for p in probes:
        assert gravity_align_euler(p) == gravity_align_euler(p, 0.0)

    from openshores.gameplay.worldgen import terrain as _tr
    from openshores.gameplay.worldgen import world_gen as _wg

    class _ProbeWorld:
        def __init__(self, size, water):
            self.size = size
            self.water = water
            self.terrain = None

        def resource_zones(self):
            return 3

    T_SIZE = 9
    T_TERRAIN = _wg.create_terrain_data(_ProbeWorld(T_SIZE, 55), AuDice(9999))
    T_R = _wg.globe_radius_units(T_SIZE)

    def _terrain_alt(xyz):
        la, lo = ll_of_loc(xyz)
        return _tr.terrain_altitude_msl(T_TERRAIN, T_SIZE, la, lo)

    def _surface_point(latd, lond):
        la, lo = math.radians(latd), math.radians(lond)
        alt = _tr.terrain_altitude_msl(T_TERRAIN, T_SIZE, la, lo)
        r = T_R + alt + BODY_ORIGIN_ABOVE_GROUND
        return ((r * math.cos(la) * math.cos(lo),
                 r * math.cos(la) * math.sin(lo),
                 r * math.sin(la)), alt)

    def _great_circle(a, b):
        na = math.sqrt(sum(c * c for c in a))
        nb = math.sqrt(sum(c * c for c in b))
        d = sum(a[i] * b[i] for i in range(3)) / (na * nb)
        return T_R * math.acos(max(-1.0, min(1.0, d)))

    LAND_ANCHORS = []
    for latd in (0.0, 12.5, -33.3, 45.0, 78.0, -70.0, 5.0, -18.25):
        for lond in (0.0, 37.0, 128.0, -95.5, 60.0):
            _a, _alt = _surface_point(latd, lond)
            if _alt >= MIN_DRY_LAND_ALT_FT:
                LAND_ANCHORS.append((latd, lond, _a))
    assert len(LAND_ANCHORS) >= 12, "Probe set has too little land to be a test"
    SEEDS = (1, 2, 3, 7, 11, 4242, 12345)

    n_bodies = 0
    n_sites = 0
    worst_body_alt = float("inf")
    worst_tilt_deg = 0.0
    gc_lo, gc_hi = float("inf"), 0.0
    roll_lo, roll_hi = 10 ** 9, 0
    attempts_hist = {}
    sites_by_anchor = {}
    for latd, lond, anchor_p in LAND_ANCHORS:
        seen = set()
        for sd in SEEDS:
            clear_village_centres()
            spot = choose_village_location(anchor_p, T_TERRAIN, T_SIZE,
                                           seed=sd, quiet=True)
            assert spot is not None, (
                "No site found on dry land at lat %.2f lon %.2f seed %d"
                % (latd, lond, sd))
            n_sites += 1
            attempts_hist[spot.attempts] = attempts_hist.get(
                spot.attempts, 0) + 1

            assert spot.alt_ft >= MIN_DRY_LAND_ALT_FT

            assert (VILLAGE_DIST_MOD + 1 <= spot.dist_ft
                    <= VILLAGE_DIST_MOD + VILLAGE_DIST_SIDES)
            roll_lo = min(roll_lo, int(spot.dist_ft))
            roll_hi = max(roll_hi, int(spot.dist_ft))

            gc = _great_circle(anchor_p, spot.xyz)
            gc_lo, gc_hi = min(gc_lo, gc), max(gc_hi, gc)
            assert VILLAGE_MIN_FT <= gc <= VILLAGE_MAX_FT, (
                "Site %.1f ft away is outside the engine's 75-175 m band" % gc)
            assert abs(gc - spot.dist_ft) < 0.1, (
                "Surface distance %.3f ft does not match the roll %.0f ft"
                % (gc, spot.dist_ft))

            assert set(spot.unchecked) == {"city_ambient_light",
                                           "development_within",
                                           "live_unit_within"}

            clear_village_centres()
            again = choose_village_location(anchor_p, T_TERRAIN, T_SIZE,
                                           seed=sd, quiet=True)
            assert again == spot, "The site search is not reproducible"
            seen.add((round(spot.lat, 9), round(spot.lon, 9)))

            clear_village_centres()
            pl = plan_native_placements(anchor_p, seed=sd,
                                        register_manifest=False,
                                        terrain=T_TERRAIN, size=T_SIZE,
                                        _DYNAMIC_SCENE_AUIDS=set())
            assert len(pl) >= POP_MIN
            for _auid, _role, _label, bxyz in pl:
                n_bodies += 1
                balt = _terrain_alt(bxyz)
                worst_body_alt = min(worst_body_alt, balt)
                assert balt > 0.0, (
                    "Villager %s is under water (%.2f ft) at lat %.2f lon %.2f seed %d" % (_label, balt, latd, lond, sd))
                bn = math.sqrt(sum(c * c for c in bxyz))
                bup = tuple(c / bn for c in bxyz)
                zc = _col(_mat(*gravity_align_euler(bxyz, 1.234)), 2)
                worst_tilt_deg = max(worst_tilt_deg, math.degrees(math.sqrt(
                    sum((zc[i] - bup[i]) ** 2 for i in range(3)))))
        sites_by_anchor[(latd, lond)] = seen

    logger.info("Village sites %d searched over %d land anchors x %d seeds",
                n_sites, len(LAND_ANCHORS), len(SEEDS))
    logger.info("Distance roll %d..%d ft (engine 1d%d+%d = %d..%d)",
                roll_lo, roll_hi, VILLAGE_DIST_SIDES, VILLAGE_DIST_MOD,
                VILLAGE_DIST_MOD + 1, VILLAGE_DIST_MOD + VILLAGE_DIST_SIDES)
    logger.info("Surface distance %.1f..%.1f ft (band %.1f..%.1f)",
                gc_lo, gc_hi, VILLAGE_MIN_FT, VILLAGE_MAX_FT)
    logger.info("Probes needed %s", dict(sorted(attempts_hist.items())))
    logger.info("  %d villagers, min ground altitude %.2f ft, max tilt from "
                "vertical %.3e deg", n_bodies, worst_body_alt, worst_tilt_deg)
    assert worst_tilt_deg < 1e-9, "A searched village is not gravity-aligned"
    for (latd, lond), seen in sites_by_anchor.items():
        assert len(seen) >= len(SEEDS) - 1, (
            "Seeds collapse onto one site at lat %.2f lon %.2f" % (latd, lond))

    OCEAN = _wg.create_terrain_data(_ProbeWorld(T_SIZE, 110), AuDice(9999))
    assert _tr.land_fraction(OCEAN, T_SIZE, samples=12) == 0.0
    ocean_anchor = (T_R, 0.0, 0.0)
    assert choose_village_location(ocean_anchor, OCEAN, T_SIZE, seed=1,
                                   quiet=True) is None, \
        "An ocean world must yield the engine's (0,0) sentinel"
    logger.info("Ocean world -> None (the engine's (0,0) sentinel)")

    pole_branch = 0
    for latd in (0.0, 45.0, 89.0, 89.5, 89.9, 90.0, -90.0, -89.9):
        for lond in (0.0, 90.0, -170.0):
            la, lo = math.radians(latd), math.radians(lond)
            p = (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
                 math.sin(la))
            up, av, bv = tangent_basis(p)
            if abs(up[0]) < ARBITRARY_AXIS_EPS and abs(up[1]) < \
                    ARBITRARY_AXIS_EPS:
                pole_branch += 1
            for v in (up, av, bv):
                assert abs(math.sqrt(_dot(v, v)) - 1.0) < 1e-12
            assert abs(_dot(up, av)) < 1e-12
            assert abs(_dot(up, bv)) < 1e-12
            assert abs(_dot(av, bv)) < 1e-12
            cr = (av[1] * bv[2] - av[2] * bv[1],
                  av[2] * bv[0] - av[0] * bv[2],
                  av[0] * bv[1] - av[1] * bv[0])
            assert max(abs(cr[i] - up[i]) for i in range(3)) < 1e-12
    assert pole_branch >= 3, "ArbitraryAxis' pole branch was never exercised"
    logger.info("Tangent basis orthonormal at 24 latitudes (%d through ArbitraryAxis' pole branch)", pole_branch)

    anchor_p = LAND_ANCHORS[0][2]
    base = choose_village_location(anchor_p, T_TERRAIN, T_SIZE, seed=5,
                                   quiet=True)
    assert base is not None and base.attempts == 1
    blocked = choose_village_location(anchor_p, T_TERRAIN, T_SIZE, seed=5,
                                      live_units=[base.xyz], quiet=True)
    assert blocked is None or blocked.attempts > 1, \
        "A live unit standing on the site did not reject it"
    assert "live_unit_within" not in (blocked.unchecked if blocked else ())
    fed = choose_village_location(anchor_p, T_TERRAIN, T_SIZE, seed=5,
                                  live_units=[], quiet=True)
    assert fed is not None and fed[:-1] == base[:-1],         "An empty live-unit list changed the chosen site"
    assert "live_unit_within" not in fed.unchecked
    assert "live_unit_within" in base.unchecked
    logger.info("Live-unit clause rejects a blocked site when fed positions")

    anchor_p = LAND_ANCHORS[0][2]
    assert centre_offset_override_ft(None) is None
    assert centre_offset_override_ft(DEFAULT_CENTRE_OFFSET_FT) is None
    clear_village_centres()
    far = village_site(anchor_p, DEFAULT_CENTRE_OFFSET_FT,
                       terrain=T_TERRAIN, size=T_SIZE, seed=1)[1]
    assert far is not None and far.dist_ft >= VILLAGE_DIST_MOD + 1

    assert centre_offset_override_ft(40.0) == 40.0
    for mode, arg in (("person", 40.0),):
        clear_village_centres()
        centre, spot = village_site(anchor_p, arg, terrain=T_TERRAIN,
                                    size=T_SIZE, seed=1)
        assert spot is not None, f"{mode}: override lost the site search"
        assert abs(spot.dist_ft - 40.0) < 1e-9, (
            f"{mode}: the distance override was ignored ({spot.dist_ft})")
        assert spot.alt_ft >= MIN_DRY_LAND_ALT_FT
        gc = _great_circle(anchor_p, centre)
        assert gc < 60.0, f"{mode}: override put the camp {gc:.1f} ft out"
    logger.info("Distance override honoured on the person atom mode (forwarded).")
    clear_village_centres()

    anchor_p = LAND_ANCHORS[1][2]
    clear_village_centres()
    searched = village_centre_xyz(anchor_p, None, terrain=T_TERRAIN,
                                  size=T_SIZE, seed=777)
    assert village_centre_xyz(anchor_p, None) == searched, \
        "The seedless caller lost the searched centre"
    assert _great_circle(anchor_p, searched) > VILLAGE_MIN_FT * 0.9
    clear_village_centres()
    logger.info("Centre memo seedless re-derivation agrees with the search")

    anchor_p = LAND_ANCHORS[2][2]
    clear_village_centres()
    far_places = plan_native_placements(anchor_p, seed=31337,
                                        register_manifest=False,
                                        terrain=T_TERRAIN, size=T_SIZE,
                                        _DYNAMIC_SCENE_AUIDS=set())
    far_centre = village_centre_xyz(anchor_p, None, terrain=T_TERRAIN,
                                    size=T_SIZE, seed=31337)
    far_heads = plan_village_headings(far_places, far_centre, anchor_p,
                                      seed=31337)
    clear_idle_bodies()
    for (a_, r_, l_, x_), h_ in zip(far_places, far_heads):
        register_idle_body(auid=a_, role=r_, label=l_, world_auid=0xC9228A1A,
                           home_xyz=x_, heading=h_, dna24=DNA_DEFAULT_HUMAN,
                           seed=31337, terrain=T_TERRAIN, size=T_SIZE)
    far_homes = {a: _IDLE_BODIES[a]["home"] for a in _IDLE_BODIES}
    far_stray = 0.0
    tt = 0.0
    while tt < 120.0:
        tt += 0.5
        _asyncio.run(build_native_idle_entries(None, now_ms=0, now_s=tt))
        for a, b in _IDLE_BODIES.items():
            hx, hy, hz = far_homes[a]
            x, y, z = b["xyz"]
            far_stray = max(far_stray, math.sqrt((x - hx) ** 2 + (y - hy) ** 2
                                                 + (z - hz) ** 2))
    logger.info("Idle at 75-175 m max stray %.3e ft (float round-off in the terrain re-projection, not motion)",
                far_stray)
    assert far_stray < 1e-6, "An idle villager walked; the engine does not"
    clear_idle_bodies()
    clear_village_centres()

    anchor = (-6670.6, -18225.7, 19944.7)
    places = plan_native_placements(anchor, pop=pop, seed=12345,
                                    register_manifest=False,
                                    _DYNAMIC_SCENE_AUIDS=set())
    centre = village_centre_xyz(anchor)
    heads = plan_village_headings(places, centre, anchor, seed=12345)
    degs = sorted(round(math.degrees(h), 1) for h in heads)
    logger.info("Headings (deg) %s", degs)
    assert len(set(degs)) == len(degs), "Villagers must not share a heading"

    clear_idle_bodies()
    for (auid, role, label, xyz), h in zip(places, heads):
        register_idle_body(auid=auid, role=role, label=label,
                           world_auid=0xC9228A1A, home_xyz=xyz, heading=h,
                           dna24=DNA_DEFAULT_HUMAN, seed=12345)
    homes = {a: _IDLE_BODIES[a]["home"] for a in _IDLE_BODIES}
    t = 0.0
    max_stray = 0.0
    max_tilt = 0.0
    turned = set()
    tilted = set()
    emitted = 0
    pkt_len: dict = {}
    while t < 600.0:
        t += 0.5
        for label, auid, pkt in _asyncio.run(
                build_native_idle_entries(None, now_ms=0, now_s=t)):
            assert pkt[0] == ATOM_TAG_CIT_INDIGENOUS
            assert pkt[-1] == _IDLE_BODIES[auid]["role"]
            assert pkt_len.setdefault(auid, len(pkt)) == len(pkt)
            emitted += 1
        for auid, b in _IDLE_BODIES.items():
            hx, hy, hz = homes[auid]
            x, y, z = b["xyz"]
            max_stray = max(max_stray, math.sqrt(
                (x - hx) ** 2 + (y - hy) ** 2 + (z - hz) ** 2))
            max_tilt = max(max_tilt, abs(b["tilt"]))
            if abs(b["heading"] - heads[places.index(
                    next(p for p in places if p[0] == auid))]) > 1e-9:
                turned.add(auid)
            if b["tilt"] != 0.0:
                tilted.add(auid)
    logger.info("Idle 600 s %d re-emits, %d/%d turned, %d/%d tilted",
                emitted, len(turned), len(_IDLE_BODIES),
                len(tilted), len(_IDLE_BODIES))
    logger.info("Max |head tilt| %.3f deg (engine cap %.1f)",
                math.degrees(max_tilt), math.degrees(HEAD_TILT_LIMIT_RAD))
    logger.info("Max stray %.3e ft (must be 0, engine-exact)",
                max_stray)
    assert max_stray == 0.0, "An idle villager walked; the engine does not"
    assert max_tilt <= HEAD_TILT_LIMIT_RAD + 1e-9, "Head tilt exceeded +-40 deg"
    assert max_tilt > 0.0, "Nobody ever tilted. The head tilt is inert"
    assert turned, "Nobody ever turned. The idle turn is inert"
    assert emitted > 0, "Nothing ever changed. Idle motion is inert"
    clear_idle_bodies()
    logger.info("OK")
