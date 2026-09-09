
from __future__ import annotations

import re as _re_gd
import string as _string_gd
from pathlib import Path

from openshores.core.logging import get_logger
from openshores.gameplay.containers import _HARDCODED_CONTAINERS
from openshores.gameplay.gd_tables import find_gd
from openshores.gameplay.use_action_tables import _HARDCODED_FOODS

logger = get_logger(__name__)


USE_FOOD_CIDS = {}

CONTAINER_CIDS = set()
CONTAINER_CAPACITIES = {}


def _load_containers_from_gd():
    path = find_gd()
    if path is None:
        logger.warning('GD file not found on any of the default paths.')
        return -1
    try:
        data = Path(path).read_bytes()
    except Exception as exc:
        logger.warning("GD read failed (%r); using the hardcoded container "
                       "fallback." % (exc,))
        return -1
    pattern = _re_gd.compile(
        rb'\xff\xff\xff\xff.\x00\x00\x00\x00', _re_gd.DOTALL)
    n_cont = 0
    n_food = 0
    for m in pattern.finditer(data):
        fp = m.start()
        if fp < 59:
            continue
        cid = int.from_bytes(
            data[fp-59:fp-57], 'big', signed=True)
        if cid <= 0:
            continue
        w = data[fp - 6]; h = data[fp - 5]
        food_flag = int.from_bytes(
            data[fp-4:fp], 'big')
        nutrition = data[fp + 4]
        qlen = int.from_bytes(data[fp+9:fp+11], 'little')
        name = ''
        if 0 < qlen < 200:
            try:
                name = (data[fp+11:fp+11+qlen]
                        .decode('utf-16-le', errors='replace'))
                for p in (':data/c_', ':data/m_'):
                    if p in name:
                        name = name.split(p, 1)[1]
                        break
                for sfx in ('.png', '.3dsN', '.3ds'):
                    if name.endswith(sfx):
                        name = name[:-len(sfx)]
                        break
            except Exception as exc:
                logger.debug("GD record at offset %d has an unreadable "
                             "texture name (%r); skipping it." % (fp, exc))
        if not name or not all(
                c in _string_gd.printable for c in name):
            continue
        if w > 0 and h > 0:
            CONTAINER_CIDS.add(int(cid))
            CONTAINER_CAPACITIES[int(cid)] = (int(w), int(h))
            n_cont += 1
            logger.debug("GD container: cid=%d pack=%dx%d=%dcu "
                         "name=%r" % (int(cid), int(w), int(h),
                                      int(w)*int(h), name))
        is_food = (food_flag >> 1) & 1
        if is_food and nutrition < 200:
            USE_FOOD_CIDS[int(cid)] = (name, int(nutrition))
            n_food += 1
            logger.debug("GD food: cid=%d nutrition=%d name=%r%s" % (
                int(cid), int(nutrition), name,
                ' [intoxicant]' if (food_flag >> 2) & 1 else ''))
    if n_cont + n_food > 0:
        logger.info("GD scan found %d containers and %d foods." % (
            n_cont, n_food))
        return n_cont
    return -1


def _load_container_cids():
    n = _load_containers_from_gd()
    if n < 0:
        for cid, (w, h, name) in _HARDCODED_CONTAINERS.items():
            CONTAINER_CIDS.add(cid)
            CONTAINER_CAPACITIES[cid] = (w, h)
            logger.info("Container fallback: cid=%d pack=%dx%d "
                        "name=%s" % (cid, w, h, name))
    else:
        logger.info("GD loader registered %d container cids." % n)
    for cid, meta in _HARDCODED_FOODS.items():
        USE_FOOD_CIDS.setdefault(cid, meta)
