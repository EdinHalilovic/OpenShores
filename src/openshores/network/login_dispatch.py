
from __future__ import annotations

from openshores.core import accounts as _accounts
from openshores.core.logging import get_logger
from openshores.protocol.login import build_login_fail_reply
from openshores.protocol.login_reply import build_login_ok_reply_for_avatars

logger = get_logger(__name__)


async def _dispatch_login(conn, req, peer_host: str = "", *,
                          save,
                          session_usernames_by_ip: dict,
                          persons_that_exist,
                          resolve_avatar_record,
                          build_login_ok_reply) -> bytes:
    fallback_user = save.person_name

    store = _accounts.default_store()
    if not store.list_users():
        if not getattr(_dispatch_login, "_warned_empty", False):
            logger.info("[login]   account store is empty; open mode.")
            _dispatch_login._warned_empty = True   # type: ignore[attr-defined]
        logger.info("[login]   reason: empty account store -> legacy open-mode reply")
        return build_login_ok_reply(0, req.username or fallback_user)

    username = req.username or ""
    wire_pw = req.password_hash or b""
    pw_hex = wire_pw.hex()
    if not store.has_user(username):
        logger.warning(f"[login] account {username!r} not found. Sending 0x0b reason=1")
        logger.warning(f"[login]   (wire password bytes were {len(wire_pw)}B: {pw_hex})")
        return build_login_fail_reply(_accounts.REASON_NO_SUCH_ACCOUNT)

    if not store.verify(username, wire_pw):
        logger.warning(f"[login] bad password for {username!r}. Sending 0x0b reason=2")
        logger.warning(f"[login]   wire password was {len(wire_pw)}B: {pw_hex}")
        return build_login_fail_reply(_accounts.REASON_BAD_PASSWORD)

    auids = store.list_avatars(username)
    _live = await persons_that_exist(conn, auids)
    _kept = [a for a in auids if (int(a) & 0xFFFFFFFF) in _live]
    _dropped_dead = [a for a in auids if (int(a) & 0xFFFFFFFF) not in _live]
    if _dropped_dead:
        logger.warning(f"[login]   {username!r}: {len(_dropped_dead)} roster entr"
                       f"{'y' if len(_dropped_dead) == 1 else 'ies'} with no a_Person "
                       f"row, excluded from the slot table: "
                       f"{[hex(int(a) & 0xFFFFFFFF) for a in _dropped_dead]}")
    if len(_kept) > 6:
        logger.warning(f"[login] {username!r} has {len(_kept)} live avatars but the 0x03 reply holds only 6. Dropping the OLDEST: {[hex(int(a) & 4294967295) for a in _kept[:-6]]}.")
        _kept = _kept[-6:]
    avatars: list = [
        await resolve_avatar_record(conn, a) for a in _kept
    ]
    logger.info(f"[login]   {username!r} authenticated; "
                f"{len(avatars)} avatar(s): "
                f"{[(hex(r.auid), r.name) for r in avatars]}")
    if peer_host:
        session_usernames_by_ip[peer_host] = username
        logger.info(f"[login]   session: {username!r} bound to peer "
                    f"host {peer_host!r}")
    else:
        logger.info(f'[login]   _session_username <- {username!r} (no peer host.')

    _active = 0
    return build_login_ok_reply_for_avatars(_active, avatars)
