
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.city_model import merge_roads_into_geo_payload
from openshores.network.broadcast import _broadcast_to_peers

logger = get_logger(__name__)

_WG_GEO_PARTS: dict = {}
_WG_ATOM_HDR: dict = {}


async def resend_planet_geo(planet_auid: int = 0, reason: str = "", *,
                            _SAVE, live_avatars,
                            gather_planet_roads):
    try:
        pa = int(planet_auid or _SAVE.planet_auid) & 0xFFFFFFFF
    except Exception as exc:
        logger.debug("[wg-geo] re-emit target not an AuId: %r", exc)
        return 0
    parts = _WG_GEO_PARTS.get(pa)
    hdr = _WG_ATOM_HDR.get(pa)
    if not parts or not hdr:
        return 0
    if parts.get("lite") or not parts.get("base_geo"):
        return 0
    try:
        roads = await gather_planet_roads(pa)
        geo = merge_roads_into_geo_payload(parts["base_geo"], roads)
        pkt = hdr + parts["prefix"] + geo + parts["suffix"] + b"\x00" * 16
    except Exception as exc:
        logger.warning(f"[wg-geo] re-emit build err: {exc!r}")
        return 0
    try:
        sent = await _broadcast_to_peers(pkt, live_avatars)
    except Exception as exc:
        logger.warning(f"[wg-geo] re-emit broadcast err: {exc!r}")
        return 0
    _uc = sum(1 for r in roads if r.get("under_construction"))
    logger.info(f"[wg-geo] re-emitted planet 0x{pa:08x} geo block "
                f"({parts['base_geo'][0]}->{geo[0]} features, {len(roads)} road(s), "
                f"{_uc} under construction, {len(pkt)}B) -> {sent} peer(s)"
                + (f"  [{reason}]" if reason else ""))
    return sent
