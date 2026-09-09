
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import damageable as _dmg
from openshores.gameplay import story_npc as _snpc
from openshores.gameplay.natives import village as _nat
from openshores.gameplay.npc_pose import _npc_pose_for
from openshores.network.broadcast import _broadcast_to_peers
from openshores.protocol.atoms.daanimal import (
    pack_animal_update as _pack_animal_update,
)

logger = get_logger(__name__)


async def _push_npc_state(d, *, include_pose: bool = True,
                          _live_avatars: dict) -> bool:
    if d is None:
        return False
    pose = _npc_pose_for(d) if include_pose else None
    pkt = None
    try:
        if d.kind == _dmg.KIND_ANIMAL:
            pkt = _pack_animal_update(int(d.auid), hp=int(d.hp),
                                      pose=pose if pose is not None else None)
        elif d.kind == _dmg.KIND_STORY:
            st = None
            for _s in (getattr(_snpc, "_NPCS", None) or {}).values():
                if (int(_s.get("auid") or 0) & 0xFFFFFFFF) == int(d.auid):
                    st = _s
                    break
            if st is None:
                return False
            if pose is not None:  # noqa: E701  (kept for the branch below)
                st["pose"] = pose
                st["mode"] = "stay"
                st["goal"] = None
            st["hp"] = int(d.hp)
            import time as _t
            pkt = _snpc.build_cit_character_move(
                atom_id=int(d.auid), now_ms=int(_t.time() * 1000),
                x=st["xyz"][0], y=st["xyz"][1], z=st["xyz"][2],
                rx=st["rot"][0], ry=st["rot"][1], rz=st["rot"][2],
                name=st["name"], dna=st["dna"],
                empire_id=st.get("empire_id", 0),
                hit_points=int(d.hp), pose=pose)
        elif d.kind == _dmg.KIND_NATIVE:
            b = (getattr(_nat, "_IDLE_BODIES", None) or {}).get(int(d.auid))
            if b is None:
                return False
            if pose is not None:
                b["pose"] = pose
            b["hp"] = int(d.hp)
            xyz = b.get("xyz") or b.get("home") or (0.0, 0.0, 0.0)
            rot = b.get("rot") or (0.0, 0.0, 0.0)
            import time as _t
            pkt = _snpc.build_cit_character_move(
                atom_id=int(d.auid), now_ms=int(_t.time() * 1000),
                x=xyz[0], y=xyz[1], z=xyz[2],
                rx=rot[0], ry=rot[1], rz=rot[2],
                name=_nat.native_display_name(b.get("role", 0)),
                dna=b["dna"], hit_points=int(d.hp), pose=pose,
                scale_byte=int(b.get("mins_to_full_grown") or 0),
                role=int(b.get("role", 0)),
                tag=_nat.ATOM_TAG_CIT_INDIGENOUS)
    except Exception as exc:
        logger.error(f"[npc-state] build failed for 0x{int(d.auid):08x}: {exc!r}")
        return False
    if not pkt:
        return False
    try:
        sent = await _broadcast_to_peers(pkt, _live_avatars,
                                         label=f"npc-state/{d.kind}")
    except Exception as exc:
        logger.error(f"[npc-state] broadcast failed for 0x{int(d.auid):08x}: {exc!r}")
        return False
    logger.debug(f"[npc-state] 0x{int(d.auid):08x} ({d.name!r}) hp={d.hp}/{d.max_hp}"
                 + (f" pose=0x{pose:02x}" if pose is not None else "")
                 + f" -> {sent} peer(s)")
    return True
