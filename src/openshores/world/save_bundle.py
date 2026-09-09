from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SiblingGlobe:
    auid: int = 0
    name: str = ""
    parent_auid: int = 0
    position: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0)
    size_code: int = 0
    size_byte_b1: int = 0
    size_byte_b2: int = 0
    size_byte_b3: int = 0
    core_radius: int = 0
    terrain: Optional[tuple] = None
    zone: int = 2
    class_kind: str = "globe"
    section_index: int = 0


@dataclass
class RealStar:
    auid: int = 0
    name: str = ""
    position: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0)


@dataclass
class SaveBundle:
    universe_name: str = ""
    universe_auid: int = 0

    empire_name: str = ""
    empire_name_short: str = ""
    empire_auid: int = 0
    capital_name: str = ""

    sector_name: str = ""
    sector_auid: int = 0
    sector_position: tuple = (0.0, 0.0, 0.0)
    sector_rotation: tuple = (0.0, 0.0, 0.0)
    galaxy_auid: int = 0
    galaxy_name_index: int = 15
    galaxy_rotation: tuple = (0.0, 0.0, 0.0)
    system_name: str = ""
    system_auid: int = 0
    system_position: tuple = (0.0, 0.0, 0.0)
    system_rotation: tuple = (0.0, 0.0, 0.0)
    star_name: str = ""
    star_spec_type: int = 4
    star_spec_size: int = 5
    star_spec_subclass: int = 5
    star_orbit_zones: bytes = b"\x01\x02\x03\x04\x04\x05\x05\x06\x06\x00\x00\x00\x00\x00\x00\x00"
    star_hab_first: int = 0xFF
    star_hab_last: int = 0xFF
    star_companion: int = 0xFF
    planet_name: str = ""
    planet_kind: str = "globe"
    planet_section_index: int = 0
    planet_auid: int = 0
    planet_position: tuple = (0.0, 0.0, 0.0)
    planet_rotation: tuple = (0.0, 0.0, 0.0)
    planet_size_code: int = 0
    planet_climate: tuple = (0.0,)*6
    planet_home_llf: tuple = (0.0, 0.0, 0.0)
    planet_terrain: Optional[tuple] = None
    planet_zone: int = 2
    planet_size_byte_b1: int = 0
    planet_size_byte_b2: int = 0
    planet_size_byte_b3: int = 0

    person_name: str = ""
    person_italic: Optional[str] = None
    person_dna24: Optional[bytes] = None
    person_auid: int = 0
    person_time_created: int = 0
    person_time_modified: int = 0
    person_pose: int = 0
    person_stamina: int = 0
    person_hunger: int = 0
    person_hit_points: int = 0
    person_surface_llf: tuple = (0.0, 0.0, 0.0)
    person_position: tuple = (0.0, 0.0, 0.0)
    person_rotation: tuple = (0.0, 0.0, 0.0)

    celestial_body_auid: int = 0
    celestial_body_position: tuple = (0.0, 0.0, 0.0)
    celestial_body_rotation: tuple = (0.0, 0.0, 0.0)

    sibling_globes: List["SiblingGlobe"] = field(default_factory=list)

    real_stars: List["RealStar"] = field(default_factory=list)

    whereabouts_place: Optional[str] = None
    whereabouts_auid: Optional[int] = None
    whereabouts_display: Optional[str] = None

    motd: str = ""

    name_pools: Dict[str, List[str]] = field(default_factory=dict)

    source: str = ""
    raw_universe: Optional[UniverseIdentity] = None  # noqa: F821
    raw_person: Optional[PersonIdentity] = None  # noqa: F821
