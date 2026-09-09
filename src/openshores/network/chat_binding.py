
from __future__ import annotations

from openshores.core.logging import get_logger

logger = get_logger(__name__)


def _chat_writer_auid(writer, *, live_avatars: dict,
                      _PENDING_CHAT_AUIDS: list):
    if writer is None:
        return 0
    cached = getattr(writer, "_player_auid", None)
    if cached:
        return int(cached)
    if _PENDING_CHAT_AUIDS:
        try:
            chat_peer = writer.get_extra_info("peername")
            chat_host = (chat_peer[0]
                         if isinstance(chat_peer, tuple) else None)
        except Exception:
            chat_host = None
        if chat_host is not None:
            for _i, _candidate in enumerate(list(_PENDING_CHAT_AUIDS)):
                _scene_entry = live_avatars.get(int(_candidate)) or {}
                _scene_w = _scene_entry.get("writer")
                if _scene_w is None:
                    continue
                _existing_cw = _scene_entry.get("chat_writer")
                if _existing_cw is not None and _existing_cw is not writer:
                    _existing_open = False
                    try:
                        _existing_open = not _existing_cw.is_closing()
                    except Exception:                   # noqa: BLE001
                        pass
                    if _existing_open:
                        logger.info(
                            'The chat writer held for 0x%08x is a stale probe.',
                            int(_candidate))
                try:
                    _sp = _scene_w.get_extra_info("peername")
                except Exception:
                    continue
                _scene_host = (_sp[0]
                               if isinstance(_sp, tuple) else None)
                if _scene_host == chat_host:
                    _claim = int(_candidate)
                    _PENDING_CHAT_AUIDS.remove(_candidate)
                    setattr(writer, "_player_auid", _claim)
                    return _claim
    try:
        chat_peer = writer.get_extra_info("peername")
    except Exception:
        return 0
    if not chat_peer:
        return 0
    chat_host = chat_peer[0] if isinstance(chat_peer, tuple) else None
    if chat_host is None:
        return 0
    for _auid, _entry in live_avatars.items():
        _sw = _entry.get("writer")
        if _sw is None or _sw.is_closing():
            continue
        _existing_cw = _entry.get("chat_writer")
        if _existing_cw is not None:
            try:
                if not _existing_cw.is_closing():
                    continue
            except Exception:                       # noqa: BLE001
                pass
        try:
            _sp = _sw.get_extra_info("peername")
        except Exception:
            continue
        if _sp and isinstance(_sp, tuple) and _sp[0] == chat_host:
            setattr(writer, "_player_auid", int(_auid))
            return int(_auid)
    return 0
