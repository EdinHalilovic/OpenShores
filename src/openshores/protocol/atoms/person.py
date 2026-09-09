
from __future__ import annotations

import struct
import time as _time


def _build_daperson_xform_update(*, player_auid: int, parent_auid: int,
                                 x: float, y: float, z: float,
                                 timestamp_ms: int = None,
                                 agent_bits: int = 0,
                                 _stamina_byte) -> bytes:
    if timestamp_ms is None:
        timestamp_ms = int(_time.time() * 1000)
    return (
        bytes([0x12])
        + struct.pack(">I", int(player_auid) & 0xFFFFFFFF)
        + struct.pack(">q", int(timestamp_ms))
        + bytes([0x29])
        + struct.pack(">I", int(parent_auid) & 0xFFFFFFFF)
        + struct.pack(">f", float(x))
        + struct.pack(">f", float(y))
        + struct.pack(">f", float(z))
        + struct.pack(">f", 0.0)
        + struct.pack(">f", 0.0)
        + struct.pack(">f", 0.0)
        + bytes([0x00])
        + bytes([0x00])
        + bytes([_stamina_byte(int(player_auid))])
        + bytes([0x00])
        + bytes([0x08])
        + bytes([int(agent_bits) & 0x3F])
    )


def build_agent_bits_daperson_update(auid: bytes, bits: int) -> bytes:
    if len(auid) != 4:
        raise ValueError("Auid must be 4 bytes")
    import time as _t
    return (
        bytes([0x12])
        + auid
        + struct.pack(">q", int(_t.time() * 1000))
        + bytes([0x20])
        + bytes([0x00])
        + bytes([0x00])
        + bytes([0x7F])
        + bytes([0x00])
        + bytes([0x08])
        + bytes([int(bits) & 0x3F])
    )


def _build_daperson_parent_update(player_auid: int,
                                  new_parent_auid: int,
                                  *,
                                  timestamp_ms: int = None,
                                  _stamina_byte, agent_bits_for) -> bytes:
    if timestamp_ms is None:
        timestamp_ms = int(_time.time() * 1000)
    return (
        bytes([0x12])
        + struct.pack(">I", int(player_auid) & 0xFFFFFFFF)
        + struct.pack(">q", int(timestamp_ms))
        + bytes([0x01])
        + struct.pack(">I", int(new_parent_auid) & 0xFFFFFFFF)
        + bytes([0x00])
        + bytes([0x00])
        + bytes([_stamina_byte(int(player_auid))])
        + bytes([0x00])
        + bytes([0x08])
        + bytes([agent_bits_for(int(player_auid)) & 0x3F])
    )


def _build_augear_only_daperson_update(auid: bytes,
                                       augear_payload: bytes,
                                       *,
                                       _stamina_byte, agent_bits_for) -> bytes:
    now_ms = int(_time.time() * 1000)
    if len(auid) != 4:
        raise ValueError("Auid must be 4 bytes")
    return (
        bytes([0x12])
        + auid
        + struct.pack(">q", now_ms)
        + bytes([0x00])
        + bytes([0x00])
        + bytes([0x00])
        + bytes([_stamina_byte(int.from_bytes(auid, 'big'))])
        + bytes([0x00])
        + bytes([0x48])
        + bytes([agent_bits_for(int.from_bytes(auid, "big")) & 0x3F])
        + augear_payload
    )
