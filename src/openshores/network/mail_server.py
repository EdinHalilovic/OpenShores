
from __future__ import annotations

import asyncio
import datetime as _dt
import os

from openshores.core.logging import get_logger
from openshores.protocol import mail as _mailmod
from openshores.protocol.mail import _mail_terminator, _mail_write_packet_size

logger = get_logger(__name__)


class _PrefixedReader:
    def __init__(self, prefix, reader):
        self._prefix = bytearray(prefix)
        self._reader = reader

    async def readexactly(self, n):
        out = bytearray()
        if self._prefix and n > 0:
            take = min(n, len(self._prefix))
            out += self._prefix[:take]; del self._prefix[:take]; n -= take
        if n > 0:
            out += await self._reader.readexactly(n)
        return bytes(out)

    async def read(self, n=-1):
        if self._prefix:
            if n is None or n < 0:
                out = bytes(self._prefix); self._prefix = bytearray(); return out
            take = min(n, len(self._prefix))
            out = bytes(self._prefix[:take]); del self._prefix[:take]; return out
        return await self._reader.read(n)

    def __getattr__(self, name):
        return getattr(self._reader, name)


async def handle_chatmail(reader, writer, *, handle_chat, handle_mail):
    try:
        first = await reader.readexactly(1)
        tag = (first[0] >> 6) & 0x3
        extra = await reader.readexactly(tag) if tag else b""
        n = first[0] & 0x3F
        for _b in extra:
            n = (n << 8) | _b
        body = await reader.readexactly(n) if n else b""
    except (asyncio.IncompleteReadError, ConnectionError, OSError):
        try:
            writer.close()
        except Exception as exc:
            logger.debug("Chat/mail socket would not close: %r", exc)
        return
    raw = bytes(first) + bytes(extra) + bytes(body)
    is_mail = (len(body) >= 5 and body[0] == 0x07 and body[1:5] == b"\x00\x00\x00\x02")
    pr = _PrefixedReader(raw, reader)
    if is_mail:
        logger.info(f"[chatmail] routed MAIL (first frame {len(raw)}B)")
        await handle_mail(pr, writer)
    else:
        await handle_chat(pr, writer)


def _mail_build_response(account_id: int):
    import time as _time
    frames = bytearray()
    count = 0
    note = ""

    mails = []

    for m in mails:
        rec = _mailmod.encode_aumailmsg(
            subject=m.get("subject", ""),
            body=m.get("body", ""),
            title=m.get("title", m.get("subject", "")),
            sender_id=int(m.get("sender_id", 0)),
            recipient_id=int(account_id),
            timestamp_ms=int(m.get("timestamp_ms", int(_time.time() * 1000))),
            status=int(m.get("msg_id") or 0) & 0xFFFFFFFF,
        )
        pkt_body = bytes([6]) + rec
        frames += _mail_write_packet_size(len(pkt_body)) + pkt_body
        count += 1
    frames += _mail_terminator()
    return bytes(frames), count, note


async def handle_mail(reader, writer):
    peer = writer.get_extra_info("peername")
    pid = f"{peer[0]}:{peer[1]}" if peer else "?"
    cap = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"mail_capture_{_dt.datetime.now():%Y%m%d_%H%M%S}.log")

    def _mlog(line):
        logger.debug(line)

    def _sniff(pkt):
        out = []
        i = 0
        while i + 4 <= len(pkt) and len(out) < 6:
            n = int.from_bytes(pkt[i:i + 4], "big")
            if 2 <= n <= 200 and n % 2 == 0 and i + 4 + n <= len(pkt):
                try:
                    v = pkt[i + 4:i + 4 + n].decode("utf-16-be")
                    if v.isprintable() and any(c.isalnum() for c in v):
                        out.append((i, v)); i += 4 + n; continue
                except Exception as exc:
                    logger.debug("Mail QString sniff at +%d: %r", i, exc)
            i += 1
        return out

    _mlog(f"\n===== [mail] CONNECT from {pid} =====")
    buf = bytearray(); total = 0
    responded = [False]
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            total += len(data); buf += data
            _mlog(f"[mail] +{len(data)}B (total {total}) raw: {data.hex()}")
            off = 0
            while off < len(buf):
                b0 = buf[off]; tag = b0 >> 6
                if off + tag + 1 > len(buf):
                    break
                if tag == 0:
                    ln = b0 & 0x3F; noff = off + 1
                elif tag == 1:
                    ln = ((b0 & 0x3F) << 8) | buf[off + 1]; noff = off + 2
                elif tag == 2:
                    ln = ((b0 & 0x3F) << 16) | (buf[off + 1] << 8) | buf[off + 2]; noff = off + 3
                else:
                    ln = ((b0 & 0x3F) << 24) | (buf[off + 1] << 16) | \
                         (buf[off + 2] << 8) | buf[off + 3]; noff = off + 4
                if noff + ln > len(buf):
                    break
                pkt = bytes(buf[noff:noff + ln])
                if pkt:
                    _mlog(f"[mail] FRAME len={ln} op=0x{pkt[0]:02x}: {pkt.hex()}")
                    for pos, v in _sniff(pkt):
                        _mlog(f"[mail]    @+{pos}: QString {v!r}")
                    if not responded[0] and len(pkt) >= 19 and pkt[0] == 0x07:
                        acct = int.from_bytes(pkt[15:19], "big")
                        try:
                            resp, cnt, rnote = _mail_build_response(acct)
                            if resp:
                                writer.write(resp)
                                await writer.drain()
                            responded[0] = True
                            _mlog(f"[mail] RESPONDED acct=0x{acct:08x} "
                                  f"mails={cnt} bytes={len(resp)} note={rnote!r}")
                            try:
                                await writer.drain()
                            except Exception as exc:
                                logger.debug("Mail response drain: %r", exc)
                            try:
                                await asyncio.wait_for(reader.read(65536), timeout=5.0)
                            except Exception as exc:
                                logger.debug("Mail client did not close: %r", exc)
                            try:
                                writer.close()
                            except Exception as exc:
                                logger.debug("Mail socket would not close: %r", exc)
                            return
                        except Exception as _rexc:
                            _mlog(f"[mail] RESPOND err: {_rexc!r}")
                off = noff + ln
            if off:
                del buf[:off]
    except Exception as exc:
        _mlog(f"[mail] read err {pid}: {exc!r}")
    finally:
        _mlog(f"===== [mail] DISCONNECT {pid} (got {total}B, log={os.path.basename(cap)}) =====")
        try:
            writer.close()
        except Exception as exc:
            logger.debug("Mail socket would not close: %r", exc)
