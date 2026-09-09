
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay import gd_tables as _gd
from openshores.gameplay.db_industry_row import build_scene_db_industry_0x32
from openshores.protocol.db_static_tables import (
    build_scene_db_commodity_0x2b,
    build_scene_db_construction_component_0x2c,
    build_scene_db_construction_process_0x2d,
    build_scene_db_manufacturing_component_0x33,
    build_scene_db_manufacturing_process_0x34,
)

logger = get_logger(__name__)


def build_scene_all_db_industry_0x32(id_prefix: bool = None) -> list:
    table = _gd.load_industries()
    if not table:
        logger.warning('[industry] GD industry table unavailable or failed validation.')
        return []
    ids = sorted(table)
    if ids != list(range(len(ids))):
        logger.warning(f'[industry] GD industry ids are not dense 0..N-1 ({len(ids)} ids, max {ids[-1]}).')
        return []
    return [build_scene_db_industry_0x32(i, table[i], id_prefix=id_prefix)
            for i in ids]


def build_scene_all_db_construction_process_0x2d() -> list:
    table = _gd.load_construction_processes()
    if not table:
        logger.warning("[cproc] GD construction-process table unavailable; "
                       "not streaming 0x2D")
        return []
    return [build_scene_db_construction_process_0x2d(table[c])
            for c in sorted(table)]


def build_scene_all_db_construction_component_0x2c() -> list:
    table = _gd.load_construction_components()
    if not table:
        logger.warning('[ccomp] GD construction-component table unavailable.')
        return []
    rows = sorted((c for bucket in table.values() for c in bucket),
                  key=lambda c: c.seq)
    if [c.seq for c in rows] != list(range(1, len(rows) + 1)):
        logger.warning('[ccomp] construction-component seq is not dense 1..N.')
        return []
    return [build_scene_db_construction_component_0x2c(c) for c in rows]


def build_scene_all_db_manufacturing_process_0x34() -> list:
    procs = _gd.load_manufacturing_processes()
    if not procs:
        logger.warning('[mfgproc] GD manufacturing-process table unavailable.')
        return []
    return [build_scene_db_manufacturing_process_0x34(p) for p in procs]


def build_scene_all_db_commodity_0x2b() -> list:
    rows = _gd.load_commodity_rows()
    if not rows:
        logger.warning('[commodity] GD commodity table unavailable or failed validation.')
        return []
    return [build_scene_db_commodity_0x2b(c) for c in rows
            if c.cid and not c.vacant]


def build_scene_all_db_manufacturing_component_0x33() -> list:
    comps = _gd.load_manufacturing_components()
    if not comps:
        logger.warning('[mfgcomp] GD manufacturing-component table unavailable.')
        return []
    return [build_scene_db_manufacturing_component_0x33(c) for c in comps]
