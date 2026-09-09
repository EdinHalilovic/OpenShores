
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.dpbody_maxes import burden_max as _bmax
from openshores.gameplay.gear_commodity import _weight_for_cid
from openshores.gameplay.gear_entry import _gear_cid_of
from openshores.protocol.atoms.container import _container_decode_body
from openshores.protocol.atoms.item import _extract_cid_from_auitem_body

logger = get_logger(__name__)


GRAVPACK_CID = 0x126


def _gear_weight(gear) -> float:
    total = 0.0
    try:
        for _e in (gear or ()):
            tid = int(_e[2]) & 0xFF
            cid = _gear_cid_of(_e)
            total += _weight_for_cid(cid)
            if tid != 0x12 or (int(cid) & 0xFFFF) == GRAVPACK_CID:
                continue
            try:
                _b, _c, nested = _container_decode_body(bytes(_e[3]))
            except Exception:
                continue
            for n in nested:
                total += _weight_for_cid(
                    _extract_cid_from_auitem_body(bytes(n[2])) & 0xFFFF)
    except Exception as exc:
        logger.error(f'Gear weight walk failed: {exc!r}.')
    return total


def _burden_max(dna=None) -> float:
    if not dna or len(dna) < 24:
        return 0.0
    try:
        return float(_bmax(bytes(dna)))
    except Exception as exc:
        logger.error('BurdenMax failed for a %d-byte genome: %r.',
                     len(bytes(dna)), exc)
        return 0.0


def _can_carry(dna, gear, cid, count=1):
    cap = _burden_max(dna)
    if cap <= 0:
        return True, None
    add = _weight_for_cid(cid) * max(1, int(count))
    cur = _gear_weight(gear)
    if cur + add <= cap:
        return True, None
    return False, ("carrying %.2f kg of %.2f; cid %s adds %.2f"
                   % (cur, cap, cid, add))
