
from __future__ import annotations

from openshores.core.logging import get_logger

logger = get_logger(__name__)


def _actor_from_udp_addr(addr, fallback_sid=0, *, _live_avatars,
                         _UDP_RESOLVE_LOGGED):
    if not addr or not isinstance(addr, tuple):
        return int(fallback_sid) & 0xFFFFFFFF
    host = addr[0]
    matches = []
    try:
        for auid, entry in _live_avatars.items():
            ra = entry.get("remote_addr") if isinstance(entry, dict) else None
            if ra and isinstance(ra, tuple) and ra[0] == host:
                matches.append(int(auid) & 0xFFFFFFFF)
    except Exception as exc:
        logger.debug("Host scan for %r stopped early: %r", host, exc)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        sid = int(fallback_sid) & 0xFFFFFFFF
        if sid in matches:
            return sid
        logger.warning("WARN multiple live avatars on host %r: %s. Sid 0x%08x not in set, defaulting to first",
                       host, [hex(a) for a in matches], sid)
        return matches[0]

    sid = int(fallback_sid) & 0xFFFFFFFF
    try:
        if sid in _live_avatars:
            return sid
        live = [int(a) & 0xFFFFFFFF for a in _live_avatars]
        if len(live) == 1:
            _k = (host, sid, live[0])
            if _k not in _UDP_RESOLVE_LOGGED:
                _UDP_RESOLVE_LOGGED.add(_k)
                logger.info("Host %r unmatched and sid 0x%08x is not live; using the only live avatar 0x%08x (silencing repeats)", host, sid, live[0])
            return live[0]
        if live:
            logger.warning("Host %r unmatched, sid 0x%08x not live, and %d avatars online.", host, sid, len(live))
    except Exception as exc:
        logger.debug("Fallback resolution for %r stopped early: %r", host, exc)
    return sid
