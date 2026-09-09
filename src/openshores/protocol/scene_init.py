
from __future__ import annotations

from openshores.protocol.stream import QDS

SCENE_PORT = 16759
CHAT_PORT = 16758


def build_scene_world_redirect(
    *,
    server_name: str = "",
    port: int = SCENE_PORT,
    world_state: int = 2,
    account_id_lo: int = 1,
    account_id_hi: int = 0,
    extra: int = 0,
) -> bytes:
    s = QDS()
    s.write_u8(0x22)
    s.write_qstring(server_name)
    s.write_u16(port & 0xFFFF)
    s.write_u8(world_state & 0xFF)
    s.write_u32(account_id_lo & 0xFFFFFFFF)
    s.write_i32(account_id_hi)
    return s.getvalue()


def build_scene_init_succeeded(motd: str,
                                autime_usec: int = 0,
                                chat_port: int = None) -> bytes:
    if chat_port is None:
        chat_port = CHAT_PORT
    s = QDS()
    s.write_u8(0x38)
    s.write_qstring(motd)
    s.write_i16(chat_port & 0xFFFF)
    s.write_u32((autime_usec >> 32) & 0xFFFFFFFF)
    s.write_u32(autime_usec & 0xFFFFFFFF)
    return s.getvalue()
