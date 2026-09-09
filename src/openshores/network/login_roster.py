
from __future__ import annotations

import asyncpg

from openshores.core.accounts import default_store
from openshores.core.logging import get_logger
from openshores.database.repositories.avatar_roster import _persons_that_exist
from openshores.protocol.framing import encode_size
from openshores.protocol.stream import QDS

logger = get_logger(__name__)


async def build_query_avatars_reply(conn: asyncpg.Connection,
                                    peer_host: str = "",
                                    username: str = "", *,
                                    session_usernames_by_ip: dict,
                                    save) -> bytes:
    active_ids: list[int] = []
    inactive_ids: list[int] = []

    if not username and peer_host:
        username = session_usernames_by_ip.get(peer_host, "")
    if username:
        try:
            roster = [int(a) for a in default_store().list_avatars(username)]
        except Exception as exc:
            logger.warning(f"[picker] roster lookup failed for {username!r}: {exc!r}")
            roster = []
        if roster:
            alive = await _persons_that_exist(conn, roster)
            missing = [a for a in roster if a not in alive]
            if missing:
                logger.warning(f"[picker] {username!r}: {len(missing)} roster entries have no a_Person row ({', '.join((f'0x{m:08x}' for m in missing))}).")
            active_ids = [a for a in roster if a in alive]

    if not active_ids:
        active_ids = [int(save.person_auid)]
        logger.info(f"[picker] {username or peer_host or 'unknown'}: no account "
                    f"roster; falling back to the bundle's own avatar "
                    f"0x{int(save.person_auid):08x}")
    else:
        logger.info(f"[picker] {username!r}: {len(active_ids)} avatar(s). {', '.join((f'0x{a:08x}' for a in active_ids))}")

    out = bytearray()
    for tpe, ids in [(0x1B, inactive_ids), (0x1C, active_ids)]:
        body = QDS()
        body.write_u8(tpe)
        body.write_i16(len(ids))
        for auid in ids:
            body.write_i32(auid & 0xFFFFFFFF)
        b = body.getvalue()
        out += encode_size(len(b)) + b
    return bytes(out)
