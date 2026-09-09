
from __future__ import annotations

_ACTIVE_CHAT_WRITER = None

_active_chat_writer = None


def set_active_chat_writer(writer) -> None:
    global _active_chat_writer
    _active_chat_writer = writer
