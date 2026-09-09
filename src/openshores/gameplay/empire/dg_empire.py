
from __future__ import annotations

from openshores.database.repositories.empire import (
    _build_nested_cities_from_sql,
    _build_nested_citizens_from_sql,
    _build_nested_knownempires_and_patents,
    _read_founder_domain,
    emperor_for_empire,
    empire_for_avatar,
    flag_for_empire,
    read_empire_name,
    read_empire_taxes,
)
from openshores.gameplay import empire_model
from openshores.protocol.atoms.office import (
    _write_auoffice_emperor,
    _write_auoffice_empty,
)
from openshores.protocol.qt_blob import qcompress
from openshores.protocol.qt_types import (
    _write_qcolor,
    _write_qcolor_null,
    _write_qimage,
)
from openshores.protocol.stream import QDS


async def _empire_name(conn, empire_id: int):
    return await read_empire_name(conn, empire_id)


async def _empire_taxes(conn, empire_id: int):
    return await read_empire_taxes(conn, empire_id)


async def build_dg_empire_empty(
    conn,
    empire_id: int = 1,
    player_avatar_id: int = 1,
    *,
    name_long: str,
    name_short: str,
    capital_name: str,
    full_variant: bool = True,
    emperor_auid: int = 0,
    _EMPIRE_NAME_OVERRIDE: dict,
    _EMPIRE_TAX_OVERRIDE: dict,
) -> bytes:
    s = QDS()

    _name_override = _EMPIRE_NAME_OVERRIDE.get(int(empire_id) & 0xFFFFFFFF)
    if _name_override:
        name_long = _name_override
        name_short = _name_override
    else:
        _eid_n = int(empire_id) & 0xFFFFFFFF
        if _eid_n:
            _rn = await _empire_name(conn, _eid_n)
            if _rn and _rn[0]:
                name_long = str(_rn[0])
                name_short = str(_rn[0])

    _immig, _stance, _rtf, _tres, _cdebt, _zbuild = 0x01, 0x01, 0x03, 0x01, 0x01, 0x00
    _chue, _csat = 0xAA, 0x7F
    _pol = (await empire_model.load_empire(conn, int(empire_id) & 0xFFFFFFFF)).status
    _immig  = _pol.immigration    & 0xFF
    _stance = _pol.default_stance & 0xFF
    _rtf    = _pol.right_to_found  & 0xFF
    _tres   = _pol.trespass        & 0xFF
    _cdebt  = _pol.city_debt       & 0xFF
    _zbuild = _pol.zone_build      & 0xFF
    _chue   = _pol.contrail_hue    & 0xFF
    _csat   = _pol.contrail_sat    & 0xFF
    _csat   = 0x40 if _csat < 0x40 else (0xBF if _csat > 0xBF else _csat)

    s.write_i32(empire_id)
    s.write_qstring(name_long)
    s.write_qstring(name_short if full_variant else "")
    s.write_u8(_immig)
    _write_qimage(s, await flag_for_empire(conn, empire_id))
    _rewards = [0] * 16
    _rewards = (await empire_model.load_empire(conn, int(empire_id) & 0xFFFFFFFF)).status.rewards
    for _i in range(16):
        s.write_i32(int(_rewards[_i]) if _i < len(_rewards) else 0)

    _eid_key = int(empire_id) & 0xFFFFFFFF
    _tax = _EMPIRE_TAX_OVERRIDE.get(_eid_key)
    if _tax is None:
        _row = await _empire_taxes(conn, _eid_key)
        if _row:
            _tax = (int(_row[0] or 0), int(_row[1] or 0),
                    int(_row[2] or 0))
            _EMPIRE_TAX_OVERRIDE[_eid_key] = _tax
    if _tax is None:
        _tax = (0, 0, 0)
    s.write_u8(_tax[0] & 0xFF)
    s.write_u8(_tax[1] & 0xFF)
    s.write_u8(_tax[2] & 0xFF)
    s.write_u8(_stance)

    s.write_bytes(qcompress(
        await _build_nested_knownempires_and_patents(conn, empire_id)))

    _theme = None
    _theme = (await empire_model.load_empire(conn, int(empire_id) & 0xFFFFFFFF)).status.theme
    if _theme:
        for (_a, _r, _g, _b) in (_theme + empire_model.THEME_DEFAULT)[:6]:
            _write_qcolor(s, _a * 257, _r * 257, _g * 257, _b * 257)
    else:
        for _ in range(6):
            _write_qcolor_null(s)

    s.write_bytes(qcompress(b""))

    s.write_bytes(qcompress(
        await _build_nested_citizens_from_sql(
            conn, empire_id,
            offices=await empire_model._load_offices(conn, empire_id))))

    s.write_bytes(qcompress(
        await _build_nested_cities_from_sql(conn, empire_id)))

    s.write_u32(player_avatar_id & 0xFFFFFFFF)

    s.write_bytes(bytes(24))

    s.write_u8(_rtf)
    s.write_u8((await _read_founder_domain(conn, empire_id)) & 0xFF)

    if emperor_auid:
        _write_auoffice_emperor(s, emperor_auid)
    else:
        _write_auoffice_empty(s)

    s.write_u8(_tres)
    s.write_u8(_chue)
    s.write_u8(_csat)
    s.write_u8(_cdebt)
    s.write_u8(_zbuild)
    s.write_qstring(capital_name)

    return s.getvalue()


async def build_scene_dg_empire_0x31(conn,
                                     last_flag: bool = True,
                                     player_avatar_id: int = 1,
                                     empire_id: int = None,
                                     emperor_auid: int = None,
                                     *,
                                     name_long: str,
                                     name_short: str,
                                     capital_name: str,
                                     _CITIZEN_EMPIRE_OVERRIDE: dict,
                                     _EMPIRE_NAME_OVERRIDE: dict,
                                     _EMPIRE_TAX_OVERRIDE: dict) -> bytes:
    if empire_id is None:
        empire_id = await empire_for_avatar(
            conn, player_avatar_id,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)
    if emperor_auid is None:
        emperor_auid = (await emperor_for_empire(conn, empire_id)
                        if empire_id else 0)
    s = QDS()
    s.write_u8(0x31)
    s.buf += await build_dg_empire_empty(
        conn, empire_id=empire_id, player_avatar_id=player_avatar_id,
        emperor_auid=emperor_auid,
        name_long=name_long, name_short=name_short,
        capital_name=capital_name,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    s.write_u8(1 if last_flag else 0)
    return s.getvalue()


async def build_scene_dg_empire(conn,
                                outer_opcode: int = 0x24,
                                *,
                                name_long: str,
                                name_short: str,
                                capital_name: str,
                                _EMPIRE_NAME_OVERRIDE: dict,
                                _EMPIRE_TAX_OVERRIDE: dict) -> bytes:
    s = QDS()
    s.write_u8(outer_opcode & 0xFF)
    s.buf += await build_dg_empire_empty(
        conn,
        name_long=name_long, name_short=name_short,
        capital_name=capital_name,
        _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE)
    return s.getvalue()
