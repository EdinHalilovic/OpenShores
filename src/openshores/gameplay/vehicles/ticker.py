
from __future__ import annotations

import asyncio
import threading
import time
from typing import Optional

import asyncpg

from openshores.core.logging import get_logger

from .persistence import Vehicle, update_vehicle
from .spawn import get_active_vehicle, list_active_vehicles, commit_vehicle
from .input import get_runtime, Switches

logger = get_logger(__name__)


FUEL_DRAIN_MS_PER_UNIT: int = 60_000
DEFAULT_TOCK_INTERVAL_MS: int = 1_000
PERSIST_EVERY_N_TOCKS: int = 30


async def tock(vehicle_id: int, now_ms: Optional[int] = None, *,
               conn: asyncpg.Connection) -> bool:
    v = get_active_vehicle(vehicle_id)
    if v is None:
        return False
    rt = get_runtime(vehicle_id)
    if now_ms is None:
        now_ms = int(time.time() * 1000)

    if rt.last_tock_ms == 0:
        rt.last_tock_ms = now_ms
        return False

    elapsed_ms = now_ms - rt.last_tock_ms
    rt.last_tock_ms = now_ms

    if elapsed_ms <= 0:
        return False

    changed = False
    if v.switches & Switches.ENGINE_BIT:
        rt.fuel_drain_accumulator_ms += elapsed_ms
        while rt.fuel_drain_accumulator_ms >= FUEL_DRAIN_MS_PER_UNIT:
            if v.fuel <= 0:
                v.switches &= ~Switches.ENGINE_BIT
                rt.fuel_drain_accumulator_ms = 0
                changed = True
                rt.force_transform_pending = True
                break
            v.fuel -= 1
            rt.fuel_drain_accumulator_ms -= FUEL_DRAIN_MS_PER_UNIT
            changed = True
    else:
        rt.fuel_drain_accumulator_ms = 0

    try:
        from .hull_stress import test_hull_stress
        hs = await test_hull_stress(vehicle_id, now_ms=now_ms, conn=conn)
        if hs.took_stress_damage or hs.took_atmosphere_damage or hs.disintegrated:
            changed = True
    except Exception as exc:
        logger.warning("Hull-stress check for vehicle %#x failed (non-fatal); "
                       "ID: %r", vehicle_id, exc)

    return changed


_tock_count: dict[int, int] = {}
_tock_count_lock = threading.Lock()


async def tock_all(now_ms: Optional[int] = None, *,
                   conn: asyncpg.Connection) -> int:
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    snapshot = list_active_vehicles()
    n = 0
    for v in snapshot:
        changed = await tock(v.id, now_ms=now_ms, conn=conn)
        n += 1
        with _tock_count_lock:
            c = _tock_count.get(v.id, 0) + 1
            _tock_count[v.id] = c
        if changed or c % PERSIST_EVERY_N_TOCKS == 0:
            await commit_vehicle(v.id, conn=conn)
    return n


_last_tick_ms: dict[int, int] = {}
_last_tick_lock = threading.Lock()
DEFAULT_TICK_INTERVAL_MS: int = 50


def tick(vehicle_id: int, now_ms: Optional[int] = None) -> bool:
    from .physics import tick_movement, MAX_TICK_MS

    if now_ms is None:
        now_ms = int(time.time() * 1000)

    with _last_tick_lock:
        last = _last_tick_ms.get(vehicle_id, 0)
        _last_tick_ms[vehicle_id] = now_ms

    if last == 0:
        dt_ms = DEFAULT_TICK_INTERVAL_MS
    else:
        dt_ms = now_ms - last
        if dt_ms <= 0:
            return False
        if dt_ms > MAX_TICK_MS:
            return False

    result = tick_movement(vehicle_id, dt_ms, now_ms=now_ms)
    return (result.velocity_changed
            or result.transform_changed
            or result.became_at_rest)


async def tick_all(now_ms: Optional[int] = None, skip_ids=None, *,
                   conn: asyncpg.Connection) -> int:
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    skip = set()
    if skip_ids:
        for _s in skip_ids:
            try:
                skip.add(int(_s) & 0xFFFFFFFF)
            except Exception:
                logger.debug("skip_ids entry %r is not a vehicle id; ignored", _s)
    snapshot = list_active_vehicles()
    n = 0
    for v in snapshot:
        if skip and (int(v.id) & 0xFFFFFFFF) in skip:
            reset_tick_clock(v.id)
            n += 1
            continue
        try:
            tick(v.id, now_ms=now_ms)
        except Exception as exc:
            logger.error("Vehicle %#x tick failed, skipping it this frame. ID: %r", v.id, exc)
        n += 1
    try:
        from .missile import tick_all_missiles
        n += await tick_all_missiles(now_ms=now_ms, conn=conn)
    except Exception as exc:
        logger.error("tick_all_missiles failed "
                     "the missiles did not: %r", exc)
    return n


def reset_tick_clock(vehicle_id: int) -> None:
    with _last_tick_lock:
        _last_tick_ms.pop(int(vehicle_id), None)


def clear_tick_clock_registry() -> None:
    with _last_tick_lock:
        _last_tick_ms.clear()


_ticker_task: Optional[asyncio.Task] = None
_ticker_stop = asyncio.Event()


async def _ticker_loop(interval_ms: int, *,
                       conn: asyncpg.Connection) -> None:
    interval_s = interval_ms / 1000.0
    while not _ticker_stop.is_set():
        now = int(time.time() * 1000)
        try:
            await tick_all(now_ms=now, conn=conn)
        except Exception as exc:
            logger.error("tick_all failed "
                         "ID: %r", exc)
        try:
            await tock_all(now_ms=now, conn=conn)
        except Exception as exc:
            logger.error("tock_all failed "
                         "ID: %r", exc)
        try:
            await asyncio.wait_for(_ticker_stop.wait(), interval_s)
        except asyncio.TimeoutError:
            continue


def start_ticker_thread(interval_ms: int = DEFAULT_TOCK_INTERVAL_MS, *,
                        conn: asyncpg.Connection) -> None:
    global _ticker_task
    if _ticker_task is not None and not _ticker_task.done():
        return
    _ticker_stop.clear()
    _ticker_task = asyncio.get_running_loop().create_task(
        _ticker_loop(interval_ms, conn=conn), name="vehicles-tocker")
    logger.info("Background tocker started (interval=%dms)", interval_ms)


async def stop_ticker_thread(join_timeout_s: float = 2.0) -> None:
    global _ticker_task
    _ticker_stop.set()
    if _ticker_task is not None:
        await asyncio.wait({_ticker_task}, timeout=join_timeout_s)
        _ticker_task = None


def _selftest() -> None:
    raise NotImplementedError(
        "Retired")


if __name__ == "__main__":
    logger.info("vehicles.ticker running self-test ...")
    _selftest()
    logger.info("vehicles.ticker self-test PASSED")
