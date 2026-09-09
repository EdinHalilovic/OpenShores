
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.dpbody_maxes import max_stamina as _dna_max_stam
from openshores.gameplay.dpbody_volume import max_hit_points as _max_hp

logger = get_logger(__name__)


def _avatar_start_stats(dna: bytes) -> tuple[int, int, int]:
    try:
        stamina = int(_dna_max_stam(dna))
    except Exception as exc:
        logger.warning(
            "Start stamina from DNA failed: %r. Using 127.", exc)
        stamina = 127
    try:
        hp = int(_max_hp(dna))
    except Exception as exc:
        logger.error(
            'Start HP from DNA failed: %r.',
            exc)
        hp = 46
    return hp, stamina, hp * 2
