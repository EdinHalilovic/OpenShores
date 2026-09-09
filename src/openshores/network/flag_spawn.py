
from __future__ import annotations

import asyncio
import struct
import time as _t

from openshores.core.logging import get_logger
from openshores.database.journal import get_queue
from openshores.network.broadcast import _broadcast_to_peers
from openshores.network.daitem_lifecycle import _daitem_lifecycle
from openshores.protocol.atoms.daitem_drop import _build_daitem_drop_packet

logger = get_logger(__name__)

_FLAG_CID = 1


async def spawn_world_flag(actor_auid: int, parent_world_auid: int,
                           flag_cid: int = None, quality: int = 100,
                           xyz: tuple = None, *, alloc_daitem_auid,
                           _tock_state, _live_avatars, _DROPPED_ITEMS,
                           _DYNAMIC_SCENE_AUIDS):
    actor = int(actor_auid) & 0xFFFFFFFF
    parent = int(parent_world_auid) & 0xFFFFFFFF
    if flag_cid is None:
        flag_cid = _FLAG_CID
    ent = _tock_state.get(actor) or _live_avatars.get(actor) or {}
    if xyz is None:
        xyz = ent.get("xyz") or (_live_avatars.get(actor, {}) or {}).get("xyz")
    if not xyz:
        logger.warning("No live position for 0x%08x; flag not placed", actor)
        return None
    rot = ent.get("last_rotation") or (0.0, 0.0, 0.0)
    auid = alloc_daitem_auid()
    body = bytes([0x04]) + struct.pack(">H", int(flag_cid) & 0xFFFF) + \
        bytes([100, int(quality) & 0xFF])
    parent_b = parent.to_bytes(4, "big")
    now_ms = int(_t.time() * 1000)
    try:
        pkt = _build_daitem_drop_packet(
            item_auid_int=auid, parent_auid=parent_b, xyz=xyz,
            item_typeId=0x01, item_body=body, rotation=rot,
            time_created_ms=now_ms)
    except Exception as exc:
        logger.warning("Packet build err: %r", exc)
        return None
    _DROPPED_ITEMS[auid] = {
        "parent": parent_b, "xyz": tuple(float(v) for v in xyz),
        "typeId": 0x01, "body": body,
        "rotation": tuple(float(v) for v in rot), "time_created_ms": now_ms,
    }
    _DYNAMIC_SCENE_AUIDS.add(auid)
    try:
        sent = await _broadcast_to_peers(pkt, _live_avatars)
        logger.info("Flag DaItem 0x%08x cid=%s at %s parent=0x%08x -> %d peer(s)",
                    auid, flag_cid, tuple(round(float(v), 1) for v in xyz),
                    parent, sent)
    except Exception as exc:
        logger.warning("Broadcast err: %r", exc)
    try:
        _queue = get_queue()
        if _queue is not None:
            _queue.submit(
                "dropped_item_insert", auid=auid, parent_auid=parent,
                xyz=tuple(float(v) for v in xyz),
                rotation=tuple(float(v) for v in rot), type_id=0x01,
                body=body, time_created_ms=now_ms)
    except Exception as exc:
        logger.warning("Persist err: %r", exc)
    asyncio.create_task(_daitem_lifecycle(auid))
    return auid
