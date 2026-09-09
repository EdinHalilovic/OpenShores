
from __future__ import annotations

from openshores.protocol.rng import AuDice

TESTQUALITY_SIDES = 0x0FAA
TESTQUALITY_BASE = 0x0DAC
TESTQUALITY_QUALITY_MUL = 2

USE_NOTHING_HAPPENED = 0
USE_CONSUMED = 1
USE_WORE_DOWN = 2
USE_INVALID = -1

_AUITEM_FLAG_NAMED = 0x08
_COND_OFFSET = 3

_DICE = AuDice()
_DICE.time_seed()


def seed(value):
    _DICE.seed(int(value) & 0xFFFFFFFF)


def _quality_offset(body):
    if not body:
        return -1
    if body[0] & _AUITEM_FLAG_NAMED:
        if len(body) < 8:
            return -1
        namelen = int.from_bytes(body[4:8], "big")
        return 8 + namelen
    return 4


def condition(body):
    body = bytes(body or b"")
    return body[_COND_OFFSET] if len(body) > _COND_OFFSET else -1


def set_condition(body, value):
    body = bytearray(body or b"")
    if len(body) > _COND_OFFSET:
        body[_COND_OFFSET] = int(value) & 0xFF
    return bytes(body)


def quality(body):
    body = bytes(body or b"")
    off = _quality_offset(body)
    return body[off] if 0 <= off < len(body) else 0


def test_quality(q, dice=None):
    d = dice or _DICE
    return d.roll(1, TESTQUALITY_SIDES) < (int(q) * TESTQUALITY_QUALITY_MUL
                                           + TESTQUALITY_BASE)


def test_failure(q, n, dice=None):
    d = dice or _DICE
    q = int(q)
    n = int(n)
    if q >= 0xFF:
        return n
    thresh = q * TESTQUALITY_QUALITY_MUL + TESTQUALITY_BASE
    roll = d.roll(1, TESTQUALITY_SIDES)
    if n == 1:
        return 1 if roll < thresh else 0
    if n <= 0x1057D8:
        survivors = (thresh * n) // TESTQUALITY_SIDES
    else:
        survivors = (n // TESTQUALITY_SIDES) * thresh
    if survivors < n and roll <= thresh:
        survivors += 1
    return survivors


def au_item_use(body, dice=None):
    cond = condition(body)
    if cond <= 0:
        return bytes(body or b""), False
    if test_quality(quality(body), dice):
        return bytes(body or b""), True
    cond -= 1
    return set_condition(body, cond), cond != 0


def sentient_use(body, *, consumable=False, dice=None):
    body = bytes(body or b"")
    if consumable:
        return body, USE_CONSUMED, True
    before = condition(body)
    new_body, usable = au_item_use(body, dice)
    if usable:
        after = condition(new_body)
        return new_body, (USE_WORE_DOWN if after != before
                          else USE_NOTHING_HAPPENED), False
    return new_body, USE_CONSUMED, True


def use_gear_item(gear, index, *, consumable=False, dice=None):
    try:
        entry = gear[index]
    except Exception:
        return USE_INVALID, False, -1, -1
    slottype = int(entry[0]) & 0xFF
    if not (1 <= slottype <= 9):
        return USE_INVALID, False, -1, -1
    body = bytes(entry[3])
    before = condition(body)
    new_body, code, destroyed = sentient_use(body, consumable=consumable,
                                             dice=dice)
    if destroyed:
        gear.pop(index)
        return code, True, before, 0
    entry[3] = new_body
    return code, False, before, condition(new_body)


def find_ready_index(gear, cid, cid_of, *, type_id=0x01):
    for i, e in enumerate(gear or ()):
        try:
            if int(e[2]) == type_id and int(cid_of(e)) == int(cid):
                return i
        except Exception:
            continue
    return -1
