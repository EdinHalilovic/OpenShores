
from __future__ import annotations

import asyncio
import time

from openshores.core.logging import get_logger

logger = get_logger(__name__)

_0X18_STREAMS: dict = {}
_0X18_LATE_COUNT: int = 0
_0X18_BACK_COUNT: int = 0
_0X18_WORST_GAP: float = 0.0
_0X18_LATE_MS: float = 600.0


def _note_0x18(t_low: int, site: str, stream=None) -> int:
    global _0X18_LATE_COUNT, _0X18_BACK_COUNT, _0X18_WORST_GAP
    key = id(stream) if stream is not None else site
    now = time.monotonic()
    prev_t, prev_low = _0X18_STREAMS.get(key, (0.0, 0))
    _0X18_STREAMS[key] = (now, int(t_low))
    if not int(t_low):
        _0X18_BACK_COUNT += 1
        logger.error("0x18 t_low is zero at %s.",
                     site)
    if prev_t and stream is not None:
        gap_ms = (now - prev_t) * 1000.0
        if gap_ms > _0X18_WORST_GAP:
            _0X18_WORST_GAP = gap_ms
        if gap_ms > _0X18_LATE_MS:
            _0X18_LATE_COUNT += 1
            logger.warning("0x18 late %.0f ms (target 250) at %s. Client extrapolated ~%.3f deg of sky and will be pulled back", gap_ms, site, gap_ms * 0.117 / 1000.0)
    if prev_low and int(t_low) < prev_low and (prev_low - int(t_low)) < (1 << 31):
        _0X18_BACK_COUNT += 1
        logger.warning("0x18 went backward by %d ms at %s (0x%08x -> 0x%08x).",
                       prev_low - int(t_low), site, prev_low,
                       int(t_low) & 0xFFFFFFFF)
    return t_low


async def _loop_lag_watchdog() -> None:
    warn_ms = 150.0
    interval = 0.25
    worst = 0.0
    late = 0
    last_summary = time.monotonic()
    logger.info("Loop-lag watchdog on: warns above %.0f ms of overshoot on a "
                "%.0f ms sleep.", warn_ms, interval * 1000)
    while True:
        t0 = time.monotonic()
        await asyncio.sleep(interval)
        over_ms = (time.monotonic() - t0 - interval) * 1000.0
        if over_ms > worst:
            worst = over_ms
        if over_ms > warn_ms:
            late += 1
            logger.warning('Event loop blocked %.0f ms.', over_ms)
        now = time.monotonic()
        if now - last_summary >= 60.0:
            logger.info("Last 60 s: worst overshoot %.0f ms, %d stall(s) "
                        "above %.0f ms; 0x18 worst gap %.0f ms, %d late, "
                        "%d backward.", worst, late, warn_ms, _0X18_WORST_GAP,
                        _0X18_LATE_COUNT, _0X18_BACK_COUNT)
            worst, late, last_summary = 0.0, 0, now
