
from __future__ import annotations

NPC_POSE_DYING = 0x12
NPC_POSE_DEAD = 0x15


def _npc_pose_for(d):
    if not d.alive:
        return NPC_POSE_DYING
    if d.hp < 1:
        return NPC_POSE_DYING
    return None
