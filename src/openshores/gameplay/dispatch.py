
from __future__ import annotations

from typing import Awaitable, Callable, Dict


OpcodeHandler = Callable[..., Awaitable[None]]

OPCODE_HANDLERS: Dict[int, OpcodeHandler] = {}


def register(op: int) -> Callable[[OpcodeHandler], OpcodeHandler]:
    def _wrap(fn: OpcodeHandler) -> OpcodeHandler:
        if op in OPCODE_HANDLERS:
            raise ValueError(
                f"Opcode 0x{op:02X} already registered by {OPCODE_HANDLERS[op].__qualname__!r}; refusing to overwrite with {fn.__qualname__!r}")
        OPCODE_HANDLERS[op] = fn
        return fn
    return _wrap


def is_registered(op: int) -> bool:
    return op in OPCODE_HANDLERS


def lookup(op: int) -> OpcodeHandler | None:
    return OPCODE_HANDLERS.get(op)


def list_registered() -> list[int]:
    return sorted(OPCODE_HANDLERS.keys())
