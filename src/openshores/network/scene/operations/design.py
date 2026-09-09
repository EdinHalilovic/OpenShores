
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.dispatch import register
from openshores.gameplay.room_types import build_scene_dn_room_type
from openshores.protocol.framing import write_framed
from openshores.protocol.stream import QDS

logger = get_logger(__name__)


@register(0x39)
async def handle_0x39_design_request(session, payload: bytes) -> None:
    s = QDS(payload)
    s.read_u8()

    design_id = 0
    req_flag = None
    try:
        design_id = s.read_u32()
    except Exception as exc:                            # noqa: BLE001
        logger.debug('0x39 DesignRequest carried no design id (%r).', exc)
    try:
        req_flag = s.read_u8()
    except Exception as exc:                            # noqa: BLE001
        logger.debug('0x39 DesignRequest carried no flag byte (%r).', exc)

    logger.debug("0x39 DesignRequest for design 0x%08x, flag %s.",
                 design_id, req_flag)

    _dr = build_scene_dn_room_type(
        room_id=design_id,
        name="Hall",
        description="",
    )
    await write_framed(session.writer, _dr)
    logger.debug("Replied 0x30 DnRoomType for room 0x%08x, %d bytes.",
                 design_id, len(_dr))
