
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import skinning as _skin
from openshores.gameplay.combat.kill_reputation import _attacker_world_auid
from openshores.gameplay.gear_entry import _ground_item_quality
from openshores.network.ground_items import (
    _despawn_ground_item,
    _spawn_ground_item,
)
from openshores.protocol.atoms.item import _extract_cid_from_auitem_body

logger = get_logger(__name__)


async def _skin_ground_carcass(target_auid, actor_auid, tool_cid,
                               tool_quality=0, *,
                               alloc_daitem_auid,
                               _live_avatars,
                               _DROPPED_ITEMS,
                               _DYNAMIC_SCENE_AUIDS,
                               world_atom_auids) -> bool:
    tid = int(target_auid) & 0xFFFFFFFF
    entry = _DROPPED_ITEMS.get(tid)
    if entry is None:
        return False
    if not (_skin.is_skinning_tool(tool_cid) or _skin.is_dna_tool(tool_cid)):
        return False
    try:
        target_cid = _extract_cid_from_auitem_body(bytes(entry["body"]))
    except Exception as exc:
        logger.debug(f"[skin] 0x{tid:08x} has no readable AuItem body: {exc!r}")
        return False
    res = _skin.use_tool_on_carcass(
        int(target_cid), int(tool_cid),
        target_quality=_ground_item_quality(entry),
        tool_quality=int(tool_quality))
    if not res.produced:
        logger.info(f"[skin] 0x{int(actor_auid):08x} used cid {tool_cid} on "
                    f"0x{tid:08x} (cid {target_cid}): {res.outcome}")
        return True
    world = 0
    try:
        world = int.from_bytes(bytes(entry["parent"]), "big") & 0xFFFFFFFF
    except Exception:
        world = _attacker_world_auid(
            actor_auid, _live_avatars=_live_avatars,
            world_atom_auids=world_atom_auids)
    xyz = entry.get("xyz") or (0.0, 0.0, 0.0)
    if res.input_consumed:
        try:
            await _despawn_ground_item(
                tid, tag="skin", _DROPPED_ITEMS=_DROPPED_ITEMS,
                _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
        except Exception as exc:
            logger.error(f"[skin] could not remove the carcass 0x{tid:08x}: {exc!r}")
    made = 0
    for out in res.outputs:
        for _ in range(max(1, int(out.quantity))):
            try:
                if await _spawn_ground_item(
                        parent_world_auid=world, xyz=xyz, cid=int(out.cid),
                        quality=int(out.quality), tag="skin",
                        alloc_daitem_auid=alloc_daitem_auid,
                        _live_avatars=_live_avatars,
                        _DROPPED_ITEMS=_DROPPED_ITEMS,
                        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS):
                    made += 1
            except Exception as exc:
                logger.error(f"[skin] yield cid={out.cid} failed: {exc!r}")
    _yield = ", ".join(_skin.describe_output(o) for o in res.outputs)
    logger.info(f"[skin] 0x{int(actor_auid):08x} skinned 0x{tid:08x} (cid {target_cid}) with cid {tool_cid}: {made} item(s). {_yield}"
                + ("" if res.tool_spared else " -- the tool took wear"))
    return True
