
from __future__ import annotations

from openshores.core.logging import get_logger

logger = get_logger(__name__)


def _ring_ref_section_auid(save) -> int:
    try:
        if getattr(save, "planet_kind", "") == "ring_section" \
                and int(getattr(save, "planet_section_index", 0)) == 0:
            return int(save.planet_auid)
        for rs in (getattr(save, "sibling_globes", None) or []):
            if getattr(rs, "class_kind", "") != "ring_section":
                continue
            if int(getattr(rs, "section_index", -1)) == 0:
                return int(rs.auid)
    except Exception as exc:
        logger.warning(
            'Ring reference section lookup failed (%r).', exc)
    return 0
