
from __future__ import annotations

from openshores.protocol.atoms.item_seed import _pack_auitem_seed_body
from openshores.protocol.atoms.weapon import (
    _WEAPON_DEFAULTS_KNIFE,
    _weapon_spec_for_cid,
)


_VARIETY_GEAR_DEF = (
    (5, 0, 0x01,  1, 5, 0x3D, "Flag"),
    (5, 1, 0x01,  5, 5, 0x3D, "Beans"),
    (5, 2, 0x01, 10, 5, 0x3D, "PistolAmmo"),
    (5, 3, 0x01, 15, 5, 0x3D, "Air"),
)

_VARIETY_GEAR_DUP_DEF = (
    (1, 1, 0x01,   2, 5, 0x3D, "Banana"),
)

_VARIETY_GEAR_WEAPONS_DEF = (
    (4, 0, 0x08, 15, 5, 0x3D, "Knife"),
    (3, 0, 0x09, 25, 5, 0x3D, "Pistol"),
    (2, 0, 0x07, 10, 5, 0x3D, "PistolMagazine"),
)


def _build_variety_gear_entries():
    out = []
    defs = list(_VARIETY_GEAR_DEF)
    defs.extend(_VARIETY_GEAR_WEAPONS_DEF)
    for st, sub, tid, cid, byte14, quality, name in defs:
        if tid == 0x08:
            wspec = _WEAPON_DEFAULTS_KNIFE
        elif tid == 0x09 or tid == 0x0C:
            wspec = _weapon_spec_for_cid(cid)
        else:
            wspec = None
        out.append((st, sub, tid,
                    _pack_auitem_seed_body(typeId=tid, cid=cid,
                                            byte14=byte14, quality=quality,
                                            name=name,
                                            weapon_spec=wspec)))
    return out
