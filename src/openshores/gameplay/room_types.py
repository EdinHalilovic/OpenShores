
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import gd_tables as _gd
from openshores.protocol.dn_room_type import build_scene_dn_room_type_0x30

logger = get_logger(__name__)


def build_scene_dn_room_type(room_id: int = 0,
                              name: str = "",
                              description: str = "") -> bytes:
    rooms = _gd.load_room_types()
    if 0 <= int(room_id) < len(rooms):
        r = rooms[int(room_id)]
        return build_scene_dn_room_type_0x30(
            r.type_id, r.sc_header, r.sc_subtitle, r.bd_header, r.bd_subtitle)
    return build_scene_dn_room_type_0x30(
        room_id, name, description, name, description)


_DN_ROOM_TYPE_PLACEHOLDERS: tuple = tuple(
    (
        f"Room {i:02d}",
        f"the room {i:02d}",
        f"Room {i:02d}",
        f"the room {i:02d}",
    )
    for i in range(25)
)


def build_scene_all_dn_room_types_0x30() -> list:
    rooms = _gd.load_room_types()
    if rooms:
        return [bytes([0x30]) + r.raw for r in rooms]
    logger.warning('GD room-type table unavailable.')
    return [build_scene_dn_room_type_0x30(i, sch, scs, bdh, bds)
            for i, (sch, scs, bdh, bds)
            in enumerate(_DN_ROOM_TYPE_PLACEHOLDERS)]
