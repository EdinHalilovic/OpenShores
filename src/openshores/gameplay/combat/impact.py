
from __future__ import annotations

import math

from openshores.gameplay import damageable as _dmg
from openshores.gameplay.combat.kill_reputation import _attacker_world_auid


def _compute_world_hit_point(player_pos, rot, aim_x, aim_y):
    px, py, pz = (float(player_pos[0]),
                  float(player_pos[1]),
                  float(player_pos[2]))
    r = math.sqrt(px * px + py * py + pz * pz)
    if r < 1e-6:
        return (px, py, pz)
    ux, uy, uz = px / r, py / r, pz / r
    ex = -uz
    ey = 0.0
    ez = ux
    elen = math.sqrt(ex * ex + ey * ey + ez * ez)
    if elen < 1e-6:
        ex, ey, ez = 1.0, 0.0, 0.0
    else:
        ex, ey, ez = ex / elen, ey / elen, ez / elen
    nx = uy * ez - uz * ey
    ny = uz * ex - ux * ez
    nz = ux * ey - uy * ex
    yaw = float(rot[2]) if len(rot) >= 3 else 0.0
    yaw_offset = -0.95
    yaw_sign = -1.0
    theta = yaw_sign * yaw + yaw_offset
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    fx = cos_t * nx + sin_t * ex
    fy = cos_t * ny + sin_t * ey
    fz = cos_t * nz + sin_t * ez
    wx = px + aim_x * fx + aim_y * ux
    wy = py + aim_x * fy + aim_y * uy
    wz = pz + aim_x * fz + aim_y * uz
    return (wx, wy, wz)


def _classify_hit_surface(target_auid, attacker_auid=0, *,
                          world_atom_auids,
                          _live_avatars,
                          spawned_buildings,
                          idle_bodies,
                          story_atom_id,
                          story_npcs):
    tid = int(target_auid or 0) & 0xFFFFFFFF
    world = 0
    if tid and tid in world_atom_auids:
        return ("terrain", tid)
    if tid and tid in _live_avatars:
        world = _attacker_world_auid(
            attacker_auid,
            _live_avatars=_live_avatars,
            world_atom_auids=world_atom_auids)
        return ("player", world)
    d = _dmg.get(tid) if tid else None
    if d is not None:
        return (d.kind or "creature",
                int(d.world_auid or 0)
                or _attacker_world_auid(
                    attacker_auid,
                    _live_avatars=_live_avatars,
                    world_atom_auids=world_atom_auids))
    if tid and _dmg.is_damageable_candidate(
            tid, idle_bodies=idle_bodies, story_atom_id=story_atom_id,
            story_npcs=story_npcs):
        return ("creature", _attacker_world_auid(
            attacker_auid,
            _live_avatars=_live_avatars,
            world_atom_auids=world_atom_auids))
    if tid:
        info = spawned_buildings.get(tid)
        if info:
            return ("building",
                    (int(info.get("parent") or 0) & 0xFFFFFFFF)
                    or _attacker_world_auid(
                        attacker_auid,
                        _live_avatars=_live_avatars,
                        world_atom_auids=world_atom_auids))
    world = _attacker_world_auid(
        attacker_auid,
        _live_avatars=_live_avatars,
        world_atom_auids=world_atom_auids)
    return ("terrain" if not tid else "unknown", world)


def _victim_world_xyz(target_auid, *,
                      story_npcs,
                      idle_bodies,
                      spawned_buildings):
    tid = int(target_auid or 0) & 0xFFFFFFFF
    if not tid:
        return None

    def _xyz3(v):
        try:
            return (float(v[0]), float(v[1]), float(v[2]))
        except Exception:
            return None

    for _st in (story_npcs or {}).values():
        if (int(_st.get("auid") or 0) & 0xFFFFFFFF) == tid:
            got = _xyz3(_st.get("xyz"))
            if got is not None:
                return got
            break
    b = (idle_bodies or {}).get(tid)
    if b:
        got = _xyz3(b.get("xyz") or b.get("home") or b.get("home_xyz"))
        if got is not None:
            return got
    d = _dmg.get(tid)
    if d is not None and d.xyz:
        return (float(d.xyz[0]), float(d.xyz[1]), float(d.xyz[2]))
    info = spawned_buildings.get(tid)
    if info and info.get("xyz"):
        x, y, z = info["xyz"][:3]
        return (float(x), float(y), float(z))
    return None
