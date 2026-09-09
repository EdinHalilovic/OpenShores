
from __future__ import annotations

from openshores.core.logging import get_logger

logger = get_logger(__name__)

_scene_connect_n = 0
_variant_b_handled: bool = False
_force_closed_once: bool = False

def _force_closed_once_get(peer_host: str, *,
                           force_closed_once_by_ip: dict) -> bool:
    if peer_host:
        return bool(force_closed_once_by_ip.get(peer_host, False))
    return _force_closed_once

def _force_closed_once_set(peer_host: str, value: bool, *,
                           force_closed_once_by_ip: dict) -> None:
    global _force_closed_once
    if peer_host:
        force_closed_once_by_ip[peer_host] = bool(value)
    _force_closed_once = bool(value)

def _scene_connect_n_get(peer_host: str, *,
                         scene_connect_n_by_ip: dict) -> int:
    if peer_host:
        return int(scene_connect_n_by_ip.get(peer_host, 0))
    return _scene_connect_n

def _scene_connect_n_inc(peer_host: str, *,
                         scene_connect_n_by_ip: dict) -> int:
    global _scene_connect_n
    if peer_host:
        cur = int(scene_connect_n_by_ip.get(peer_host, 0))
        scene_connect_n_by_ip[peer_host] = cur + 1
        _scene_connect_n = cur + 1
        return cur
    cur = _scene_connect_n
    _scene_connect_n += 1
    return cur

def _scene_connect_n_dec(peer_host: str, *,
                         scene_connect_n_by_ip: dict) -> None:
    global _scene_connect_n
    if peer_host:
        cur = int(scene_connect_n_by_ip.get(peer_host, 0))
        if cur > 0:
            scene_connect_n_by_ip[peer_host] = cur - 1
    if _scene_connect_n > 0:
        _scene_connect_n -= 1

def _variant_b_handled_get(peer_host: str, *,
                           variant_b_handled_by_ip: dict) -> bool:
    if peer_host:
        return bool(variant_b_handled_by_ip.get(peer_host, False))
    return _variant_b_handled

def _variant_b_handled_set(peer_host: str, value: bool, *,
                           variant_b_handled_by_ip: dict) -> None:
    global _variant_b_handled
    if peer_host:
        variant_b_handled_by_ip[peer_host] = bool(value)
    _variant_b_handled = bool(value)

def _ip_has_live_scene(live_avatars: dict, peer_host: str) -> bool:
    if not peer_host:
        return False
    for _e in live_avatars.values():
        if not isinstance(_e, dict):
            continue
        _ra = _e.get("remote_addr")
        if (_ra and isinstance(_ra, tuple)
                and _ra[0] == peer_host):
            return True
    return False

def _reset_session_state_for_ip(peer_host: str, *,
                                scene_connect_n_by_ip: dict,
                                variant_b_handled_by_ip: dict,
                                force_closed_once_by_ip: dict) -> None:
    if not peer_host:
        return
    scene_connect_n_by_ip.pop(peer_host, None)
    variant_b_handled_by_ip.pop(peer_host, None)
    force_closed_once_by_ip.pop(peer_host, None)
    logger.info("Per-IP scene state reset for %r.", peer_host)
