from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import asyncpg

from openshores.core.logging import get_logger
from openshores.database.pool import _now_ms
from openshores.database.repositories import native as _rows
from openshores.database.repositories.native import (
    NATIVE_AUID_BASE,
    NATIVE_COLUMN_NAMES,
    _table_exists,
    _u32,
)

logger = get_logger(__name__)


def _assert_auid_base_matches() -> bool:
    from openshores.gameplay.natives import village as _n
    return int(getattr(_n, "NATIVE_AUID_BASE", NATIVE_AUID_BASE)) == \
        NATIVE_AUID_BASE


def _seed_mins_to_full_grown(dna: bytes, role: int) -> int:
    from openshores.gameplay.natives import village as _n
    return int(_n.seed_mins_to_full_grown(bytes(dna), int(role))) & 0xFF


def native_row(*, id: int, idp: int, xyz: Sequence[float],
               rot: Sequence[float], name: str, role: int, dna: bytes,
               hp: int = 100, hunger: int = 1000, stamina: int = 100,
               pose: int = 0x24, sex: int = 0, islefty: int = 0,
               homeworld: Optional[int] = None, interlocutor: int = 0,
               now_ms: Optional[int] = None, **overrides) -> Dict[str, Any]:
    if now_ms is None:
        now_ms = _now_ms()
    if len(bytes(dna)) != 24:
        raise ValueError("DhDNA must be exactly 24 bytes, got %d"
                         % len(bytes(dna)))
    row: Dict[str, Any] = {
        "id": _u32(id), "idp": _u32(idp),
        "locX": float(xyz[0]), "locY": float(xyz[1]), "locZ": float(xyz[2]),
        "rotX": float(rot[0]), "rotY": float(rot[1]), "rotZ": float(rot[2]),
        "timeCreate": int(now_ms), "timeModified": int(now_ms),
        "timeTick": int(now_ms), "timeTock": int(now_ms), "timeDeath": 0,
        "name": str(name), "allegiance": 0, "arenaTeam": 0,
        "conditions": None, "damageHistory": None,
        "hunger": int(hunger), "seatIndex": 0, "hp": int(hp),
        "sex": int(sex), "dna": bytes(dna), "islefty": int(bool(islefty)),
        "pose": int(pose), "whichConsole": 0,
        "atRest": 1,
        "vecX": 0.0, "vecY": 0.0, "vecZ": 0.0,
        "stamina": int(stamina),
        "minsToFullGrown": _seed_mins_to_full_grown(dna, role),
        "lineage": 0,
        "ship": 0, "orders": None, "posture": 0, "inv": None,
        "homeworld": _u32(idp if homeworld is None else homeworld),
        "interlocutor": _u32(interlocutor),
        "role": int(role) & 0xFF,
    }
    row.update({k: v for k, v in overrides.items()
                if k in NATIVE_COLUMN_NAMES})
    return row


async def save_conversation_state(
        conn: asyncpg.Connection, world_auid: int, *,
        _STATE,
        _REPUTATION) -> Tuple[int, int]:
    w = _u32(world_auid)
    if not await _table_exists(conn, "a_CitIndigenous"):
        return (0, 0)
    ours = await _rows.world_native_ids(conn, w)
    pairs: List[Tuple[int, int]] = []
    for auid, st in _STATE.items():
        aid = _u32(auid)
        if aid not in ours:
            continue
        pairs.append((aid, _u32(st.get("interlocutor"))))
    n_nat = await _rows.store_interlocutors(conn, pairs)
    items: List[Tuple[int, int]] = []
    for (rw, player), rep in _REPUTATION.items():
        if _u32(rw) != w:
            continue
        items.append((_u32(player), int(rep)))
    n_rep = await _rows.store_reputations(conn, w, items)
    return (n_nat, n_rep)


async def restore_conversation_state(
        conn: asyncpg.Connection, world_auid: int, *,
        _state,
        set_contacted) -> Tuple[int, int]:
    w = _u32(world_auid)
    n_nat = 0
    for aid, who in await _rows.stored_interlocutors(conn, w):
        _state(_u32(aid))["interlocutor"] = _u32(who)
        n_nat += 1
    n_rep = 0
    for player, rep in await _rows.stored_reputations(conn, w):
        set_contacted(w, _u32(player), int(rep))
        n_rep += 1
    if n_nat or n_rep:
        logger.info("Restored %d interlocutor(s) and %d reputation(s) for "
                    "world 0x%08X.", n_nat, n_rep, w)
    return (n_nat, n_rep)


async def save_drift(conn: asyncpg.Connection, world_auid: int,
                     moved: Optional[Sequence[Sequence[Any]]] = None) -> int:
    if moved is None:
        from openshores.gameplay.natives import village as _n
        w = _u32(world_auid)
        moved = []
        for auid, b in _n._IDLE_BODIES.items():
            if _u32(b.get("world_auid")) != w:
                continue
            xyz = b.get("xyz") or b.get("home")
            rot = _n.gravity_align_euler(xyz, float(b.get("heading", 0.0)))
            moved.append((auid, xyz, rot, float(b.get("tilt") or 0.0)))
    return await _rows.save_drift_rows(conn, moved)


async def generate_village_rows(conn: asyncpg.Connection, world_auid: int, *,
                                anchor_xyz: Sequence[float],
                                dna24: bytes, seed: int = 1,
                                auid_base: Optional[int] = None,
                                pop: Optional[int] = None,
                                terrain: Optional[Sequence[float]] = None,
                                size: Optional[int] = None,
                                centre_offset_ft: Optional[float] = None,
                                now_ms: Optional[int] = None,
                                _DYNAMIC_SCENE_AUIDS: set,
                                ) -> Tuple[List[Dict[str, Any]],
                                           Dict[int, Dict[str, Any]],
                                           Tuple[float, float, float]]:
    from openshores.gameplay.natives import village as _n
    if auid_base is None:
        auid_base = await _rows.allocate_block(conn,
                                               world_auid) or NATIVE_AUID_BASE
    placements = _n.plan_native_placements(
        anchor_xyz, pop=pop, seed=seed, auid_base=auid_base,
        register_manifest=False, centre_offset_ft=centre_offset_ft,
        terrain=terrain, size=size,
        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
    centre = _n.village_centre_xyz(anchor_xyz, centre_offset_ft)
    headings = _n.plan_village_headings(placements, centre, anchor_xyz,
                                        seed=seed)
    rows: List[Dict[str, Any]] = []
    homes: Dict[int, Dict[str, Any]] = {}
    for (auid, role, label, xyz), heading in zip(placements, headings):
        rot = _n.gravity_align_euler(xyz, heading)
        rows.append(native_row(
            id=auid, idp=int(world_auid), xyz=xyz, rot=rot,
            name=_n.native_display_name(role), role=role, dna=dna24,
            now_ms=now_ms))
        homes[_u32(auid)] = {"label": label, "home": tuple(float(c)
                                                           for c in xyz),
                             "heading": float(heading)}
    return rows, homes, tuple(float(c) for c in centre)


async def load_or_create_village(conn: asyncpg.Connection, world_auid: int, *,
                                 anchor_xyz: Sequence[float],
                                 dna24: bytes, seed: int = 1,
                                 pop: Optional[int] = None,
                                 terrain: Optional[Sequence[float]] = None,
                                 size: Optional[int] = None,
                                 centre_offset_ft: Optional[float] = None,
                                 now_ms: Optional[int] = None,
                                 _DYNAMIC_SCENE_AUIDS: set,
                                 ) -> Optional[Dict[str, Any]]:
    existing = await _rows.load_village(conn, world_auid)
    if existing is not None:
        existing["created"] = False
        return existing

    base = await _rows.allocate_block(conn, world_auid)
    if base is None:
        return None
    rows, homes, centre = await generate_village_rows(
        conn, world_auid, anchor_xyz=anchor_xyz, dna24=dna24, seed=seed,
        auid_base=base, pop=pop, terrain=terrain, size=size,
        centre_offset_ft=centre_offset_ft, now_ms=now_ms,
        _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
    await _rows.save_village(conn, world_auid, rows, seed=seed, dna=dna24,
                             centre_xyz=centre, homes=homes)
    out = await _rows.load_village(conn, world_auid)
    if out is None:
        out = {"world_auid": _u32(world_auid), "auid_base": base,
               "seed": int(seed), "pop": len(rows), "dna": bytes(dna24),
               "centre_xyz": centre, "rows": rows, "homes": homes}
    out["created"] = True
    return out


def village_placements(village: Dict[str, Any], *,
                       register_manifest: bool = True,
                       _DYNAMIC_SCENE_AUIDS: set,
                       ) -> List[Tuple[int, int, str,
                                       Tuple[float, float, float]]]:
    out = []
    homes = village.get("homes") or {}
    for r in village["rows"]:
        aid = _u32(r["id"])
        label = (homes.get(aid) or {}).get("label") or str(r.get("name") or "")
        out.append((aid, int(r.get("role") or 0), label,
                    (float(r["locX"]), float(r["locY"]), float(r["locZ"]))))
        if register_manifest:
            _DYNAMIC_SCENE_AUIDS.add(aid)
    return out


def build_entries(village: Dict[str, Any], *,
                  now_ms: Optional[int] = None,
                  base_flags: Optional[int] = None,
                  terrain: Optional[Sequence[float]] = None,
                  size: Optional[int] = None,
                  register_manifest: bool = True,
                  register_idle: bool = True,
                  _DYNAMIC_SCENE_AUIDS: set,
                  ) -> List[Tuple[str, bytes]]:
    from openshores.gameplay.native_atom import (ATOM_TAG_CIT_INDIGENOUS,
                                                 BASEFLAGS_FULL,
                                                 build_cit_indigenous)
    if base_flags is None:
        base_flags = BASEFLAGS_FULL
    if now_ms is None:
        now_ms = _now_ms()
    homes = village.get("homes") or {}
    entries: List[Tuple[str, bytes]] = []
    for r in village["rows"]:
        aid = _u32(r["id"])
        label = (homes.get(aid) or {}).get("label") or str(r.get("name") or "")
        dna = bytes(r.get("dna") or b"")
        if len(dna) != 24:
            logger.warning(
                'Villager 0x%08X has a %d-byte DNA.',
                aid, len(dna))
            continue
        tilt = float((homes.get(aid) or {}).get("tilt") or 0.0)
        mins = int(r.get("minsToFullGrown") or 0)
        pkt = build_cit_indigenous(
            atom_id=aid,
            parent_id=_u32(r.get("idp") or village["world_auid"]),
            now_ms=now_ms,
            x=float(r["locX"]), y=float(r["locY"]), z=float(r["locZ"]),
            rx=float(r["rotX"]), ry=float(r["rotY"]), rz=float(r["rotZ"]),
            head_tilt=tilt,
            name=str(r.get("name") or "Native"),
            role=int(r.get("role") or 0),
            dna=dna,
            pose=int(r.get("pose") or 0x24),
            hunger=int(r.get("hunger") or 0),
            gender=int(r.get("sex") or 0),
            left_handed=bool(r.get("islefty")),
            scale_byte=mins,
            base_flags=int(base_flags),
            tag=ATOM_TAG_CIT_INDIGENOUS,
        )
        entries.append(("DaCitIndigenous/%s" % (label or "Adult"), pkt))

        if register_manifest:
            _DYNAMIC_SCENE_AUIDS.add(aid)
        if register_idle:
            from openshores.gameplay.natives import village as _n
            try:
                h = homes.get(aid) or {}
                _n.register_idle_body(
                    auid=aid, role=int(r.get("role") or 0),
                    label=label or "Adult",
                    world_auid=_u32(r.get("idp") or village["world_auid"]),
                    home_xyz=h.get("home", (float(r["locX"]),
                                            float(r["locY"]),
                                            float(r["locZ"]))),
                    heading=float(h.get("heading", r.get("rotZ") or 0.0)),
                    dna24=dna,
                    seed=int(village.get("seed") or 1),
                    terrain=terrain, size=size, base_flags=int(base_flags),
                    mins_to_full_grown=mins)
                if tilt:
                    _rec = _n._IDLE_BODIES.get(aid)
                    if _rec is not None:
                        _rec["tilt"] = tilt
                        _rec["sent_tilt"] = tilt
            except Exception as exc:                        # noqa: BLE001
                logger.error(
                    'Idle registration failed for 0x%08X (%r).', aid, exc)
    return entries


__all__ = [
    "native_row",
    "save_drift",
    "save_conversation_state", "restore_conversation_state",
    "generate_village_rows", "load_or_create_village",
    "village_placements", "build_entries",
]
