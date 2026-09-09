
from __future__ import annotations

from openshores.world.session import Session


def attach_to_live_avatars(live_avatars: dict, session: Session) -> None:
    if session.player_auid == 0:
        return
    entry = live_avatars.setdefault(session.player_auid, {})
    entry["session"] = session


def session_for_auid(live_avatars: dict, auid: int):
    entry = live_avatars.get(int(auid))
    if not isinstance(entry, dict):
        return None
    sess = entry.get("session")
    return sess if isinstance(sess, Session) else None


def session_for_writer(live_avatars: dict, writer):
    for entry in live_avatars.values():
        if not isinstance(entry, dict):
            continue
        sess = entry.get("session")
        if isinstance(sess, Session) and sess.writer is writer:
            return sess
    return None


def detach_from_live_avatars(live_avatars: dict, session: Session) -> None:
    if session.player_auid == 0:
        return
    entry = live_avatars.get(session.player_auid)
    if isinstance(entry, dict) and entry.get("session") is session:
        entry.pop("session", None)
        if not entry:
            live_avatars.pop(session.player_auid, None)
