
from __future__ import annotations


# Chat frames start 0x0A. On the scene socket the first byte is an atom
# class tag and 0x0A is DaCitWorker, so the client builds the wrong object
# and crashes in AuGear::Weight. Never fall back to the scene writer.
def _chat_only_writer(entry):
    w = (entry or {}).get("chat_writer")
    if w is None:
        return None
    try:
        if w.is_closing():
            return None
    except Exception:
        return None
    return w
