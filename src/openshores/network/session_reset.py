
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.network import connection_state as _connection_state
from openshores.network import peer_ip_state as _peer_ip_state
from openshores.network.connection_state import (
    _CREATE_IN_FLIGHT_TTL_SEC,
    _create_in_flight_end,
    _init_ack_event,
)

logger = get_logger(__name__)

_session_username: str = ""


def _signal_init_ack(auid: int) -> None:
    try:
        auid = int(auid) & 0xFFFFFFFF
    except Exception:
        logger.debug("Init-ack signal ignored a bad auid %r", auid)
        return
    if not auid:
        return
    ev = _init_ack_event(auid)
    if not ev.is_set():
        ev.set()
        logger.info('[scene]   client ACKed 0x2A for avatar 0x%08x (chat 0x0B from App::InitSucceeded).',
                    auid)


def _create_in_flight_active() -> bool:
    if not _connection_state._create_in_flight:
        return False
    import time as _t
    if _t.monotonic() > _connection_state._create_in_flight_until:
        logger.warning('[scene]   create-in-flight marker EXPIRED (%.0fs with no variant B).',
                       _CREATE_IN_FLIGHT_TTL_SEC)
        _create_in_flight_end()
        return False
    return True


def _reset_session_state(live_avatars: dict) -> None:
    if live_avatars:
        logger.info("[login] session reset: suppressed legacy-global reset (%d live avatar(s) still active.", len(live_avatars))
        return
    global _session_username
    _peer_ip_state._scene_connect_n = 0
    _peer_ip_state._variant_b_handled = False
    _peer_ip_state._force_closed_once = False
    _session_username = ""
    _create_in_flight_end("fresh login, no live avatars")
    logger.info('[login]   session reset: scene_conn_n=0, variant_b=False, force_closed_once=False (legacy globals.')
