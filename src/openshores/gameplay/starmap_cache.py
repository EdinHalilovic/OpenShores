
from __future__ import annotations

from typing import Optional

from openshores.core.logging import get_logger
from openshores.protocol.starmap import build_from_save, encode_star_map_data

logger = get_logger(__name__)


_STARMAP_BLOB: Optional[bytes] = None


def _get_starmap_blob(*, save) -> bytes:
    global _STARMAP_BLOB
    if _STARMAP_BLOB is not None:
        return _STARMAP_BLOB
    sectors = build_from_save(save)
    _STARMAP_BLOB = encode_star_map_data(sectors)
    n_sys = sum(len(s.systems) for s in sectors)
    logger.info(f"[starmap] built {len(sectors)} sectors / {n_sys} systems "
                f"-> {len(_STARMAP_BLOB)} bytes")
    return _STARMAP_BLOB
