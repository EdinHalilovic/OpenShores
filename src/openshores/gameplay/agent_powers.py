
from __future__ import annotations

from openshores.core.logging import get_logger

logger = get_logger(__name__)


RANK_PLAYER = 0
RANK_AGENT = 3
RANK_PROGRAMMER = 4
RANK_ARCHITECT = 5

RANK_NAMES = {
    RANK_AGENT: "Agent",
    RANK_PROGRAMMER: "Programmer",
    RANK_ARCHITECT: "Architect",
}

BIT_ANIMAL = 0x01
BIT_ENTITY = 0x02
BIT_INVISIBLE = 0x04
BIT_POWERS = 0x08
BIT_INCOGNITO = 0x10
BIT_INVINCIBLE = 0x20

BIT_NAMES = (
    (BIT_INVINCIBLE, "Invincible"),
    (BIT_INVISIBLE, "Invisible"),
    (BIT_ANIMAL, "Animal"),
    (BIT_ENTITY, "Entity"),
    (BIT_INCOGNITO, "Incognito"),
)


def _default_bits() -> int:
    return 0x00


def agent_bits_for(agent_bits: dict, auid) -> int:
    return int(agent_bits.get(int(auid) & 0xFFFFFFFF, _default_bits())) & 0x3F


def set_agent_bits(agent_bits: dict, auid, bits: int, *,
                   live_avatars: dict, pb2_last_cursor: dict) -> int:
    auid = int(auid) & 0xFFFFFFFF
    bits = int(bits) & 0x3F
    old = agent_bits_for(agent_bits, auid)
    agent_bits[auid] = bits
    if old != bits:
        patch_cached_pb2_bits(live_avatars, auid, old, bits,
                              pb2_last_cursor=pb2_last_cursor)
    return bits


def rank_for(agent_rank: dict, auid) -> int:
    auid = int(auid) & 0xFFFFFFFF
    if auid in agent_rank:
        return int(agent_rank[auid])
    return RANK_ARCHITECT


def set_rank(agent_rank: dict, auid, rank: int) -> int:
    rank = int(rank) & 0xFF
    agent_rank[int(auid) & 0xFFFFFFFF] = rank
    return rank


def is_agent(agent_rank: dict, auid) -> bool:
    return rank_for(agent_rank, auid) >= RANK_AGENT


def is_programmer(agent_rank: dict, auid) -> bool:
    return rank_for(agent_rank, auid) >= RANK_PROGRAMMER


def is_architect(agent_rank: dict, auid) -> bool:
    return rank_for(agent_rank, auid) == RANK_ARCHITECT


def powers_on(agent_bits: dict, auid) -> bool:
    return bool(agent_bits_for(agent_bits, auid) & BIT_POWERS)


def describe_bits(bits: int) -> str:
    parts = [name for bit, name in BIT_NAMES if bits & bit]
    return ", ".join(parts) if parts else "none"


def resolve_actor(live_avatars: dict, auid) -> int:
    auid = int(auid or 0) & 0xFFFFFFFF
    if auid:
        return auid
    live = live_avatars
    if len(live) == 1:
        only = int(next(iter(live))) & 0xFFFFFFFF
        logger.info("A chat frame arrived with no avatar bound; attributing "
                    "it to the only avatar on line, 0x%08x.", only)
        return only
    if live:
        logger.warning('A chat frame arrived with no avatar bound and %d avatars are on line.', len(live))
    return 0


def _actor_entry(live_avatars: dict, auid):
    return live_avatars.get(resolve_actor(live_avatars, auid))


def patch_cached_pb2_bits(live_avatars: dict, actor_auid: int, old_bits: int,
                          new_bits: int, *, pb2_last_cursor: dict) -> bool:
    entry = _actor_entry(live_avatars, actor_auid)
    if entry is None:
        return False
    pb2 = entry.get("pb2")
    if not pb2:
        return False
    old_bits = int(old_bits) & 0x3F
    new_bits = int(new_bits) & 0x3F
    if old_bits == new_bits:
        return True
    last = pb2_last_cursor.get(id(pb2))
    if last is None:
        last = (9, 0, 0)
    for gate in (0x00, 0x80):
        ab = old_bits | gate
        idx = pb2.find(bytes([ab, last[0], last[1], last[2]]))
        if idx < 0:
            continue
        patched = pb2[:idx] + bytes([new_bits | gate]) + pb2[idx + 1:]
        if len(patched) != len(pb2):
            return False
        entry["pb2"] = patched
        pb2_last_cursor[id(patched)] = tuple(last)
        logger.debug("Cached pb2 agent-bits at 0x%x: 0x%02x -> 0x%02x.",
                     idx, ab, new_bits | gate)
        return True
    logger.warning("The cached pb2 for 0x%08x has no agent-bits marker "
                   "0x%02x+%s, so a later re-send may revert the change.",
                   int(actor_auid) & 0xFFFFFFFF, old_bits, last)
    return False
