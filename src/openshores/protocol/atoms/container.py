
from __future__ import annotations

from openshores.protocol.atoms.item import _unpack_auitem_body


def _container_locate_nested_block(body):
    if not body or len(body) < 5:
        return None
    flag = body[0]
    off = 1 + 2
    if flag & 0x04:
        off += 1
    if flag & 0x08:
        if off + 4 > len(body):
            return None
        nl = int.from_bytes(body[off:off+4], 'big'); off += 4
        off += nl
    off += 1
    if flag & 0x10:
        off += 4
    if flag & 0x20:
        off += 1
    if off > len(body):
        return None
    return off


def _container_decode_body(body):
    nb_off = _container_locate_nested_block(body)
    if nb_off is None or nb_off + 3 > len(body):
        raise ValueError(
            "AuItemBox body: truncated at capacity/magic/count "
            "(len=%d off=%s)" % (len(body), nb_off))
    base = bytes(body[:nb_off])
    capacity = body[nb_off]
    magic = body[nb_off + 1]
    cur = nb_off + 2
    if magic >= 0xF1:
        if cur >= len(body):
            raise ValueError(
                "AuItemBox body: truncated at explicit-count")
        n_nested = body[cur]; cur += 1
        explicit_keys = True
    else:
        n_nested = magic
        explicit_keys = False
    nested = []
    for i in range(n_nested):
        key = 0
        if explicit_keys:
            if cur >= len(body):
                raise ValueError(
                    "AuItemBox body: truncated at nested[%d] key" % i)
            key = body[cur]; cur += 1
        if cur >= len(body):
            raise ValueError(
                "AuItemBox body: truncated at nested[%d] typeId" % i)
        n_tid = body[cur]; cur += 1
        n_body, cur = _unpack_auitem_body(n_tid, body, cur)
        nested.append([key, n_tid, n_body])
    return base, capacity, nested


def _container_encode_body(base_bytes, capacity, nested):
    out = bytearray(base_bytes)
    if int(capacity) > 0xFF:
        raise ValueError("AuItemBox capacity overflow")
    out += bytes([int(capacity) & 0xFF])
    out += bytes([0xF1])
    if len(nested) > 0xFF:
        raise ValueError("AuItemBox nested count overflow")
    out += bytes([len(nested)])
    for entry in nested:
        if len(entry) >= 3:
            key, n_tid, n_body = entry[0], entry[1], entry[2]
        else:
            raise ValueError("Nested entry malformed: %r" % (entry,))
        out += bytes([int(key) & 0xFF, int(n_tid) & 0xFF])
        out += bytes(n_body)
    return bytes(out)
