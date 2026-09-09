
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.obituary import (
    obituary_for_kill,
    render,
    victim_kind_for_damageable,
)

logger = get_logger(__name__)


def _file_npc_obituary(d, killer_auid, *, live_avatars) -> bool:
    kind = victim_kind_for_damageable(d)
    if kind is None:
        return False
    killer_name = ""
    _ke = live_avatars.get(int(killer_auid) & 0xFFFFFFFF) or {}
    killer_name = str(_ke.get("name") or "")
    obit = obituary_for_kill(kind, victim_name=d.name or "",
                             killer_name=killer_name)
    if obit is None:
        return False
    logger.info("Obituary filed: %s 0x%08x (%r) killed by 0x%08x%s. %s",
                d.kind, int(d.auid), d.name,
                int(killer_auid) & 0xFFFFFFFF,
                f" ({killer_name})" if killer_name else "",
                render(obit.kill) if hasattr(obit, "kill") else obit)
    return True
