
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import person_combat as _pc
from openshores.protocol.atoms.commodity import (
    _AMMO_CAPACITY_BY_CID,
    _COMMODITY_OVERRIDES_DEFAULT,
)

logger = get_logger(__name__)


def _body_slot_of_cursor(cursor_slot):
    s = int(cursor_slot) & 0xFF
    s = s - 0x100 if s >= 0x80 else s
    return s if -7 <= s <= -1 else None


def _body_slot_name(slot) -> str:
    return _pc.BODY_SLOT_NAMES.get(int(slot), str(slot))


def _ammo_capacity_for_cid(cid: int):
    return _AMMO_CAPACITY_BY_CID.get(int(cid) & 0xFFFF, (0, 0))


def _weapon_ammo_cids(cid: int):
    _want = int(cid) & 0xFFFF
    for entry in _COMMODITY_OVERRIDES_DEFAULT:
        try:
            if (int(entry[0]) & 0xFFFF) != _want:
                continue
        except (TypeError, ValueError, IndexError):
            logger.debug("Commodity override row has an unreadable cid: %r", entry)
            continue
        if len(entry) >= 10:
            try:
                return (int(entry[8]) & 0xFFFF, int(entry[9]) & 0xFFFF)
            except (TypeError, ValueError):
                logger.debug("Commodity override row 0x%04x has unreadable ammo cids: %r", _want, entry)
                return (0, 0)
        return (0, 0)
    return (0, 0)


def _assert_forage_0x145_reserved():
    seen = {}
    for _r in _COMMODITY_OVERRIDES_DEFAULT:
        _cid = int(_r[0]) & 0xFFFF
        if _cid in seen:
            raise AssertionError(
                "_COMMODITY_OVERRIDES_DEFAULT has duplicate cid "
                "0x%04x (entries %r and %r)" % (_cid, seen[_cid], _r))
        seen[_cid] = _r
    if 0x145 not in seen:
        raise AssertionError(
            "Task #forage-0x145: cid 0x145 must be present in _COMMODITY_OVERRIDES_DEFAULT")
    _r145 = seen[0x145]
    if int(_r145[3]) != 0 or int(_r145[4]) != 0:
        raise AssertionError(
            "Task #forage-0x145: cid 0x145 must have primary_mode == secondary_mode == 0 (no weapon synth); got primary=%r secondary=%r" % (_r145[3], _r145[4]))


_assert_forage_0x145_reserved()
