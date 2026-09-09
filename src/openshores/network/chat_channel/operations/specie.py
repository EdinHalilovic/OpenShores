
from __future__ import annotations

import struct

from openshores.core.logging import get_logger
from openshores.protocol.framing import encode_size

logger = get_logger(__name__)


async def handle_specie_requested(payload: bytes, writer, *,
                                  _DROPPED_ITEMS: dict) -> None:
    try:
        global _0XB3_LAST_HEX, _0XB3_FRAME_N
        try:
            _0XB3_LAST_HEX
        except NameError:
            _0XB3_LAST_HEX = ""
            _0XB3_FRAME_N = 0
        _hx = payload.hex()
        _0XB3_FRAME_N += 1
        if _hx != _0XB3_LAST_HEX:
            logger.debug(f"[chat-0xB3 #{_0XB3_FRAME_N}] "
                         f"len={len(payload)} CHANGED: {_hx}")
            if _0XB3_LAST_HEX and len(_0XB3_LAST_HEX) == len(_hx):
                _diffs = []
                for _i in range(0, len(_hx), 2):
                    _a = _hx[_i:_i + 2]
                    _b = _0XB3_LAST_HEX[_i:_i + 2]
                    if _a != _b:
                        _diffs.append((_i // 2, _b, _a))
                if _diffs:
                    _ds = " ".join(
                        f"@{off}:{old}->{new}"
                        for off, old, new in _diffs[:16])
                    logger.debug(f"[chat-0xB3]   diff: {_ds}")
            _0XB3_LAST_HEX = _hx
        else:
            if _0XB3_FRAME_N % 30 == 0:
                logger.debug(f"[chat-0xB3 #{_0XB3_FRAME_N}] "
                             f"steady ({len(payload)}B)")
        if len(payload) >= 5:
            import struct as _s44
            for _off in range(1, min(len(payload) - 3, 28)):
                _u32 = _s44.unpack_from(
                    ">I", payload, _off)[0]
                if _u32 in _DROPPED_ITEMS:
                    logger.debug(f"[chat-0xB3]   *DROP* AuId "
                                 f"0x{_u32:08x} at byte offset {_off}")
    except Exception as _b3e:                           # noqa: BLE001
        logger.debug(f"[chat-0xB3] dump error: {_b3e!r}")

    try:
        if len(payload) >= 29:
            _b3_len = struct.unpack_from(">I", payload, 1)[0]
            if _b3_len == 24 and len(payload) >= 5 + 24:
                _dna = payload[5:5 + 24]
                _b2 = (b"\xB2"
                       + struct.pack(">I", 24) + _dna
                       + b"\xFF\xFF\xFF\xFF"
                       + struct.pack(">I", 2440588)
                       + struct.pack(">I", 0)
                       + b"\x02"
                       + struct.pack(">i", 0))
                writer.write(
                    encode_size(len(_b2)) + _b2)
                await writer.drain()
                _n_b2 = globals().get("_0XB3_FRAME_N", 0)
                if _n_b2 <= 3 or _n_b2 % 30 == 0:
                    logger.debug(f"[chat-0xB2] -> DzSpecie for "
                                 f"{_dna.hex()} ({len(_b2)}B body)")
            else:
                logger.warning(f"[chat-0xB3] unexpected DhDNA length "
                               f"{_b3_len}, not replying")
        else:
            logger.warning(f"[chat-0xB3] frame too short "
                           f"({len(payload)}B), not replying")
    except Exception as _b2e:                           # noqa: BLE001
        logger.warning(f"[chat-0xB2] reply failed (non-fatal): {_b2e!r}")
