
from __future__ import annotations

import logging
import struct as _udp_struct

logger = logging.getLogger(__name__)


def _udp_decode_0x37(buf):
    out = {'target': 0, 'flags': 0, 'kind': 0, 'action': 0, 'arg': 0,
           'hit_target': 0, 'aim_x': 0.0, 'aim_y': 0.0,
           'count': 0, 'part': 0, 'range': 0, 'aim_z': 0.0,
           'cursor_slot': 0, 'cursor_sub': 0}
    if not buf or buf[0] != 0x37 or len(buf) < 16:
        return out
    try:
        out['target'] = _udp_struct.unpack_from('>I', buf, 11)[0]
        out['flags'] = buf[15]
        off = 16
        if buf[15] and off + 2 <= len(buf):
            _cur_slot = buf[off]
            _cur_sub = buf[off + 1]
            off += 2
            if (_cur_sub & 0x80) and off < len(buf):
                off += 1 + buf[off]
            out['cursor_slot'] = _cur_slot
            out['cursor_sub'] = _cur_sub & 0x7F
        if off < len(buf):
            out['count'] = buf[off]
            off += 1
        if off + 2 <= len(buf):
            _ef = buf[off]
            out['kind'] = _ef
            out['action'] = buf[off + 1]
            out['part'] = _ef & 0x0F
            off += 2
            if _ef & 0x80:
                off += 8
            if not (_ef & 0x40):
                if off + 2 <= len(buf):
                    out['arg'] = _udp_struct.unpack_from('>h', buf, off)[0]
                off += 2
            else:
                out['arg'] = -1
            if not (_ef & 0x20):
                if off + 2 <= len(buf):
                    out['range'] = _udp_struct.unpack_from('>h', buf, off)[0]
                off += 2
            if (_ef & 0x10) and off + 20 <= len(buf):
                out['hit_target'] = _udp_struct.unpack_from('>I', buf, off)[0]
                out['target_level'] = _udp_struct.unpack_from(
                    '>i', buf, off + 4)[0]
                out['aim_x'] = _udp_struct.unpack_from('>f', buf, off + 8)[0]
                out['aim_y'] = _udp_struct.unpack_from('>f', buf, off + 12)[0]
                out['aim_z'] = _udp_struct.unpack_from('>f', buf, off + 16)[0]
                off += 20
        _NOARG_CIS = (0x73, 0x89, 0x95, 0x96)
        if (out['action'] == 0 and len(buf) >= 3
                and buf[-3] == 0x01 and buf[-2] == 0x60
                and buf[-1] in _NOARG_CIS):
            out['kind'] = buf[-2]
            out['action'] = buf[-1]
    except Exception as exc:
        logger.warning("Decode err: %r hex=%s", exc, bytes(buf).hex())
    return out
