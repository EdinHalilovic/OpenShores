
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import seachest as _sc
from openshores.gameplay.containers import _get_seachests, _persist_seachests
from openshores.protocol.atoms.gear import _pack_auitem_hash

logger = get_logger(__name__)


async def _seachest_wire_blob(conn, auid, *, _SEACHEST_STATES) -> bytes:
    try:
        chests = await _get_seachests(conn, auid, _SEACHEST_STATES=_SEACHEST_STATES)
        return _sc.pack_column(chests)
    except Exception as exc:
        logger.error('Sea chest wire emit for 0x%08x fell back to two empty hashes: %r.',
                     int(auid) & 0xFFFFFFFF, exc)
        return _pack_auitem_hash([]) + _pack_auitem_hash([])


async def _seachest_add(conn, auid, galaxy, cid, type_id, body, count=1, *,
                        _SEACHEST_STATES):
    chests = await _get_seachests(conn, auid, _SEACHEST_STATES=_SEACHEST_STATES)
    idx = _sc.chest_index(galaxy)
    chest = chests[idx]
    ok, reason = _sc.can_add(chest, cid, count)
    if not ok:
        logger.debug("Sea chest add for 0x%08x refused: cid %s x%s into "
                     "chest %d rejected by CanAddToSeaChest (%s).",
                     int(auid) & 0xFFFFFFFF, cid, count, idx, reason)
        return False, reason
    for i, e in enumerate(chest):
        if (int(e[0]) & 0xFFFF) == (int(cid) & 0xFFFF):
            chest[i] = (e[0], e[1], e[2], int(e[3]) + int(count))
            break
    else:
        chest.append((int(cid) & 0xFFFF, int(type_id) & 0xFF,
                      bytes(body), int(count)))
    await _persist_seachests(conn, auid, _SEACHEST_STATES=_SEACHEST_STATES)
    return True, None


async def _seachest_take(conn, auid, galaxy, cid, count=1, *, _SEACHEST_STATES):
    chests = await _get_seachests(conn, auid, _SEACHEST_STATES=_SEACHEST_STATES)
    idx = _sc.chest_index(galaxy)
    chest = chests[idx]
    for i, e in enumerate(chest):
        if (int(e[0]) & 0xFFFF) != (int(cid) & 0xFFFF):
            continue
        have = int(e[3])
        if have < int(count):
            return False, "chest holds %d of cid %d, asked for %d" % (
                have, cid, count)
        if have == int(count):
            chest.pop(i)
        else:
            chest[i] = (e[0], e[1], e[2], have - int(count))
        await _persist_seachests(conn, auid, _SEACHEST_STATES=_SEACHEST_STATES)
        return True, e
    return False, "cid %d is not in chest %d" % (cid, idx)
