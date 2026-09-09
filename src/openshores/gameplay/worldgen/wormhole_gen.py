
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from openshores.protocol.rng import AuNoise

POLARITY_POSITIVE = 1
POLARITY_NEGATIVE = 2
POLARITY_BLACK_HOLE = 3

WORMHOLE_RANGE = 5.0

NOISE_THRESHOLD = 0.15

NO_BEST = -1.0

STAR_DISTANCE_MULT = 2.0
NEGATIVE_DISTANCE_MULT = 1.100000023841858

SECTOR_SIZE = 10.0
NEIGHBOUR_OFFSETS = tuple(
    (dx, dy, dz)
    for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1))


@dataclass(frozen=True)
class SystemNode:
    auid: int
    cell: Tuple[int, int, int]
    x: float
    y: float
    z: float


@dataclass
class Wormhole:
    polarity: int
    target: int
    vec: Tuple[float, float, float]
    ids: Tuple[int, ...] = ()
    name: str = ""


@dataclass
class WormholeMap:
    by_system: Dict[int, List[Wormhole]] = field(default_factory=dict)

    def get(self, auid: int) -> List[Wormhole]:
        return self.by_system.get(auid, [])

    def counts(self):
        pos = sum(1 for ws in self.by_system.values()
                  for w in ws if w.polarity == POLARITY_POSITIVE)
        neg = sum(1 for ws in self.by_system.values()
                  for w in ws if w.polarity == POLARITY_NEGATIVE)
        return pos, neg


def positive_wormhole_count(x: float, y: float, z: float) -> int:
    n = 2 if AuNoise.integer_noise1(0, int(x)) > NOISE_THRESHOLD else 1
    if AuNoise.integer_noise1(1, int(y)) > NOISE_THRESHOLD:
        n += 1
    if AuNoise.integer_noise1(2, int(z)) > NOISE_THRESHOLD:
        n += 1
    return 3 if n > 3 else n


def neighbourhood(index: Dict[Tuple[int, int, int], List[SystemNode]],
                  cell: Tuple[int, int, int]) -> List[SystemNode]:
    cx, cy, cz = cell
    out: List[SystemNode] = []
    for dx, dy, dz in NEIGHBOUR_OFFSETS:
        got = index.get((cx + dx, cy + dy, cz + dz))
        if got:
            out.extend(got)
    return out


def positive_targets(system: SystemNode,
                     candidates: Sequence[SystemNode]) -> List[SystemNode]:
    wanted = positive_wormhole_count(system.x, system.y, system.z)
    excluded = {system.auid}
    chosen: List[SystemNode] = []
    for _ in range(wanted):
        best = None
        best_d2 = NO_BEST
        for cand in candidates:
            if cand.auid in excluded:
                continue
            dx = cand.x - system.x
            dy = cand.y - system.y
            dz = cand.z - system.z
            if abs(dx) >= WORMHOLE_RANGE or abs(dy) >= WORMHOLE_RANGE \
                    or abs(dz) >= WORMHOLE_RANGE:
                continue
            d2 = dx * dx + dy * dy + dz * dz
            if best_d2 == NO_BEST or d2 < best_d2:
                best = cand
                best_d2 = d2
        if best is None:
            break
        excluded.add(best.auid)
        chosen.append(best)
    return chosen


def generate(systems: Sequence[SystemNode]) -> WormholeMap:
    index: Dict[Tuple[int, int, int], List[SystemNode]] = {}
    for s in systems:
        index.setdefault(s.cell, []).append(s)

    wmap = WormholeMap()

    inbound: Dict[int, List[SystemNode]] = {}
    node_by_id = {s.auid: s for s in systems}
    for s in systems:
        cands = neighbourhood(index, s.cell)
        links = []
        for t in positive_targets(s, cands):
            links.append(Wormhole(POLARITY_POSITIVE, t.auid,
                                  (t.x - s.x, t.y - s.y, t.z - s.z)))
            inbound.setdefault(t.auid, []).append(s)
        if links:
            wmap.by_system[s.auid] = links

    for auid, sources in inbound.items():
        s = node_by_id.get(auid)
        if s is None:
            continue
        seen = set()
        links = wmap.by_system.setdefault(auid, [])
        for src in sources:
            if src.auid in seen:
                continue
            seen.add(src.auid)
            links.append(Wormhole(POLARITY_NEGATIVE, src.auid,
                                  (src.x - s.x, src.y - s.y, src.z - s.z)))
    return wmap


def _encode_qstring(s: str) -> bytes:
    if s is None:
        return b"\xff\xff\xff\xff"
    data = s.encode("utf-16-be")
    return struct.pack(">I", len(data)) + data


def encode(wormholes: Sequence[Wormhole]) -> bytes:
    out = bytearray(struct.pack(">i", len(wormholes)))
    for w in wormholes:
        out += struct.pack(">i", len(w.ids))
        for i in w.ids:
            out += struct.pack(">I", i & 0xFFFFFFFF)
        out += _encode_qstring(w.name)
        out += struct.pack(">b", w.polarity)
        out += struct.pack(">I", w.target & 0xFFFFFFFF)
        out += struct.pack(">ddd", *w.vec)
    return bytes(out)


def decode(blob: bytes) -> List[Wormhole]:
    if not blob:
        return []
    off = 0
    (count,) = struct.unpack_from(">i", blob, off)
    off += 4
    out: List[Wormhole] = []
    for _ in range(count):
        (nids,) = struct.unpack_from(">i", blob, off)
        off += 4
        ids = []
        for _ in range(nids):
            (v,) = struct.unpack_from(">i", blob, off)
            off += 4
            ids.append(v & 0xFFFFFFFF)
        (slen,) = struct.unpack_from(">I", blob, off)
        off += 4
        if slen == 0xFFFFFFFF:
            name = None
        else:
            name = blob[off:off + slen].decode("utf-16-be")
            off += slen
        (polarity,) = struct.unpack_from(">b", blob, off)
        off += 1
        (target,) = struct.unpack_from(">i", blob, off)
        off += 4
        vec = struct.unpack_from(">ddd", blob, off)
        off += 24
        out.append(Wormhole(polarity, target & 0xFFFFFFFF, vec,
                            tuple(ids), name))
    return out
