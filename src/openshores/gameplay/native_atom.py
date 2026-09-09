from __future__ import annotations

import struct
from typing import List, Optional, Sequence, Tuple

from openshores.core.logging import get_logger

from openshores.protocol.framing import write_framed
from openshores.protocol.rng import AuDice

logger = get_logger(__name__)


def u8(v: int) -> bytes:    return struct.pack(">B", v & 0xFF)
def i16(v: int) -> bytes:   return struct.pack(">h", v)
def i32(v: int) -> bytes:
    return struct.pack(">i", ((int(v) & 0xFFFFFFFF) ^ 0x80000000) - 0x80000000)
def u32(v: int) -> bytes:   return struct.pack(">I", v & 0xFFFFFFFF)
def i64(v: int) -> bytes:   return struct.pack(">q", v)
def f32(v: float) -> bytes: return struct.pack(">f", v)


def qstring(s: str) -> bytes:
    if s is None:
        return struct.pack(">i", -1)
    b = s.encode("utf-16-be")
    return struct.pack(">I", len(b)) + b


def qbytearray(b: bytes) -> bytes:
    return struct.pack(">I", len(b)) + b


ATOM_TAG_CIT_INDIGENOUS = 0x48
ATOM_TAG_CIT_CHARACTER  = 0x03

ROLE_ADULT, ROLE_CHILD, ROLE_ELDER, ROLE_DOCTOR = 0, 1, 2, 3

DNA_DEFAULT_HUMAN = bytes.fromhex(
    "650D8092" "80107116" "8277586A" "54460582" "A254C272" "56141400"
)

BASEFLAGS_FULL = 0xEF
BASEFLAGS_LEAN = 0x29

UNIT_FLAGS_FIRST     = 0x01
CREATURE_FLAGS_FIRST = 0x2F
SENTIENT_FLAGS_FIRST = 0x00
CITIZEN_FLAG_GEAR    = 0x01
CITIZEN_FLAG_SHIP    = 0x02
CITIZEN_FLAGS_FIRST  = 0x00

POSE_SPAWNED_NATIVE = 0x24


GEAR_SLOT_INVALID = 0
GEAR_SLOT_HAND    = 1
GEAR_SLOT_HEAD    = 2
GEAR_SLOT_FACE    = 3
GEAR_SLOT_NECK    = 4
GEAR_SLOT_BODY    = 5
GEAR_SLOT_WEAR    = 6
GEAR_SLOT_LIMB    = 7
GEAR_SLOT_DIGIT   = 8
GEAR_SLOT_WAIST   = 9

GEAR_SLOT_CAPACITY = {
    GEAR_SLOT_INVALID: 0,
    GEAR_SLOT_HAND:    2,
    GEAR_SLOT_HEAD:    1,
    GEAR_SLOT_FACE:    1,
    GEAR_SLOT_NECK:    1,
    GEAR_SLOT_BODY:    1,
    GEAR_SLOT_WEAR:    2,
    GEAR_SLOT_LIMB:    4,
    GEAR_SLOT_DIGIT:   4,
    GEAR_SLOT_WAIST:   4,
}


AUITEM_TYPE_NONE   = 0x00
AUITEM_TYPE_PLAIN  = 0x01
AUITEM_TYPE_DNA    = 0x04
AUITEM_TYPE_WEAPON = 0x08
AUITEM_TYPE_BOX    = 0x12

AUITEM_FLAG_COUNT = 0x01
AUITEM_FLAG_AUX   = 0x02
AUITEM_FLAG_GRADE = 0x04
AUITEM_FLAG_NAME  = 0x08
AUITEM_FLAG_X24   = 0x10
AUITEM_FLAG_X28   = 0x20

DNA_NULL = bytes(24)


def auitem_body_plain(cid: int, quality: int = 1) -> bytes:
    cid = int(cid) & 0xFFFF
    quality = int(quality) & 0xFF
    if quality == 0:
        quality = 1
    return u8(0x00) + i16(cid) + u8(quality)


def auitem_body_dna(cid: int, quality: int = 1,
                    dna: bytes = DNA_NULL, dna_flags: int = 0x00) -> bytes:
    if len(dna) < 24:
        raise ValueError("DhDNA payload must be >= 24 bytes, got %d" % len(dna))
    return (auitem_body_plain(cid, quality)
            + qbytearray(bytes(dna[:24]))
            + u8(int(dna_flags) & 0x03))


def auitem_body_box(cid: int, quality: int = 1, state: int = 0x00) -> bytes:
    return auitem_body_plain(cid, quality) + u8(int(state) & 0xFF) + u8(0x00)


AUITEM_CREATABLE_TYPES = frozenset(range(0x01, 0x18))


def pack_augear(slots: Sequence[Tuple[int, int, int, bytes]]) -> bytes:
    kept = []
    for slot, which, type_id, body in slots:
        tid = int(type_id) & 0xFF
        if tid not in AUITEM_CREATABLE_TYPES:
            logger.error(
                'DROPPED gear slot=%s which=%s typeId=0x%02X.', slot, which, tid)
            continue
        kept.append((slot, which, tid, body))
    if len(kept) > 0xFF:
        raise ValueError("AuGear slot count overflow (%d)" % len(kept))
    used: dict = {}
    out = u8(len(kept))
    for slot, which, type_id, body in kept:
        slot, which = int(slot), int(which)
        if not 0 <= slot <= 0x0F:
            raise ValueError("Slot %r does not fit the low nibble" % (slot,))
        if not 0 <= which <= 0x0F:
            raise ValueError("Which %r does not fit the high nibble" % (which,))
        if (slot, which) in used:
            raise ValueError(
                "Duplicate AuGearPos (slot=%d, which=%d)" % (slot, which))
        used[(slot, which)] = True
        seen = sum(1 for (s, _w) in used if s == slot)
        cap = GEAR_SLOT_CAPACITY.get(slot, 0)
        if seen > cap:
            raise ValueError(
                "Slot %d holds %d items but DaSentient::AddGearItemAt (AuAtom13 0x1804a36f0) caps it at %d. The engine would have evicted the oldest" % (slot, seen, cap))
        out += u8(((which & 0x0F) << 4) | (slot & 0x0F))
        out += u8(type_id)
        out += bytes(body)
    return out


INDIGENOUS_WEAPON_CIDS = (0, 116, 86, 86, 4, 4, 4)
INDIGENOUS_ARMOR_CIDS = (0, 0, 0, 92, 92, 17, 17)
INDIGENOUS_HELMET_CIDS = (0, 0, 0, 41, 41, 96, 96)
INDIGENOUS_CLOTHING_CIDS = (0, 0, 0, 0, 95, 95)

INDIGENOUS_WEAPON_QUALITY_SRC   = (0, 59, 86, 86, 86, 76, 76)
INDIGENOUS_ARMOR_QUALITY_SRC    = (0, 0, 0, 30, 30, 14, 14)
INDIGENOUS_HELMET_QUALITY_SRC   = (0, 0, 0, 30, 30, 14, 14)
INDIGENOUS_CLOTHING_QUALITY_SRC = (0, 0, 0, 0, 14, 14)

INDIGENOUS_AMMO_CIDS = (0,) * 7

INDIGENOUS_DOCTOR_CIDS = (119, 109, 73)

INDIGENOUS_TRINKET_CIDS = (
    14, 15, 16, 18, 20, 22, 23, 24, 26, 30, 33, 34, 35, 37, 38, 39,
    42, 43, 46, 47, 49, 52, 53, 58, 59, 62, 66, 73, 74, 78, 79, 81,
    83, 85, 99, 100, 109, 110, 119, 126, 131, 233, 282, 326, 327, 333,
)

_AUITEM_TYPE_BY_CID = {
      4: AUITEM_TYPE_WEAPON,
     17: AUITEM_TYPE_DNA,
     41: AUITEM_TYPE_PLAIN,
     73: AUITEM_TYPE_PLAIN,
     86: AUITEM_TYPE_PLAIN,
     92: AUITEM_TYPE_PLAIN,
     95: AUITEM_TYPE_DNA,
     96: AUITEM_TYPE_DNA,
    109: AUITEM_TYPE_BOX,
    116: AUITEM_TYPE_WEAPON,
    119: AUITEM_TYPE_PLAIN,
}

_SERIALISABLE_TYPES = frozenset((AUITEM_TYPE_PLAIN, AUITEM_TYPE_DNA))

INDIGENOUS_GEAR_QUALITY = 1

GEAR_DICE_SALT = 0x6EA71E00


def _indigenous_item(cid: int, quality: int) -> Tuple[int, bytes]:
    try:
        type_id = _AUITEM_TYPE_BY_CID[int(cid)]
    except KeyError:
        raise ValueError(
            "Commodity %d has no verified AuItem type id. Read it out of AuItem::ItemType @ AuData13 0x180179860 (case byte at 0x18017992c + cid - 1) before emitting it" % (cid,)) from None
    if type_id not in _SERIALISABLE_TYPES:
        raise ValueError(
            "Commodity %d is AuItem type 0x%02X, whose body this module does not build; emitting it would desync every byte after the gear block" % (cid, type_id))
    if type_id == AUITEM_TYPE_DNA:
        return type_id, auitem_body_dna(cid, quality)
    return type_id, auitem_body_plain(cid, quality)


def roll_indigenous_gear(dice: AuDice,
                         role: int = ROLE_ADULT,
                         guarantee_clothing: bool = True,
                         include_weapon: bool = False,
                         include_trinket: bool = False,
                         quality: int = INDIGENOUS_GEAR_QUALITY,
                         ) -> List[Tuple[int, int, int, bytes]]:
    quality = max(1, int(quality) & 0xFF)
    slots: List[Tuple[int, int, int, bytes]] = []

    widx = dice.roll(1, 7, -1)
    weapon_cid = INDIGENOUS_WEAPON_CIDS[widx]
    if include_weapon and weapon_cid:
        raise ValueError(
            "include_weapon cannot be honoured for cid %d: type 0x08 bodies "
            "are unread (cids 4, 116) and cid 86 is a plain AuItem whose "
            "vftable+0xB0 returns 0, so it does not take the slot-5 arm and "
            "its real slot lives in the runtime commodity table. Read "
            "??6AuItemWeapon and the DbCommodity flag word before flipping "
            "this on." % (weapon_cid,))

    armor_cid = INDIGENOUS_ARMOR_CIDS[dice.roll(1, 7, -1)]
    wear_which = 0
    if armor_cid:
        type_id, body = _indigenous_item(armor_cid, quality)
        slots.append((GEAR_SLOT_WEAR, wear_which, type_id, body))
        wear_which += 1

    helmet_cid = INDIGENOUS_HELMET_CIDS[dice.roll(1, 7, -1)]
    if helmet_cid:
        type_id, body = _indigenous_item(helmet_cid, quality)
        slots.append((GEAR_SLOT_HEAD, 0, type_id, body))

    cidx = dice.roll(1, 6, -1)
    if guarantee_clothing and INDIGENOUS_CLOTHING_CIDS[cidx] == 0:
        cidx = 4 + (cidx & 1)
    clothing_cid = INDIGENOUS_CLOTHING_CIDS[cidx]
    if clothing_cid:
        type_id, body = _indigenous_item(clothing_cid, quality)
        slots.append((GEAR_SLOT_WEAR, wear_which, type_id, body))
        wear_which += 1

    tidx = dice.roll(1, len(INDIGENOUS_TRINKET_CIDS), -1)
    if include_trinket:
        trinket_cid = INDIGENOUS_TRINKET_CIDS[tidx]
        type_id, body = _indigenous_item(trinket_cid, quality)
        slots.append((GEAR_SLOT_HAND, 0, type_id, body))

    return slots


def default_indigenous_gear(atom_id: int, role: int = ROLE_ADULT, **kw
                            ) -> List[Tuple[int, int, int, bytes]]:
    dice = AuDice((int(atom_id) ^ GEAR_DICE_SALT) & 0xFFFFFFFF)
    return roll_indigenous_gear(dice, role=role, **kw)


def build_cit_indigenous(atom_id: int,
                         parent_id: int,
                         now_ms: int,
                         x: float, y: float, z: float,
                         rx: float = 0.0, ry: float = 0.0, rz: float = 0.0,
                         head_tilt: float = 0.0,
                         name: str = "Native",
                         role: int | None = ROLE_ADULT,
                         dna: bytes = DNA_DEFAULT_HUMAN,
                         pose: int = POSE_SPAWNED_NATIVE,
                         empire_id: int = 0,
                         hunger: int = 1000,
                         gender: int = 0,
                         left_handed: bool = False,
                         scale_byte: int = 0,
                         base_flags: int = BASEFLAGS_FULL,
                         tag: int = ATOM_TAG_CIT_INDIGENOUS,
                         gear: Optional[Sequence[Tuple[int, int, int, bytes]]]
                         = None) -> bytes:
    if len(dna) != 24:
        raise ValueError("DhDNA must be exactly 24 bytes, got %d" % len(dna))

    always_492 = (((dna[0] >> 4) & 0x0F) << 4) | 0x0F

    out = u8(tag)
    out += i32(atom_id) + i64(now_ms)
    out += u8(base_flags)
    if base_flags & 0x01:
        out += i32(parent_id)
    if base_flags & 0x02:
        out += i64(now_ms)
    if base_flags & 0x04:
        out += i64(0)
    if base_flags & 0x08:
        out += f32(x) + f32(y) + f32(z) + f32(rx) + f32(ry) + f32(rz)
    out += u8(UNIT_FLAGS_FIRST)
    out += qstring(name)
    out += i32(empire_id)
    out += u8(0)
    out += u8(CREATURE_FLAGS_FIRST)
    out += u8((gender & 0x03) | (0x04 if left_handed else 0x00))
    out += qbytearray(dna)
    out += f32(head_tilt)
    out += i16(hunger)
    out += bytes([pose & 0xFF]) * 10
    out += i32(0)
    out += u8(always_492)
    out += u8(scale_byte)
    out += u8(SENTIENT_FLAGS_FIRST)
    if gear is None:
        gear = default_indigenous_gear(atom_id, ROLE_ADULT if role is None
                                       else role)
    if gear is False:
        out += u8(CITIZEN_FLAGS_FIRST)
    else:
        out += u8(CITIZEN_FLAGS_FIRST | CITIZEN_FLAG_GEAR)
        out += pack_augear(gear)
    if role is not None:
        out += u8(role & 0xFF)
    return out


SPIKE_ATOM_ID_BASE = 0x7A000000


async def spawn(writer, parent_auid, xyz, atom_id: int | None = None,
                name: str = "Native", role: int = ROLE_ADULT,
                base_flags: int | None = None, tag: int | None = None,
                *, _DYNAMIC_SCENE_AUIDS: set):
    import time

    if isinstance(parent_auid, (bytes, bytearray)):
        parent_auid = int.from_bytes(bytes(parent_auid), "big")
    parent_auid = int(parent_auid)

    if atom_id is None:
        atom_id = SPIKE_ATOM_ID_BASE
    if base_flags is None:
        base_flags = 0xEF
    if tag is None:
        tag = 0x48

    _DYNAMIC_SCENE_AUIDS.add(atom_id & 0xFFFFFFFF)

    pkt = build_cit_indigenous(
        atom_id=atom_id,
        parent_id=parent_auid,
        now_ms=int(time.time() * 1000),
        x=float(xyz[0]), y=float(xyz[1]), z=float(xyz[2]),
        name=name,
        role=(role if tag == ATOM_TAG_CIT_INDIGENOUS else None),
        base_flags=base_flags,
        tag=tag,
    )
    logger.debug("tag=0x%02X baseFlags=0x%02X atom=0x%08X "
                 "parent=0x%08X xyz=%s len=%d", tag, base_flags, atom_id,
                 parent_auid, tuple(xyz), len(pkt))
    logger.debug("%s", pkt.hex())
    await write_framed(writer, pkt)
    logger.debug("Sent. Now check soh.txt for "
                 "'AuModel::SyncData Cloning new atom'.")
    return pkt


if __name__ == "__main__":

    assert auitem_body_plain(92, 1) == bytes.fromhex("00005c01")
    assert len(auitem_body_plain(92, 1)) == 4
    assert auitem_body_plain(92, 0)[3] == 1, "Quality 0 must be floored to 1"

    dna_body = auitem_body_dna(95, 1)
    assert dna_body[:4] == bytes.fromhex("00005f01")
    assert dna_body[4:8] == bytes.fromhex("00000018")
    assert dna_body[8:32] == bytes(24)
    assert dna_body[32:] == b"\x00"
    assert len(dna_body) == 33, "AuItemDNA body is 4+4+24+1"

    box_body = auitem_body_box(109, 1)
    assert box_body == bytes.fromhex("00006d01" "00" "00"), box_body.hex()
    assert len(box_body) == 6, "Empty AuItemBox body is 4+1+1"
    assert AUITEM_TYPE_BOX not in _SERIALISABLE_TYPES, \
        "The box body is encodable but its SLOT is not known."

    one = pack_augear([(GEAR_SLOT_WEAR, 1, AUITEM_TYPE_DNA, dna_body)])
    assert one[0] == 1
    assert one[1] == 0x16
    assert one[2] == AUITEM_TYPE_DNA
    assert one[3:] == dna_body
    assert len(one) == 1 + 2 + 33 == 36
    assert pack_augear([]) == b"\x00", "Empty AuGear is a single zero byte"
    assert pack_augear([(GEAR_SLOT_HAND, 0, AUITEM_TYPE_NONE, b"")]) \
        == b"\x00", "A null-item slot must not reach the wire"
    assert pack_augear([(GEAR_SLOT_HAND, 0, 0x7F, b"body")]) \
        == b"\x00", "An unknown typeId must not reach the wire either"
    _dropmix = pack_augear([(GEAR_SLOT_WEAR, 0, AUITEM_TYPE_DNA, dna_body),
                            (GEAR_SLOT_HAND, 0, AUITEM_TYPE_NONE, b"")])
    assert _dropmix[0] == 1 and len(_dropmix) == 36, _dropmix.hex()

    for bad_cid in (4, 116, 109):
        try:
            _indigenous_item(bad_cid, 1)
        except ValueError:
            continue
        else:
            raise AssertionError("Cid %d should not be serialisable" % bad_cid)
    _unknown_refused = 0
    try:
        _indigenous_item(999, 1)
    except ValueError:
        _unknown_refused += 1
    assert _unknown_refused, "Unknown cid must raise"


    def _rd_auitem(buf, off):
        flags = buf[off]; off += 1
        cid = struct.unpack_from(">h", buf, off)[0]; off += 2
        f = {"flags": flags, "cid": cid}
        if flags & 0x01:
            f["count"] = struct.unpack_from(">i", buf, off)[0]; off += 4
        if flags & 0x02:
            f["aux"] = struct.unpack_from(">i", buf, off)[0]; off += 4
        if flags & 0x04:
            f["grade"] = buf[off]; off += 1
        if flags & 0x08:
            n = struct.unpack_from(">i", buf, off)[0]; off += 4
            if n > 0:
                off += n
        f["quality"] = buf[off]; off += 1
        if flags & 0x10:
            f["serial"] = struct.unpack_from(">i", buf, off)[0]; off += 4
        if flags & 0x20:
            f["state"] = buf[off] & 0xE0; off += 1
        return f, off

    def _rd_item_body(type_id, buf, off):
        f, off = _rd_auitem(buf, off)
        if type_id == AUITEM_TYPE_DNA:
            n = struct.unpack_from(">i", buf, off)[0]; off += 4
            assert n >= 24, "DhDNA QByteArray shorter than 24 bytes (%d)" % n
            f["dna"] = bytes(buf[off:off + 24]); off += n
            bits = buf[off]; off += 1
            f["dna_flags"] = bits & 0x03
        elif type_id != AUITEM_TYPE_PLAIN:
            raise AssertionError("Reference reader has no body for type 0x%02X"
                                 % type_id)
        return f, off

    def _rd_augear(buf, off):
        n = buf[off]; off += 1
        recs = []
        for _ in range(n):
            packed = buf[off]; off += 1
            slot, which = packed & 0x0F, packed >> 4
            type_id = buf[off]; off += 1
            item = None
            if type_id != 0:
                assert type_id in _SERIALISABLE_TYPES, (
                    "Type 0x%02X would desync the reference reader" % type_id)
                item, off = _rd_item_body(type_id, buf, off)
            recs.append((slot, which, type_id, item))
        return recs, off

    for seed in range(500):
        g = roll_indigenous_gear(AuDice(seed))
        blob = pack_augear(g)
        recs, end = _rd_augear(blob, 0)
        assert end == len(blob), (
            "seed %d: reader consumed %d of %d bytes, so the role byte is lost" % (seed, end, len(blob)))
        assert len(recs) == len(g)
        for (eslot, ewhich, etype, ebody), (slot, which, type_id, item) in \
                zip(g, recs):
            assert (slot, which, type_id) == (eslot, ewhich, etype)
            if type_id:
                assert item["flags"] == 0x00
                assert item["quality"] >= 1, "Reader forces quality 0 -> 1"
                if type_id == AUITEM_TYPE_DNA:
                    assert item["dna"] == DNA_NULL, \
                        "Engine-made garments carry a null DhDNA"

    _seen_slots = set()
    for seed in range(500):
        for slot, which, type_id, body in roll_indigenous_gear(AuDice(seed)):
            _seen_slots.add(slot)
    assert _seen_slots <= {GEAR_SLOT_HEAD, GEAR_SLOT_WEAR}, \
        "Default outfit reached an unpinned slot: %s" % (_seen_slots,)

    _trinket_checked = 0
    for seed in range(3000):
        base = roll_indigenous_gear(AuDice(seed))
        try:
            withal = roll_indigenous_gear(AuDice(seed), include_trinket=True)
        except ValueError:
            continue
        extra = [s for s in withal if s not in base]
        assert len(extra) == 1, "Seed %d: trinket added %d slots" % (seed,
                                                                    len(extra))
        assert extra[0][0] == GEAR_SLOT_HAND, (
            "Seed %d: carried trinket went to slot %d, but AuItem+0x120 / AuItemDNA+0x120 are both the folded `xor al,al; ret` at 0x180023a30, so AddGearItemAt sends it to Hand (1)"
            % (seed, extra[0][0]))
        _trinket_checked += 1
        if _trinket_checked >= 5:
            break
    assert _trinket_checked >= 5, \
        "never found 5 buildable trinkets"

    _weapon_refusals = 0
    for seed in range(200):
        try:
            roll_indigenous_gear(AuDice(seed), include_weapon=True)
        except ValueError:
            _weapon_refusals += 1
    assert _weapon_refusals > 0, \
        "include_weapon emitted a weapon."
    assert _weapon_refusals < 200, "Every seed rolled a weapon; table face 0 lost"

    _exact_cids = {GEAR_SLOT_HEAD: set(), GEAR_SLOT_WEAR: set()}
    _clothed = 0
    _N = 6000
    for seed in range(_N):
        g = roll_indigenous_gear(AuDice(seed), guarantee_clothing=False)
        for slot, _w, _t, body in g:
            _exact_cids[slot].add(struct.unpack_from(">h", body, 1)[0])
        if any(struct.unpack_from(">h", b, 1)[0] == 95 for _s, _w, _t, b in g):
            _clothed += 1
    assert _exact_cids[GEAR_SLOT_HEAD] == {41, 96}, _exact_cids[GEAR_SLOT_HEAD]
    assert _exact_cids[GEAR_SLOT_WEAR] == {17, 92, 95}, _exact_cids[GEAR_SLOT_WEAR]
    assert 0.28 < _clothed / _N < 0.39, \
        "Engine-exact clothing rate %.3f is not the table's 2/6" % (_clothed / _N)

    _cap_refused = 0
    try:
        pack_augear([(GEAR_SLOT_WEAR, 0, AUITEM_TYPE_PLAIN,
                      auitem_body_plain(92)),
                     (GEAR_SLOT_WEAR, 1, AUITEM_TYPE_DNA, dna_body),
                     (GEAR_SLOT_WEAR, 2, AUITEM_TYPE_PLAIN,
                      auitem_body_plain(92))])
    except ValueError:
        _cap_refused += 1
    assert _cap_refused, "Wear slot cap of 2 was not enforced"
    _dup_refused = 0
    try:
        pack_augear([(GEAR_SLOT_HEAD, 0, AUITEM_TYPE_PLAIN,
                      auitem_body_plain(41)),
                     (GEAR_SLOT_HEAD, 0, AUITEM_TYPE_PLAIN,
                      auitem_body_plain(41))])
    except ValueError:
        _dup_refused += 1
    assert _dup_refused, "Duplicate AuGearPos was not rejected"

    for seed in range(200):
        d_on = AuDice(seed)
        worn = roll_indigenous_gear(d_on, guarantee_clothing=True)
        d_off = AuDice(seed)
        roll_indigenous_gear(d_off, guarantee_clothing=False)
        assert d_on.state == d_off.state, \
            "guarantee_clothing changed the dice stream at seed %d" % seed
        wear = [s for s in worn if s[0] == GEAR_SLOT_WEAR]
        assert wear, "Seed %d produced no Wear-slot item" % seed
        assert sorted(w[1] for w in wear) == list(range(len(wear))), \
            "Wear `which` values are not 0..n-1 at seed %d" % seed
        assert len(wear) <= 2, "Wear holds at most one armor + one clothing"
        clothing = [w for w in wear if w[2] == AUITEM_TYPE_DNA
                    and struct.unpack_from(">h", w[3], 1)[0] == 95]
        assert len(clothing) == 1, \
            "Seed %d: expected exactly one cid-95 garment, got %d" % (
                seed, len(clothing))
        assert len(clothing[0][3]) == 33

    pkt = build_cit_indigenous(atom_id=0x1001, parent_id=0x0007,
                               now_ms=0x0000018AB0C00000,
                               x=1.0, y=2.0, z=3.0)

    naked = build_cit_indigenous(atom_id=0x1001, parent_id=0x0007,
                                 now_ms=0x0000018AB0C00000,
                                 x=1.0, y=2.0, z=3.0, gear=False)
    assert len(naked) == 135, "No-gear variant must still be 135 bytes, got %d" \
        % len(naked)
    assert naked[0x85] == 0x00, "Citizen flag byte should be 0x00 with no gear"
    assert naked[0x86] == ROLE_ADULT

    gear = default_indigenous_gear(0x1001)

    assert pack_augear(gear) == bytes.fromhex(
        "02"
        "0204" "00006001" "00000018" + "00" * 24 + "00"
        "0604" "00005f01" "00000018" + "00" * 24 + "00"), \
        "Gear block for atom 0x1001 changed: %s" % pack_augear(gear).hex()
    assert len(pack_augear(gear)) == 71

    _recs, _end = _rd_augear(pack_augear(gear), 0)
    assert _end == 71, "Reader consumed %d of 71 bytes" % _end
    assert len(_recs) == 2
    _helm, _garment = _recs
    assert _helm[0] == GEAR_SLOT_HEAD
    assert _helm[1] == 0
    assert _helm[2] == AUITEM_TYPE_DNA
    assert _helm[3]["flags"] == 0x00
    assert _helm[3]["cid"] == 96
    assert _helm[3]["quality"] == INDIGENOUS_GEAR_QUALITY
    assert _helm[3]["dna"] == DNA_NULL
    assert _helm[3]["dna_flags"] == 0
    assert "grade" not in _helm[3], \
        "Flag 0x04 must stay clear so the client fills +0x14 from its own DbCommodity table, which is what AuItem::AuItem does by construction"
    assert "count" not in _helm[3] and "aux" not in _helm[3]
    assert "serial" not in _helm[3] and "state" not in _helm[3]
    assert _garment[0] == GEAR_SLOT_WEAR
    assert _garment[1] == 0
    assert _garment[2] == AUITEM_TYPE_DNA
    assert _garment[3]["flags"] == 0x00
    assert _garment[3]["cid"] == 95
    assert _garment[3]["quality"] == INDIGENOUS_GEAR_QUALITY
    assert _garment[3]["dna"] == DNA_NULL

    expect = 135 + len(pack_augear(gear))
    assert expect == 206, "Full default packet should be 206 bytes, got %d" \
        % expect
    assert len(pkt) == expect, "Expected %d bytes, got %d" % (expect, len(pkt))
    assert pkt[0] == 0x48
    assert pkt[-1] == ROLE_ADULT
    assert pkt[0x82] == 0x6F, "The +0x492 byte should be 0x6F for default human"
    assert pkt[0x84] == SENTIENT_FLAGS_FIRST
    assert pkt[0x85] == CITIZEN_FLAG_GEAR, "Citizen flag bit 0 must be set"
    assert pkt[0x86] == len(gear), "The byte after the flags is the slot count"
    assert pkt[0x86:-1] == pack_augear(gear)

    lean = build_cit_indigenous(atom_id=0x1001, parent_id=0x0007, now_ms=0,
                                x=1.0, y=2.0, z=3.0,
                                base_flags=BASEFLAGS_LEAN)
    assert len(lean) == expect - 16, "Lean variant should be 16 bytes shorter"

    char = build_cit_indigenous(atom_id=0x1001, parent_id=0x0007, now_ms=0,
                                x=1.0, y=2.0, z=3.0,
                                role=None, tag=ATOM_TAG_CIT_CHARACTER)
    assert len(char) == expect - 1 and char[0] == 0x03

    again = build_cit_indigenous(atom_id=0x1001, parent_id=0x0007, now_ms=0,
                                 x=9.0, y=9.0, z=9.0)
    assert again[0x86:] == pkt[0x86:], "Outfit must be stable per atom id"

    logger.info("Full (0x48, baseFlags 0xEF) %3d bytes %s", len(pkt),
                pkt.hex())
    logger.info("Naked (0x48, gear=False) %3d bytes %s", len(naked),
                naked.hex())
    logger.info("Lean (0x48, baseFlags 0x29) %3d bytes %s", len(lean),
                lean.hex())
    logger.info("Char (0x03, no ROLE byte) %3d bytes %s", len(char),
                char.hex())
    logger.info("Outfit for atom 0x1001: %s",
                [(s, w, "0x%02X" % t, len(b)) for s, w, t, b in gear])
    logger.info("AuGear block            %s", pack_augear(gear).hex())
    logger.info("Self-test OK")
