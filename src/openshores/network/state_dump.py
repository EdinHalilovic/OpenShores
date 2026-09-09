
from __future__ import annotations

import signal as _sig

from openshores.core.logging import get_logger
from openshores.database.repositories.person import _synthetic_auid_map

logger = get_logger(__name__)


def dump_server_state(label: str = "manual", *,
                      _live_avatars: dict,
                      _AUGEAR_STATES: dict,
                      _tock_state: dict,
                      scene_connect_n_by_ip: dict,
                      variant_b_handled_by_ip: dict,
                      force_closed_once_by_ip: dict,
                      session_usernames_by_ip: dict,
                      _DROPPED_ITEMS: dict,
                      _PENDING_CHAT_AUIDS,
                      _WORLD_ATOM_AUIDS) -> None:
    _sm = _synthetic_auid_map
    logger.info(f"\n=== [server-state] dump trigger={label!r} ===")
    logger.info(f"  _live_avatars       ({len(_live_avatars)} entries):")
    for _a, _e in list(_live_avatars.items()):
        if not isinstance(_e, dict):
            continue
        _ra = _e.get("remote_addr")
        _name = _e.get("name", "?")
        _xyz = _e.get("xyz")
        _has_chat = _e.get("chat_writer") is not None
        _wopen = (
            "open"
            if (_e.get("writer") and not _e["writer"].is_closing())
            else "closed")
        logger.info(f"    auid=0x{int(_a):08x} name={_name!r} addr={_ra} "
                    f"xyz={_xyz} writer={_wopen} chat={_has_chat}")
    logger.info(f"  _AUGEAR_STATES      ({len(_AUGEAR_STATES)} entries):")
    for _a, _g in list(_AUGEAR_STATES.items()):
        logger.info(f"    auid=0x{int(_a):08x} slots={len(_g)} "
                    f"items={[(e[0], e[1]) for e in _g]}")
    logger.info(f"  _tock_state         ({len(_tock_state)} entries):")
    for _a, _t in list(_tock_state.items()):
        _bio = {k: _t.get(k) for k in
                ("hp", "max_hp", "hunger", "stamina", "pose")}
        logger.info(f"    auid=0x{int(_a):08x} {_bio}")
    logger.info(f"  _scene_connect_n_by_ip   {dict(scene_connect_n_by_ip)}")
    logger.info(f"  _variant_b_handled_by_ip {dict(variant_b_handled_by_ip)}")
    logger.info(f"  _force_closed_once_by_ip {dict(force_closed_once_by_ip)}")
    logger.info(f"  _session_usernames_by_ip {dict(session_usernames_by_ip)}")
    logger.info(f"  _DROPPED_ITEMS      ({len(_DROPPED_ITEMS)} entries)")
    logger.info(f"  _PENDING_CHAT_AUIDS {[hex(a) for a in _PENDING_CHAT_AUIDS]}")
    logger.info(f"  _WORLD_ATOM_AUIDS   {[hex(a) for a in _WORLD_ATOM_AUIDS]}")
    logger.info(f"  synthetic_auid_map  {dict(_sm)}")
    logger.info("=== [server-state] end dump ===\n")


def _install_dump_state_signal_handler(*, dump_server_state) -> None:
    if hasattr(_sig, "SIGUSR1"):
        try:
            _sig.signal(_sig.SIGUSR1,
                        lambda *_a: dump_server_state(label="SIGUSR1"))
        except Exception as _se:
            logger.warning(f"[boot] dump_state signal handler not "
                           f"registered: {_se!r}")
            return
        logger.info("[boot] SIGUSR1 -> dump_server_state registered "
                    "(send `kill -USR1 <pid>` to dump live state)")
