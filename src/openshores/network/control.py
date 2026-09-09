

from __future__ import annotations

import asyncio
import functools
import json
import time
from typing import Awaitable, Callable, Dict

from openshores.core.logging import get_logger
from openshores.database.repositories import galaxy_admin
from openshores.network.chat import broadcast_system_message
from openshores.protocol.atoms.aucomm import SYSTEM_CHANNEL

logger = get_logger(__name__)


ControlCommand = Callable[..., Awaitable[str]]


async def _cmd_ping(line: str, *, live_avatars: dict, pool) -> str:
    return "OK pong\n"


async def _cmd_who(line: str, *, live_avatars: dict, pool) -> str:
    names = []
    for auid, ent in list(live_avatars.items()):
        names.append(f"0x{int(auid) & 0xFFFFFFFF:08x}"
                     f"={ent.get('name') or '?'}")
    return f"OK {len(names)} {' '.join(names)}\n"


async def _cmd_say(line: str, *, live_avatars: dict, pool) -> str:
    head, _, text = line.partition(" ")
    channel = SYSTEM_CHANNEL
    if ":" in head:
        channel = head.split(":", 1)[1] or SYSTEM_CHANNEL
    text = text.strip()
    if not text:
        return "ERR say needs text\n"
    else:
        n = await broadcast_system_message(live_avatars, text, channel=channel,
                                           pool=pool)
        return f"OK sent {n}\n"


def _parse_set(line: str, required) -> tuple[int, dict]:
    _cmd, _, rest = line.partition(" ")
    auid_tok, _, blob = rest.strip().partition(" ")
    if not auid_tok or not blob.strip():
        raise ValueError("Expected: <command> <auid> <json-object>")
    auid = int(auid_tok, 0)
    fields = json.loads(blob)
    if not isinstance(fields, dict):
        raise ValueError("Fields must be a JSON object")
    missing = [k for k in required if k not in fields]
    if missing:
        raise ValueError(f"Missing field(s): {', '.join(missing)}")
    extra = [k for k in fields if k not in required]
    if extra:
        raise ValueError(f"Unknown field(s): {', '.join(sorted(extra))}")
    return auid, fields


_SECTOR_FIELDS = ("name", "locX", "locY", "locZ")
_SYSTEM_FIELDS = ("name", "locX", "locY", "locZ", "parent_atom")
_WORLD_FIELDS = ("name", "parent_atom", "orbitZone", "orbitRadius",
                 "atmType", "atmDensity", "water", "radius")


def _set_reply(command: str, auid: int, created: bool) -> str:
    return (f"OK {command} 0x{int(auid) & 0xFFFFFFFF:08x} "
            f"{'created' if created else 'updated'}\n")


async def _cmd_sector_set(line: str, *, live_avatars: dict, pool) -> str:
    auid, f = _parse_set(line, _SECTOR_FIELDS)
    async with pool.acquire() as conn:
        created = await galaxy_admin.sector_set(
            conn, auid=auid, name=f["name"], loc_x=f["locX"],
            loc_y=f["locY"], loc_z=f["locZ"], now=int(time.time()))
    return _set_reply("sector.set", auid, created)


async def _cmd_system_set(line: str, *, live_avatars: dict, pool) -> str:
    auid, f = _parse_set(line, _SYSTEM_FIELDS)
    async with pool.acquire() as conn:
        created = await galaxy_admin.system_set(
            conn, auid=auid, name=f["name"], loc_x=f["locX"],
            loc_y=f["locY"], loc_z=f["locZ"],
            parent_atom=f["parent_atom"], now=int(time.time()))
    return _set_reply("system.set", auid, created)


async def _cmd_world_set(line: str, *, live_avatars: dict, pool) -> str:
    auid, f = _parse_set(line, _WORLD_FIELDS)
    async with pool.acquire() as conn:
        created = await galaxy_admin.world_set(
            conn, auid=auid, name=f["name"], parent_atom=f["parent_atom"],
            orbit_zone=f["orbitZone"], orbit_radius=f["orbitRadius"],
            atm_type=f["atmType"], atm_density=f["atmDensity"],
            water=f["water"], radius=f["radius"], now=int(time.time()))
    return _set_reply("world.set", auid, created)


CONTROL_COMMANDS: Dict[str, ControlCommand] = {
    "ping": _cmd_ping,
    "who": _cmd_who,
    "say": _cmd_say,
    "sector.set": _cmd_sector_set,
    "system.set": _cmd_system_set,
    "world.set": _cmd_world_set,
}

_TOKEN_COMMANDS = ("sector.set", "system.set", "world.set")


def _command_name(line: str) -> str | None:
    if line == "ping":
        return "ping"
    if line == "who":
        return "who"
    if line.startswith("say"):
        return "say"
    head = line.split(" ", 1)[0]
    if head in _TOKEN_COMMANDS:
        return head
    return None


async def handle_control(reader, writer, *, live_avatars: dict, pool) -> None:
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=10.0)
    except Exception as exc:
        logger.debug("Control connection sent no command line: %r", exc)
        try:
            writer.close()
        except Exception as close_exc:
            logger.debug("Control socket would not close: %r", close_exc)
        return
    line = (raw or b"").decode("utf-8", "replace").strip()
    reply = "ERR empty\n"
    try:
        if not line:
            reply = "ERR empty\n"
        else:
            name = _command_name(line)
            if name is None:
                reply = f"ERR unknown command {line.split(' ', 1)[0]!r}\n"
            else:
                reply = await CONTROL_COMMANDS[name](
                    line, live_avatars=live_avatars, pool=pool)
    except Exception as exc:
        logger.error("Control command %r failed: %r", line, exc)
        reply = f"ERR {exc!r}\n"
    try:
        writer.write(reply.encode("utf-8"))
        await writer.drain()
    except Exception as exc:
        logger.debug("Control reply was not delivered: %r", exc)
    try:
        writer.close()
    except Exception as exc:
        logger.debug("Control socket would not close: %r", exc)


async def _control_start(*, control_port: int, live_avatars: dict, pool):
    if not control_port:
        logger.info("Operator control socket disabled: control_port is 0.")
        return None
    try:
        server = await asyncio.start_server(
            functools.partial(handle_control,
                              live_avatars=live_avatars, pool=pool),
            "127.0.0.1", control_port)
    except Exception as exc:
        logger.error(f"[control] not started on 127.0.0.1:{control_port}: {exc!r}")
        return None
    logger.info(f"[control] listening on 127.0.0.1:{control_port} "
                f"(say / who / ping)")
    return server
