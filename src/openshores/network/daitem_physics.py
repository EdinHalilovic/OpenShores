
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.protocol.atoms.daitem_drop import _build_daitem_drop_packet
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


async def _daitem_physics_fall(item_auid_int: int, *,
                               _DROPPED_ITEMS,
                               _live_avatars) -> None:
    import math as _pm
    import time as _pt
    entry = _DROPPED_ITEMS.get(item_auid_int)
    if entry is None:
        return
    start_xyz = entry["xyz"]
    fall_distance = 10.0
    fall_time = 1.0
    fps = 20.0
    mag = _pm.sqrt(start_xyz[0]**2 + start_xyz[1]**2 + start_xyz[2]**2)
    if mag <= fall_distance + 1e-3:
        return
    settle_scale = (mag - fall_distance) / mag
    target_xyz = tuple(start_xyz[i] * settle_scale for i in range(3))
    n_steps = max(1, int(fall_time * fps))
    dt = 1.0 / fps
    logger.debug("Drop 0x%08x begins its fall from %s to %s: "
                 "fall_distance=%.2f mag=%.2f steps=%d dt=%.3fs",
                 item_auid_int, start_xyz, target_xyz,
                 fall_distance, mag, n_steps, dt)
    try:
        for step in range(1, n_steps + 1):
            await asyncio.sleep(dt)
            entry = _DROPPED_ITEMS.get(item_auid_int)
            if entry is None:
                return
            writer = None
            for _e in _live_avatars.values():
                _w = _e.get("writer")
                if _w is not None and not _w.is_closing():
                    writer = _w
                    break
            if writer is None:
                return
            t_norm = step / n_steps
            frac = t_norm * t_norm
            cur_xyz = tuple(
                start_xyz[i] + (target_xyz[i] - start_xyz[i]) * frac
                for i in range(3)
            )
            entry["xyz"] = cur_xyz
            try:
                pkt = _build_daitem_drop_packet(
                    item_auid_int=item_auid_int,
                    parent_auid=entry["parent"],
                    xyz=cur_xyz,
                    item_typeId=entry["typeId"],
                    item_body=entry["body"],
                    rotation=entry.get("rotation", (0.0, 0.0, 0.0)),
                    time_created_ms=entry.get("time_created_ms"),
                )
                await write_framed(writer, pkt)
                if step == n_steps:
                    logger.debug("Drop 0x%08x settled at %s after %d steps",
                                 item_auid_int, cur_xyz, n_steps)
            except Exception as _pe:
                logger.warning("Drop 0x%08x could not be pushed on step "
                               "%d/%d; it stops falling where it is: %r",
                               item_auid_int, step, n_steps, _pe)
                return
    except asyncio.CancelledError:
        return
