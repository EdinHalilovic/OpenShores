
from __future__ import annotations

from openshores.gameplay.empire.dg_empire import build_scene_dg_empire
from openshores.protocol.atoms.aucomm import build_scene_auccomm_empty
from openshores.protocol.scene_frames import (
    build_scene_accept_invite_empire,
    build_scene_dn_building_empty,
    build_scene_dn_room_empty,
)


def _mk_probe(subtype: int):
    return lambda: build_scene_auccomm_empty(subtype)


def _mk_dg_empire_probe(outer_opcode: int, *, conn,
                        name_long: str,
                        name_short: str,
                        capital_name: str,
                        _EMPIRE_NAME_OVERRIDE: dict,
                        _EMPIRE_TAX_OVERRIDE: dict):
    async def _probe():
        return await build_scene_dg_empire(
            conn, outer_opcode,
            name_long=name_long, name_short=name_short,
            capital_name=capital_name,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    return _probe


SCENE_PROBES: dict[str, list] = {
    "none":           [],
    "dn_building_38": [(0x38, build_scene_dn_building_empty)],
    "dn_building_24": [(0x24, build_scene_dn_building_empty)],
    "dn_room_38":     [(0x38, build_scene_dn_room_empty)],
    "dn_room_24":     [(0x24, build_scene_dn_room_empty)],
    "accept_empire_24": [(0x24, build_scene_accept_invite_empire)],
    "accept_empire_38": [(0x38, build_scene_accept_invite_empire)],
}

LITERAL_PROBE_NAMES = frozenset(SCENE_PROBES)


def install_generated_probes(*, empire: dict | None = None) -> int:
    made: dict[str, list] = {}
    for _st in range(0x00, 0xA0):
        made[f"sub_{_st:02x}"] = [(0x38, _mk_probe(_st))]

    if empire is not None:
        for _op in (list(range(0x20, 0x40))
                    + [0x0A, 0x28, 0x44, 0x62, 0x66, 0x7A]):
            _probe = _mk_dg_empire_probe(_op, **empire)
            made[f"dg_empire_op{_op:02x}_24"] = [(0x24, _probe)]
            made[f"dg_empire_op{_op:02x}_38"] = [(0x38, _probe)]

    clash = set(made) & LITERAL_PROBE_NAMES
    if clash:
        raise KeyError(f"Generated probe names collide with the literal table: {sorted(clash)}")
    SCENE_PROBES.update(made)
    return len(made)
