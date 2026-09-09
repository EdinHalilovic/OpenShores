
from __future__ import annotations

from openshores.gameplay import gd_tables

PATENT_COMMODITIES = gd_tables._PATENT_CIDS

is_patent = gd_tables.is_patent

_SC_PATENT_RANGES = (
    (0x179, 0x17A), (0x1FC, 0x215), (0x21D, 0x21F),
    (0x223, 0x224),
    (0x23C, 0x23C), (0x257, 0x260), (0x27F, 0x27F),
)

is_tech = gd_tables.is_tech


def _expand(ranges):
    out = set()
    for lo, hi in ranges:
        out.update(range(lo, hi + 1))
    return frozenset(out)


SC_PATENT_COMMODITIES = _expand(_SC_PATENT_RANGES)

assert len(PATENT_COMMODITIES) == 206, len(PATENT_COMMODITIES)
assert len(SC_PATENT_COMMODITIES) == 45, len(SC_PATENT_COMMODITIES)
assert SC_PATENT_COMMODITIES <= PATENT_COMMODITIES
assert not any(is_tech(c) for c in PATENT_COMMODITIES)

assert sum(is_tech(c) for c in range(0, 0x400)) == 88, \
    sum(is_tech(c) for c in range(0, 0x400))


def is_sc_patent(cid: int) -> bool:
    return int(cid) in SC_PATENT_COMMODITIES
