
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import gd_tables as _gd
from openshores.protocol.dn_detail_type import (
    _build_dn_detail_type_frame,
    build_scene_dn_detail_type_0x2f,
)

logger = get_logger(__name__)


def build_scene_dn_detail_type(type_id: int = 0,
                                name: str = "",
                                description: str = "") -> bytes:
    details = _gd.load_detail_types()
    if 0 <= int(type_id) < len(details):
        return build_scene_dn_detail_type_0x2f(details[int(type_id)])
    return _build_dn_detail_type_frame(type_id, name, description,
                                       name, description, bytes(8))


def build_scene_all_dn_detail_types_0x2f() -> list:
    details = _gd.load_detail_types()
    if not details:
        logger.warning("[detailtype] GD detail-type table unavailable; "
                       "not streaming 0x2F")
        return []
    return [build_scene_dn_detail_type_0x2f(d) for d in details]
