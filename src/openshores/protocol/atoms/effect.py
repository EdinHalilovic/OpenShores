
from __future__ import annotations

import struct
import time as _time


def _build_au_effect_bytes(origin_xyz=(0.0, 0.0, 0.0),
                           sound_type=0x5F,
                           visual_type=0x1E,
                           alpha=1.0,
                           scale=1.0,
                           time_ms=None,
                           *,
                           next_effect_time_ms):
    if time_ms is None:
        time_ms = next_effect_time_ms()
    flag = 0x01 | 0x02 | 0x04
    parts = [
        bytes([flag]),
        struct.pack(">H", int(time_ms) & 0xFFFF),
        struct.pack(">fff", *origin_xyz),
        bytes([int(sound_type) & 0xFF]),
        struct.pack(">f", float(alpha)),
        struct.pack(">f", float(scale)),
        bytes([int(visual_type) & 0xFF]),
    ]
    return b"".join(parts)


def _build_player_effect_atom_pkt(player_auid: int,
                                  origin_xyz=(0.0, 0.0, 0.0),
                                  sound_type=0x5F,
                                  visual_type=0x1E,
                                  time_ms=None,
                                  *,
                                  next_effect_time_ms,
                                  _stamina_byte,
                                  agent_bits_for):
    _wall_ms = int(_time.time() * 1000)
    effect = _build_au_effect_bytes(
        origin_xyz=origin_xyz,
        sound_type=sound_type,
        visual_type=visual_type,
        time_ms=(int(time_ms) if time_ms is not None else None),
        next_effect_time_ms=next_effect_time_ms,
    )
    bp2 = (
        bytes([0x10])
        + bytes([0x01])
        + effect
    )
    return (
        bytes([0x12])
        + struct.pack(">I", int(player_auid))
        + struct.pack(">q", _wall_ms)
        + bp2
        + bytes([0x00])
        + bytes([0x00])
        + bytes([_stamina_byte(int(player_auid))])
        + bytes([0x00])
        + bytes([0x08])
        + bytes([agent_bits_for(int(player_auid)) & 0x3F])
    )


def _build_world_atom_effect_pkt(world_auid: int,
                                 origin_xyz=(0.0, 0.0, 0.0),
                                 sound_type=0x5F,
                                 visual_type=0x14,
                                 time_ms=None,
                                 *,
                                 next_effect_time_ms):
    _wall_ms = int(_time.time() * 1000)
    effect = _build_au_effect_bytes(
        origin_xyz=origin_xyz,
        sound_type=sound_type,
        visual_type=visual_type,
        time_ms=(int(time_ms) if time_ms is not None else None),
        next_effect_time_ms=next_effect_time_ms,
    )
    bp2 = (
        bytes([0x10])
        + bytes([0x01])
        + effect
    )
    return (
        bytes([0x1F])
        + struct.pack(">I", int(world_auid) & 0xFFFFFFFF)
        + struct.pack(">q", _wall_ms)
        + bp2
        + bytes([0x00])
        + struct.pack(">i", -1)
        + bytes([0x00])
    )
