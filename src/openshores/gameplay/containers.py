
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.database.repositories.person import (
    read_person_state as _sql_read_person_state,
    update_person_state as _ups,
)
from openshores.gameplay import seachest as _sc
from openshores.protocol.atoms.container import (
    _container_decode_body,
    _container_encode_body,
)
from openshores.protocol.atoms.item_state import _read_auitem_cid_from_body

logger = get_logger(__name__)


async def _get_seachests(conn, auid, *, _SEACHEST_STATES):
    auid = int(auid) & 0xFFFFFFFF
    cached = _SEACHEST_STATES.get(auid)
    if cached is not None:
        return cached
    blob = None
    try:
        st = await _sql_read_person_state(conn, auid) or {}
        blob = st.get("seaChest")
    except Exception as exc:
        logger.error("Sea chest SQL read failed for 0x%08x: %r. "
                     "Loading empty chests.", auid, exc)
    try:
        chests = _sc.unpack_column(blob)
    except Exception as exc:
        logger.error('Sea chest column for 0x%08x is undecodable (%r).',
                     auid, exc)
        chests = [[] for _ in range(_sc.CHEST_COUNT)]
    _SEACHEST_STATES[auid] = chests
    total = sum(len(c) for c in chests)
    if total:
        logger.debug("Sea chests for 0x%08x: %d entr(ies) loaded (%s).",
                     auid, total,
                     ", ".join("chest%d=%d" % (i, len(c))
                               for i, c in enumerate(chests)))
    return chests


async def _persist_seachests(conn, auid, *, _SEACHEST_STATES) -> bool:
    auid = int(auid) & 0xFFFFFFFF
    chests = _SEACHEST_STATES.get(auid)
    if chests is None:
        return False
    try:
        blob = _sc.pack_column(chests)
        return bool(await _ups(conn, auid, seaChest=blob))
    except Exception as exc:
        logger.error("Sea chest persist failed for 0x%08x: %r.",
                     auid, exc)
        return False


def _container_pop_nested(body, key):
    base, capacity, nested = _container_decode_body(body)
    for i, entry in enumerate(nested):
        if (int(entry[0]) & 0xFF) == (int(key) & 0xFF):
            popped_tid  = int(entry[1]) & 0xFF
            popped_body = bytes(entry[2])
            del nested[i]
            new_body = _container_encode_body(
                base, capacity, nested)
            return popped_tid, popped_body, new_body
    return None


def _container_add_nested(body, src_entry, capacity_hint=None):
    base, capacity, nested = _container_decode_body(body)
    if capacity_hint is not None:
        capacity = max(int(capacity), int(capacity_hint) & 0xFF)
    cap = max(1, int(capacity))
    if len(nested) >= cap:
        return None
    used_keys = {int(n[0]) & 0xFF for n in nested}
    new_key = None
    for k in range(1, cap + 1):
        if k not in used_keys:
            new_key = k
            break
    if new_key is None:
        return None
    nested.append([new_key & 0xFF,
                   int(src_entry[2]) & 0xFF,
                   bytes(src_entry[3])])
    return _container_encode_body(base, capacity, nested)


_HARDCODED_CONTAINERS = {
    107: (12, 20, "Crate"),
    109: ( 4,  5, "Knapsack"),
    110: ( 6,  8, "Backpack"),
    293: ( 5,  3, "UtilityPouch"),
    294: ( 8, 12, "GravPack"),
}


def _is_container_cid(cid, *, CONTAINER_CIDS):
    return int(cid) & 0xFFFF in CONTAINER_CIDS


def _upgrade_to_container(typeId, body, cid=None, *, CONTAINER_CAPACITIES):
    if int(typeId) in (0x0B, 0x12):
        return int(typeId), bytes(body)
    if int(typeId) != 0x01:
        return int(typeId), bytes(body)
    if cid is None:
        cid = _read_auitem_cid_from_body(bytes(body))
    pw, ph = CONTAINER_CAPACITIES.get(int(cid) & 0xFFFF, (4, 4))
    capacity = max(1, int(pw) * int(ph)) & 0xFF
    return 0x12, (bytes(body)
                  + bytes([capacity, 0xF1, 0]))
