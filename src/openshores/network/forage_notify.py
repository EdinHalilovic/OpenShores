
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.network.agent import notify, notify_thought

logger = get_logger(__name__)


async def _forage_notify(actor_auid: int, text: str, *,
                         live_avatars: dict) -> None:
    try:
        if await notify_thought(live_avatars, int(actor_auid), text):
            return
        logger.debug('The forage Thought for 0x%08x was not delivered.', int(actor_auid))
        await notify(live_avatars, int(actor_auid), text)
    except Exception as exc:                            # noqa: BLE001
        logger.warning("Forage notify failed for 0x%08x: %r",
                       int(actor_auid), exc)
