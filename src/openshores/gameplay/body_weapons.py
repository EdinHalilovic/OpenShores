
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import person_combat as _pc

logger = get_logger(__name__)


def _body_weapons_from_dna(dna24, mins_to_full_grown=0):
    try:
        return _pc.body_weapon_cycle(dna24, mins_to_full_grown)
    except Exception as _bwe:
        logger.error('Body-weapon derivation failed: %r.', _bwe)
        return [(-3, 0)]
