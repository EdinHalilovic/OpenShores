
from __future__ import annotations

import struct


def _bp2(parent_auid):
    return bytes([0x01]) + parent_auid


def _bpt2(parent_auid, tx=0.0, ty=0.0, tz=0.0,
          rx=0.0, ry=0.0, rz=0.0):
    return (bytes([0x09]) + parent_auid
            + struct.pack(">ffffff", tx, ty, tz, rx, ry, rz))


def _bpt2_tc(parent_auid, time_created_ms, tx=0.0, ty=0.0, tz=0.0,
             rx=0.0, ry=0.0, rz=0.0):
    return (bytes([0x0B]) + parent_auid
            + struct.pack(">q", int(time_created_ms))
            + struct.pack(">ffffff", tx, ty, tz, rx, ry, rz))
