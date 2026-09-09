
from __future__ import annotations

import asyncio
import contextvars
import time
from contextlib import asynccontextmanager

import asyncpg

from openshores.core.config import Deployment
from openshores.core.logging import get_logger

logger = get_logger(__name__)


Row = asyncpg.Record
Error = (asyncpg.PostgresError, asyncpg.InterfaceError,
         asyncpg.InternalClientError)
DatabaseError = (asyncpg.PostgresError, asyncpg.InterfaceError,
                 asyncpg.InternalClientError)
IntegrityError = asyncpg.IntegrityConstraintViolationError

DEFAULT_MIN_POOL_SIZE = 1
DEFAULT_MAX_POOL_SIZE = 10

_POOLS: dict[str, asyncpg.Pool] = {}
_LOCK = asyncio.Lock()


def _now_ms() -> int:
    return int(time.time() * 1000)

SharedConnection = asyncpg.pool.PoolConnectionProxy


async def connect(database_url: str | None = None, *,
                  min_size: int = DEFAULT_MIN_POOL_SIZE,
                  max_size: int = DEFAULT_MAX_POOL_SIZE) -> asyncpg.Pool:
    url = (database_url if database_url is not None
           else Deployment.from_env().database_url)
    pool = _POOLS.get(url)
    if pool is not None:
        return pool
    async with _LOCK:
        pool = _POOLS.get(url)
        if pool is not None:
            return pool
        try:
            pool = await asyncpg.create_pool(url, min_size=min_size,
                                             max_size=max_size)
        except Exception as exc:
            logger.error('Cannot open a database connection pool: %s.', exc)
            raise
        _POOLS[url] = pool
        return pool


async def close_path(database_url: str) -> None:
    async with _LOCK:
        pool = _POOLS.pop(database_url, None)
    if pool is not None:
        await pool.close()


async def close_all() -> None:
    async with _LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for p in pools:
        await p.close()


async def terminate_all() -> None:


    async with _LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for p in pools:
        p.terminate()


def stats() -> dict:
    return {"connections": sum(p.get_size() for p in _POOLS.values())}


LOCK_SPACE_PERSON = 1
LOCK_SPACE_SYSTEM = 2


def _lock_int4(value: int) -> int:
    value = int(value) & 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


@asynccontextmanager
async def _immediate(conn: asyncpg.Connection, space: int, key: int):
    async with conn.transaction(isolation="read_committed"):
        await conn.execute("SELECT pg_advisory_xact_lock($1, $2)",
                           _lock_int4(space), _lock_int4(key))
        yield conn


_PINNED: contextvars.ContextVar = contextvars.ContextVar(
    "openshores_pinned_connection", default=None)


def _pinned():
    entry = _PINNED.get()
    if entry is None:
        return None
    owner, conn = entry
    return conn if owner is asyncio.current_task() else None


class TaskConnection:

    __slots__ = ("_pool",)

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    def __repr__(self) -> str:                              # pragma: no cover
        return f"<TaskConnection pool={self._pool!r}>"

    async def execute(self, *args, **kwargs):
        conn = _pinned()
        if conn is not None:
            return await conn.execute(*args, **kwargs)
        async with self._pool.acquire() as conn:
            return await conn.execute(*args, **kwargs)

    async def executemany(self, *args, **kwargs):
        conn = _pinned()
        if conn is not None:
            return await conn.executemany(*args, **kwargs)
        async with self._pool.acquire() as conn:
            return await conn.executemany(*args, **kwargs)

    async def fetch(self, *args, **kwargs):
        conn = _pinned()
        if conn is not None:
            return await conn.fetch(*args, **kwargs)
        async with self._pool.acquire() as conn:
            return await conn.fetch(*args, **kwargs)

    async def fetchrow(self, *args, **kwargs):
        conn = _pinned()
        if conn is not None:
            return await conn.fetchrow(*args, **kwargs)
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(*args, **kwargs)

    async def fetchval(self, *args, **kwargs):
        conn = _pinned()
        if conn is not None:
            return await conn.fetchval(*args, **kwargs)
        async with self._pool.acquire() as conn:
            return await conn.fetchval(*args, **kwargs)

    def transaction(self, **kwargs):
        return _TaskTransaction(self._pool, kwargs)


class _TaskTransaction:

    __slots__ = ("_pool", "_kwargs", "_conn", "_tr", "_token")

    def __init__(self, pool: asyncpg.Pool, kwargs: dict) -> None:
        self._pool = pool
        self._kwargs = kwargs
        self._conn = None
        self._tr = None
        self._token = None

    async def __aenter__(self):
        conn = _pinned()
        if conn is not None:
            self._tr = conn.transaction(**self._kwargs)
            return await self._tr.__aenter__()
        self._conn = await self._pool.acquire()
        self._token = _PINNED.set((asyncio.current_task(), self._conn))
        try:
            self._tr = self._conn.transaction(**self._kwargs)
            return await self._tr.__aenter__()
        except BaseException:
            await self._unpin()
            raise

    async def __aexit__(self, exc_type, exc, tb):
        try:
            return await self._tr.__aexit__(exc_type, exc, tb)
        finally:
            if self._token is not None:
                await self._unpin()

    async def _unpin(self) -> None:
        _PINNED.reset(self._token)
        self._token = None
        conn, self._conn = self._conn, None
        await self._pool.release(conn)


RAW_CONNECTION_TYPES = (asyncpg.Connection, asyncpg.pool.PoolConnectionProxy)


def task_connection(pool: asyncpg.Pool) -> TaskConnection:
    return TaskConnection(pool)
