
from __future__ import annotations

import struct

from openshores.core.heartbeat_watch import _note_0x18
from openshores.world.sim_time_low import _current_sim_t_low


def _build_scene_manifest(*, writer, active_avatar_auid: int,
                          scene_auids: list, live_auids_for_manifest: set,
                          live_avatars: dict,
                          manifest_suppress: set,
                          dynamic_scene_auids: set,
                          sim_time_anchor_full: int,
                          sim_time_state: dict) -> bytes:
    _t_low = _note_0x18(_current_sim_t_low(anchor_full=sim_time_anchor_full),
                        "manifest", writer)
    _live_now = {int(active_avatar_auid)} | set(live_avatars.keys())
    _live_now -= manifest_suppress
    _static_auids = [a for a in scene_auids
                     if a not in live_auids_for_manifest]
    _all_auids = _static_auids + list(_live_now) + [
        a for a in dynamic_scene_auids
        if a not in _static_auids and a not in _live_now
    ]
    sim_time_state["last_0x18_t_low"] = _t_low & 0xFFFFFFFF
    return (bytes([0x18])
            + struct.pack(">I", _t_low & 0xFFFFFFFF)
            + bytes([0x01])
            + struct.pack(">h", len(_all_auids))
            + b"".join(struct.pack(">I", a) for a in _all_auids))
