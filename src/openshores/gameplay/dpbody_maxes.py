from __future__ import annotations

import struct
from typing import NamedTuple, Optional

from openshores.core.logging import get_logger

logger = get_logger(__name__)


MAX_HP_CONSTANT = struct.unpack("<f", bytes([0xEB, 0x86, 0xEC, 0x41]))[0]


def _dna_dwords(dna: bytes) -> tuple[int, int, int, int, int, int]:
    if len(dna) < 24:
        dna = bytes(dna) + b"\x00" * (24 - len(dna))
    return struct.unpack("<6I", bytes(dna)[:24])


def can_fly(dna: bytes) -> bool:
    d = _dna_dwords(dna)
    if (d[1] & 0x400) == 0:
        return False
    return (d[0] & 0x300) != 0 and (d[0] & 0x60000) != 0


def can_jump(dna: bytes) -> bool:
    d = _dna_dwords(dna)
    if (d[1] & 0x400) == 0:
        return False
    return (d[0] & 0x300) == 0 or (d[0] & 0x60000) == 0


def max_stamina(dna: bytes) -> int:
    if not dna:
        return 0
    return ((int(dna[0]) >> 4) & 0xF) * 16 + 15


def max_hp_from_volume(volume: float, dna: bytes) -> int:
    import math
    raw = int(math.sqrt(max(0.0, float(volume))) * MAX_HP_CONSTANT)
    raw = max(0, min(0x7FFF, raw))
    if can_fly(dna):
        result = raw // 2
    elif can_jump(dna):
        result = (raw * 2) // 3
    else:
        result = raw
    return max(1, result)


def max_hp(dna: bytes) -> int:
    from openshores.gameplay.dpbody_volume import max_hit_points
    return int(max_hit_points(dna))


def max_hunger_from_max_hp(max_hp: int) -> int:
    return int(max_hp) * 2


GROWTH_SCALE_MIN = 0.2
GROWTH_SCALE_SPAN = 0.8


def minutes_to_full_grown(dna: bytes) -> int:
    d = _dna_dwords(dna)
    field = (d[3] >> 11) & 0x1F
    return (((field + 1) * 0x40) >> 3) - 1


def growth_scale(minutes_remaining: int, minutes_total: int) -> float:
    remaining = int(minutes_remaining)
    total = int(minutes_total)
    if remaining <= 0:
        return 1.0
    if total <= 0:
        return 1.0
    return ((total - remaining + 1) / total) * GROWTH_SCALE_SPAN + GROWTH_SCALE_MIN


def is_full_grown(minutes_remaining: int) -> bool:
    return int(minutes_remaining) <= 0


BURDEN_SCALE = 25


def burden_strength(dna: bytes) -> int:
    d = _dna_dwords(dna)
    return (d[4] >> 12) & 0xF


def burden_max(dna: bytes, max_hp: int = None) -> int:
    if max_hp is None:
        max_hp = max_hp_from_dna_cached(dna)
    return (burden_strength(dna) + 1 + int(max_hp) // 10) * BURDEN_SCALE


def max_hp_from_dna_cached(dna: bytes) -> int:
    try:
        return max_hp(dna)
    except Exception:
        return 1


class AvatarMaxes(NamedTuple):
    max_hp: Optional[int]
    max_stamina: int
    max_hunger: Optional[int]


def compute_maxes(dna: bytes, *,
                  volume: Optional[float] = None,
                  manual_max_hp: Optional[int] = None) -> AvatarMaxes:
    stam = max_stamina(dna)
    if manual_max_hp is not None:
        hp = int(manual_max_hp)
    elif volume is not None:
        hp = max_hp_from_volume(volume, dna)
    else:
        hp = max_hp(dna)
    hunger = max_hunger_from_max_hp(hp) if hp is not None else None
    return AvatarMaxes(max_hp=hp, max_stamina=stam, max_hunger=hunger)


if __name__ == "__main__":
    cases = [
        ("Robert",
         bytes.fromhex("7A9D60651450611672004B6C5474C562627606692D4C4E00"),
         46,
         127),
        ("Maj. Spess Croc",
         bytes.fromhex("FF16CEEAF014B2BEFB003078D426D1B3F97F32A27F167F00"),
         36,
         255),
    ]
    for name, dna, exp_hp, exp_stam in cases:
        d = _dna_dwords(dna)
        fly = can_fly(dna)
        jump = can_jump(dna)
        m = compute_maxes(dna)
        logger.info("%s:", name)
        logger.info("  dna[0..3]    = 0x%08X", d[0])
        logger.info("  dna[4..7]    = 0x%08X", d[1])
        logger.info("  CanFly       = %s", fly)
        logger.info("  CanJump      = %s", jump)
        logger.info("max_stamina = %s (expected %s, %s)",
                    m.max_stamina, exp_stam,
                    "OK" if m.max_stamina == exp_stam else "MISMATCH")
        logger.info("max_hp = %s (client says %s, %s)",
                    m.max_hp, exp_hp,
                    "OK" if m.max_hp == exp_hp else "MISMATCH")
        logger.info("  max_hunger   = %s", m.max_hunger)
        logger.info("")
