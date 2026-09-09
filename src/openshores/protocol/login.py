
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from openshores.protocol.encryption import LOGIN_PACKET_KEY_SEED, au_crypt, net_crypt_key
from openshores.protocol.stream import QDS


@dataclass
class LoginRequest:
    type: int
    version: Optional[str]
    username: str
    password_hash: bytes


def parse_login_request(payload: bytes) -> LoginRequest:
    s = QDS(payload)
    tpe = s.read_u8()
    if tpe != 0x03:
        raise ValueError(f"Expected login TYPE 0x03, got {tpe:#04x}")
    version = s.read_qstring()
    user_ct = s.read_bytes() or b""
    passwd  = s.read_bytes() or b""
    key = net_crypt_key(LOGIN_PACKET_KEY_SEED)
    user_pt = au_crypt(user_ct, key)
    username = None
    for enc in ("latin-1", "utf-8", "utf-16-le", "utf-16-be"):
        try:
            username = user_pt.decode(enc).rstrip("\x00")
            break
        except UnicodeDecodeError:
            continue
    if username is None:
        username = user_pt.hex()
    return LoginRequest(tpe, version, username, passwd)


def build_login_fail_reply(reason: int = 1) -> bytes:
    s = QDS()
    s.write_u8(0x0b)
    s.write_u8(reason & 0xFF)
    s.write_i32(0)
    return s.getvalue()


def build_redirect_reply(host: str, port: int) -> bytes:
    s = QDS()
    s.write_u8(0x02)
    s.write_qstring(host)
    s.write_i16(port)
    return s.getvalue()


def build_version_mismatch_reply() -> bytes:
    return bytes([0x09])
