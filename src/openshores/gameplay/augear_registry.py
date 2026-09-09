
from __future__ import annotations

_AUGEAR_STATES: dict = {}


def _get_augear(auid):
    auid = int(auid) & 0xFFFFFFFF
    return _AUGEAR_STATES.setdefault(auid, [])
