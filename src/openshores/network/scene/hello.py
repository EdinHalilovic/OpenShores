
from __future__ import annotations


def _scene_hello_char_id(frame):
    try:
        if not frame or frame[0] != 0x38 or len(frame) < 5:
            return None
        name_len = int.from_bytes(frame[1:5], "big")
        off = 5 + name_len + 4 + 4
        if len(frame) < off + 4:
            return None
        return int.from_bytes(frame[off:off + 4], "big")
    except Exception:
        return None


def _frame_is_new_avatar_hello(frame) -> bool:
    return _scene_hello_char_id(frame) == 0
