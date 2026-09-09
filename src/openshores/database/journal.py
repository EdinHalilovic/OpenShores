
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import asyncpg

from openshores.core.logging import get_logger

logger = get_logger(__name__)


MAX_BATCH: int = 64
BATCH_WINDOW_MS: int = 50
SHUTDOWN_GRACE_S: float = 5.0

_OP_DISPATCH: dict[str, Any] = {}


def _build_dispatch(conn: Any, resolve_person_id: Any,
                    session_login_ms: dict) -> dict[str, Any]:


    async def _resolve(auid: int) -> Optional[int]:
        return await resolve_person_id(conn, auid)

    def _now_ms() -> int:
        return int(time.time() * 1000)

    async def op_mark_online(auid: int, perm: int = 5) -> bool:
        rid = await _resolve(auid)
        if rid is None:
            return False
        now = _now_ms()
        await conn.execute(
            'UPDATE "a_Person" SET "isonline" = 1, "timeModified" = $1 '
            'WHERE "id" = $2',
            now, rid)
        session_login_ms[rid] = now
        return True

    async def op_mark_offline(auid: int) -> bool:
        rid = await _resolve(auid)
        if rid is None:
            return False
        await conn.execute(
            'UPDATE "a_Person" SET "isonline" = 0 WHERE "id" = $1', rid)
        return True

    async def op_flush_online_time(auid: int) -> bool:
        rid = await _resolve(auid)
        if rid is None:
            return False
        start_ms = session_login_ms.pop(rid, None)
        if start_ms is None:
            return False
        delta_s = max(0, (_now_ms() - start_ms) // 1000)
        if delta_s == 0:
            return True
        await conn.execute(
            'UPDATE "a_Person" SET "timeOnlineSecs" = "timeOnlineSecs" + $1 '
            'WHERE "id" = $2', int(delta_s), rid)
        return True

    async def op_update_person_state(auid: int, **fields) -> bool:
        if not fields:
            return False
        rid = await _resolve(auid)
        if rid is None:
            return False
        _valid = {row["column_name"] for row in await conn.fetch(
            """SELECT "column_name" FROM "information_schema"."columns"
                WHERE "table_schema" = 'public' AND "table_name" = $1""",
            "a_Person")}
        cols = [k for k in fields if k in _valid]
        if not cols:
            return False
        sets = ", ".join(f'"{c}" = ${n}' for n, c in enumerate(cols, 1))
        vals = [fields[c] for c in cols] + [rid]
        await conn.execute(
            f'UPDATE "a_Person" SET {sets} WHERE "id" = ${len(cols) + 1}',
            *vals)
        return True

    async def op_update_person_position(
            auid: int, x: float, y: float, z: float,
            parent_auid: Optional[int] = None) -> bool:
        rid = await _resolve(auid)
        if rid is None:
            return False
        if parent_auid is None:
            await conn.execute(
                'UPDATE "a_Person" SET "locX" = $1, "locY" = $2, "locZ" = $3 '
                'WHERE "id" = $4', float(x), float(y), float(z), rid)
        else:
            await conn.execute(
                'UPDATE "a_Person" SET "locX" = $1, "locY" = $2, "locZ" = $3, '
                '"idp" = $4 WHERE "id" = $5',
                float(x), float(y), float(z),
                int(parent_auid) & 0xFFFFFFFF, rid)
        return True

    async def op_dropped_item_insert(
            auid: int, parent_auid: int, xyz, rotation,
            type_id: int, body: bytes, time_created_ms: int) -> bool:
        import time as _t
        row = await conn.fetchrow(
            'SELECT "table_name" FROM "information_schema"."tables" '
            'WHERE "table_type" = $1 AND "table_name" = $2',
            'BASE TABLE', 'a_Item')
        if not row:
            return False
        item_blob = bytes([int(type_id) & 0xFF]) + bytes(body)
        await conn.execute(
            'INSERT INTO "a_Item" '
            '("id", "idp", "locX", "locY", "locZ", "rotX", "rotY", "rotZ", '
            ' "timeCreate", "timeModified", "item", "atRest") '
            'VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 1) '
            'ON CONFLICT ("id") DO UPDATE SET '
            '"idp" = EXCLUDED."idp", '
            '"locX" = EXCLUDED."locX", '
            '"locY" = EXCLUDED."locY", '
            '"locZ" = EXCLUDED."locZ", '
            '"rotX" = EXCLUDED."rotX", '
            '"rotY" = EXCLUDED."rotY", '
            '"rotZ" = EXCLUDED."rotZ", '
            '"timeCreate" = EXCLUDED."timeCreate", '
            '"timeModified" = EXCLUDED."timeModified", '
            '"item" = EXCLUDED."item", '
            '"atRest" = EXCLUDED."atRest"',
            int(auid) & 0xFFFFFFFF,
            int(parent_auid) & 0xFFFFFFFF,
            float(xyz[0]), float(xyz[1]), float(xyz[2]),
            float(rotation[0]), float(rotation[1]), float(rotation[2]),
            int(time_created_ms), int(_t.time() * 1000), item_blob)
        return True

    async def op_dropped_item_delete(auid: int) -> bool:
        await conn.execute(
            'DELETE FROM "a_Item" WHERE "id" = $1',
            int(auid) & 0xFFFFFFFF)
        return True

    return {
        "mark_online":            op_mark_online,
        "mark_offline":           op_mark_offline,
        "flush_online_time":      op_flush_online_time,
        "update_person_state":    op_update_person_state,
        "update_person_position": op_update_person_position,
        "dropped_item_insert":    op_dropped_item_insert,
        "dropped_item_delete":    op_dropped_item_delete,
    }


class PersistQueue:

    def __init__(self, pool: Any, resolve_person_id: Any,
                 session_login_ms: dict):
        self._pool = pool
        self._resolve_person_id = resolve_person_id
        self._session_login_ms = session_login_ms
        self._q: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._stop_evt = asyncio.Event()
        self.submitted_total: int = 0
        self.committed_total: int = 0
        self.failed_total: int = 0
        self.batches_total: int = 0
        self.last_batch_size: int = 0
        self.last_batch_dur_ms: float = 0.0

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_evt.clear()
        self._task = asyncio.get_running_loop().create_task(
            self._run(), name="persist-queue")

    async def stop(self, timeout: float = SHUTDOWN_GRACE_S) -> None:
        if self._task is None:
            return
        self._stop_evt.set()
        self._q.put_nowait(("__SHUTDOWN__", (), {}))
        await asyncio.wait({self._task}, timeout=timeout)
        if not self._task.done():
            logger.warning(
                "Persist queue worker did not exit in %ss; %d write(s) are "
                "still queued and will be lost.", timeout, self._q.qsize())
        self._task = None

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def submit(self, op: str, *args, **kwargs) -> bool:
        if not self.is_running():
            return False
        self._q.put_nowait((op, args, kwargs))
        self.submitted_total += 1
        return True

    def depth(self) -> int:
        return self._q.qsize()

    async def _open_conn(self) -> Optional[Any]:
        if self._pool is None:
            logger.error(
                'Persist queue has no database pool.')
            return None
        conn = await self._pool.acquire()
        logger.info(
            "Persist queue worker holding one pooled connection; batching up "
            "to %d op(s) per transaction.", MAX_BATCH)
        return conn

    async def _run(self) -> None:
        conn = await self._open_conn()
        if conn is None:
            while not self._stop_evt.is_set():
                try:
                    await asyncio.wait_for(self._q.get(), timeout=0.5)
                except TimeoutError:
                    continue
            return
        dispatch = _build_dispatch(
            conn, self._resolve_person_id, self._session_login_ms)
        try:
            while True:
                batch = await self._collect_batch()
                if batch is None:
                    break
                if not batch:
                    continue
                await self._apply_batch(conn, dispatch, batch)
        finally:
            await self._pool.release(conn)
            logger.info(
                "Persist queue worker shut down. Committed=%d failed=%d batches=%d", self.committed_total, self.failed_total,
                self.batches_total)

    async def _collect_batch(self) -> Optional[list]:
        first = await self._q.get()
        if first[0] == "__SHUTDOWN__":
            tail = []
            while True:
                try:
                    item = self._q.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if item[0] != "__SHUTDOWN__":
                    tail.append(item)
            if tail:
                return tail
            return None
        batch = [first]
        deadline = time.monotonic() + (BATCH_WINDOW_MS / 1000.0)
        while len(batch) < MAX_BATCH:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                item = await asyncio.wait_for(self._q.get(), timeout=remaining)
            except TimeoutError:
                break
            if item[0] == "__SHUTDOWN__":
                self._stop_evt.set()
                break
            batch.append(item)
        return batch

    async def _apply_batch(self, conn: Any,
                           dispatch: dict, batch: list) -> None:
        t0 = time.monotonic()
        ok = 0
        bad = 0
        try:
            async with conn.transaction():
                for op, args, kwargs in batch:
                    fn = dispatch.get(op)
                    if fn is None:
                        logger.error(
                            "Persist queue dropped an unknown op %r; that "
                            "write is lost.", op)
                        bad += 1
                        continue
                    try:
                        async with conn.transaction():
                            await fn(*args, **kwargs)
                        ok += 1
                    except Exception as exc:
                        bad += 1
                        logger.error("Persist queue op %s failed: %r", op, exc)
                        self._metrics_incr("sql_async_failed", op)
                        self._metrics_incr(
                            "exceptions_total", type(exc).__name__)
            self.committed_total += ok
            self.failed_total += bad
        except (asyncpg.PostgresError, asyncpg.InterfaceError,
                asyncpg.InternalClientError) as exc:
            logger.error(
                "Persist queue batch commit failed: %r; %d op(s) rolled back "
                "and lost.", exc, len(batch))
            self.failed_total += len(batch)
        self.batches_total += 1
        self.last_batch_size = len(batch)
        self.last_batch_dur_ms = (time.monotonic() - t0) * 1000.0

    @staticmethod
    def _metrics_incr(name: str, tag: str) -> None:
        from openshores.core import metrics as _sm
        _sm.incr(name, tag=tag)


_singleton: Optional[PersistQueue] = None


def get_queue() -> Optional[PersistQueue]:
    return _singleton


def start_queue(pool: Any, resolve_person_id: Any,
                session_login_ms: dict) -> Optional[PersistQueue]:
    global _singleton
    if _singleton is not None and _singleton.is_running():
        return _singleton
    _singleton = PersistQueue(
        pool=pool, resolve_person_id=resolve_person_id,
        session_login_ms=session_login_ms)
    _singleton.start()
    logger.info("Persist queue started. MAX_BATCH=%d BATCH_WINDOW_MS=%d",
                MAX_BATCH, BATCH_WINDOW_MS)
    return _singleton


async def stop_queue(timeout: float = SHUTDOWN_GRACE_S) -> None:
    global _singleton
    if _singleton is None:
        return
    await _singleton.stop(timeout=timeout)
    _singleton = None


