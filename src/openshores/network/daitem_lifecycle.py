
from __future__ import annotations

from openshores.core.logging import get_logger

logger = get_logger(__name__)


async def _daitem_keepalive(item_auid_int: int) -> None:
    logger.info('auid=0x%08x disabled (HZ_DAITEM_KEEPALIVE_ENABLED=0).',
                item_auid_int)


async def _daitem_lifecycle(item_auid_int: int) -> None:
    await _daitem_keepalive(item_auid_int)
