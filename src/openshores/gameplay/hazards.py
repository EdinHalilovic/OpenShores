
from __future__ import annotations


_SWIM_POSES = frozenset({0x2A})


def _is_in_gravity(auid, *,
                   tock_state,
                   live_avatars) -> bool:
    key = int(auid) & 0xFFFFFFFF
    ent = (tock_state.get(key) or {})
    live = (live_avatars.get(key) or {})
    for name in ("parent", "parent_auid", "parent_world", "AP",
                 "world", "world_auid"):
        val = ent.get(name) or live.get(name)
        if val:
            return True
    return False
