
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

async def _spawn_ground_item(parent_world_auid: int, xyz: tuple, cid: int,
                             quality: int = 100, integrity: int = 100,
                             rotation: tuple = (0.0, 0.0, 0.0),
                             tag: str = "drop", *, alloc_daitem_auid,
                             _live_avatars, _DROPPED_ITEMS,
                             _DYNAMIC_SCENE_AUIDS) -> int:
    parent = int(parent_world_auid) & 0xFFFFFFFF
    if not parent or not xyz:
        return 0
    auid = alloc_daitem_auid()
    body = (bytes([0x04]) + struct.pack(">H", int(cid) & 0xFFFF)
            + bytes([int(integrity) & 0xFF, int(quality) & 0xFF]))
    parent_b = parent.to_bytes(4, "big")
    now_ms = int(_t.time() * 1000)
    xyz_t = tuple(float(v) for v in xyz)
    rot_t = tuple(float(v) for v in rotation)
    try:
        pkt = _build_daitem_drop_packet(
            item_auid_int=auid, parent_auid=parent_b, xyz=xyz_t,
            item_typeId=0x01, item_body=body, rotation=rot_t,
            time_created_ms=now_ms)
    except Exception as exc:
        logger.warning("[%s] packet build err: %r", tag, exc)
        return 0
    _DROPPED_ITEMS[auid] = {
        "parent": parent_b, "xyz": xyz_t, "typeId": 0x01, "body": body,
        "rotation": rot_t, "time_created_ms": now_ms,
    }
    _DYNAMIC_SCENE_AUIDS.add(auid)
    try:
        sent = await _broadcast_to_peers(pkt, _live_avatars)
        logger.info("[%s] DaItem 0x%08x cid=%s q=%s at %s -> %d peer(s)",
                    tag, auid, cid, quality,
                    tuple(round(v, 1) for v in xyz_t), sent)
    except Exception as exc:
        logger.warning("[%s] broadcast err: %r", tag, exc)
    try:
        _queue = get_queue()
        if _queue is not None:
            _queue.submit(
                "dropped_item_insert", auid=auid, parent_auid=parent,
                xyz=xyz_t, rotation=rot_t,
                type_id=0x01, body=body, time_created_ms=now_ms)
    except Exception as exc:
        logger.warning("[%s] persist err: %r", tag, exc)
    asyncio.create_task(_daitem_lifecycle(auid))
    return auid


async def _despawn_ground_item(item_auid, tag: str = "despawn", *,
                               _DROPPED_ITEMS,
                               _DYNAMIC_SCENE_AUIDS) -> bool:
    tid = int(item_auid) & 0xFFFFFFFF
    if tid not in _DROPPED_ITEMS:
        return False
    _DYNAMIC_SCENE_AUIDS.discard(tid)
    del _DROPPED_ITEMS[tid]
    try:
        _queue = get_queue()
        if _queue is not None:
            _queue.submit("dropped_item_delete", auid=tid)
    except Exception as exc:
        logger.warning("[%s] sql delete failed for 0x%08x: %r",
                       tag, tid, exc)
    logger.info("[%s] ground item 0x%08x removed from the world",
                tag, tid)
    return True
