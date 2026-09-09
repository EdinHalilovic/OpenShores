
from __future__ import annotations

import json

from openshores.core.logging import get_logger
from openshores.database.repositories.person import update_person_state
from openshores.gameplay import gear_wear, manufacturing
from openshores.gameplay.worldgen import zone_resources as zr
from openshores.protocol.atoms.container import (
    _container_decode_body,
    _container_encode_body,
)
from openshores.protocol.atoms.gear import _pack_au_gear
from openshores.protocol.atoms.item import _extract_cid_from_auitem_body

logger = get_logger(__name__)

_RECIPES = None

_TYPEID_ITEM = 0x01
_TYPEID_CONTAINER = 0x12

_COMMODITY_ELECTRICITY = 3
_COMMODITY_MONEY = 0x9D

_VEHICLE_CIDS = frozenset({6, 7, 8, 9, 0x1C, 0x36, 0x46, 0x47, 0x4D, 0x52,
                           0x67, 0x68, 0x84, 0x85, 0xE7})
_TORCH_CIDS = frozenset({0x156, 0x15D})

_STRICT_INDUSTRY = False

_BASE_QUALITY_OVERRIDE = None

RECIPES_PATH = "gd_recipes.json"


def _recipes_path() -> str:
    return RECIPES_PATH


def _load_recipes():
    global _RECIPES
    if _RECIPES is not None:
        return _RECIPES
    procs, comps = {}, {}
    try:
        with open(_recipes_path(), "r") as f:
            raw = json.load(f)
        procs = {int(k): v for k, v in raw.get("processes", {}).items()}
        for c in raw.get("components", []):
            comps.setdefault(int(c["idmp"]), []).append(c)
        logger.info("Loaded %d processes, %d components from %s",
                    len(procs), sum(len(v) for v in comps.values()),
                    _recipes_path())
    except Exception as exc:
        logger.error("Recipe load failed (%r); handcraft disabled", exc)
    _RECIPES = (procs, comps)
    return _RECIPES


def _player_current_industry(actor_i, *, industry_hooks):
    for fname in ("_player_current_industry", "_current_industry_for",
                  "_building_industry_at_player"):
        fn = getattr(industry_hooks, fname, None)
        if not callable(fn):
            continue
        try:
            res = fn(actor_i)
        except Exception as exc:
            logger.warning("Industry resolver %s err: %r", fname, exc)
            continue
        if res is None:
            continue
        if isinstance(res, (tuple, list)) and len(res) >= 2:
            ind, inb = res[0], res[1]
        else:
            ind, inb = res, True
        if ind is None:
            continue
        try:
            return (int(ind) & 0xFFFF, bool(inb))
        except (TypeError, ValueError):
            return (None, None)
    return (None, None)


def _iter_candidates(gear):
    for i, e in enumerate(gear or ()):
        try:
            tid = int(e[2]) & 0xFF
        except Exception:
            continue
        if tid == _TYPEID_ITEM:
            yield ("top", i, -1), bytes(e[3])
        elif tid == _TYPEID_CONTAINER:
            try:
                _base, _cap, nested = _container_decode_body(bytes(e[3]))
            except Exception:
                continue
            for j, n in enumerate(nested):
                try:
                    if (int(n[1]) & 0xFF) == _TYPEID_ITEM:
                        yield ("nested", i, j), bytes(n[2])
                except Exception:
                    continue


def _cid_of_body(body):
    try:
        return _extract_cid_from_auitem_body(bytes(body)) & 0xFFFF
    except Exception:
        return -1


def _find_by_cid(gear, cid):
    return [(loc, body) for loc, body in _iter_candidates(gear)
            if _cid_of_body(body) == int(cid) & 0xFFFF]


def _remove_locs(gear, locs):
    nested_by_container = {}
    top = []
    for kind, i, j in locs:
        if kind == "nested":
            nested_by_container.setdefault(i, []).append(j)
        else:
            top.append(i)
    for i, js in nested_by_container.items():
        try:
            base, cap, nested = _container_decode_body(bytes(gear[i][3]))
        except Exception as exc:
            logger.error("Container rewrite skipped at gear[%d]: %r", i, exc)
            continue
        for j in sorted(js, reverse=True):
            if 0 <= j < len(nested):
                del nested[j]
        gear[i][3] = _container_encode_body(base, cap, nested)
    for i in sorted(top, reverse=True):
        if 0 <= i < len(gear):
            gear.pop(i)


def _wear_tool(gear, loc, dice=None):
    kind, i, j = loc
    if kind == "top":
        return gear_wear.use_gear_item(gear, i, dice=dice)
    try:
        base, cap, nested = _container_decode_body(bytes(gear[i][3]))
    except Exception as exc:
        logger.warning("Tool wear skipped, container unreadable: %r", exc)
        return gear_wear.USE_INVALID, False, -1, -1
    if not (0 <= j < len(nested)):
        return gear_wear.USE_INVALID, False, -1, -1
    body = bytes(nested[j][2])
    before = gear_wear.condition(body)
    new_body, code, destroyed = gear_wear.sentient_use(body, dice=dice)
    if destroyed:
        del nested[j]
        after = 0
    else:
        nested[j][2] = new_body
        after = gear_wear.condition(new_body)
    gear[i][3] = _container_encode_body(base, cap, nested)
    return code, destroyed, before, after


async def _zone_quality_for(actor_i, out_cid, *, _person_zone):
    try:
        zr_obj = await _person_zone(actor_i)
        if zr_obj is None:
            return 0
        return int(zr.quality(zr_obj, int(out_cid) & 0xFFFF))
    except Exception as exc:
        logger.warning("Zone quality unavailable: %r", exc)
        return 0


def compute_output_quality(out_cid, component_mins, tool_qualities,
                           zone_quality=0, tech_cap=255):
    inputs = [(int(q), int(c)) for q, c in component_mins
              if int(q) and int(c)]

    if tool_qualities:
        base = max(int(q) for q in tool_qualities)
    else:
        total = sum(q * c for q, c in inputs)
        n = sum(c for _, c in inputs)
        if int(zone_quality):
            total += int(zone_quality)
            n += 1
        base = (total // n) if n else 0

    return manufacturing.output_quality(
        int(out_cid) & 0xFFFF, base, inputs,
        zone_quality=int(zone_quality), tech_cap=int(tech_cap))


def _actor_parent_world(actor_i, *, _tock_state, _live_avatars):
    for src in (_tock_state, _live_avatars):
        if not isinstance(src, dict):
            continue
        ent = src.get(int(actor_i)) or {}
        for key in ("parent", "parent_auid", "parent_world", "AP",
                    "world", "world_auid"):
            val = ent.get(key)
            if val:
                try:
                    if isinstance(val, (bytes, bytearray)):
                        return int.from_bytes(bytes(val), "big") & 0xFFFFFFFF
                    return int(val) & 0xFFFFFFFF
                except (TypeError, ValueError):
                    continue
    return None


async def _persist(conn, actor_i, gear) -> None:
    try:
        blob = bytes(_pack_au_gear(gear))
    except Exception as exc:
        logger.error("Inv pack err: %r", exc)
        return
    try:
        await update_person_state(conn, int(actor_i), inv=blob)
    except Exception as exc:
        logger.error("Inv persist err: %r", exc)
