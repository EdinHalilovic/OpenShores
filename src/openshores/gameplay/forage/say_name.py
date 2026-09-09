
from __future__ import annotations

from openshores.gameplay.forage_names import _forage_cid_name, _quality_desc


def _item_say_name(cid: int, quality: int, *, USE_FOOD_CIDS: dict) -> str:
    return '%s %s' % (_quality_desc(quality),
                      _forage_cid_name(int(cid), USE_FOOD_CIDS=USE_FOOD_CIDS))
