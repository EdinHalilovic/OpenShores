
from __future__ import annotations

import struct

from openshores.gameplay.food import _hunger_i16


def _build_creature_state_pkt(auid: int, *, hp: int, pose: int,
                              hunger: int, stamina: int,
                              tock_state,
                              agent_bits_for) -> bytes:
    import time as _bts_t
    _now_ms = int(_bts_t.time() * 1000)
    _hp_clamped = max(-30, min(0x7fff, int(hp)))
    _pose_byte = int(pose) & 0xFF
    _stam = int(stamina) & 0xFF
    _hunger = int(hunger) & 0x7fff
    return (
        bytes([0x12])
        + struct.pack(">I", int(auid))
        + struct.pack(">q", _now_ms)
        + bytes([0x00])
        + bytes([0x00])
        + bytes([0x0C])
        + struct.pack(">h", _hp_clamped)
        + bytes([_pose_byte] * 10)
        + struct.pack(">I", 0)
        + bytes([_stam])
        + bytes([0x00])
        + bytes([0x0C])
        + struct.pack(">H", _hunger_i16(int(auid), _hunger,
                                        _tock_state=tock_state))
        + bytes([agent_bits_for(int(auid)) & 0x3F])
    )
