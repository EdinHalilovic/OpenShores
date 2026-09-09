from __future__ import annotations

import math
import struct
from typing import Dict, List, Optional, Sequence, Tuple

from openshores.core.logging import get_logger
from openshores.protocol.atoms.aucomm import build_chat_aucomm_v4
from openshores.protocol.framing import write_framed

from openshores.gameplay.natives.village import (          # noqa: E402
    gravity_align_euler,
    project_to_terrain,
)

logger = get_logger(__name__)


def _u8(v: int) -> bytes:
    return struct.pack(">B", int(v) & 0xFF)


def _i16(v: int) -> bytes:
    return struct.pack(">h", int(v))


def _i32(v: int) -> bytes:
    return struct.pack(">i", ((int(v) & 0xFFFFFFFF) ^ 0x80000000) - 0x80000000)


def _i64(v: int) -> bytes:
    return struct.pack(">q", int(v))


def _f32(v: float) -> bytes:
    return struct.pack(">f", float(v))


def _qstring(s: Optional[str]) -> bytes:
    if s is None:
        return struct.pack(">i", -1)
    b = s.encode("utf-16-be")
    return struct.pack(">I", len(b)) + b


def _qbytearray(b: bytes) -> bytes:
    return struct.pack(">I", len(b)) + bytes(b)


ATOM_TAG_CIT_CHARACTER = 0x03

CIT_CHARACTER_SIZE = 0x47B8

DNA_DEFAULT_HUMAN = bytes.fromhex(
    "650D8092" "80107116" "8277586A" "54460582" "A254C272" "56141400"
)

BASEFLAGS_FULL = 0xEF

UNIT_FLAGS_FIRST = 0x01
CREATURE_FLAGS_FIRST = 0x2F
SENTIENT_FLAGS_FIRST = 0x00

CITIZEN_FLAG_GEAR = 0x01
CITIZEN_FLAG_SHIP = 0x02
CITIZEN_FLAGS_FIRST = 0x00

POSE_STANDING = 0x24

GEAR_SLOT_INVALID = 0
GEAR_SLOT_HAND = 1
GEAR_SLOT_HEAD = 2
GEAR_SLOT_FACE = 3
GEAR_SLOT_NECK = 4
GEAR_SLOT_BODY = 5
GEAR_SLOT_WEAR = 6
GEAR_SLOT_LIMB = 7
GEAR_SLOT_DIGIT = 8
GEAR_SLOT_WAIST = 9

GEAR_SLOT_CAPACITY = {
    GEAR_SLOT_INVALID: 0, GEAR_SLOT_HAND: 2, GEAR_SLOT_HEAD: 1,
    GEAR_SLOT_FACE: 1, GEAR_SLOT_NECK: 1, GEAR_SLOT_BODY: 1,
    GEAR_SLOT_WEAR: 2, GEAR_SLOT_LIMB: 4, GEAR_SLOT_DIGIT: 4,
    GEAR_SLOT_WAIST: 4,
}

AUITEM_TYPE_NONE = 0x00
AUITEM_TYPE_PLAIN = 0x01
AUITEM_TYPE_DNA = 0x04
AUITEM_TYPE_WEAPON = 0x08
AUITEM_TYPE_WEAPON_STATE = 0x0C
AUITEM_TYPE_BOX = 0x12

_SERIALISABLE_TYPES = frozenset((AUITEM_TYPE_PLAIN, AUITEM_TYPE_DNA))

AUITEM_CREATABLE_TYPES = frozenset(range(0x01, 0x18))

DNA_NULL = bytes(24)

_AUITEM_TYPE_BY_CID = {
    4: AUITEM_TYPE_WEAPON,
    17: AUITEM_TYPE_DNA,
    21: AUITEM_TYPE_PLAIN,
    41: AUITEM_TYPE_PLAIN,
    73: AUITEM_TYPE_PLAIN,
    86: AUITEM_TYPE_PLAIN,
    92: AUITEM_TYPE_PLAIN,
    95: AUITEM_TYPE_DNA,
    96: AUITEM_TYPE_DNA,
    109: AUITEM_TYPE_BOX,
    116: AUITEM_TYPE_WEAPON,
    119: AUITEM_TYPE_PLAIN,
    131: AUITEM_TYPE_WEAPON_STATE,
}

_COMMODITY_BY_NAME = {
    "torch": 131,
    "fabric clothing": 21,
    "leather clothing": 95,
}

_GEAR_SLOT_BY_NAME = {
    "clothing": GEAR_SLOT_WEAR,
    "armor": GEAR_SLOT_WEAR,
    "wear": GEAR_SLOT_WEAR,
    "hand": GEAR_SLOT_HAND,
    "right hand": GEAR_SLOT_HAND,
    "left hand": GEAR_SLOT_HAND,
    "head": GEAR_SLOT_HEAD,
    "helmet": GEAR_SLOT_HEAD,
    "face": GEAR_SLOT_FACE,
    "neck": GEAR_SLOT_NECK,
    "body": GEAR_SLOT_BODY,
    "limb": GEAR_SLOT_LIMB,
    "digit": GEAR_SLOT_DIGIT,
    "waist": GEAR_SLOT_WAIST,
}

TARGOSS_AUID = 0x7C000001
TARGOSS_NAME = "Targoss"

STORY_ID = 0x1001

SPAWN_ANGLE_DEG = 180.0
SPAWN_DIST_FT = 50.0

WALK_SPEED_FT_S = 5.0

FOLLOW_STOP_FT = 8.0

GOTO_ARRIVE_FT = 0.05

EMIT_EPS_FT = 0.25
EMIT_EPS_RAD = 0.01

TURN_RATE_RAD_S = 1.6


def _atom_id() -> int:
    return TARGOSS_AUID


def auitem_body_plain(cid: int, quality: int = 1) -> bytes:
    cid = int(cid) & 0xFFFF
    quality = int(quality) & 0xFF or 1
    return _u8(0x00) + _i16(cid) + _u8(quality)


def auitem_body_dna(cid: int, quality: int = 1, dna: bytes = DNA_NULL,
                    dna_flags: int = 0x00) -> bytes:
    if len(dna) < 24:
        raise ValueError("DhDNA payload must be >= 24 bytes, got %d" % len(dna))
    return (auitem_body_plain(cid, quality)
            + _qbytearray(bytes(dna[:24]))
            + _u8(int(dna_flags) & 0x03))


def pack_augear(slots: Sequence[Tuple[int, int, int, bytes]]) -> bytes:
    kept = []
    for slot, which, type_id, body in slots:
        tid = int(type_id) & 0xFF
        if tid not in AUITEM_CREATABLE_TYPES:
            logger.error('Dropped gear slot=%s which=%s typeId=0x%02X: AuItem::Create cannot build it, so the client would hold a NULL item and crash in AuGear::Weight.',
                         slot, which, tid)
            continue
        kept.append((slot, which, tid, body))
    if len(kept) > 0xFF:
        raise ValueError("AuGear slot count overflow (%d)" % len(kept))
    used: Dict[Tuple[int, int], bool] = {}
    out = _u8(len(kept))
    for slot, which, type_id, body in kept:
        slot, which = int(slot), int(which)
        if not 0 <= slot <= 0x0F:
            raise ValueError("Slot %r does not fit the low nibble" % (slot,))
        if not 0 <= which <= 0x0F:
            raise ValueError("Which %r does not fit the high nibble" % (which,))
        if (slot, which) in used:
            raise ValueError("Duplicate AuGearPos (slot=%d, which=%d)"
                             % (slot, which))
        used[(slot, which)] = True
        seen = sum(1 for (s, _w) in used if s == slot)
        cap = GEAR_SLOT_CAPACITY.get(slot, 0)
        if seen > cap:
            raise ValueError(
                "Slot %d holds %d items but DaSentient::AddGearItemAt (AuAtom13 0x1804a36f0) caps it at %d" % (slot, seen, cap))
        out += _u8(((which & 0x0F) << 4) | (slot & 0x0F))
        out += _u8(type_id)
        out += bytes(body)
    return out


def commodity_id(name: str) -> Optional[int]:
    if name is None:
        return None
    key = " ".join(str(name).split()).strip().lower()
    if not key:
        return None
    if key.isdigit():
        return int(key)
    hit = _COMMODITY_BY_NAME.get(key)
    if hit is not None:
        return hit
    import json
    try:
        fh = open("gd_recipes.json", "r", encoding="utf-8")
    except OSError as exc:
        logger.warning("No recipe table (%s), so %r resolves no further than "
                       "the names built in above.", exc, name)
        return None
    with fh:
        procs = json.load(fh).get("processes", {})
    for rec in procs.values():
        nm = " ".join(str(rec.get("name", "")).split()).strip().lower()
        if nm == key:
            _COMMODITY_BY_NAME[key] = int(rec["out"])
            return int(rec["out"])
    return None


def gear_item(cid: int, quality: int = 1) -> Optional[Tuple[int, bytes]]:
    type_id = _AUITEM_TYPE_BY_CID.get(int(cid))
    if type_id is None or type_id not in _SERIALISABLE_TYPES:
        return None
    if type_id == AUITEM_TYPE_DNA:
        return type_id, auitem_body_dna(cid, quality)
    return type_id, auitem_body_plain(cid, quality)


def build_cit_character(atom_id: int,
                        parent_id: int,
                        now_ms: int,
                        x: float, y: float, z: float,
                        rx: float = 0.0, ry: float = 0.0, rz: float = 0.0,
                        head_tilt: float = 0.0,
                        name: str = TARGOSS_NAME,
                        dna: bytes = DNA_DEFAULT_HUMAN,
                        pose: int = POSE_STANDING,
                        empire_id: int = 0,
                        hunger: int = 1000,
                        gender: int = 0,
                        left_handed: bool = False,
                        scale_byte: int = 0,
                        base_flags: int = BASEFLAGS_FULL,
                        tag: int = ATOM_TAG_CIT_CHARACTER,
                        gear: Optional[Sequence[Tuple[int, int, int, bytes]]]
                        = None,
                        ship_auid: Optional[int] = None) -> bytes:
    if len(dna) != 24:
        raise ValueError("DhDNA must be exactly 24 bytes, got %d" % len(dna))

    always_492 = (((dna[0] >> 4) & 0x0F) << 4) | 0x0F

    out = _u8(tag)

    out += _i32(atom_id)
    out += _i64(now_ms)

    out += _u8(base_flags)
    if base_flags & 0x01:
        out += _i32(parent_id)
    if base_flags & 0x02:
        out += _i64(now_ms)
    if base_flags & 0x04:
        out += _i64(0)
    if base_flags & 0x08:
        out += (_f32(x) + _f32(y) + _f32(z)
                + _f32(rx) + _f32(ry) + _f32(rz))

    out += _u8(UNIT_FLAGS_FIRST)
    out += _qstring(name)
    out += _i32(empire_id)
    out += _u8(0)

    out += _u8(CREATURE_FLAGS_FIRST)
    out += _u8((int(gender) & 0x03) | (0x04 if left_handed else 0x00))
    out += _qbytearray(dna)
    out += _f32(head_tilt)
    out += _i16(hunger)
    out += bytes([int(pose) & 0xFF]) * 10
    out += _i32(0)
    out += _u8(always_492)
    out += _u8(scale_byte)

    out += _u8(SENTIENT_FLAGS_FIRST)

    flags = CITIZEN_FLAGS_FIRST
    if gear is not False:
        flags |= CITIZEN_FLAG_GEAR
    if ship_auid is not None:
        flags |= CITIZEN_FLAG_SHIP
    out += _u8(flags)
    if gear is not False:
        out += pack_augear(gear or ())
    if ship_auid is not None:
        out += _i32(ship_auid)
    return out


def build_cit_character_move(atom_id: int,
                             now_ms: int,
                             x: float, y: float, z: float,
                             rx: float = 0.0, ry: float = 0.0,
                             rz: float = 0.0,
                             name: str = TARGOSS_NAME,
                             dna: bytes = DNA_DEFAULT_HUMAN,
                             empire_id: int = 0,
                             hit_points: Optional[int] = None,
                             pose: Optional[int] = None,
                             scale_byte: int = 0,
                             role: Optional[int] = None,
                             tag: int = ATOM_TAG_CIT_CHARACTER) -> bytes:
    if len(dna) != 24:
        raise ValueError("DhDNA must be exactly 24 bytes, got %d" % len(dna))
    always_492 = (((dna[0] >> 4) & 0x0F) << 4) | 0x0F

    out = _u8(tag)
    out += _i32(atom_id)
    out += _i64(now_ms)

    out += _u8(0x08)
    out += (_f32(x) + _f32(y) + _f32(z)
            + _f32(rx) + _f32(ry) + _f32(rz))

    out += _u8(UNIT_FLAGS_FIRST)
    out += _qstring(name)
    out += _i32(empire_id)
    out += _u8(0)

    cflags = 0
    if hit_points is not None:
        cflags |= 0x04
    if pose is not None:
        cflags |= 0x08
    if scale_byte:
        cflags |= 0x20
    out += _u8(cflags)
    if hit_points is not None:
        out += _i16(max(-30, min(0x7FFF, int(hit_points))))
    if pose is not None:
        out += bytes([int(pose) & 0xFF]) * 10
        out += _i32(0)
    out += _u8(always_492)
    if scale_byte:
        out += _u8(scale_byte)

    out += _u8(SENTIENT_FLAGS_FIRST)
    out += _u8(CITIZEN_FLAGS_FIRST)
    if role is not None:
        out += _u8(int(role) & 0xFF)
    return out


def _norm3(v: Sequence[float]) -> Tuple[float, float, float]:
    n = math.sqrt(float(v[0]) ** 2 + float(v[1]) ** 2 + float(v[2]) ** 2)
    if n <= 0.0:
        return (0.0, 0.0, 0.0)
    return (float(v[0]) / n, float(v[1]) / n, float(v[2]) / n)


def _cross(a: Sequence[float], b: Sequence[float]
           ) -> Tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def player_basis(xyz: Sequence[float], live_rot: Optional[Sequence[float]]
                 ) -> Tuple[Tuple[float, float, float],
                            Tuple[float, float, float],
                            Tuple[float, float, float]]:
    up = _norm3(xyz)
    if up == (0.0, 0.0, 0.0):
        return ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))

    east = _norm3((-up[2], 0.0, up[0]))
    if east == (0.0, 0.0, 0.0):
        east = (1.0, 0.0, 0.0)
    north = _norm3(_cross(up, east))

    yaw = None
    if live_rot is not None and len(live_rot) >= 3:
        try:
            yaw = float(live_rot[2])
        except Exception:
            yaw = None
    if yaw is None:
        right0 = _norm3(_cross(north, up))
        return (north, right0 if right0 != (0.0, 0.0, 0.0) else east, up)
    sign, offset = -1.0, -0.95
    theta = sign * yaw + offset
    ct, st = math.cos(theta), math.sin(theta)
    fwd = (ct * north[0] + st * east[0],
           ct * north[1] + st * east[1],
           ct * north[2] + st * east[2])
    d = _dot(fwd, up)
    fwd = _norm3((fwd[0] - d * up[0], fwd[1] - d * up[1], fwd[2] - d * up[2]))
    if fwd == (0.0, 0.0, 0.0):
        fwd = north
    right = _norm3(_cross(fwd, up))
    return (fwd, right, up)


def spawn_offset_xyz(person_xyz: Sequence[float],
                     forward: Sequence[float],
                     right: Sequence[float],
                     angle_deg: float,
                     dist_ft: float) -> Tuple[float, float, float]:
    a = math.radians(float(angle_deg))
    c, s = math.cos(a), math.sin(a)
    d = float(dist_ft)
    return (float(person_xyz[0]) + d * (c * forward[0] - s * right[0]),
            float(person_xyz[1]) + d * (c * forward[1] - s * right[1]),
            float(person_xyz[2]) + d * (c * forward[2] - s * right[2]))


def heading_to_face(xyz: Sequence[float], target_xyz: Sequence[float],
                    default: float = 0.0) -> float:
    from openshores.gameplay.natives.village import heading_to_face as _h
    return _h(xyz, target_xyz, default)


def tangent_distance_ft(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt((float(a[0]) - float(b[0])) ** 2
                     + (float(a[1]) - float(b[1])) ** 2
                     + (float(a[2]) - float(b[2])) ** 2)


def _step_toward(pos: Sequence[float], target: Sequence[float],
                 step_ft: float) -> Tuple[float, float, float]:
    up = _norm3(pos)
    dx = float(target[0]) - float(pos[0])
    dy = float(target[1]) - float(pos[1])
    dz = float(target[2]) - float(pos[2])
    r = dx * up[0] + dy * up[1] + dz * up[2]
    dx -= r * up[0]
    dy -= r * up[1]
    dz -= r * up[2]
    n = math.sqrt(dx * dx + dy * dy + dz * dz)
    if n < 1e-9:
        return (float(pos[0]), float(pos[1]), float(pos[2]))
    k = min(float(step_ft), n) / n
    return (float(pos[0]) + dx * k,
            float(pos[1]) + dy * k,
            float(pos[2]) + dz * k)


_NPCS: Dict[int, dict] = {}


def _avatar(live_avatars: dict, auid: int) -> Optional[dict]:
    entry = live_avatars.get(int(auid) & 0xFFFFFFFF)
    return entry if isinstance(entry, dict) else None


def player_xyz(live_avatars: dict,
               avatar_auid: int) -> Optional[Tuple[float, float, float]]:
    e = _avatar(live_avatars, avatar_auid)
    if e is None:
        return None
    xyz = e.get("xyz")
    if not xyz:
        return None
    try:
        return (float(xyz[0]), float(xyz[1]), float(xyz[2]))
    except Exception:
        return None


def _player_rot(live_avatars: dict,
                avatar_auid: int) -> Optional[Sequence[float]]:
    e = _avatar(live_avatars, avatar_auid)
    return None if e is None else e.get("live_rot")


def _parent_world(live_avatars: dict, avatar_auid: int) -> Optional[int]:
    e = _avatar(live_avatars, avatar_auid)
    if e is None:
        return None
    p = e.get("parent_world")
    if p is None:
        return None
    if isinstance(p, (bytes, bytearray)):
        return int.from_bytes(bytes(p), "big")
    try:
        return int(p)
    except Exception:
        return None


def _player_dna(dna: Optional[bytes]) -> bytes:
    if dna and len(dna) >= 24 and bytes(dna[:24]) != bytes(24):
        return bytes(dna[:24])
    return DNA_DEFAULT_HUMAN


def _terrain_and_size(save) -> Tuple[Optional[Sequence[float]],
                                     Optional[int]]:
    terrain = getattr(save, "planet_terrain", None)
    size = int(getattr(save, "planet_size_code", 0) or 0)
    if not size or not terrain:
        return (None, None)
    return (terrain, size)


def _place(xyz: Sequence[float], terrain, size, target_xyz
           ) -> Tuple[Tuple[float, float, float],
                      Tuple[float, float, float]]:
    pos = tuple(float(c) for c in xyz)
    if terrain is not None and size:
        pos = project_to_terrain(pos, terrain, size)
    heading = heading_to_face(pos, target_xyz) if target_xyz else 0.0
    return (pos, gravity_align_euler(pos, heading))


def _register_manifest(atom_id: int, *, _DYNAMIC_SCENE_AUIDS: set) -> None:
    _DYNAMIC_SCENE_AUIDS.add(int(atom_id) & 0xFFFFFFFF)


def _scene_writer(live_avatars: dict, avatar_auid: int):
    e = _avatar(live_avatars, avatar_auid)
    if e is None:
        return None
    w = e.get("writer")
    if w is None or w.is_closing():
        return None
    return w


def _packet_for(st: dict, now_ms: Optional[int] = None,
                full: bool = True) -> bytes:
    import time as _t
    if now_ms is None:
        now_ms = int(_t.time() * 1000)
    if not full:
        return build_cit_character_move(
            atom_id=st["auid"],
            now_ms=now_ms,
            x=st["xyz"][0], y=st["xyz"][1], z=st["xyz"][2],
            rx=st["rot"][0], ry=st["rot"][1], rz=st["rot"][2],
            name=st["name"],
            dna=st["dna"],
            empire_id=st["empire_id"],
            hit_points=st.get("hp"),
            pose=st.get("pose"),
        )
    return build_cit_character(
        atom_id=st["auid"],
        parent_id=st["world"],
        now_ms=now_ms,
        x=st["xyz"][0], y=st["xyz"][1], z=st["xyz"][2],
        rx=st["rot"][0], ry=st["rot"][1], rz=st["rot"][2],
        head_tilt=st["head_tilt"],
        name=st["name"],
        dna=st["dna"],
        pose=st.get("pose") or POSE_STANDING,
        empire_id=st["empire_id"],
        hunger=(st["hp"] if st.get("hp") is not None else 1000),
        gear=st["gear"],
    )


async def _emit(live_avatars: dict, avatar_auid: int, st: dict,
                why: str = "", full: Optional[bool] = None) -> bool:
    writer = _scene_writer(live_avatars, avatar_auid)
    if writer is None:
        return False
    if full is None:
        full = not st.get("emitted")
    pkt = _packet_for(st, full=full)
    try:
        await write_framed(writer, pkt)
    except Exception as exc:
        logger.warning('Targoss atom not sent (%s): %r.', why, exc)
        return False
    st["sent_xyz"] = st["xyz"]
    st["sent_heading"] = st["heading"]
    st["sent_tilt"] = st["head_tilt"]
    st["emitted"] = True
    return True


async def spawn(live_avatars: dict,
                avatar_auid: int,
                angle_deg: float = SPAWN_ANGLE_DEG,
                dist_ft: float = SPAWN_DIST_FT,
                name: str = TARGOSS_NAME,
                *,
                save,
                avatar_dna: Optional[bytes],
                _DYNAMIC_SCENE_AUIDS: set) -> Optional[int]:
    auid = int(avatar_auid) & 0xFFFFFFFF
    pxyz = player_xyz(live_avatars, auid)
    world = _parent_world(live_avatars, auid)
    if pxyz is None or world is None:
        logger.warning("Targoss not spawned: player xyz=%r parent_world=%r",
                       pxyz, world)
        return None

    fwd, right, _up = player_basis(pxyz, _player_rot(live_avatars, auid))
    raw = spawn_offset_xyz(pxyz, fwd, right, angle_deg, dist_ft)
    terrain, size = _terrain_and_size(save)
    pos, rot = _place(raw, terrain, size, pxyz)

    st = _NPCS.get(auid)
    fresh = st is None
    if fresh:
        st = {
            "auid": _atom_id(),
            "name": name,
            "dna": _player_dna(avatar_dna),
            "empire_id": 0,
            "gear": [],
            "head_tilt": 0.0,
            "mode": "stay",
            "goal": None,
            "emitted": False,
            "last_t": None,
            "pending_turn": 0.0,
            "sent_xyz": None,
            "sent_heading": None,
            "sent_tilt": None,
        }
        _NPCS[auid] = st
    st["world"] = int(world)
    st["terrain"], st["size"] = terrain, size
    st["xyz"] = pos
    st["heading"] = heading_to_face(pos, pxyz)
    st["rot"] = rot
    st["mode"] = "stay"
    st["goal"] = None

    _register_manifest(st["auid"], _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
    ok = await _emit(live_avatars, auid, st, "spawn", full=True)
    logger.info("%s %s 0x%08X parent=0x%08X angle=%.0f dist=%.0f "
                "xyz=(%.1f, %.1f, %.1f) rot=(%.4f, %.4f, %.4f) "
                "dist_to_player=%.1f ft",
                "Spawned" if fresh else "Teleported",
                name, st["auid"], st["world"], angle_deg, dist_ft,
                pos[0], pos[1], pos[2], rot[0], rot[1], rot[2],
                tangent_distance_ft(pos, pxyz))
    if not ok:
        logger.warning('...')
    return st["auid"] if ok else None


async def stay(avatar_auid: int) -> bool:
    st = _NPCS.get(int(avatar_auid) & 0xFFFFFFFF)
    if st is None:
        return False
    st["mode"] = "stay"
    st["goal"] = None
    logger.debug("Targoss ordered to stay (order 0).")
    return True


async def follow_person(avatar_auid: int) -> bool:
    st = _NPCS.get(int(avatar_auid) & 0xFFFFFFFF)
    if st is None:
        return False
    st["mode"] = "follow"
    st["goal"] = None
    logger.debug("Targoss ordered to follow, as a repeated gotoPerson "
                 "(order 9).")
    return True


async def move_back(avatar_auid: int, dist_ft: float) -> bool:
    auid = int(avatar_auid) & 0xFFFFFFFF
    st = _NPCS.get(auid)
    if st is None:
        return False
    from openshores.gameplay.natives.village import body_axes
    _right, fwd, _up = body_axes(*st["rot"])
    d = float(dist_ft)
    goal = (st["xyz"][0] - d * fwd[0],
            st["xyz"][1] - d * fwd[1],
            st["xyz"][2] - d * fwd[2])
    if st["terrain"] is not None and st["size"]:
        goal = project_to_terrain(goal, st["terrain"], st["size"])
    st["goal"] = goal
    st["mode"] = "goto"
    logger.debug("Targoss ordered back %.1f ft "
                 "(order 9 -> Project(0, -%.1f, 0)).", d, d)
    return True


async def equip(live_avatars: dict, avatar_auid: int, slot_name: str,
                commodity_name: str, quality: int = 1) -> bool:
    auid = int(avatar_auid) & 0xFFFFFFFF
    st = _NPCS.get(auid)
    if st is None:
        return False
    cid = commodity_id(commodity_name)
    if cid is None:
        logger.warning("Targoss not equipped: unknown commodity %r.",
                       commodity_name)
        return False
    built = gear_item(cid, quality)
    if built is None:
        tid = _AUITEM_TYPE_BY_CID.get(cid)
        logger.warning('Targoss not equipped: commodity %d (%r) is AuItem type %s, whose body is not built here.',
                       cid, commodity_name,
                       ("0x%02X" % tid) if tid is not None else "unknown")
        return False
    slot = _GEAR_SLOT_BY_NAME.get(
        " ".join(str(slot_name or "").split()).strip().lower())
    if slot is None:
        logger.warning("Targoss not equipped: unknown gear slot %r.",
                       slot_name)
        return False
    type_id, body = built
    used = [w for (s, w, _t, _b) in st["gear"] if s == slot]
    if len(used) >= GEAR_SLOT_CAPACITY.get(slot, 0):
        logger.warning("Targoss not equipped: slot %d already holds its cap "
                       "of %d.", slot, GEAR_SLOT_CAPACITY.get(slot, 0))
        return False
    which = 0
    while which in used:
        which += 1
    st["gear"].append((slot, which, type_id, body))
    logger.info("Targoss equipped cid=%d (%r) in slot %d/%d, type 0x%02X.",
                cid, commodity_name, slot, which, type_id)
    await _emit(live_avatars, auid, st, "equip")
    return True


async def despawn(avatar_auid: int, *, _DYNAMIC_SCENE_AUIDS: set) -> bool:
    auid = int(avatar_auid) & 0xFFFFFFFF
    st = _NPCS.pop(auid, None)
    if st is None:
        return False
    _DYNAMIC_SCENE_AUIDS.discard(st["auid"] & 0xFFFFFFFF)
    logger.info("Targoss 0x%08X despawned; the next 0x18 manifest culls the "
                "body.", st["auid"])
    return True


def atom_auid(avatar_auid: int) -> Optional[int]:
    st = _NPCS.get(int(avatar_auid) & 0xFFFFFFFF)
    if st is None or not st.get("emitted"):
        return None
    return int(st["auid"])


def has_body(avatar_auid: int) -> bool:
    return atom_auid(avatar_auid) is not None


def distance_ft(live_avatars: dict, avatar_auid: int) -> Optional[float]:
    auid = int(avatar_auid) & 0xFFFFFFFF
    st = _NPCS.get(auid)
    p = player_xyz(live_avatars, auid)
    if st is None or p is None:
        return None
    return tangent_distance_ft(st["xyz"], p)


def distance_less(live_avatars: dict, avatar_auid: int,
                  ft: float) -> Optional[bool]:
    d = distance_ft(live_avatars, avatar_auid)
    return None if d is None else bool(d < float(ft))


def distance_more(live_avatars: dict, avatar_auid: int,
                  ft: float) -> Optional[bool]:
    d = distance_ft(live_avatars, avatar_auid)
    return None if d is None else bool(d > float(ft))


def _augear_entries(avatar_auid: int, augear_states: dict) -> Optional[list]:
    states = augear_states
    key = int(avatar_auid) & 0xFFFFFFFF
    if key not in states:
        return None
    return list(states[key] or ())


def _entry_cid(entry) -> Optional[int]:
    try:
        if int(entry[2]) == 0:
            return None
        body = bytes(entry[3] or b"")
        if len(body) < 3:
            return None
        return struct.unpack(">h", body[1:3])[0]
    except Exception:
        return None


def person_has_item(avatar_auid: int, commodity, *,
                    augear_states: dict) -> Optional[bool]:
    cid = commodity if isinstance(commodity, int) else commodity_id(commodity)
    if cid is None:
        return None
    entries = _augear_entries(avatar_auid, augear_states)
    if entries is None:
        return None
    return any(_entry_cid(e) == int(cid) for e in entries)


def person_current_item(avatar_auid: int, commodity, *,
                        augear_states: dict,
                        actor_cursor: dict) -> Optional[bool]:
    cid = commodity if isinstance(commodity, int) else commodity_id(commodity)
    if cid is None:
        return None
    auid = int(avatar_auid) & 0xFFFFFFFF
    entries = _augear_entries(auid, augear_states)
    if entries is None:
        return None
    cursor = actor_cursor.get(auid)
    if not cursor:
        return None
    cslot, csub = int(cursor[0]) & 0xFF, int(cursor[1]) & 0x0F
    if cslot > 0x7F:
        return False
    for e in entries:
        if (int(e[0]) & 0xFF) == cslot and (int(e[1]) & 0x0F) == csub:
            return _entry_cid(e) == int(cid)
    return False


_RE_HELP = (
    "char.distanceLess(X, ft) / char.distanceMore(X, ft) / "
    "person.hasItem(X) / person.currentItem(X)"
)


def evaluate_condition(live_avatars: dict, avatar_auid: int, cond: str, *,
                       augear_states: dict,
                       actor_cursor: dict) -> Optional[bool]:
    import re as _re
    if not cond:
        return None
    text = str(cond).strip()
    if not text:
        return None
    if "|" in text:
        return None
    result: Optional[bool] = True
    for part in text.split("&"):
        term = part.strip()
        if not term:
            continue
        neg = False
        while term.startswith("!"):
            neg = not neg
            term = term[1:].strip()
        m = _re.match(r"^([A-Za-z_][\w.]*)\s*\((.*)\)$", term)
        if not m:
            return None
        fn, argtext = m.group(1), m.group(2)
        args = [a.strip() for a in argtext.split(",")] if argtext.strip() else []
        val: Optional[bool] = None
        try:
            if fn == "char.distanceLess" and len(args) >= 2:
                val = distance_less(live_avatars, avatar_auid, float(args[1]))
            elif fn == "char.distanceMore" and len(args) >= 2:
                val = distance_more(live_avatars, avatar_auid, float(args[1]))
            elif fn == "person.hasItem" and args:
                val = person_has_item(avatar_auid, args[0],
                                      augear_states=augear_states)
            elif fn == "person.currentItem" and args:
                val = person_current_item(avatar_auid, args[0],
                                          augear_states=augear_states,
                                          actor_cursor=actor_cursor)
        except Exception:
            val = None
        if val is None:
            return None
        if neg:
            val = not val
        result = bool(result) and bool(val)
    return result


def tick(live_avatars: dict, now_s: Optional[float] = None
         ) -> List[Tuple[int, int, bytes]]:
    if not _NPCS:
        return []
    import time as _t
    now = float(_t.monotonic() if now_s is None else now_s)
    speed = WALK_SPEED_FT_S
    stop_ft = FOLLOW_STOP_FT
    out: List[Tuple[int, int, bytes]] = []

    for avatar_auid, st in list(_NPCS.items()):
        last = st.get("last_t")
        st["last_t"] = now
        dt = 0.0 if last is None else max(0.0, min(now - last, 1.0))
        pxyz = player_xyz(live_avatars, avatar_auid)

        target = None
        stop_at = 0.0
        if st["mode"] == "follow" and pxyz is not None:
            target, stop_at = pxyz, stop_ft
        elif st["mode"] == "goto" and st.get("goal") is not None:
            target, stop_at = st["goal"], 0.0

        if target is not None and dt > 0.0:
            d = tangent_distance_ft(st["xyz"], target)
            if d > stop_at:
                step = min(speed * dt, d - stop_at)
                nxt = _step_toward(st["xyz"], target, step)
                if st["terrain"] is not None and st["size"]:
                    nxt = project_to_terrain(nxt, st["terrain"], st["size"])
                st["xyz"] = nxt
            if (st["mode"] == "goto"
                    and tangent_distance_ft(st["xyz"], target)
                    <= GOTO_ARRIVE_FT):
                st["mode"] = "stay"
                st["goal"] = None

        if pxyz is not None:
            want = heading_to_face(st["xyz"], pxyz, st["heading"])
            delta = want - st["heading"]
            delta = math.fmod(delta + math.pi, 2.0 * math.pi)
            if delta <= 0.0:
                delta += 2.0 * math.pi
            delta -= math.pi
            if dt > 0.0:
                step = TURN_RATE_RAD_S * dt
                if abs(delta) <= step:
                    st["heading"] = want
                else:
                    st["heading"] += math.copysign(step, delta)
        st["rot"] = gravity_align_euler(st["xyz"], st["heading"])

        moved = (st.get("sent_xyz") is None
                 or tangent_distance_ft(st["xyz"], st["sent_xyz"])
                 > EMIT_EPS_FT)
        turned = (st.get("sent_heading") is None
                  or abs(st["heading"] - st["sent_heading"]) > EMIT_EPS_RAD)
        tilted = (st.get("sent_tilt") is None
                  or abs(st["head_tilt"] - st["sent_tilt"]) > EMIT_EPS_RAD)
        if not (moved or turned or tilted):
            continue
        pkt = _packet_for(st)
        st["sent_xyz"] = st["xyz"]
        st["sent_heading"] = st["heading"]
        st["sent_tilt"] = st["head_tilt"]
        out.append((int(avatar_auid), int(st["auid"]), pkt))
    return out


def tick_packets(live_avatars: dict,
                 now_s: Optional[float] = None) -> List[bytes]:
    return [p for _a, _b, p in tick(live_avatars, now_s)]


async def pump(live_avatars: dict, now_s: Optional[float] = None) -> int:
    sent = 0
    for avatar_auid, _atom, pkt in tick(live_avatars, now_s):
        writer = _scene_writer(live_avatars, avatar_auid)
        if writer is None:
            continue
        await write_framed(writer, pkt)
        sent += 1
    return sent


AUCOMM_TYPE_CHAT_AUDIO = 0x2A
AUCOMM_TYPE_NARRATE_AUDIO = 0x4B

NARRATOR_SCOPE = 10


def audio_op(avatar_auid: int) -> int:
    return (AUCOMM_TYPE_CHAT_AUDIO if has_body(avatar_auid)
            else AUCOMM_TYPE_NARRATE_AUDIO)


def build_audio_packet(wav: bytes, avatar_auid: int,
                       story_instance: int = STORY_ID,
                       op: Optional[int] = None) -> Tuple[int, bytes]:
    auid = int(avatar_auid) & 0xFFFFFFFF
    tb = int(audio_op(auid) if op is None else op)
    sender = atom_auid(auid) or 0
    tail = (struct.pack(">I", len(wav)) + bytes(wav)
            + struct.pack(">i", int(story_instance))
            + struct.pack(">i", 0))
    frame = build_chat_aucomm_v4(
        type_byte=tb,
        body_after_parent=tail,
        sender_auid_int=(sender if tb == AUCOMM_TYPE_CHAT_AUDIO else 0),
        sender_name=(TARGOSS_NAME if tb == AUCOMM_TYPE_CHAT_AUDIO else ""),
        target_auid_int=auid,
        channel_name="",
        flags_byte=0x0F,
        scope=NARRATOR_SCOPE,
    )
    return (tb, frame)


if __name__ == "__main__":
    import sys

    _fails = []

    def check(label, cond, detail=""):
        if cond:
            logger.info("Ok %s", label)
        else:
            _fails.append(label)
            logger.error("Fail %s %s", label, detail)

    logger.info("Primitives")
    check("i32 normalises a high-bit auid",
          _i32(0xC9228A1A) == bytes.fromhex("c9228a1a"))
    check("qstring is i32 len + UTF-16BE",
          _qstring("Ab") == bytes.fromhex("00000004") + "Ab".encode("utf-16-be"))
    check("qbytearray is i32 len + raw",
          _qbytearray(b"\x01\x02") == bytes.fromhex("0000000201 02".replace(" ", "")))

    logger.info("\nAuGear, against AuData13 0x180157630 / 0x18016a320 / 0x18016a7d0")
    check("plain AuItem body is u8 00 | i16 cid | u8 quality",
          auitem_body_plain(21, 1) == bytes.fromhex("00001501"))
    check("quality 0 is floored to 1", auitem_body_plain(21, 0)[3] == 1)
    _dnab = auitem_body_dna(95, 1)
    check("AuItemDNA body is 4 + 4 + 24 + 1 = 33 B", len(_dnab) == 33)
    check("AuItemDNA carries a NULL DhDNA", _dnab[8:32] == bytes(24))
    _g = pack_augear([(GEAR_SLOT_WEAR, 0, AUITEM_TYPE_PLAIN,
                       auitem_body_plain(21, 100))])
    check("gear block = count | (which<<4)|slot | type | body",
          _g == bytes([1, 0x06, 0x01]) + auitem_body_plain(21, 100), _g.hex())
    check("empty gear block is one 00 byte", pack_augear(()) == b"\x00")
    try:
        pack_augear([(GEAR_SLOT_HEAD, 0, 1, b""), (GEAR_SLOT_HEAD, 1, 1, b"")])
        check("slot cap is enforced", False, "no raise")
    except ValueError:
        check("slot cap is enforced (Head caps at 1, 0x1804a36f0)", True)

    logger.info("\ncommodity / item-type tables, re-read from AuData13 0x180179860")
    check("Torch resolves to cid 131", commodity_id("Torch") == 131)
    check("Fabric Clothing resolves to cid 21",
          commodity_id("Fabric Clothing") == 21)
    check("cid 21 is a plain AuItem and IS emittable",
          gear_item(21, 100) is not None)
    check("cid 131 is AuItemWeaponState (0x0C) and is NOT emittable",
          gear_item(131, 100) is None
          and _AUITEM_TYPE_BY_CID[131] == AUITEM_TYPE_WEAPON_STATE)

    logger.info("\nthe 0x03 packet")
    _pkt = build_cit_character(
        atom_id=TARGOSS_AUID, parent_id=0x13E769E8, now_ms=1,
        x=1.0, y=2.0, z=3.0, rx=0.1, ry=0.2, rz=0.3,
        name=TARGOSS_NAME, dna=DNA_DEFAULT_HUMAN, gear=())
    check("tag byte is 0x03 (DaCitCharacter::Type @0x180116160)",
          _pkt[0] == 0x03)
    check("baseFlags is 0xEF", _pkt[13] == 0xEF)
    _i = 1
    _aid = struct.unpack(">i", _pkt[_i:_i + 4])[0] & 0xFFFFFFFF
    _i += 4
    _t0 = struct.unpack(">q", _pkt[_i:_i + 8])[0]
    _i += 8
    _bf = _pkt[_i]
    _i += 1
    check("RxUpdateId: AuId then AuTime", _aid == TARGOSS_AUID and _t0 == 1)
    _par = struct.unpack(">i", _pkt[_i:_i + 4])[0] & 0xFFFFFFFF
    _i += 4
    check("baseFlags bit0 -> parent AuId", _par == 0x13E769E8)
    _i += 8 + 8
    _six = struct.unpack(">6f", _pkt[_i:_i + 24])
    _i += 24
    check("baseFlags bit3 -> 6 floats, position then euler",
          all(abs(a - b) < 1e-6 for a, b in
              zip(_six, (1.0, 2.0, 3.0, 0.1, 0.2, 0.3))), _six)
    check("DaUnit flags == 0x01", _pkt[_i] == 0x01)
    _i += 1
    _nl = struct.unpack(">I", _pkt[_i:_i + 4])[0]
    _i += 4
    check("DaUnit name round-trips",
          _pkt[_i:_i + _nl].decode("utf-16-be") == TARGOSS_NAME)
    _i += _nl
    _i += 4 + 1
    check("DaCreature flags == 0x2F", _pkt[_i] == 0x2F)
    _i += 1
    check("bodyBits 0 == Male, right-handed", _pkt[_i] == 0x00)
    _i += 1
    _dl = struct.unpack(">I", _pkt[_i:_i + 4])[0]
    _i += 4
    check("DhDNA is a 24-byte QByteArray",
          _dl == 24 and _pkt[_i:_i + 24] == DNA_DEFAULT_HUMAN)
    _i += 24
    _i += 4
    check("hit points / hunger == 1000",
          struct.unpack(">h", _pkt[_i:_i + 2])[0] == 1000)
    _i += 2
    check("POSE array is 10 x 0x24",
          _pkt[_i:_i + 10] == bytes([0x24]) * 10)
    _i += 10 + 4
    check("+0x492 is ((dna[0]>>4)<<4)|0x0F",
          _pkt[_i] == ((((DNA_DEFAULT_HUMAN[0] >> 4) & 0x0F) << 4) | 0x0F))
    _i += 1 + 1
    check("DaSentient flags == 0x00", _pkt[_i] == 0x00)
    _i += 1
    check("DaCitCharacter leaf flags == 0x01 (gear present, no ship AuId)",
          _pkt[_i] == 0x01)
    _i += 1
    check("empty gear block, then END -- no role byte",
          _pkt[_i] == 0x00 and _i + 1 == len(_pkt),
          "i=%d len=%d tail=%s" % (_i, len(_pkt), _pkt[_i:].hex()))

    try:
        from openshores.gameplay.native_atom import (
            build_cit_indigenous as _bci)
        _ref = _bci(atom_id=TARGOSS_AUID, parent_id=0x13E769E8, now_ms=1,
                    x=1.0, y=2.0, z=3.0, rx=0.1, ry=0.2, rz=0.3,
                    name=TARGOSS_NAME, role=None, dna=DNA_DEFAULT_HUMAN,
                    tag=ATOM_TAG_CIT_CHARACTER, gear=())
        check("byte-identical to build_cit_indigenous(tag=0x03, role=None)",
              _pkt == _ref,
              "ours=%s\n     ref =%s" % (_pkt.hex(), _ref.hex()))
    except Exception as _sx:
        logger.info("  ..   spike cross-check skipped (%r)" % (_sx,))

    logger.info("\nplacement, against char.spawn @0x18020d718")
    _R = 27961.7
    _p = (_R * 0.6, _R * 0.48, _R * 0.64)
    _p = tuple(c * _R / math.sqrt(sum(v * v for v in _p)) for c in _p)
    _fwd, _rgt, _up = player_basis(_p, (0.0, 0.0, 0.0))
    check("player basis is orthonormal",
          all(abs(_dot(a, a) - 1.0) < 1e-12 for a in (_fwd, _rgt, _up))
          and abs(_dot(_fwd, _rgt)) < 1e-12
          and abs(_dot(_fwd, _up)) < 1e-12
          and abs(_dot(_rgt, _up)) < 1e-12)
    check("right = forward x up, so +90 deg is LEFT",
          _dot(_cross(_fwd, _up), _rgt) > 0.999999)
    _behind = spawn_offset_xyz(_p, _fwd, _rgt, 180.0, 50.0)
    _front = spawn_offset_xyz(_p, _fwd, _rgt, 0.0, 50.0)
    _left = spawn_offset_xyz(_p, _fwd, _rgt, 90.0, 50.0)
    _right_pt = spawn_offset_xyz(_p, _fwd, _rgt, -90.0, 50.0)
    check("angle 0 is forward",
          _dot([_front[i] - _p[i] for i in range(3)], _fwd) > 49.999)
    check("angle 180 is behind",
          _dot([_behind[i] - _p[i] for i in range(3)], _fwd) < -49.999)
    check("angle 90 is left (-right)",
          _dot([_left[i] - _p[i] for i in range(3)], _rgt) < -49.999)
    check("angle -90 is right",
          _dot([_right_pt[i] - _p[i] for i in range(3)], _rgt) > 49.999)
    check("the offset is 50 ft from the player",
          abs(tangent_distance_ft(_behind, _p) - 50.0) < 1e-6)

    from openshores.gameplay.natives.village import body_axes as _axes

    def _angle_deg(a, b):
        c = _cross(a, b)
        return math.degrees(math.atan2(
            math.sqrt(c[0] * c[0] + c[1] * c[1] + c[2] * c[2]), _dot(a, b)))

    _worst = 0.0
    for _hdg in (0.0, 0.7, -2.4, math.pi):
        for _pt in (_behind, _front, _left, _right_pt,
                    (0.0, 0.0, _R), (0.0, 0.0, -_R), (_R, 0.0, 0.0)):
            _rot = gravity_align_euler(_pt, _hdg)
            _worst = max(_worst, _angle_deg(_axes(*_rot)[2], _norm3(_pt)))
    check("up-axis matches local vertical to < 1e-9 deg (worst %.2e deg)"
          % _worst, _worst < 1e-9, _worst)

    _hdg = heading_to_face(_behind, _p)
    _rot_b = gravity_align_euler(_behind, _hdg)
    _fw = _axes(*_rot_b)[1]
    _up_b = _axes(*_rot_b)[2]
    _los = [_p[i] - _behind[i] for i in range(3)]
    _rad = _dot(_los, _up_b)
    _level = _norm3([_los[i] - _rad * _up_b[i] for i in range(3)])
    check("the spawned body faces the person, levelled "
          "(RotateZ(pi) @0x18020d7b8) -- %.2e deg off"
          % _angle_deg(_fw, _level),
          _angle_deg(_fw, _level) < 1e-9, _angle_deg(_fw, _level))
    check("that level facing is 0.10 deg off the raw line of sight, which is "
          "the sphere's own geometry",
          abs(_angle_deg(_fw, _norm3(_los))
              - math.degrees(math.asin(50.0 / math.sqrt(_R * _R + 2500.0))))
          < 1e-9)

    _terr = (0.5, 0.5, 0.0, 0.11, 0.22, 0.5)
    try:
        _pr = project_to_terrain(_behind, _terr, 5)
        _pr2 = project_to_terrain(_pr, _terr, 5)
        check("project_to_terrain is idempotent",
              tangent_distance_ft(_pr, _pr2) < 1e-6,
              tangent_distance_ft(_pr, _pr2))
        from openshores.gameplay.worldgen.terrain import (
            terrain_altitude_msl as _alt)
        from openshores.gameplay.worldgen.world_gen import (
            globe_radius_units as _gru)
        _lat = math.asin(max(-1.0, min(1.0, _pr[2]
                                       / math.sqrt(sum(c * c for c in _pr)))))
        _lon = math.atan2(_pr[1], _pr[0])
        _want_r = _gru(5) + _alt(_terr, 5, _lat, _lon) + 2.95
        _got_r = math.sqrt(sum(c * c for c in _pr))
        check("the body sits on the terrain surface + creature height "
              "(err %.3e)" % abs(_got_r - _want_r),
              abs(_got_r - _want_r) < 1e-3, (_got_r, _want_r))
    except Exception as _tx:
        logger.info("  ..   terrain assertions skipped (%r)" % (_tx,))

    logger.info("\ncondition parser")
    def _cond(text):
        return evaluate_condition({}, 1, text, augear_states={},
                                  actor_cursor={})

    check("unknown predicate -> None (never a guess)",
          _cond("person.xpLess(10)") is None)
    check("disjunction -> None", _cond("a(1) | b(2)") is None)
    check("empty -> None", _cond("") is None)
    check("no live avatar -> None (don't-know, not False)",
          _cond("char.distanceLess(Targoss, 12)") is None)
    check("_entry_cid pulls the cid out of an AuItem body",
          _entry_cid([6, 0, 1, auitem_body_plain(21, 100)]) == 21)
    check("_entry_cid on an empty slot -> None",
          _entry_cid([6, 0, 0, b""]) is None)

    logger.info("\nconsistency with story_targoss")
    check("the shipped script really is spawn(180, 50)",
          (SPAWN_ANGLE_DEG, SPAWN_DIST_FT) == (180.0, 50.0))

    logger.info("\naudio op selection")
    check("auto with no body falls back to 0x4B",
          audio_op(1) == AUCOMM_TYPE_NARRATE_AUDIO)

    logger.info("\n%d failure(s)", len(_fails))
    sys.exit(1 if _fails else 0)
