
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.creature_state import _build_creature_state_pkt
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


async def _push_creature_state(writer, auid, *, hp, pose,
                               hunger, stamina,
                               tock_state,
                               agent_bits_for):
    if writer is None:
        return
    try:
        if writer.is_closing():
            return
    except Exception as exc:
        logger.debug(f"[push-creature] auid=0x{int(auid):08x} writer state "
                     f"unreadable: {exc!r}")
        return
    try:
        body = _build_creature_state_pkt(
            int(auid), hp=int(hp), pose=int(pose),
            hunger=int(hunger), stamina=int(stamina),
            tock_state=tock_state, agent_bits_for=agent_bits_for)
        await write_framed(writer, body)
    except Exception as _pcs_e:
        logger.error(f"[push-creature] auid=0x{int(auid):08x} write err: "
                     f"{_pcs_e!r}")
