
from __future__ import annotations


def _nc_heal_hook(player_auid: int, new_hp: int, *,
                  hp_provider,
                  apply_damage) -> None:
    cur = hp_provider(player_auid)
    if cur is None:
        return
    delta = int(new_hp) - cur[0]
    if delta <= 0:
        return
    apply_damage(player_auid, -delta, source="native-healer")
