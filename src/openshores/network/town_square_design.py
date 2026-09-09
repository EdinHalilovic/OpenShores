
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.protocol.atoms.building import (
    TOWN_SQUARE_DESIGN_ID,
    build_town_square_design,
)
from openshores.protocol.framing import write_framed
from openshores.protocol.stream import QDS
from openshores.world.chat_writer import _chat_only_writer

logger = get_logger(__name__)


async def serve_town_square_design(writer, design_id: int = TOWN_SQUARE_DESIGN_ID):
    detail, room, header = build_town_square_design(design_id)
    await write_framed(writer, bytes([0x24]) + detail)
    await write_framed(writer, bytes([0x39]) + room)
    await write_framed(writer, bytes([0x22]) + header)
    await write_framed(writer, bytes([0x22]) + header)
    logger.debug("Served town-square design 0x%08x: detail %dB, room %dB, "
                 "header %dB twice.", design_id, len(detail), len(room),
                 len(header))


async def on_building_design_request(payload: bytes, actor: int, *,
                                     live_avatars: dict,
                                     _ACTIVE_CHAT_WRITER) -> None:
    s = QDS(payload)
    s.read_u8()
    try:
        design_id = s.read_u32()
    except Exception:
        logger.warning('A 0x22 BuildingDesign request from 0x%08x is too short to carry a design id.', actor)
        return
    logger.debug("0x22 BuildingDesign request id=0x%08x actor=0x%08x.",
                 design_id, actor)
    if design_id != (TOWN_SQUARE_DESIGN_ID & 0xFFFFFFFF):
        return
    writer = None
    ent = live_avatars.get(int(actor) & 0xFFFFFFFF)
    if ent:
        writer = _chat_only_writer(ent)
    if writer is None:
        writer = _ACTIVE_CHAT_WRITER
    if writer is None:
        logger.warning('No chat writer for 0x%08x, which asked for the town-square design.', actor)
        return
    try:
        await serve_town_square_design(writer, design_id)
    except Exception:
        logger.exception("Serving the town-square design to 0x%08x failed.",
                         actor)


async def serve_to_all_peers(design_id: int = TOWN_SQUARE_DESIGN_ID, *,
                             live_avatars: dict) -> int:
    served = 0
    for peer_auid, ent in list(live_avatars.items()):
        w = _chat_only_writer(ent)
        if w is None:
            logger.debug('Peer 0x%08x has no chat writer bound.',
                         peer_auid)
            continue
        if w.is_closing():
            continue
        try:
            await serve_town_square_design(w, design_id)
            served += 1
        except Exception:
            logger.warning("Town-square design not pushed to peer 0x%08x.",
                           peer_auid, exc_info=True)
    return served
