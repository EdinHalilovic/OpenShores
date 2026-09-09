
from __future__ import annotations

import os

from openshores.core.logging import get_logger
from openshores.gameplay import city_model as _cm
from openshores.gameplay import city_sim as _cs
from openshores.gameplay.construction_labor import MAX_CONSTRUCTED_LEVELS
from openshores.gameplay.industry_econ import _dev_industry_id, _jobs_for

logger = get_logger(__name__)


def _building_state_key(i: int, dev: dict):
    bauid = int(dev.get("bauid") or 0)
    return f"b{bauid:08x}" if bauid else f"i{i}:{_dev_industry_id(dev)}"


_building_quality_key = _building_state_key


def _restore_building_quality(st, snap: dict, devs: list) -> None:
    q = snap.get("building_quality") or {}
    if not q:
        return
    for b in st.buildings:
        b.quality = int(q.get(getattr(b, "sim_key", ""), 0) or 0)


def _snapshot_building_quality(st, devs: list = None) -> dict:
    out = {}
    for b in st.buildings:
        if int(getattr(b, "quality", 0) or 0) and getattr(b, "sim_key", ""):
            out[b.sim_key] = int(b.quality)
    return out


def _restore_building_levels(st, snap: dict) -> None:
    lv = snap.get("building_levels_by_key") or {}
    if not lv:
        return
    for b in st.buildings:
        v = lv.get(getattr(b, "sim_key", ""))
        if v is None:
            continue
        b.levels = max(1, min(int(v), _cs_max_levels()))
        b.jobs = _jobs_for(b)


def _snapshot_building_levels(st) -> dict:
    out = {}
    for b in st.buildings:
        if getattr(b, "sim_key", ""):
            out[b.sim_key] = max(1, int(getattr(b, "levels", 1) or 1))
    return out


def _cs_max_levels() -> int:
    return int(MAX_CONSTRUCTED_LEVELS)


def _write_city_report_html(cauid: int, info: dict, report_html: str,
                            *, report_dir):
    d = report_dir
    try:
        os.makedirs(d, exist_ok=True)
    except Exception as exc:
        logger.warning('City report directory %s cannot be created: %s.', d, exc)
        return
    nm = "".join(c if (c.isalnum() or c in "-_") else "_"
                 for c in (info.get("name") or "city"))[:40] or "city"
    path = os.path.join(d, f"{nm}_{cauid & 0xFFFFFFFF:08x}.html")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(report_html)
        info["report_html_path"] = path
    except Exception as exc:
        logger.warning('City 0x%08x report file not written: %s.', cauid & 0xFFFFFFFF, exc)


def _split_developments(blob):
    try:
        blds = _cm.developments_from_blob(blob) or []
    except Exception as exc:
        logger.warning("A city's developments blob will not read: %s.", exc)
        return [], [], []
    return (
        [dict(b) for b in blds if b.get("kind", "building") == "building"],
        [dict(b) for b in blds if b.get("kind") == "road"],
        [dict(b) for b in blds if b.get("kind") == "area_op"],
    )


def _staff_city(st) -> None:
    _cs.reset_employment(st.buildings)
    pool = int(st.population)
    ratio = _cs.staffing_ratio(st.population, _cs.city_job_total(st))
    for kind in _cs.producer_priority(st.enclosure_needed):
        pool = _cs.employ_producers(st.buildings, pool,
                                    1.0 if kind == "repair" else ratio, kind)
