
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.network.peer_ip_state import _ip_has_live_scene

logger = get_logger(__name__)

_INIT_ACK_EVENTS: dict = {}

_create_in_flight: bool = False
_create_in_flight_until: float = 0.0
_create_defer_replayed: bool = False
_create_person_auid_atom: bytes = b""
_create_autime_ms: int = 0
_create_defer_echo_world: int = 0


def _init_ack_event(auid: int):
    auid = int(auid) & 0xFFFFFFFF
    ev = _INIT_ACK_EVENTS.get(auid)
    if ev is None:
        ev = asyncio.Event()
        _INIT_ACK_EVENTS[auid] = ev
    return ev


def _clear_init_ack(auid: int) -> None:
    try:
        _INIT_ACK_EVENTS.pop(int(auid) & 0xFFFFFFFF, None)
    except Exception:
        logger.debug("Init-ack clear ignored a bad auid %r", auid)


_CREATE_IN_FLIGHT_TTL_SEC = 900.0


def _create_in_flight_begin() -> None:
    global _create_in_flight, _create_in_flight_until, _create_defer_replayed
    import time as _t
    _create_in_flight = True
    _create_in_flight_until = _t.monotonic() + _CREATE_IN_FLIGHT_TTL_SEC
    _create_defer_replayed = False


def _create_in_flight_end(reason: str = "") -> None:
    global _create_in_flight, _create_in_flight_until
    global _create_defer_replayed, _create_person_auid_atom
    global _create_defer_echo_world, _create_autime_ms
    was = _create_in_flight
    _create_in_flight = False
    _create_in_flight_until = 0.0
    _create_defer_replayed = False
    _create_person_auid_atom = b""
    _create_defer_echo_world = 0
    _create_autime_ms = 0
    if was and reason:
        logger.info("[scene]   create-in-flight cleared (%s)", reason)


def _conn0_hold_reason(decision: str, *,
                       conn0_hold_reasons: dict) -> str:
    return conn0_hold_reasons.get(decision, decision)


def _cleanup_ip_state_if_idle(live_avatars: dict, peer_host: str, *,
                              scene_connect_n_by_ip: dict,
                              variant_b_handled_by_ip: dict,
                              force_closed_once_by_ip: dict,
                              session_usernames_by_ip: dict) -> None:
    if not peer_host:
        return
    if _ip_has_live_scene(live_avatars, peer_host):
        return
    pruned = []
    if peer_host in scene_connect_n_by_ip:
        scene_connect_n_by_ip.pop(peer_host, None)
        pruned.append("scene_connect_n")
    if peer_host in variant_b_handled_by_ip:
        variant_b_handled_by_ip.pop(peer_host, None)
        pruned.append("variant_b_handled")
    if peer_host in force_closed_once_by_ip:
        force_closed_once_by_ip.pop(peer_host, None)
        pruned.append("force_closed_once")
    if peer_host in session_usernames_by_ip:
        session_usernames_by_ip.pop(peer_host, None)
        pruned.append("session_username")
    if pruned:
        logger.info("[cleanup] pruned per-IP state for %r: %s",
                    peer_host, pruned)
