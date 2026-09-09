from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.city_report_lookup import _lookup_city_for_report
from openshores.gameplay.city_snapshot import _write_city_report_html
from openshores.protocol.mail import _mail_write_packet_size

logger = get_logger(__name__)


async def on_city_report_request(payload: bytes, actor: int, *, conn,
                                 _CITY_SIM, _city_info_from_row, report_dir,
                                 _SAVE, _live_avatars,
                                 _ACTIVE_CHAT_WRITER) -> None:
    try:
        if len(payload) < 6:
            logger.warning(f"[city-report-req] 0x50 short body {payload.hex()}")
            return
        rtype = payload[1]
        req_id = int.from_bytes(payload[2:6], "big") & 0xFFFFFFFF
        cauid, info = await _lookup_city_for_report(
            conn, req_id, _CITY_SIM=_CITY_SIM,
            _city_info_from_row=_city_info_from_row)
        label = {0: "recent", 1: "history"}.get(rtype, f"type{rtype}")
        if info is None:
            logger.warning(f"[city-report-req] 0x50 {label} for 0x{req_id:08x}: "
                           f"no city matched (id or capitol)")
            return
        from openshores.gameplay import city_report as _cr
        reports = info.get("reports") or []
        name = info.get("name", "") or f"City 0x{cauid & 0xFFFFFFFF:08x}"
        lines = []
        if rtype == 1 and reports:
            lines.append(f"{name} — report history ({len(reports)} cycles):")
            for rep in reports[-10:]:
                lines.append(_cr.format_history_line(rep))
        elif info.get("last_report"):
            lines.append(_cr.format_report_text(_cr.report_from_dict(info["last_report"])))
        elif reports:
            lines.append(_cr.format_report_text(_cr.report_from_dict(reports[-1])))
        else:
            snap = info.get("sim_snapshot") or {}
            lines.append(f"City report: {name}")
            lines.append(f"Population {snap.get('population', 0)}  "
                         f"satisfaction {snap.get('satisfaction', 0)}  "
                         f"(no cycle has run yet)")
        _ = "\n".join(lines)
        try:
            src = info.get("last_report") or (reports[-1] if reports else None)
            if src:
                _write_city_report_html(
                    cauid, info, _cr.format_report_html(_cr.report_from_dict(src)),
                    report_dir=report_dir)
        except Exception as _wexc:
            logger.error(f"[city-report-req] html refresh err: {_wexc!r}")
        try:
            from openshores.gameplay.city_report_native import (
                build_aucityreport, build_aucityreporthistory,
                report_fields_from_info, races_from_report, events_from_report,
                inventory_from_info, tools_from_info,
                industries_from_developments,
                industries_from_report, report_kind_default)
            import struct as _st2
            src2 = info.get("last_report") or (reports[-1] if reports else None)
            rd = src2 or {}
            _geo = {}
            try:
                _sv = _SAVE
                def _f3f(p):
                    return ("(%.1f, %.1f, %.1f)" % (float(p[0]), float(p[1]),
                            float(p[2]))) if p else ""
                def _f3i(p):
                    return ("(%d, %d, %d)" % (round(p[0] / 10.0), round(p[1] / 10.0),
                            round(p[2] / 10.0))) if p else ""
                _geo = {
                    "planet_name": getattr(_sv, "planet_name", "") or "",
                    "star_name": getattr(_sv, "star_name", "") or "",
                    "system_name": getattr(_sv, "system_name", "") or "",
                    "sector_name": getattr(_sv, "sector_name", "") or "",
                    "system_coords": _f3f(getattr(_sv, "system_position", None)),
                    "sector_coords": _f3i(getattr(_sv, "sector_position", None)),
                    "founder_name": ((info.get("founder") or {}).get("name")
                                     or getattr(_sv, "person_name", "") or ""),
                    "founder_auid": int(((info.get("founder") or {}).get("empire"))
                                        or getattr(_sv, "empire_auid", 0) or 0) & 0xFFFFFFFF,
                    "world_auid": int(getattr(_sv, "planet_auid", 0) or 0) & 0xFFFFFFFF,
                }
            except Exception as _gexc:
                logger.error(f"[city-report-req] geo err: {_gexc!r}")
                _geo = {}
            rname, rts, rfields = report_fields_from_info(info, rd, _geo)
            _races = races_from_report(info, rd)
            _events = events_from_report(rd)
            _inv = inventory_from_info(info, rd)
            _tools = tools_from_info(info)
            def _inds_for(_rec):
                _i = industries_from_report(_rec)
                if _i is not None:
                    return _i
                return industries_from_developments(info.get("buildings"))

            _inds = _inds_for(rd)
            if src2 and industries_from_report(rd) is None:
                logger.warning('[city-report-req] report predates the stored industry hash.')
            one = build_aucityreport(
                industries=_inds,
                name=(rname or name), population=int(rd.get("population", 0) or 0),
                timestamp_ms=rts, kind=report_kind_default(),
                fields=rfields, probe=False,
                founder_auid=_geo.get("founder_auid", 0),
                founder_name=_geo.get("founder_name", ""),
                extra_flags=0, races=_races, events=_events,
                inventory=_inv, tools=_tools)
            if rtype == 1:
                _depth = 20
                _hist = []
                for _hr in (reports[-_depth:] if reports else []):
                    try:
                        _hraces = races_from_report(info, _hr)
                        _hevents = events_from_report(_hr)
                        _hn, _hts, _hfields = report_fields_from_info(info, _hr, _geo)
                        _hist.append(build_aucityreport(
                            industries=_inds_for(_hr),
                            name=(rname or name),
                            population=int(_hr.get("population", 0) or 0),
                            timestamp_ms=_hts, kind=report_kind_default(),
                            fields=_hfields, probe=False,
                            founder_auid=_geo.get("founder_auid", 0),
                            founder_name=_geo.get("founder_name", ""),
                            extra_flags=0, races=_hraces, events=_hevents,
                            inventory=_inv,
                            tools=_tools))
                    except Exception as _hexc:
                        logger.error(f"[city-report-req] history entry err: {_hexc!r}")
                data = build_aucityreporthistory(_hist or [one])
                logger.info(f"[city-report-req] history payload: "
                            f"{len(_hist or [one])} report(s) "
                            f"(Last + NextToLast resolve when >= 2)")
            else:
                data = one
            _resp_type = 1 if rtype == 1 else 0
            body = (bytes([0x50, _resp_type & 0xFF])
                    + _st2.pack(">I", cauid & 0xFFFFFFFF) + data)
            frame = _mail_write_packet_size(len(body)) + body
            w = None
            try:
                ent = _live_avatars.get(int(actor))
                if ent:
                    w = ent.get("chat_writer")
            except Exception as _lexc:
                logger.error(f"[city-report-req] chat writer lookup err: "
                             f"{_lexc!r}")
            w = w or _ACTIVE_CHAT_WRITER
            if w is not None:
                w.write(frame)
                try:
                    await w.drain()
                except Exception as _dexc:
                    logger.error(f"[city-report-req] native response drain err: "
                                 f"{_dexc!r}")
                logger.info(f"[city-report-req] native response sent {len(frame)}B "
                            f"(type {rtype}, report {len(data)}B)")
            else:
                logger.warning("[city-report-req] native response: no chat writer")
        except Exception as _rexc:
            logger.error(f"[city-report-req] native response err: {_rexc!r}")
        logger.info(f"[city-report-req] 0x50 {label} for city 0x{cauid & 4294967295:08x} '{name}' -> report refreshed (HTML backup.")
    except Exception as exc:
        logger.error(f"[city-report-req] handler err: {exc!r}")
