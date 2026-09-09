
from __future__ import annotations

from openshores.core.logging import get_logger
from openshores.gameplay.natives.conversation import (
    CONVERSATION_STORY_INSTANCE,
    is_native,
    on_conversation_choice,
)
from openshores.gameplay.story_targoss import on_story_op, parse_choice_picked
from openshores.network.chat_binding import _chat_writer_auid

logger = get_logger(__name__)


async def handle_construction_op(payload: bytes, op: int, peer, writer,
                                 _bound_auid: int, *,
                                 _live_avatars: dict,
                                 _PENDING_CHAT_AUIDS: list,
                                 set_active_chat_writer,
                                 on_chat_construction_op,
                                 on_chat_demolish) -> None:
    _cd_name = "ConstructionOp" if op == 0x06 else "Demolish"
    logger.info(f"[chat] <- {peer} 0x{op:02X} ({_cd_name}) "
                f"len={len(payload)}: {payload[:64].hex()}"
                f"{' ...' if len(payload) > 64 else ''}")
    try:
        set_active_chat_writer(writer)
        _cd_actor = _chat_writer_auid(
            writer, live_avatars=_live_avatars,
            _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS) or _bound_auid or 0
        if op == 0x06:
            await on_chat_construction_op(
                payload, _cd_actor)
        else:
            await on_chat_demolish(payload, _cd_actor)
    except Exception as _cd_exc:                        # noqa: BLE001
        logger.warning(f"[chat]   {_cd_name} dispatch err: {_cd_exc!r}")


async def handle_story_op(payload: bytes, op: int, peer, writer,
                          _bound_auid: int, *, _live_avatars: dict,
                          _PENDING_CHAT_AUIDS: list) -> None:
    _st_actor = _chat_writer_auid(
        writer, live_avatars=_live_avatars,
        _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS) or _bound_auid
    logger.info(f"[chat] <- {peer} 0x{op:02X} (story op) "
                f"actor={('0x%08x' % _st_actor) if _st_actor else None} "
                f"len={len(payload)}: {payload[:16].hex()}")
    if _st_actor:
        _conv_handled = False
        if op == 0x7C:
            try:
                _parsed = parse_choice_picked(payload)
                if _parsed is not None:
                    _inst, _choice, _offered = _parsed
                    if (_inst == CONVERSATION_STORY_INSTANCE
                            and _offered
                            and is_native(_offered)):
                        logger.info("[chat]   0x7C instance=1 -> live "
                                    "conversation with native 0x%08x "
                                    "(choice=%d)" % (_offered, _choice))
                        _pkts = on_conversation_choice(
                            _st_actor, _offered, _choice)
                        for _p in _pkts:
                            writer.write(_p)
                        if _pkts:
                            await writer.drain()
                        _conv_handled = True
                        logger.debug("[chat]     sent %d packet(s)"
                                     % len(_pkts))
            except Exception as _cv_exc:                # noqa: BLE001
                logger.warning("[chat]   native conversation err: "
                               f"{_cv_exc!r}")
        if not _conv_handled:
            try:
                await on_story_op(_live_avatars, _st_actor, payload)
            except Exception as _st_exc:                # noqa: BLE001
                logger.warning("[chat]   story op "
                               f"0x{op:02X} err: {_st_exc!r}")
    else:
        logger.warning("[chat] story op dropped. No bound avatar")


async def dispatch_chat_direct(payload: bytes, op: int, peer, writer,
                               _bound_auid: int, *, _live_avatars: dict,
                               _PENDING_CHAT_AUIDS: list,
                               set_active_chat_writer,
                               CHAT_DIRECT_EMPIRE_HANDLERS: dict,
                               CHAT_DIRECT_HANDLERS_EMPIRE_MUTATIONS: dict,
                               CHAT_DIRECT_HANDLERS_AGENT: dict) -> bool:
    _ed_table = dict(CHAT_DIRECT_EMPIRE_HANDLERS or {})
    for _k, _v in CHAT_DIRECT_HANDLERS_EMPIRE_MUTATIONS.items():
        _ed_table.setdefault(_k, _v)
    for _k, _v in CHAT_DIRECT_HANDLERS_AGENT.items():
        _ed_table.setdefault(_k, _v)
    _ed_entry = _ed_table.get(op)
    if _ed_entry is not None:
        _ed_name, _ed_handler = _ed_entry
        actor = _chat_writer_auid(
            writer, live_avatars=_live_avatars,
            _PENDING_CHAT_AUIDS=_PENDING_CHAT_AUIDS) or _bound_auid
        logger.info(f"[chat] <- {peer} 0x{op:02X} ({_ed_name}) "
                    f"len={len(payload)}: {payload[:48].hex()}"
                    f"{' ...' if len(payload) > 48 else ''}")
        set_active_chat_writer(writer)
        try:
            await _ed_handler(payload, actor or 0)
        except Exception as _eheh:                      # noqa: BLE001
            logger.warning(f"[chat]   {_ed_name} handler err: "
                           f"{_eheh!r}")
        return True
    return False
