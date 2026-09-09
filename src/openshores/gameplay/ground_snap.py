
from __future__ import annotations

import math as _m

from openshores.core.logging import get_logger
from openshores.gameplay.natives.village import gravity_align_euler as _gae

logger = get_logger(__name__)


_AVATAR_HEIGHT_M: float = 1.5


def _ground_snap_radial(xyz, height_m: float = None):
    if height_m is None:
        height_m = _AVATAR_HEIGHT_M
    mag = _m.sqrt(xyz[0] * xyz[0] + xyz[1] * xyz[1] + xyz[2] * xyz[2])
    if mag < 1e-6:
        return tuple(float(c) for c in xyz)
    nx = xyz[0] / mag
    ny = xyz[1] / mag
    nz = xyz[2] / mag
    return (float(xyz[0] - nx * height_m),
            float(xyz[1] - ny * height_m),
            float(xyz[2] - nz * height_m))


def _peer_upright_euler(xyz):
    try:
        return tuple(_gae(tuple(xyz)))
    except Exception as exc:
        logger.error(f'[scene] gravity align unavailable ({exc!r}).')
        return (0.0, 0.0, 0.0)
