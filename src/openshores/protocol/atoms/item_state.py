
from __future__ import annotations


def _read_auitem_cid_from_body(body):
    if not body or len(body) < 3:
        return 0
    return int.from_bytes(body[1:3], "big")


def _flip_auitemstate_switched_on(body):
    if not body:
        return body, 0, 0
    old = body[-1] & 0xFF
    new = 0 if old else 1
    return bytes(body[:-1]) + bytes([new]), new, old


def _read_auitemstate_switched_on(typeId, body):
    if int(typeId) != 0x06 or not body:
        return 0
    return body[-1] & 0xFF


def _upgrade_to_auitemstate(typeId, body, switched_on=1):
    if int(typeId) == 0x06:
        return 0x06, bytes(body)
    if int(typeId) != 0x01:
        return int(typeId), bytes(body)
    return 0x06, bytes(body) + bytes([1 if switched_on else 0])
