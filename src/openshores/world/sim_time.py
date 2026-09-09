
import math
import struct
import time
from typing import Iterable, Optional, Tuple

from openshores.core.logging import get_logger

logger = get_logger(__name__)


MS_PER_DAY = 86_400_000.0
DAYS_PER_HAZ_YEAR = 365.0 / 28.0
GAME_UNITS_PER_AU = 2_400_000.0

_NOISE_TAB1 = (15629, 15641, 15643, 15647, 15649, 15661,
               15667, 15671, 15679, 15683, 15727, 15731)
_NOISE_TAB2 = (754907, 754921, 754931, 754937, 754939, 754967,
               754969, 754973, 754979, 754981, 754991, 789221)
_NOISE_TAB3 = (1372950023, 1372950043, 1372950049, 1372950071,
               1372950077, 1372950101, 1372950133, 1372950169,
               1372950191, 1372950193, 1372950221, 1372950233)
_NOISE_OFFSET = 1.0
_NOISE_SCALE  = 1.0 / (1 << 30)


def integer_noise(zone_byte: int, slot: int) -> float:
    if not (0 <= zone_byte < len(_NOISE_TAB1)):
        return 0.0
    v = ((slot << 13) ^ slot) & 0xFFFFFFFF
    val = (_NOISE_TAB1[zone_byte] * v * v + _NOISE_TAB2[zone_byte]) * v + _NOISE_TAB3[zone_byte]
    val &= 0x7FFFFFFF
    return _NOISE_OFFSET - val * _NOISE_SCALE


def angle_at_sim_time(au: float, zone_byte: int, sim_time_ms: int,
                      parent_rot_z: float = 0.0) -> float:
    yrs = (sim_time_ms / MS_PER_DAY) / DAYS_PER_HAZ_YEAR
    period = au ** 1.5
    n = integer_noise(zone_byte, round(au * 4 - 1))
    raw = yrs / period + n
    frac = math.modf(raw)[0]
    return (frac * 2.0 * math.pi) - parent_rot_z


_SEARCH_STEPS = 200_000


def positions_for_planets(planets, sim_time_ms: int) -> dict:
    out = {}
    for name, au, zone in planets:
        a = angle_at_sim_time(au, zone, sim_time_ms)
        out[name] = (au * math.cos(a), au * math.sin(a), a)
    return out


def total_distance_from(planets, sim_time_ms: int, anchor_name: str,
                         home_fixed_au: Optional[Tuple[float, float]] = None) -> float:
    pos = positions_for_planets(planets, sim_time_ms)
    if home_fixed_au is not None:
        rx, ry = home_fixed_au
    elif anchor_name in pos:
        rx, ry, _ = pos[anchor_name]
    else:
        return float("inf")
    return sum(math.sqrt((p[0] - rx) ** 2 + (p[1] - ry) ** 2)
               for n, p in pos.items() if n != anchor_name)


def optimize_anchor(planets, anchor_name: str,
                    wallclock_ms: Optional[int] = None,
                    steps: int = _SEARCH_STEPS,
                    home_fixed_au: Optional[Tuple[float, float]] = None
                    ) -> Tuple[int, float]:
    if wallclock_ms is None:
        wallclock_ms = int(time.time() * 1000)
    high = wallclock_ms & 0xFFFFFFFF00000000
    best_T = wallclock_ms
    best_d = total_distance_from(planets, wallclock_ms, anchor_name, home_fixed_au)
    if steps <= 0:
        return best_T, best_d
    step_size = max(1, int((1 << 32) / steps))
    T_low = 0
    while T_low < (1 << 32):
        T = high | T_low
        d = total_distance_from(planets, T, anchor_name, home_fixed_au)
        if d < best_d:
            best_d = d
            best_T = T
        T_low += step_size
    return best_T, best_d


def tx32_low_bits(anchor_ms: int) -> int:
    return int(anchor_ms) & 0xFFFFFFFF


def realign_anchor_to_now(anchor_ms: int, wallclock_ms=None) -> int:
    if wallclock_ms is None:
        wallclock_ms = int(time.time() * 1000)
    return (wallclock_ms & 0xFFFFFFFF00000000) | (int(anchor_ms) & 0xFFFFFFFF)


async def compute_and_persist_anchor(conn, system_auid, anchor_name,
                                     wallclock_ms=None, *, note=""):
    from openshores.database.repositories import sim_time as repo

    if wallclock_ms is None:
        wallclock_ms = int(time.time() * 1000)
    planets = [p async for p in repo.planets_from_sql(conn, system_auid)]
    if not planets:
        return None
    names = [n for n, _, _ in planets]
    if anchor_name not in names:
        hab = [n for n, _, z in planets if z == 2]
        anchor_name = hab[0] if hab else names[0]
    home_fixed = None
    hr = await repo.home_wire_position(conn, anchor_name)
    if hr is not None:
        home_fixed = (hr[0] / GAME_UNITS_PER_AU, hr[1] / GAME_UNITS_PER_AU)
    T_full, total = optimize_anchor(planets, anchor_name, wallclock_ms,
                                      home_fixed_au=home_fixed)
    anchor_auid = await repo.atom_auid_by_name(conn, anchor_name)
    sr = await repo.system_row_for(conn, system_auid)
    system_name = sr[0] if sr else f"@{system_auid:06x}"
    await repo.upsert_anchor_row(
        conn, system_auid=system_auid, system_name=system_name,
        anchor_ms=int(T_full), total_dist_sum_au=float(total),
        optimized_for_auid=int(anchor_auid),
        optimized_for_name=anchor_name,
        wallclock_ms=int(wallclock_ms),
        source="auto-optimize", note=note)
    return await repo.read_anchor_row(conn, system_auid)


async def _bootstrap_sim_time_anchor(conn, *, whereabouts_auid):
    from openshores.database.repositories import sim_time as repo

    wb = whereabouts_auid or 0
    system_auid = 0
    anchor_name = ""
    if wb:
        for tbl in ("a_WorldGlobe", "a_WorldGasGiant"):
            r = await repo.atom_name_row(conn, tbl, wb)
            if r:
                anchor_name = r[0] or ""
                break
        cur_id = wb
        for _ in range(8):
            row = None
            for tbl in ("a_WorldGlobe", "a_WorldGasGiant", "a_Star",
                        "a_SolarSystem"):
                r = await repo.parent_atom_row(conn, tbl, cur_id)
                if r:
                    row = (tbl, r[0])
                    break
            if row is None:
                break
            tbl, parent = row
            if tbl == "a_SolarSystem":
                system_auid = cur_id
                break
            if not parent:
                break
            cur_id = parent
    if not system_auid:
        r = await repo.any_system_row(conn)
        if r:
            system_auid = r[0]
    if not system_auid:
        logger.warning(
            "No solar system in the database, so sim-time stays unpinned: "
            "the client will place every planet from its own wall clock.")
        return None
    wallclock_ms = int(time.time() * 1000)
    row = await compute_and_persist_anchor(
        conn, system_auid, anchor_name or "",
        wallclock_ms=wallclock_ms,
        note="server_stub boot")
    if row is None:
        logger.warning(
            "System 0x%08x has no usable planets, so sim-time stays unpinned: "
            "the client will place every planet from its own wall clock.",
            system_auid)
        return None
    T_full = int(row["anchor_ms"])
    T_full = realign_anchor_to_now(T_full, wallclock_ms)
    logger.info(
        "Sim-time pinned at T=0x%x (low 32 bits 0x%08x), clustering system "
        "0x%08x around %r at %.2f AU total sibling distance.",
        T_full, T_full & 0xFFFFFFFF, system_auid,
        row.get("optimized_for_name", "?"), row.get("total_dist_sum_au", 0))
    return T_full, T_full & 0xFFFFFFFF


_SIM_BOOT_MONO_T0: float = time.monotonic()
_SIM_TIME_RATE: float = 1000.0


def _current_sim_time_ms(*, anchor_full: int) -> int:
    if not anchor_full:
        return int(time.time() * 1000)
    _elapsed = time.monotonic() - _SIM_BOOT_MONO_T0
    return anchor_full + int(_elapsed * _SIM_TIME_RATE)
