
from __future__ import annotations

import logging
import struct

from openshores.protocol.atoms.daitem import (
    pack_auitem_body as _pack_auitem_body,
)
from openshores.protocol.atoms.item import (
    _extract_cid_from_auitem_body,
    _pack_qstring,
    _skip_qstring,
    _unpack_auitem_body,
)
from openshores.protocol.atoms.item_seed import _pack_auitem_seed_body
from openshores.protocol.atoms.weapon import (
    _EXPECTED_AMMO_BODYLEN,
    _EXPECTED_KNIFE_BODYLEN,
    _WEAPON_DEFAULTS_KNIFE,
    _WEAPON_MIN_INTEGRITY,
    _weapon_cid_sets,
    _weapon_spec_for_cid,
)

logger = logging.getLogger(__name__)


def _pack_auitem_hash(entries=()):
    out = bytearray()
    out += struct.pack(">i", len(entries))
    for typeId, cid in entries:
        out.append(int(typeId) & 0xFF)
        out += _pack_auitem_body(int(cid) & 0xFFFF)
    return bytes(out)


_AUITEM_CREATABLE_TYPES = frozenset(range(0x01, 0x18))


def _pack_au_gear(slots=()):
    weapon_sets = _weapon_cid_sets()
    has_filters = any(weapon_sets)
    work = list(slots)
    in_place = isinstance(slots, list) and slots and isinstance(slots[0], list)
    if has_filters and work:
        norm = [list(e) if not isinstance(e, list) else e for e in work]
        try:
            _apply_weapon_typeid_migration(norm, source="emit")
        except Exception as _me:
            logger.error('Weapon typeId migration failed while packing AuGear: %r.', _me)
        if in_place:
            for i, e in enumerate(norm):
                slots[i][:] = e
        work = norm
    kept = []
    for _entry in work:
        _st, _sub, _tid, _body = _entry
        if (int(_tid) & 0xFF) not in _AUITEM_CREATABLE_TYPES:
            logger.warning(
                'Dropped AuGear slot=%s sub=%s typeId=0x%02x: AuItem::Create cannot build it.',
                _st, _sub, int(_tid) & 0xFF)
            continue
        kept.append(_entry)
    out = bytearray()
    n = len(kept)
    if n > 0xFF:
        raise ValueError("AuGear slot count overflow")
    out.append(n)
    for slottype, subindex, typeId, body in kept:
        meta = ((int(subindex) & 0x0F) << 4) | (int(slottype) & 0x0F)
        out.append(meta & 0xFF)
        out.append(int(typeId) & 0xFF)
        out += body
    return bytes(out)


def _unpack_au_gear(blob):
    if not blob:
        return []
    n = blob[0]
    off = 1
    out = []
    for _ in range(n):
        if off + 2 > len(blob):
            raise ValueError("AuGear: truncated at slot header")
        meta = blob[off]; off += 1
        typeId = blob[off]; off += 1
        slottype = meta & 0x0F
        sub = (meta >> 4) & 0x0F
        if typeId == 0:
            out.append([slottype, sub, 0, b""])
            continue
        body, off = _unpack_auitem_body(typeId, blob, off)
        out.append([slottype, sub, typeId, body])
    if out and off < len(blob):
        trailing = blob[off:]
        last = out[-1]
        last[3] = bytes(last[3]) + bytes(trailing)
        logger.debug("Folded %d trailing bytes into AuGear slot %d/sub %d "
                     "typeId 0x%02X (hex=%s)",
                     len(trailing), last[0], last[1], last[2],
                     trailing.hex())
    return out


def _auitem_base_end(body: bytes) -> int:
    body = bytes(body or b"")
    if len(body) < 4:
        return -1
    flag = body[0]
    off = 4
    if flag & 0x08:
        if off + 4 > len(body):
            return -1
        off += 4 + int.from_bytes(body[off:off + 4], "big")
    if off >= len(body):
        return -1
    return off + 1


def _set_item_message(orig_body: bytes, text) -> bytes:
    body = bytes(orig_body or b"")
    end = _auitem_base_end(body)
    if end < 0 or end >= len(body):
        return body
    state = body[end]
    return body[:end] + bytes([state]) + _pack_qstring(text)


def _set_item_picture(orig_body: bytes, url, url_hidden=None,
                      rotate=None) -> bytes:
    body = bytes(orig_body or b"")
    end = _auitem_base_end(body)
    if end < 0:
        return body
    try:
        after_url = _skip_qstring(body, end, "AuItemPicture url")
    except ValueError:
        return body
    old = body[after_url] if after_url < len(body) else 0
    rot = (old & 0x01) if rotate is None else (1 if rotate else 0)
    hid = ((old >> 1) & 0x01) if url_hidden is None else (1 if url_hidden else 0)
    return body[:end] + _pack_qstring(url) + bytes([(hid << 1) | rot])


def _reinscribe_body(orig_body: bytes, text) -> bytes:
    body = bytes(orig_body or b"")
    if len(body) < 4:
        return body
    flag = body[0]
    off = 1
    cid = int.from_bytes(body[off:off + 2], "big") & 0xFFFF
    off += 2
    byte14 = body[off]
    off += 1
    if flag & 0x08:
        if off + 4 > len(body):
            return body
        nlen = int.from_bytes(body[off:off + 4], "big")
        off += 4 + nlen
    if off >= len(body):
        return body
    quality = body[off]
    tail = body[off + 1:]

    new_name = "" if text is None else str(text)
    out = bytearray()
    out.append((flag & ~0x08) | (0x08 if new_name else 0x00))
    out += int(cid).to_bytes(2, "big")
    out.append(byte14 & 0xFF)
    if new_name:
        utf16 = new_name.encode("utf-16-be")
        out += len(utf16).to_bytes(4, "big")
        out += utf16
    out.append(quality & 0xFF)
    out += tail
    return bytes(out)


def _rebuild_body_with_typeid(orig_body: bytes, new_typeid: int,
                              switched_on: int = 0,
                              weapon_spec=None) -> bytes:
    if len(orig_body) < 4:
        return orig_body
    flag = orig_body[0]
    off = 1
    cid = int.from_bytes(orig_body[off:off+2], "big") & 0xFFFF
    off += 2
    byte14 = orig_body[off]
    off += 1
    name = ""
    if flag & 0x08:
        if off + 4 > len(orig_body):
            return orig_body
        nlen = int.from_bytes(orig_body[off:off+4], "big")
        off += 4
        try:
            name = orig_body[off:off+nlen].decode("utf-16-be")
        except Exception:
            name = ""
        off += nlen
    if off >= len(orig_body):
        return orig_body
    quality = orig_body[off]
    if new_typeid in (0x08, 0x09, 0x0C) and byte14 < _WEAPON_MIN_INTEGRITY:
        byte14 = _WEAPON_MIN_INTEGRITY
    if (new_typeid == 0x09 and weapon_spec is not None
            and len(orig_body) >= 4):
        _live_a1q = orig_body[-4]
        _live_a1c = orig_body[-3]
        _live_a2q = orig_body[-2]
        _live_a2c = orig_body[-1]
        weapon_spec = dict(weapon_spec)
        weapon_spec["ammo1_qty"]     = _live_a1q
        weapon_spec["ammo1_quality"] = _live_a1c
        weapon_spec["ammo2_qty"]     = _live_a2q
        weapon_spec["ammo2_quality"] = _live_a2c
    return _pack_auitem_seed_body(typeId=new_typeid, cid=cid,
                                   byte14=byte14, quality=quality,
                                   name=name,
                                   switched_on=switched_on,
                                   weapon_spec=weapon_spec)


def _apply_weapon_typeid_migration(entries, source: str = "?") -> list:
    knife_cids, gun_cids, ammo_cids = _weapon_cid_sets()
    if not (knife_cids or gun_cids or ammo_cids):
        return entries
    promoted = 0
    for entry in entries:
        if len(entry) < 4:
            continue
        slottype, sub, tid, body = entry
        cid = _extract_cid_from_auitem_body(body)
        new_tid = None
        wspec = None
        if cid in knife_cids:
            new_tid = 0x08
            wspec = _WEAPON_DEFAULTS_KNIFE
        elif cid in gun_cids:
            new_tid = 0x09
            wspec = _weapon_spec_for_cid(cid)
        elif cid in ammo_cids:
            new_tid = 0x07
        if new_tid is None:
            continue
        expected_len = None
        if new_tid == 0x08 and wspec is _WEAPON_DEFAULTS_KNIFE:
            expected_len = _EXPECTED_KNIFE_BODYLEN
        elif new_tid == 0x09:
            expected_len = None
        elif new_tid == 0x07:
            expected_len = _EXPECTED_AMMO_BODYLEN
        bb = bytes(body)
        name_overhead = 0
        if len(bb) >= 1 and (bb[0] & 0x08):
            if len(bb) >= 8:
                _nlen = int.from_bytes(bb[4:8], "big")
                name_overhead = 4 + _nlen
        try:
            new_body = _rebuild_body_with_typeid(
                bb, new_tid, weapon_spec=wspec)
        except Exception as e:
            logger.error('Rebuilding cid %d from typeId 0x%02x to 0x%02x failed: %r.',
                         cid, tid, new_tid, e)
            continue
        if tid == new_tid and bb == new_body:
            continue
        entry[2] = new_tid
        entry[3] = new_body
        promoted += 1
        logger.info("%s: promoted cid %d (slot %s/sub %s) from typeId "
                    "0x%02x to 0x%02x, body %db -> %db.",
                    source, cid, slottype, sub, tid, new_tid,
                    len(body), len(new_body))
    if promoted == 0:
        pass
    return entries
