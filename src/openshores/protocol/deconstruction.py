
from __future__ import annotations

import struct


def serialize_deconstruction(st: dict) -> bytes:
    flags = (st.get("flags", 0) & 0x7f) | (0x80 if st.get("designId") else 0)
    b = struct.pack(">B", flags)
    b += struct.pack(">B", st["procId"] & 0xFF)
    b += struct.pack(">h", int(st["labor"]))
    comps = st["components"]
    b += struct.pack(">B", len(comps) & 0xFF)
    for cid, b2, eff, req, applied in comps:
        b += (struct.pack(">h", cid & 0xFFFF) + struct.pack(">B", b2 & 0xFF)
              + struct.pack(">B", eff & 0xFF) + struct.pack(">i", int(req))
              + struct.pack(">i", int(applied)) + struct.pack(">B", 0))
    b += struct.pack(">B", st.get("f28", 0) & 0xFF)
    b += struct.pack(">h", int(st.get("f2a", 0)))
    b += struct.pack(">B", st.get("flags2", 0) & 0xFF)
    if flags & 0x80:
        b += struct.pack(">i", st["designId"] & 0xFFFFFFFF)
    return b


def parse_deconstruction(blob: bytes) -> dict:
    p = 0
    flags = blob[p]; p += 1
    proc = blob[p]; p += 1
    labor = struct.unpack_from(">h", blob, p)[0]; p += 2
    count = blob[p]; p += 1
    comps = []
    for _ in range(count):
        cid = struct.unpack_from(">h", blob, p)[0]; p += 2
        b2 = blob[p]; p += 1
        eff = blob[p]; p += 1
        req = struct.unpack_from(">i", blob, p)[0]; p += 4
        applied = struct.unpack_from(">i", blob, p)[0]; p += 4
        p += 1
        comps.append([cid, b2, eff, req, applied])
    f28 = blob[p]; p += 1
    f2a = struct.unpack_from(">h", blob, p)[0]; p += 2
    flags2 = blob[p]; p += 1
    did = struct.unpack_from(">i", blob, p)[0] if (flags & 0x80) else 0
    return {"flags": flags, "procId": proc, "labor": labor, "components": comps,
            "f28": f28, "f2a": f2a, "flags2": flags2, "designId": did}
