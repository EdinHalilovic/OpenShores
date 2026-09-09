
from __future__ import annotations

import asyncio


def encode_size(n: int) -> bytes:
    if n < 0x40:
        return bytes([n])
    if n < 0x4000:
        return bytes([0x40 | (n >> 8), n & 0xFF])
    if n < 0x400000:
        return bytes([0x80 | (n >> 16), (n >> 8) & 0xFF, n & 0xFF])
    if n < 0x40000000:
        return bytes([0xC0 | (n >> 24),
                      (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])
    raise ValueError(f"Packet too large: {n}")


async def read_size(reader: asyncio.StreamReader) -> int:
    first = await reader.readexactly(1)
    tag = (first[0] >> 6) & 0x3
    extra = await reader.readexactly(tag) if tag else b""
    n = first[0] & 0x3F
    for b in extra:
        n = (n << 8) | b
    return n


async def read_framed(reader: asyncio.StreamReader) -> bytes:
    n = await read_size(reader)
    return await reader.readexactly(n)


async def write_framed(writer: asyncio.StreamWriter, payload: bytes):
    writer.write(encode_size(len(payload)) + payload)
    await writer.drain()


async def write_framed_burst(writer: asyncio.StreamWriter, payloads,
                             drain_every: int = 256) -> int:
    total = 0
    pending = []
    for i, payload in enumerate(payloads, 1):
        pending.append(encode_size(len(payload)) + payload)
        total += len(payload)
        if i % drain_every == 0:
            writer.write(b"".join(pending))
            pending.clear()
            await writer.drain()
    if pending:
        writer.write(b"".join(pending))
        await writer.drain()
    return total
