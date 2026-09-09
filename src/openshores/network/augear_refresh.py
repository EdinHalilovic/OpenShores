
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.protocol.atoms.gear import _pack_au_gear
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


async def _push_augear_refresh_for(avatar_auid: int,
                                   log_prefix: str = "weapon", *,
                                   _live_avatars, _AUGEAR_STATES,
                                   _build_augear_only_daperson_update) -> None:
    try:
        _auid_int = int(avatar_auid) & 0xFFFFFFFF
        _entry = _live_avatars.get(_auid_int)
        if _entry is None:
            logger.debug(f'[{log_prefix}]   AuGear refresh: no live entry for actor=0x{_auid_int:08x} (was variant-B pre-register.')
            return
        _writer = _entry.get("writer")
        _auid_bytes = _entry.get("AP") or _auid_int.to_bytes(4, "big")
        if _writer is None or not _auid_bytes:
            return
        if hasattr(_writer, "is_closing") and _writer.is_closing():
            return
        state = _AUGEAR_STATES.get(_auid_int)
        if state is None:
            return
        aug = _pack_au_gear(state)
        pkt = _build_augear_only_daperson_update(_auid_bytes, aug)
        await write_framed(_writer, pkt)
        logger.debug(f"[{log_prefix}]   -> AuGear refresh ({len(aug)}B) sent "
                     f"actor=0x{_auid_int:08x}")
    except Exception as exc:                            # noqa: BLE001
        logger.warning(f"[{log_prefix}]   AuGear refresh failed: {exc!r}")
