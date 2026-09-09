
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.protocol.rng import AuDice

from . import geology

logger = get_logger(__name__)


def _gen_geo_payload(planet_auid: int, size: int = None,
                     atm_density: int = None, water: int = None,
                     terrain=None, orbit_zone: int = 2,
                     is_satellite: bool = False) -> bytes:
    if terrain is None or size is None:
        return bytes([0])
    try:
        gw = geology.GeoWorld(terrain=tuple(terrain), size=int(size),
                              water=int(water or 0) & 0xFF,
                              is_satellite=bool(is_satellite))
        feats = geology.create_geological_features(
            gw, int(orbit_zone), int(atm_density or 0),
            AuDice(seed=(int(planet_auid) ^ 0xFEA7) or 1))
        return geology.encode(feats)
    except Exception as _gerr:
        logger.warning(
            'World 0x%06x: no geological features could be placed (%r).', planet_auid, _gerr)
        return bytes([0])
