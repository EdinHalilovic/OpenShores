
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.person import _lookup_person_by_auid
from openshores.protocol.dhdna import DhDNA

logger = get_logger(__name__)


_DEFAULT_ACTIVE_CYCLE = [(1,0,0), (1,1,0),
                         (9,0,0), (9,1,0), (9,2,0), (9,3,0),
                         (5,0,0)]


def _DhDNA_from_bytes(raw):
    try:
        return DhDNA.from_bytes(bytes(raw))
    except Exception as exc:
        logger.debug("DhDNA view over a %s refused (%r); the caller gets None.",
                     type(raw).__name__, exc)
        return None


def _stamina_byte(actor_auid: int = 0, *, _tock_state) -> int:
    ent = _tock_state.get(int(actor_auid) & 0xFFFFFFFF) or {}
    try:
        return int(ent.get("stamina", 0x7F)) & 0xFF
    except (TypeError, ValueError) as exc:
        logger.warning('Stamina for actor %r will not convert (%r).',
                       actor_auid, exc)
        return 0x7F


async def _mins_to_full_grown_for_actor(conn, actor_auid: int = 0) -> int:
    if not int(actor_auid or 0):
        return 0
    try:
        row = await _lookup_person_by_auid(conn, int(actor_auid))
    except Exception as exc:
        logger.warning("MinsToFullGrown lookup for actor %r failed (%r); treated as an adult.", actor_auid, exc)
        return 0
    if not isinstance(row, dict):
        return 0
    try:
        return max(0, int(row.get("minsToFullGrown") or 0))
    except Exception as exc:
        logger.warning('a_Person.minsToFullGrown for actor %r will not convert (%r).',
                       actor_auid, exc)
        return 0
