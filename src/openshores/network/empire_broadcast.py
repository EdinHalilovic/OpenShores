
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import empire_for_avatar
from openshores.gameplay.empire.dg_empire import build_scene_dg_empire_0x31
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


async def broadcast_dg_empire_to_members(empire_id: int,
                                         reason: str = "citizen-add",
                                         quiet: bool = False, *,
                                         _live_avatars, conn,
                                         name_long,
                                         name_short,
                                         capital_name,
                                         _CITIZEN_EMPIRE_OVERRIDE,
                                         _EMPIRE_NAME_OVERRIDE,
                                         _EMPIRE_TAX_OVERRIDE) -> int:
    if not empire_id:
        return 0
    sent = 0
    for _peer_auid, _peer_entry in list(_live_avatars.items()):
        try:
            _w = _peer_entry.get("writer") if isinstance(_peer_entry, dict) else None
            if _w is None or _w.is_closing():
                continue
            _peer_emp = await empire_for_avatar(
                conn, int(_peer_auid),
                _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
            if int(_peer_emp) != int(empire_id):
                continue
            _pkt = await build_scene_dg_empire_0x31(
                conn,
                last_flag=True,
                player_avatar_id=int(_peer_auid),
                empire_id=int(empire_id),
                emperor_auid=None,
                name_long=name_long, name_short=name_short,
                capital_name=capital_name,
                _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
                _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
                _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
            await write_framed(_w, _pkt)
            sent += 1
            if not quiet:
                logger.debug("%s: -> peer 0x%08x empire=%s (%dB)",
                             reason, int(_peer_auid), empire_id, len(_pkt))
        except Exception as _bex:
            logger.warning("%s: peer 0x%08x failed: %r",
                           reason, int(_peer_auid), _bex)
    if sent == 0 and not quiet:
        logger.debug("%s: no online citizens of empire %s (nothing to push)",
                     reason, empire_id)
    return sent
