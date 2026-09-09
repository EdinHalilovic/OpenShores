
from __future__ import annotations

import asyncio
import time

from openshores.core.config import Deployment
from openshores.core.logging import get_logger
from openshores.database.pool import Error, connect

logger = get_logger(__name__)


_TRIM_EVERY = 25

_DDL = """
CREATE TABLE IF NOT EXISTS hz_chat_log (
    id          INTEGER PRIMARY KEY,
    ts          INTEGER NOT NULL,   -- unix ms, same basis as a_Person.timeModified
    channel     TEXT    NOT NULL,
    sender_auid INTEGER NOT NULL,
    sender_name TEXT    NOT NULL,
    text        TEXT    NOT NULL
);
"""

_since_trim = 0

_INFLIGHT: set[asyncio.Task] = set()


def enabled(deployment: Deployment | None = None) -> bool:
    d = Deployment.from_env() if deployment is None else deployment
    return d.chat_log


def channels(deployment: Deployment | None = None) -> frozenset:
    d = Deployment.from_env() if deployment is None else deployment
    raw = d.chat_log_channels
    return frozenset(c.strip() for c in raw.split(",") if c.strip())


def keep(deployment: Deployment | None = None) -> int:
    d = Deployment.from_env() if deployment is None else deployment
    return max(1, d.chat_log_keep)


async def _trim(conn, *, deployment: Deployment | None = None) -> None:
    await conn.execute(
        'DELETE FROM "hz_chat_log" '
        'WHERE "id" <= (SELECT MAX("id") FROM "hz_chat_log") - $1',
        keep(deployment))


async def record(conn, channel, sender_auid, sender_name, text, ts_ms=None,
                 *, deployment: Deployment | None = None) -> bool:
    global _since_trim
    if not enabled(deployment):
        return False
    text = (text or "").strip()
    if not text:
        return False
    if channel not in channels(deployment):
        return False
    try:
        async with conn.transaction():
            await conn.execute(
                'INSERT INTO "hz_chat_log" '
                '("ts", "channel", "sender_auid", "sender_name", "text") '
                'VALUES ($1, $2, $3, $4, $5)',
                int(ts_ms if ts_ms is not None else time.time() * 1000),
                str(channel),
                int(sender_auid or 0) & 0xFFFFFFFF,
                str(sender_name or "Unknown")[:64],
                text[:512])
            _since_trim += 1
            if _since_trim >= _TRIM_EVERY:
                _since_trim = 0
                await _trim(conn, deployment=deployment)
    except Error as exc:
        logger.warning("Chat line not recorded for the web panel: %r", exc)
        return False
    return True


async def _record_via_pool(pool, channel, sender_auid, sender_name, text,
                           ts_ms, deployment) -> None:
    try:
        async with pool.acquire() as conn:
            await record(conn, channel, sender_auid, sender_name, text, ts_ms,
                         deployment=deployment)
    except Error as exc:
        logger.warning("Chat line not recorded for the web panel: %r", exc)


def record_soon(pool, channel, sender_auid, sender_name, text, ts_ms=None,
                *, deployment: Deployment | None = None) -> None:
    if not enabled(deployment):
        return
    text = (text or "").strip()
    if not text or channel not in channels(deployment):
        return
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error('Chat line not recorded: record_soon needs a running event loop.')
        return
    task = loop.create_task(
        _record_via_pool(pool, channel, sender_auid, sender_name, text, ts_ms,
                         deployment))
    _INFLIGHT.add(task)
    task.add_done_callback(_INFLIGHT.discard)


async def recent(conn, limit: int = 30) -> list:
    limit = max(1, min(int(limit or 30), 500))
    try:
        rows = await conn.fetch(
            'SELECT "id", "ts", "channel", "sender_name", "text" '
            'FROM "hz_chat_log" ORDER BY "id" DESC LIMIT $1', limit)
    except Error as exc:
        logger.warning("Chat history unavailable: %r", exc)
        return []
    return [{"id": int(rid), "ts": int(ts or 0), "channel": ch or "",
             "name": name or "", "text": txt or ""}
            for rid, ts, ch, name, txt in reversed(rows)]


async def count(conn, speaker: str = None) -> int:
    clause, params = ("TRUE", ())
    if speaker is not None:
        clause, params = ('lower("sender_name") = lower($1)',
                          (speaker.strip(),))
    try:
        return int(await conn.fetchval(
            'SELECT COUNT(*) FROM "hz_chat_log" WHERE ' + clause, *params))
    except Error as exc:
        logger.warning("Chat history count failed: %r", exc)
        return -1


async def _delete_where(conn, clause: str, params: tuple) -> int:
    try:
        status = await conn.execute(
            'DELETE FROM "hz_chat_log" WHERE ' + clause, *params)
    except Error as exc:
        logger.warning("Chat history delete failed: %r", exc)
        return -1
    return int(status.split()[-1])


async def delete(conn, *ids) -> int:
    ids = tuple(int(i) for i in ids)
    if not ids:
        return 0
    marks = ",".join("$%d" % i for i in range(1, len(ids) + 1))
    return await _delete_where(conn, '"id" IN (%s)' % marks, ids)


async def delete_by_speaker(conn, name: str) -> int:
    if not (name or "").strip():
        return 0
    return await _delete_where(conn, 'lower("sender_name") = lower($1)',
                               (name.strip(),))


async def clear(conn) -> int:
    return await _delete_where(conn, "TRUE", ())


_USAGE = """\
chat_log.py -- galactic chat history

  list [N]             show the last N lines (default 30), with their ids
  delete ID [ID...]    remove specific lines
  purge NAME           remove every line from one speaker
  clear                remove the whole history

purge and clear need --yes as well; neither is recoverable.

Removing a line only affects the website. It was already delivered to whoever
was connected when it was said. The site picks the change up within a couple
of seconds -- no restart, on either process.
"""


def _print_rows(rows):
    if not rows:
        logger.info('(empty.')
        return
    for r in rows:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S",
                              time.localtime(r["ts"] / 1000.0))
        logger.info("%6d  %s  [%s] %s: %s"
                    % (r["id"], stamp, r["channel"], r["name"], r["text"]))


async def _main(argv) -> int:
    args = [a for a in argv if a != "--yes"]
    confirmed = "--yes" in argv
    cmd = args[0] if args else "list"

    if cmd.isdigit():
        args, cmd = ["list", cmd], "list"

    if cmd in ("-h", "--help", "help"):
        logger.info(_USAGE)
        return 0

    pool = await connect()
    async with pool.acquire() as conn:
        if cmd == "list":
            n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 30
            _print_rows(await recent(conn, n))
            return 0

        if cmd == "delete":
            ids = [a for a in args[1:] if a.lstrip("-").isdigit()]
            if not ids:
                logger.info("Delete needs at least one id. Run `list` to find them")
                return 2
            n = await delete(conn, *ids)
            logger.info("deleted %d line(s)" % n if n >= 0 else "no database")
            return 0 if n >= 0 else 1

        if cmd == "purge":
            if len(args) < 2:
                logger.info("Purge needs a speaker name")
                return 2
            name = args[1]
            if not confirmed:
                logger.info("Would remove %d line(s) from %r. Re-run with --yes." % (await count(conn, name), name))
                return 1
            n = await delete_by_speaker(conn, name)
            logger.info("deleted %d line(s) from %r" % (n, name)
                        if n >= 0 else "no database")
            return 0 if n >= 0 else 1

        if cmd == "clear":
            if not confirmed:
                logger.info("Would remove the entire history (%d line(s)). Re-run with --yes." % await count(conn))
                return 1
            n = await clear(conn)
            logger.info("deleted %d line(s)" % n if n >= 0 else "no database")
            return 0 if n >= 0 else 1

        logger.info(_USAGE)
        return 2


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(_main(sys.argv[1:])))
