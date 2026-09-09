
from __future__ import annotations

from typing import Dict, Iterable, Set

MODE_LAND = 0x1
MODE_SEA = 0x2
MODE_AIR = 0x4

AIR_BUILDING_TYPES = frozenset((0x6F, 0x86))
SEA_BUILDING_TYPES = frozenset((0x22, 0x88))

ATOM_STATE_SKIP_MASK = 0xFB


class TradeConnections:

    __slots__ = ("peers", "has_air", "has_sea", "owner")

    def __init__(self, owner=0):
        self.peers: Dict[int, int] = {}
        self.has_air = False
        self.has_sea = False
        self.owner = int(owner)

    def has_connection(self, peer_id: int) -> bool:
        return int(peer_id) in self.peers

    def has_connection_by_ground(self, peer_id: int) -> bool:
        return bool(self.peers.get(int(peer_id), 0) & MODE_LAND)

    def _count(self, bit: int) -> int:
        return sum(1 for pid, modes in self.peers.items()
                   if pid != self.owner and (modes & bit))

    def by_land(self) -> int:
        return self._count(MODE_LAND)

    def by_air(self) -> int:
        return self._count(MODE_AIR) if self.has_air else 0

    def by_sea(self) -> int:
        return self._count(MODE_SEA) if self.has_sea else 0

    def any_connection(self) -> bool:
        return bool(self.peers)


def update_ground_trade_connections(owner_id: int, owner_building_type: int,
                                    peers: Iterable[dict]) -> TradeConnections:
    tc = TradeConnections(owner=owner_id)
    t = int(owner_building_type)
    tc.has_air = t in AIR_BUILDING_TYPES
    tc.has_sea = t in SEA_BUILDING_TYPES

    for p in peers or ():
        if int(p.get("atom_state", 0) or 0) & ATOM_STATE_SKIP_MASK:
            continue
        pid = int(p.get("id", 0) or 0)
        if not pid:
            continue
        tc.peers[pid] = tc.peers.get(pid, 0) | MODE_LAND
        if p.get("kind") == "city":
            if p.get("has_airport"):
                tc.has_air = True
            elif p.get("has_seaport"):
                tc.has_sea = True
        else:
            bt = int(p.get("building_type", 0) or 0)
            if bt in AIR_BUILDING_TYPES:
                tc.has_air = True
            elif bt in SEA_BUILDING_TYPES:
                tc.has_sea = True
    return tc


def road_peers_of(city_id: int, cities: Dict[int, dict], connected) -> Set[int]:
    seen: Set[int] = set()
    queue = [int(city_id)]
    while queue:
        cur = queue.pop()
        for other in cities:
            other = int(other)
            if other == cur or other in seen or other == int(city_id):
                continue
            if connected(cur, other):
                seen.add(other)
                queue.append(other)
    return seen
