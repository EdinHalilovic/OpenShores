
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.blueprint_lookup import _iter_capitol_blueprints

logger = get_logger(__name__)


async def _select_capitol_blueprint(conn, selector=None, payload=None,
                                    design_serial=None):
    import struct as _struct
    bps = await _iter_capitol_blueprints(conn)
    if not bps:
        return None
    if payload:
        ids = {bp["design_id"]: bp for bp in bps if bp["design_id"]}
        if ids:
            for i in range(0, max(0, len(payload) - 3)):
                for fmt in (">I", "<I"):
                    v = _struct.unpack_from(fmt, payload, i)[0]
                    if v in ids:
                        bp = ids[v]
                        logger.info("Blueprint from request: %r name=%r "
                                    "design=0x%08x", bp["stem"], bp["name"], v)
                        return bp
    sel = selector if selector is not None else ""
    sel = (sel or "").strip()
    if sel:
        sid = None
        try:
            sid = int(sel, 0) & 0xFFFFFFFF
        except (ValueError, TypeError):
            sid = None
        for bp in bps:
            if sid is not None and bp["design_id"] == sid:
                logger.info("Blueprint from selector: %r", bp["stem"])
                return bp
        low = sel.lower()
        for bp in bps:
            if low in bp["stem"].lower() or low in bp["name"].lower():
                logger.info("Blueprint from selector: %r name=%r",
                            bp["stem"], bp["name"])
                return bp
        logger.warning("Selector %r matched no blueprint; available: %s",
                       sel,
                       [(b["stem"], b["name"], hex(b["design_id"]))
                        for b in bps])
    fb = bps[0]
    serial_txt = (f"0x{int(design_serial) & 0xFFFFFFFF:08x}"
                  if design_serial else "(not transmitted / none found in request)")
    logger.warning('Design serial %s matched no stored blueprint; falling back to %r (name=%r, design=0x%08x).', serial_txt, fb["stem"],
                   fb["name"], fb["design_id"])
    if len(bps) > 1:
        logger.warning("Pass one as the selector: %s",
                       [(b["stem"], b["name"], hex(b["design_id"]))
                        for b in bps])
    return fb


async def on_design_loaded_notify(payload: bytes, actor: int) -> None:
    import struct as _struct
    did = _struct.unpack_from(">I", payload, 1)[0] if len(payload) >= 5 else 0
    logger.debug("0xE0: client 0x%08x loaded design 0x%08x from its local "
                 "BD cache.", int(actor) & 0xFFFFFFFF, did)
