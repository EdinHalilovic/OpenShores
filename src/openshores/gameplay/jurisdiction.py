from __future__ import annotations

import math

from openshores.database.repositories.city import planet_city_rows

JURISDICTION_AREA_CONST = 1345488.8020887126


def jurisdiction_radius_from_lotsize(lot_size: int) -> float:
    if lot_size and lot_size > 1:
        return float(round(math.sqrt(lot_size * JURISDICTION_AREA_CONST)))
    return 0.0


def default_radius_m() -> float:
    return 2600.0


def _dist2(a, b) -> float:
    return sum((float(a[i]) - float(b[i])) ** 2 for i in range(3))


def _unpack_city(c):
    if isinstance(c, dict):
        return (int(c.get("empire", c.get("allegiance", 0)) or 0),
                float(c.get("x", c.get("locX", 0.0)) or 0.0),
                float(c.get("y", c.get("locY", 0.0)) or 0.0),
                float(c.get("z", c.get("locZ", 0.0)) or 0.0))
    return (int(c[0] or 0), float(c[1] or 0.0), float(c[2] or 0.0), float(c[3] or 0.0))


def founding_blocked(new_xyz, empire_id: int, existing_cities, radius_m=None):
    if radius_m is None:
        radius_m = default_radius_m()
    r2 = float(radius_m) * float(radius_m)
    emp = int(empire_id) & 0xFFFFFFFF
    for c in existing_cities:
        c_emp, cx, cy, cz = _unpack_city(c)
        if c_emp and (c_emp & 0xFFFFFFFF) != emp:
            return (True, f"planet already claimed by empire 0x{c_emp & 0xFFFFFFFF:08x}")
    for c in existing_cities:
        c_emp, cx, cy, cz = _unpack_city(c)
        if _dist2(new_xyz, (cx, cy, cz)) <= r2:
            return (True, "location is inside an existing city's jurisdiction zone")
    return (False, "")


async def _planet_city_rows(conn, world_auid: int):
    return await planet_city_rows(conn, world_auid)


async def load_planet_cities(conn, world_auid: int, exclude_id: int = 0):
    out = []
    rows = await _planet_city_rows(conn, world_auid)
    for row in rows:
        if exclude_id and (int(row[0]) & 0xFFFFFFFF) == (exclude_id & 0xFFFFFFFF):
            continue
        out.append({"id": row[0], "empire": row[1], "x": row[2],
                    "y": row[3], "z": row[4]})
    return out
