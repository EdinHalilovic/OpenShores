from __future__ import annotations

import logging
import struct
from typing import Dict, Any

logger = logging.getLogger(__name__)


def parse(payload: bytes) -> Dict[str, Any]:
    if len(payload) < 3 or payload[0] != 0x42:
        return {}
    flags = struct.unpack(">h", payload[1:3])[0]
    off = 3
    out: Dict[str, Any] = {"flags": flags & 0xFFFF}

    def _need(n: int) -> bool:
        return off + n <= len(payload)

    if flags & 0x0001 and _need(4):
        out["speed"] = struct.unpack(">f", payload[off:off+4])[0]
        off += 4
    if flags & 0x0002 and _need(48):
        out["projected"] = struct.unpack(">ddd", payload[off:off+24])
        out["rotation"]  = struct.unpack(">ddd", payload[off+24:off+48])
        off += 48
    if flags & 0x0004 and _need(4):
        out["auid_004"] = struct.unpack(">I", payload[off:off+4])[0]
        off += 4
    if flags & 0x0008 and _need(16):
        out["poses"]     = list(payload[off:off+10])
        out["flag08_i16"] = struct.unpack(">h", payload[off+10:off+12])[0]
        out["flag08_i32"] = struct.unpack(">i", payload[off+12:off+16])[0]
        off += 16
    if flags & 0x0010 and _need(24):
        out["position"] = struct.unpack(">ddd", payload[off:off+24])
        off += 24
    if flags & 0x0040 and _need(1):
        out["flag40_u8"] = payload[off]
        off += 1
    if flags & 0x0080 and _need(1):
        out["flag80_u8"] = payload[off]
        off += 1
    if flags & 0x0200 and _need(48):
        out["sec_matrix_a"] = struct.unpack(">ddd", payload[off:off+24])
        out["sec_matrix_b"] = struct.unpack(">ddd", payload[off+24:off+48])
        off += 48
    if flags & 0x0400 and _need(4):
        out["auid_400"] = struct.unpack(">I", payload[off:off+4])[0]
        off += 4
    if flags & 0x0800 and _need(46):
        out["flag800_i32x10"] = list(struct.unpack(">10i",
                                                    payload[off:off+40]))
        out["flag800_i16"] = struct.unpack(">h", payload[off+40:off+42])[0]
        out["flag800_i32"] = struct.unpack(">i", payload[off+42:off+46])[0]
        off += 46
    if flags & 0x1000 and _need(24):
        out["secondary_position"] = struct.unpack(">ddd",
                                                   payload[off:off+24])
        off += 24

    out["_consumed"] = off
    return out


if __name__ == "__main__":
    pkt = (bytes([0x42]) +
           struct.pack(">h", 0x0012) +
           struct.pack(">ddd", 1.0, 2.0, 3.0) +
           struct.pack(">ddd", 0.0, 0.0, 1.0) +
           struct.pack(">ddd", 100.5, 200.25, -300.125))
    r = parse(pkt)
    assert r["position"] == (100.5, 200.25, -300.125), r
    assert r["projected"] == (1.0, 2.0, 3.0)
    logger.info("Parse smoke test OK: %s", r)
