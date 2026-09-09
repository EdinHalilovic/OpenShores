
from __future__ import annotations

import json as _json
import time as _time

import asyncpg

from openshores.database.repositories.city_reports import all_city_rows
from openshores.gameplay import city_report as _cr


async def _mail_reports_for_account(conn: asyncpg.Connection, account_id: int):
    out = []
    rows = await all_city_rows(conn)
    for r in rows:
        try:
            d = dict(r)
        except Exception:
            continue
        city_id = int(d.get("id", 0) or 0) & 0xFFFFFFFF
        name = d.get("name") or ("City 0x%08x" % city_id)
        ss = d.get("sim_state")
        if not ss:
            continue
        try:
            sd = _json.loads(ss)
            reps = sd.get("reports") or []
        except Exception:
            reps = []
        if not reps:
            continue
        last = reps[-1]
        try:
            rep = _cr.report_from_dict(last)
            body_html = _cr.format_report_html(rep)
        except Exception:
            continue
        ts = int(last.get("t") or int(_time.time() * 1000))
        msg_id = ((ts ^ (ts >> 32) ^ city_id) & 0xFFFFFFFF) or 1
        out.append(dict(
            subject=name,
            title="City Report",
            body=body_html,
            sender_id=city_id,
            timestamp_ms=ts,
            msg_id=msg_id,
        ))
    return out
