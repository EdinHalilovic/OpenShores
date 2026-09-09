
from __future__ import annotations

import asyncio

from openshores.core.heartbeat_watch import _note_0x18
from openshores.core.logging import get_logger
from openshores.protocol.framing import write_framed
from openshores.world.sim_time_low import _current_sim_t_low

logger = get_logger(__name__)


async def _ticker_c2_factory(w, *,
                             anchor_full,
                             sim_time_state):
    try:
        while not w.is_closing():
            t_low = _note_0x18(_current_sim_t_low(anchor_full=anchor_full),
                               "ticker_c2", w)
            tp = (bytes([0x18])
                  + t_low.to_bytes(4, "big")
                  + bytes([0x02]))
            await write_framed(w, tp)
            sim_time_state["last_0x18_t_low"] = t_low
            await asyncio.sleep(0.25)
    except Exception as _tc2e:
        logger.info(f"[scene]   ticker_c2 ended: "
                    f"{_tc2e!r}")
