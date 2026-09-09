
from openshores.world.sim_time import _current_sim_time_ms


def _current_sim_t_low(*, anchor_full: int) -> int:
    return _current_sim_time_ms(anchor_full=anchor_full) & 0xFFFFFFFF


def _next_effect_time_ms(*, anchor_full: int, anchor_low32: int,
                         last_0x18_t_low: int, effect_emit_state: dict) -> int:
    if last_0x18_t_low:
        anchor = last_0x18_t_low
    elif anchor_full:
        anchor = anchor_full
    elif anchor_low32:
        anchor = anchor_low32
    else:
        import time as _t
        anchor = int(_t.time() * 1000)
    jitter = effect_emit_state["counter"] % 200
    effect_emit_state["counter"] += 1
    return anchor - jitter
