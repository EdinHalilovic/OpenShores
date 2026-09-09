
from __future__ import annotations

from openshores.gameplay.natives.village import gravity_align_euler


_FAUNA_BODY_OFFSET: float = 2.95


def _fauna_align(xyz, yaw_rad: float):
    return gravity_align_euler(tuple(xyz), float(yaw_rad))
