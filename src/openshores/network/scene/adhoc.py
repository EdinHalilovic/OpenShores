
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import empire_for_avatar
from openshores.protocol.framing import write_framed
from openshores.protocol.stream import QDS

logger = get_logger(__name__)


_adhoc_tally: dict = {}


async def _handle_scene_adhoc(conn, first_frame: bytes,
                              writer: asyncio.StreamWriter,
                              peer, *,
                              _live_avatars: dict,
                              _CITIZEN_EMPIRE_OVERRIDE: dict,
                              _get_starmap_blob) -> None:
    op = first_frame[0] if first_frame else -1
    _adhoc_tally[op] = _adhoc_tally.get(op, 0) + 1
    _tot = sum(_adhoc_tally.values())
    logger.debug(f"[scene-adhoc] {peer} op=0x{op:02X} len={len(first_frame)} "
                 f"(session-adhoc-total: {_tot}, 0x35_count="
                 f"{_adhoc_tally.get(0x35, 0)}): {first_frame.hex()}")

    try:
        if op == 0x35:
            s = QDS(first_frame); s.read_u8()
            try:
                req_a = s.read_i32()
                req_b = s.read_i32()
                req_auid = s.read_u32()
                req_c = s.read_i32()
                logger.debug(f"[scene-adhoc]   0x35 RequestStarMap "
                             f"A=0x{req_a:x} B=0x{req_b:x} "
                             f"avatar_auid=0x{req_auid:x} C=0x{req_c:x}")
            except Exception as e:
                logger.warning(f"[scene-adhoc]   0x35 parse failed: {e!r}")

            blob = _get_starmap_blob()
            reply = bytes([0x35]) + blob
            await write_framed(writer, reply)
            logger.debug(f"[scene-adhoc]   -> 0x35 StarMap reply "
                         f"({len(reply)}B, {len(blob)}B body)")

        elif op == 0x3C:
            _entries = QDS()
            _entries.write_u8(0x3C)
            _online = list(_live_avatars.items())
            _entries.write_i32(len(_online))
            for _auid, _entry in _online:
                _entries.write_u32(await empire_for_avatar(
                    conn, int(_auid),
                    _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE))
                _entries.write_u32(int(_auid) & 0xFFFFFFFF)
                _entries.write_qstring(str(_entry.get("name", "") or ""))
                _entries.write_u8(0)
                _entries.write_u8(0)
            reply = _entries.getvalue()
            await write_framed(writer, reply)
            logger.debug(f"[scene-adhoc]   -> 0x3C OnlineStatus(count={len(_online)}) "
                         f"({len(reply)}B) "
                         f"{[(hex(a), e.get('name')) for a, e in _online]}")

        else:
            logger.info(f"[scene-adhoc]   unknown ad-hoc opcode 0x{op:02X}, "
                        f"closing")
    except Exception as e:
        logger.warning(f"[scene-adhoc] handler error: {e!r}")
    finally:
        try:
            await writer.drain()
        except Exception as exc:
            logger.debug("[scene-adhoc] drain before close refused (%r); "
                         "closing anyway.", exc)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as exc:
            logger.debug("[scene-adhoc] close refused (%r); the socket is "
                         "already gone.", exc)
