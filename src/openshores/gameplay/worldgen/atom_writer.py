
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional

from openshores.database.repositories import atom_writer as _rows
from openshores.protocol.rng import AuDice

from . import fauna as fau
from . import geology as geol
from . import world_gen as wg


@dataclass
class SystemRows:

    star: List[tuple] = field(default_factory=list)
    globe: List[tuple] = field(default_factory=list)
    gas_giant: List[tuple] = field(default_factory=list)
    ring: List[tuple] = field(default_factory=list)
    ring_section: List[tuple] = field(default_factory=list)
    ringworlds: int = 0

    def extend(self, other: "SystemRows") -> None:
        self.star += other.star
        self.globe += other.globe
        self.gas_giant += other.gas_giant
        self.ring += other.ring
        self.ring_section += other.ring_section
        self.ringworlds += other.ringworlds

    @property
    def total(self) -> int:
        return (len(self.star) + len(self.globe) + len(self.gas_giant)
                + len(self.ring) + len(self.ring_section))


async def build_system_rows(primary, system_auid: int, system_seed: int,
                            claim: Callable[[int, int], Awaitable[int]], *,
                            detail: bool = False) -> SystemRows:
    out = SystemRows()
    star_ids: Dict[int, int] = {}

    for st in wg.walk_stars(primary):
        stid = await claim(system_seed, 0xC3 + st.index)
        star_ids[st.index] = stid
        spid = system_auid if st.is_primary else star_ids[primary.index]
        out.star.append((
            stid, spid, spid, f"Star_{stid:06x}",
            bytes([st.star_type & 0xFF]),
            bytes([st.subclass & 0xFF]),
            bytes([st.size & 0xFF]),
            float(st.min_orbit & 0xFF),
            float(st.companion_orbit & 0xFF),
            float(st.hab_orbit & 0xFF),
            bytes(z & 0xFF for z in st.zones)))

        parent_of: Dict[int, object] = {}
        for top in st.worlds:
            for b in top.walk():
                for m in b.moons:
                    parent_of[id(m)] = b
        assigned: Dict[int, int] = {}
        salt = 0
        for w in (b for top in st.worlds for b in top.walk()):
            salt += 1
            wid = await claim(system_seed,
                              0xD4 + st.index * 4096 + salt)
            assigned[id(w)] = wid
            par = parent_of.get(id(w))
            pid = assigned[id(par)] if par is not None else stid
            orbit_blob = struct.pack("<d", w.orbit_radius)
            zone_blob = bytes([w.orbit_zone & 0xFF])

            if w.kind == "globe":
                flora = faunablob = geoblob = None
                if detail:
                    flora, faunablob, geoblob = world_detail(w, wid)
                out.globe.append((
                    wid, pid, pid, w.name or f"World_{wid:06x}",
                    orbit_blob, zone_blob,
                    float(w.size & 0xFF),
                    bytes([w.atm_density & 0xFF]),
                    bytes([w.atm_type & 0xFF]),
                    bytes([w.water & 0xFF]),
                    struct.pack(">ffffff", *w.terrain),
                    flora, faunablob, geoblob))
            elif w.kind == "gasgiant":
                out.gas_giant.append((
                    wid, pid, pid, w.name or f"GasGiant_{wid:06x}",
                    orbit_blob, zone_blob,
                    float(w.size & 0xFF),
                    bytes([w.atm_density & 0xFF]),
                    bytes([w.atm_type & 0xFF]),
                    bytes([w.water & 0xFF]),
                    struct.pack(">ffffff", *w.terrain)))
            elif w.kind == "ring":
                out.ring.append((
                    wid, pid, pid, w.name or f"Ring_{wid:06x}",
                    orbit_blob, zone_blob))
            else:
                out.ringworlds += 1
                for sec in w.ring_sections:
                    secid = await claim(wid ^ (sec.index + 1), 0xE5)
                    sec.name = (f"{w.name} {sec.index + 1}" if w.name
                                else f"RingSection_{secid:06x}")
                    out.ring_section.append((
                        secid, stid, stid, sec.name,
                        orbit_blob, zone_blob,
                        bytes([sec.atm_density & 0xFF]),
                        bytes([sec.atm_type & 0xFF]),
                        bytes([sec.water & 0xFF]),
                        int(sec.index),
                        struct.pack(">ffffff", *sec.terrain),
                        geol.encode(sec.features)))
    return out


def world_detail(w, wid: int):
    seed = (int(wid) & 0xFFFFFFFF) or 1
    flora = wg.world_flora_blob(w, AuDice(seed))
    geoblob = geol.world_geo_blob(w, AuDice(seed))
    faunablob = (fau.world_fauna_blob(w, AuDice(seed))
                 if w.can_have_fauna() else None)
    return flora, faunablob, geoblob


_PARENT_INDEXED = ("a_Star", "a_WorldGlobe", "a_WorldGasGiant", "a_WorldRing",
                   "a_WorldRingSection", "a_SolarSystem", "a_Sector")


async def ensure_parent_atom_indexes(con) -> int:
    raise NotImplementedError(
        "The parent_atom index DDL moved out of gameplay.")


async def ensure_core_radius_column(con) -> bool:
    raise NotImplementedError(
        "The coreRadius heal moved out of gameplay")


async def write_system_rows(con, rows: SystemRows) -> None:
    await _rows.write_system_rows(con, rows)
