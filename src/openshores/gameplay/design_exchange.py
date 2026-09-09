
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.gear_slots import _add_gear_item
from openshores.protocol.atoms.design_exchange import (
    ITEM_TYPECODE_STORAGE_MEDIA,
    storage_media_body,
)

logger = get_logger(__name__)


def grant_blueprint_disk(session, bd_entries, cid=200, quality=100):
    gear = session.augear
    body = storage_media_body(bd_entries=bd_entries, cid=cid, quality=quality)
    st, _sub = _add_gear_item(gear, ITEM_TYPECODE_STORAGE_MEDIA, body)
    if st is None:
        logger.warning('No gear slot free for a data disk carrying %d blueprint(s).', len(bd_entries))
        return False
    logger.debug("Granted a data disk, cid %d, carrying %d blueprint(s) "
                 "(typeId 0x16, body %dB).", cid, len(bd_entries), len(body))
    return True
