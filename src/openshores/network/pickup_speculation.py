
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger

logger = get_logger(__name__)


async def _pickup_speculation_loop(*, _live_avatars, _DROPPED_ITEMS) -> None:
    import time as _t
    tick = 0.15
    heartbeat_sec = 5.0
    logger.info(f"[pickup-spec] started in diagnostic-only mode (timed auto-pickup disabled; only 0x42 target-pin trigger). heartbeat={heartbeat_sec}s")
    last_heartbeat = 0.0
    import math as _m_loop
    while True:
        try:
            await asyncio.sleep(max(tick, 0.5))
            now = _t.monotonic()
            if now - last_heartbeat < heartbeat_sec:
                continue
            last_heartbeat = now
            drops = list(_DROPPED_ITEMS.keys())
            if not _live_avatars:
                if drops:
                    logger.debug(f"[pickup-spec] heartbeat: drops={len(drops)} "
                                 f"no live avatars "
                                 f"lookat=n/a (no live avatars)")
                else:
                    logger.debug("[pickup-spec] heartbeat: no drops registered "
                                 "(lookat=n/a)")
                continue
            for _hb_auid, _hb_entry in list(_live_avatars.items()):
                player_auid_int = int(_hb_auid) & 0xFFFFFFFF
                player_xyz = (_hb_entry.get("xyz")
                              if isinstance(_hb_entry, dict) else None)
                if drops and player_xyz is not None:
                    best_auid = 0
                    best_d = float("inf")
                    for auid, entry in _DROPPED_ITEMS.items():
                        ix, iy, iz = entry["xyz"]
                        dx = ix - player_xyz[0]
                        dy = iy - player_xyz[1]
                        dz = iz - player_xyz[2]
                        d = _m_loop.sqrt(dx * dx + dy * dy + dz * dz)
                        if d < best_d:
                            best_d = d
                            best_auid = auid
                    _hb_sess = (_hb_entry.get("session")
                                if isinstance(_hb_entry, dict) else None)
                    _hb_lookat = (_hb_sess.lookat_target_auid
                                  if _hb_sess is not None else 0)
                    logger.debug(f"[pickup-spec] heartbeat: drops={len(drops)} "
                                 f"closest=0x{best_auid:08x} dist={best_d:.2f}m "
                                 f"lookat=0x{_hb_lookat:08x} "
                                 f"player_xyz=({player_xyz[0]:.1f},"
                                 f"{player_xyz[1]:.1f},{player_xyz[2]:.1f})")
                elif drops:
                    _hb_sess2 = (_hb_entry.get("session")
                                 if isinstance(_hb_entry, dict) else None)
                    _hb_lookat2 = (_hb_sess2.lookat_target_auid
                                   if _hb_sess2 is not None else 0)
                    logger.debug(f"[pickup-spec] heartbeat: drops={len(drops)} "
                                 f"player xyz unknown for actor=0x"
                                 f"{player_auid_int:08x} "
                                 f"lookat=0x{_hb_lookat2:08x}")
                else:
                    logger.debug("[pickup-spec] heartbeat: no drops registered "
                                 "(lookat=n/a)")
                    break
        except asyncio.CancelledError:
            return
        except Exception as _exc:                           # noqa: BLE001
            logger.error(f"[pickup-spec] loop error (continuing): {_exc!r}")
