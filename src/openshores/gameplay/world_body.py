
from __future__ import annotations

import struct

from openshores.core.logging import get_logger
from openshores.database.repositories.world import _ring_section_geo
from openshores.gameplay.city_model import merge_roads_into_geo_payload
from openshores.gameplay.worldgen import real
from openshores.gameplay.worldgen.globe_divisions import (
    _GLOBE_DIVISIONS_MAX_SIZE,
)
from openshores.gameplay.worldgen.planet_flora import _get_or_init_planet_flora
from openshores.protocol.rng import AuDice

logger = get_logger(__name__)

_RING_FLORA_ZONES: int = 2


async def _build_wg_body(conn, name_str, zone, size_code,
                         size_byte_b1, size_byte_b2, size_byte_b3,
                         auid_seed=0,
                         home_llf=None,
                         home_anchor=0,
                         diag_label="",
                         lite=False,
                         orbit_au=1.0,
                         kind="globe",
                         core_radius=None,
                         section_index=0,
                         terrain=None,
                         *,
                         wg_geo_parts: dict,
                         gather_planet_roads,
                         get_or_init_planet_geo):
    _n_utf16 = (name_str or "").encode("utf-16-be")
    _seed_base = (auid_seed & 0xFFFFFFFF) or 0xA1B2C3D4
    _noise_seed_x = float((_seed_base * 97) % 100000) + 0.37
    _noise_seed_y = float((_seed_base * 61 + 12345) % 100000) + 0.81
    _water_byte = size_byte_b3 if size_byte_b3 else 50
    _water_x = (_water_byte / 111.11 - 0.5) * 2.0
    _water_sq = _water_x * _water_x
    if _water_x < 0.0:
        _water_sq = -_water_sq
    if kind == "ring_section":
        if lite:
            _wg_flag = 0x01 | 0x40
        else:
            _wg_flag = (0x01 | 0x02 | 0x08 | 0x40
                        | 0x20)
    elif lite:
        _wg_flag = 0x01 | 0x20
    else:
        _wg_flag = (
            0x01
            | 0x02
            | 0x04
            | 0x08
            | 0x10
            | 0x20
        )
    _dna_core: bytes
    if _seed_base == 0xA1B2C3D4:
        _dna_core = bytes([
            0x4b, 0x6c, 0x54, 0x74, 0xc5, 0x62, 0x62, 0x76,
            0x06, 0x69, 0x2d, 0x4c, 0x4e, 0x00, 0x2e, 0x24,
            0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24,
        ])
    else:
        _rng = _seed_base & 0xFFFFFFFF or 0xDEADBEEF
        _buf = bytearray(24)
        for _i in range(24):
            _rng ^= (_rng << 13) & 0xFFFFFFFF
            _rng ^= (_rng >> 17) & 0xFFFFFFFF
            _rng ^= (_rng << 5)  & 0xFFFFFFFF
            _buf[_i] = _rng & 0xFF
        _dna_core = bytes(_buf)
    if kind == "ring_section":
        _dna_bytes = b"" if lite else (
            struct.pack(">I", 24) + _dna_core)
    elif lite:
        _dna_bytes = b""
    else:
        _dna_bytes = struct.pack(">I", 24) + _dna_core
        logger.debug(f"[wg-dna] planet_auid=0x{_seed_base:08x} "
                     f"dna24={_dna_core.hex()}")
    _hl, _hg = (0.0, 0.0) if home_llf is None else home_llf
    if kind == "ring_section":
        if lite:
            _flora_bytes = b""
        else:
            _flora_bytes = await _get_or_init_planet_flora(
                conn, int(auid_seed), _RING_FLORA_ZONES,
                int(size_code or 0), table="a_WorldRingSection")
            logger.debug(f"[wg-flora] ring section zones="
                         f"{_RING_FLORA_ZONES} -> {len(_flora_bytes)}B "
                         f"flag-0x20 block")
    elif lite:
        _flora_bytes = b""
        if diag_label:
            logger.debug(f'[wg-lite] {diag_label}: flag=0x21 (size+home only).')
    else:
        _zones = 3 if int(size_code) > 2 else 1
        _flora_bytes = await _get_or_init_planet_flora(
            conn, int(auid_seed), int(_zones), int(size_code or 0))
        logger.debug(f"[wg-flora] zones={_zones} "
                     f"-> {len(_flora_bytes)}B flag-0x10 block "
                     f"(persisted per-AUID)")
    if not lite:
        _geo_bytes = await get_or_init_planet_geo(
            int(auid_seed), int(size_code),
            int(size_byte_b2 or 0), int(size_byte_b3 or 0))
        logger.debug(f"[wg-geo] "
                     f"{len(_geo_bytes)}B persisted-per-AUID geo "
                     f"({_geo_bytes[0]} feature(s))")
    else:
        _geo_bytes = bytes([0x00])
        logger.debug("[wg-geo] count=0 (empty)")
    if kind == "ring_section":
        _geo_bytes = b"" if lite else await _ring_section_geo(
            conn, int(auid_seed))
    elif lite:
        _geo_bytes = b""
    _geo_base = _geo_bytes
    if _geo_bytes and not lite:
        try:
            _rds = await gather_planet_roads(int(auid_seed))
            if _rds:
                _pre = _geo_bytes[0]
                _geo_bytes = merge_roads_into_geo_payload(
                    _geo_bytes, _rds)
                logger.info(f"[wg-geo] merged {len(_rds)} road(s) into geo "
                            f"payload (features {_pre}->{_geo_bytes[0]})")
        except Exception as _rex:
            logger.warning(f"[wg-geo] road merge err: {_rex!r}")
    _hl, _hg = (0.0, 0.0) if home_llf is None else home_llf
    _home_bytes = (
        struct.pack(">ff", float(_hl), float(_hg))
        + struct.pack(">i", int(home_anchor))
    )
    try:
        _fx = (float(max(size_code, 2)), 2.26, 0.65,
               _noise_seed_x, _noise_seed_y, _water_sq)
        _hshown = (_hl, _hg)
        logger.debug(f"[wg] {diag_label or name_str!r}"
                     f" size={size_code} b1/atmType={size_byte_b1}"
                     f" b2/atmDens={size_byte_b2}"
                     f" b3/water={size_byte_b3} zone={zone}"
                     f" flag=0x{_wg_flag:02x}"
                     f" flora=YES"
                     f" home={_hshown} src={'save' if home_llf else 'default'}")
    except Exception as _wgd:
        logger.debug(f"[wg] diag failed: {_wgd!r}")
    _zone_render_profiles = {
        0: (4, 80),
        1: (4, 10),
        2: (0, 60),
        3: (2, 30),
        4: (3, 80),
    }
    _zone_at, _zone_water = _zone_render_profiles.get(
        int(zone) & 0xFF, (0, 30))

    _atm_done = False
    if kind == "moon":
        _atmDens_resolved = 0
        _atmType_resolved = 0
        _water_resolved   = 0
    elif kind == "ring_section":
        _atmType_resolved = int(size_byte_b1 or 0) & 0xFF
        _atmDens_resolved = int(size_byte_b2 or 0) & 0xFF
        _water_resolved   = int(size_byte_b3 or 0) & 0xFF
        _atm_done = True
    elif kind == "gas_giant":
        _atmType_resolved = int(size_byte_b1 or 0) & 0xFF
        _atmDens_resolved = int(size_byte_b2 or 0) & 0xFF
        _water_resolved   = 0
        _atm_done = True
    else:
        _atm_done = False
        try:
            _habp = (real.HAB_HOMEWORLD if int(zone) in (1, 2, 3)
                     else real.HAB_SYSTEM)
            _adp = AuDice(
                seed=((auid_seed & 0xFFFFFFFF) ^ 0xA7) or 1)
            (_atmDens_resolved, _atmType_resolved,
             _water_resolved) = real.roll_atm_water(
                _adp, int(size_code), _habp)
            _atm_done = True
        except Exception as _aerr:
            logger.warning(f"[physical] worldgen_real unavailable "
                           f"({_aerr!r})")
        if not _atm_done:
            _atmDens_resolved = (
                int(size_byte_b2) if size_byte_b2 else 30) & 0xFF

    if kind != "moon" and not _atm_done:
        _atmType_resolved = (
            int(size_byte_b1) if size_byte_b1 else _zone_at) & 0xFF
        _water_resolved = (
            int(size_byte_b3) if size_byte_b3 else _zone_water) & 0xFF
    if kind == "gas_giant":
        _core_radius = int(core_radius or 0) & 0xFF
        if not 0 <= _core_radius <= _GLOBE_DIVISIONS_MAX_SIZE:
            logger.warning(f"[gas-giant] {diag_label or name_str!r} core radius {_core_radius} is outside the client's divisions LUT (0..{_GLOBE_DIVISIONS_MAX_SIZE}).")
            _core_radius = min(max(_core_radius, 1),
                               _GLOBE_DIVISIONS_MAX_SIZE)
        elif _core_radius == 0:
            _core_radius = 1
        _class_bytes = bytes([
            size_code & 0xFF,
            _core_radius,
            _atmType_resolved,
            _atmDens_resolved,
        ])
        try:
            if terrain is not None and len(terrain) == 6:
                _tf = tuple(terrain)
            else:
                _tf = real.create_terrain_data(
                    AuDice(seed=(auid_seed & 0xFFFFFFFF) or 1),
                    int(size_code), 0,
                    zone_count=(3 if int(size_code) > 2 else 1))
            _class_floats = struct.pack(">fffff", *_tf[:5])
        except Exception as _twerr:
            logger.warning(f"[terrain] gas-giant worldgen unavailable ({_twerr!r})")
            _class_floats = struct.pack(">fffff",
                                         float(max(size_code, 4)),
                                         2.26, 0.65,
                                         _noise_seed_x,
                                         _noise_seed_y)
    elif kind == "ring_section":
        _class_bytes = bytes([
            _atmType_resolved,
            _atmDens_resolved,
            _water_resolved,
            int(section_index or 0) & 0xFF,
        ])
        try:
            if terrain is not None and len(terrain) == 6:
                _tf = tuple(terrain)
            else:
                _tf = (1.0, 1.0, 0.5, _noise_seed_x,
                       _noise_seed_y, 0.0)
                logger.debug(f'[terrain] ring section {diag_label or name_str!r} has no stored terrain.')
            _class_floats = struct.pack(">ffffff", *_tf)
        except Exception as _twerr:
            logger.warning(f"[terrain] ring section body failed ({_twerr!r})")
            _class_floats = struct.pack(">ffffff", 1.0, 1.0, 0.5,
                                         _noise_seed_x,
                                         _noise_seed_y, 0.0)
    else:
        _class_bytes = bytes([
            size_code & 0xFF,
            _atmType_resolved,
            _atmDens_resolved,
            _water_resolved,
        ])
        try:
            if terrain is not None and len(terrain) == 6:
                _tf = tuple(terrain)
            else:
                _tf = real.create_terrain_data(
                    AuDice(seed=(auid_seed & 0xFFFFFFFF) or 1),
                    int(size_code), int(_water_resolved),
                    zone_count=(3 if int(size_code) > 2 else 1))
            _class_floats = struct.pack(">ffffff", *_tf)
        except Exception as _twerr:
            logger.warning(f"[terrain] worldgen_real unavailable ({_twerr!r})")
            _class_floats = struct.pack(">ffffff",
                                         float(max(size_code, 2)),
                                         2.26, 0.65,
                                         _noise_seed_x,
                                         _noise_seed_y,
                                         _water_sq)
    try:
        logger.debug(f"[wg-wire] {diag_label or name_str!r} kind={kind}"
                     f" flag=0x{_wg_flag:02x}"
                     f" class_bytes={_class_bytes.hex()}"
                     f" (atmType={_atmType_resolved}"
                     f" atmDens={_atmDens_resolved}"
                     f" water={_water_resolved})"
                     f" in=({size_byte_b1},{size_byte_b2},{size_byte_b3})"
                     f" atm_done={_atm_done}"
                     f" floats={len(_class_floats)//4}"
                     f" body={len(_class_bytes)+len(_class_floats)}B")
    except Exception as _wgw:
        logger.debug(f"[wg-wire] diag failed: {_wgw!r}")
    _wg_prefix = (
        bytes([0x01])
        + bytes([zone & 0xFF])
        + struct.pack(">d", float(orbit_au))
        + struct.pack(">I", len(_n_utf16))
        + _n_utf16
        + bytes([_wg_flag])
        + _class_bytes
        + _class_floats
    )
    _wg_suffix = _dna_bytes + _flora_bytes + _home_bytes
    try:
        wg_geo_parts[int(auid_seed) & 0xFFFFFFFF] = {
            "prefix": _wg_prefix,
            "base_geo": _geo_base,
            "suffix": _wg_suffix,
            "lite": bool(lite),
        }
    except Exception as _wgp_exc:
        logger.debug(f"[wg-geo] parts cache skipped: {_wgp_exc!r}")
    return (
        bytes([0x01])
        + bytes([zone & 0xFF])
        + struct.pack(">d", float(orbit_au))
        + struct.pack(">I", len(_n_utf16))
        + _n_utf16
        + bytes([_wg_flag])
        + _class_bytes
        + _class_floats
        + _geo_bytes
        + _dna_bytes
        + _flora_bytes
        + _home_bytes
    )
