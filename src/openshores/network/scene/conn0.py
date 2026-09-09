
from __future__ import annotations


def _frame_is_resume_hello(frame, *, _scene_hello_char_id) -> bool:
    cid = _scene_hello_char_id(frame)
    return cid is not None and cid != 0


_CONN0_HOLD_REASONS = {
    "create_in_flight": (
        "conn #0 arrived with a character creation already in flight -- this "
        "is the reconnect our own 0x22 asked for. NOT redirecting again; "
        "waiting for its 0x38 so we can replay the world and let variant B "
        "fire."),
    "create_hello": (
        "conn #0 hello carries charId=0 -- this client is CREATING a "
        "character, not resuming. Holding back the 0x22 so the reconnect "
        "cannot discard its slot selection."),
    "no_redirect_flag": (
        "HZ_NO_WORLD_REDIRECT=1 -- holding back the 0x22 on conn #0 so the "
        "client's first message is observable (watch the charId in its "
        "0x38)"),
}


def _conn0_redirect_decision(conn_n: int, first_frame,
                             *, create_in_flight: bool,
                             no_redirect: bool,
                             _frame_is_new_avatar_hello) -> str:
    if conn_n != 0:
        return "redirect"
    if create_in_flight:
        return "create_in_flight"
    if _frame_is_new_avatar_hello(first_frame):
        return "create_hello"
    if no_redirect:
        return "no_redirect_flag"
    return "redirect"
