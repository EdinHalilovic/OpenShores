
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.body_slots import _ammo_capacity_for_cid
from openshores.protocol.atoms.commodity import _COMMODITY_OVERRIDES_DEFAULT
from openshores.protocol.db_static_tables import _build_dbcommodity_row
from openshores.protocol.framing import write_framed

logger = get_logger(__name__)


async def _send_commodity_overrides(writer):
    ranged = 5
    melee  = 2
    sent = 0
    for entry in _COMMODITY_OVERRIDES_DEFAULT:
        wpn1_block = (0, 0, 0, 0, 0, 0, 0)
        if len(entry) >= 17:
            (cid, ccc, dmg, pm, sm, name, bitmap, model,
             ammo1, ammo2, bw, ncond, sw, sh, stk, wt, wpn1_block) = entry[:17]
        elif len(entry) >= 16:
            (cid, ccc, dmg, pm, sm, name, bitmap, model,
             ammo1, ammo2, bw, ncond, sw, sh, stk, wt) = entry[:16]
        elif len(entry) >= 8:
            (cid, ccc, dmg, pm, sm, name, bitmap, model) = entry[:8]
            ammo1 = ammo2 = bw = ncond = sw = sh = stk = 0
            wt = 0.0
        elif len(entry) == 6:
            (cid, ccc, dmg, pm, sm, name) = entry
            bitmap = model = None
            ammo1 = ammo2 = bw = ncond = sw = sh = stk = 0
            wt = 0.0
        else:
            logger.error(f"Commodity override recipe is malformed and was "
                         f"skipped (len={len(entry)}): {entry!r}")
            continue
        pm_eff = ranged if pm == 5 else (melee if pm == 2 else pm)
        sm_eff = ranged if sm == 5 else (melee if sm == 2 else sm)
        (w1_range, w1_eff1, w1_dmg1, w1_mod1, w1_rad1, w1_ap1, w1_st1) = wpn1_block
        _ammo1_cap, _ammo2_cap = _ammo_capacity_for_cid(cid)
        body = _build_dbcommodity_row(
            cid, ccc_flags=ccc, damage_scalar=dmg,
            primary_mode=pm_eff, secondary_mode=sm_eff,
            name=name, bitmap=bitmap, model=model,
            ammo1_qty=_ammo1_cap, ammo2_qty=_ammo2_cap,
            ammo1_type=ammo1, ammo2_type=ammo2,
            bits_wear=bw, newcond=ncond,
            cap_w=sw, cap_h=sh,
            size_w=sw, size_h=sh, stack_limit=stk, weight=wt,
            wpn1_range=w1_range, wpn1_effect1=w1_eff1, wpn1_damage1=w1_dmg1,
            wpn1_damage_mod1=w1_mod1, wpn1_radius1=w1_rad1,
            wpn1_ap1=w1_ap1, wpn1_st1=w1_st1)
        pkt = bytes([0x2B]) + body
        try:
            await write_framed(writer, pkt)
            sent += 1
            logger.debug(f"Commodity override cid={cid} ccc=0x{ccc:x} dmg={dmg} "
                         f"sub1_mode={pm_eff} sub2_mode={sm_eff} name={name!r} "
                         f"bw=0x{bw:x} wt={wt} size={sw}x{sh} "
                         f"ammo={ammo1}/{ammo2} ({len(pkt)}B)")
        except Exception as exc:
            logger.error(f"Commodity override cid={cid} was not sent; that "
                         f"weapon's stats will not display: {exc!r}")
    if sent:
        logger.debug(f"Pushed {sent} commodity overrides.")
