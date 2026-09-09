
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.protocol.auid import _as_auid
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


_SCENE_GUARD_LOGGED: set = set()


async def _broadcast_to_peers(packet: bytes, live_avatars: dict, *,
                              parent_auid=None, label: str = "atom") -> int:
    sent = 0
    want = _as_auid(parent_auid) if parent_auid is not None else None
    for _pauid, _pe in list((live_avatars or {}).items()):
        _pw = _pe.get("writer")
        if _pw is None or _pw.is_closing():
            continue
        if want is not None:
            _have = _as_auid(_pe.get("parent_world"))
            if _have != want:
                _key = (want, _as_auid(_pauid), _have)
                if _key not in _SCENE_GUARD_LOGGED:
                    _SCENE_GUARD_LOGGED.add(_key)
                    logger.info(
                        "%s withheld from peer 0x%08x: that peer is on world "
                        "0x%08x and the atom's parent is 0x%08x, so sending "
                        "it would orphan the atom and crash the client.",
                        label, _as_auid(_pauid), _have, want)
                continue
        try:
            await write_framed(_pw, packet)
            sent += 1
        except Exception as exc:
            logger.debug("Peer 0x%08x did not take the %s packet: %s",
                         _as_auid(_pauid), label, exc)
    return sent


_MANIFEST_SUPPRESS: set = set()


async def _force_scene_manifest_push(reason: str = "", *,
                                     _live_avatars: dict) -> int:
    sent = 0
    for _auid, _peer in list(_live_avatars.items()):
        w = _peer.get("writer") if isinstance(_peer, dict) else None
        if w is None or w.is_closing():
            continue
        builder = getattr(w, "_scene_manifest_builder", None)
        if builder is None:
            continue
        try:
            await write_framed(w, builder())
            sent += 1
        except Exception as exc:
            logger.debug("[manifest] forced push to 0x%08x failed: %r",
                         _auid, exc)
    if sent:
        logger.info("[manifest] forced re-emit to %d client(s)%s",
                    sent, f" -- {reason}" if reason else "")
    return sent
