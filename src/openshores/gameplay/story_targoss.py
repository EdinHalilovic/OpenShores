
# Hardcoded Getting Started for testing

from __future__ import annotations

import asyncio
import os
import re
from typing import List, Optional, Tuple

from openshores.core.logging import get_logger
from openshores.protocol.atoms.aucomm import build_chat_aucomm_v4
from openshores.protocol.framing import write_framed
from openshores.world.chat_writer import _chat_only_writer

logger = get_logger(__name__)


SCRIPT_CANDIDATES = (
    "/srv/openshores/Old/TutorialScript/script.txt",
    "D:/Hazeron/Old/ExampleStory/script.txt",
)


def _resolve_default_script() -> str:
    for cand in SCRIPT_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    return SCRIPT_CANDIDATES[0]


DEFAULT_SCRIPT = _resolve_default_script()

DEFAULT_DWELL_S = 8.0

CONDITION_TIMEOUT_S = 45.0

CONDITION_POLL_S = 0.4

ENTRY_LABEL = "targoss"

DEFAULT_SECTION_TITLE = "Getting Started"

VOICE_CHANNEL_INDEX = 2
VOICE_SCOPE = 15

AUCOMM_TYPE_CHAT = 0x29
AUCOMM_TYPE_CHAT_CHOICE = 0x2B
AUCOMM_TYPE_CHAT_STORY = 0x2D
AUCOMM_TYPE_NARRATE = 0x4A
AUCOMM_TYPE_NARRATE_CHOICE = 0x4C
AUCOMM_TYPE_NARRATE_TITLE = 0x4E
AUCOMM_TYPE_NARRATE_AUDIO = 0x4B
AUCOMM_TYPE_CHAT_AUDIO = 0x2A

NARRATOR_SCOPE = 10

TORCH_CID = 131

STORY_ID = 0x1001

TORCH_DROP_DIST_FT = 4.0

TARGOSS_AUID = 0x7C000001
TARGOSS_NAME = "Targoss"


_RE_SAYAUDIO = re.compile(
    r"char\.sayAudio\s*\(\s*\w+\s*,\s*([^,]*?)\s*,\s*(.*?)\)\s*;", re.DOTALL)
_RE_SAYCHOICE = re.compile(
    r"char\.sayChoice\s*\(\s*\w+\s*,\s*(\d+)\s*,\s*(.*?)\)\s*;", re.DOTALL)
_RE_EDGE = re.compile(r"if\s*\((.*?)\)\s*(\w+)\s*;", re.DOTALL)
_RE_COND_CHOICE = re.compile(r"choiceMade\s*\(\s*(\d+)\s*\)")
_RE_COND_SECONDS = re.compile(r"secondsElapsed\s*\(\s*(\d+)\s*\)")
_RE_DROP = re.compile(r"char\.drop\s*\(\s*\w+\s*,\s*([^)]+?)\s*\)\s*;")
_RE_ACTION = re.compile(
    r"char\.(spawn|stay|followPerson|gotoPerson|moveBack|equip|drop)\s*"
    r"\(\s*\w+\s*(?:,([^)]*))?\)\s*;")
_RE_NARRATE = re.compile(r"narrator\.say\s*\(\s*(.*?)\)\s*;", re.DOTALL)
_RE_NARRATE_TITLE = re.compile(
    r"narrator\.title\s*\(\s*(.*?)\)\s*;", re.DOTALL)
_RE_SECONDS = re.compile(r"if\s*\(\s*secondsElapsed\s*\(\s*(\d+)\s*\)\s*\)\s*(\w+)\s*;")
_RE_ANY_GOTO = re.compile(r"if\s*\(.*?\)\s*(\w+)\s*;", re.DOTALL)
_RE_STRINGS = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _joined_strings(blob: str) -> str:
    parts = _RE_STRINGS.findall(blob)
    return "".join(p.replace('\\"', '"').replace("\\\\", "\\") for p in parts)


def _split_blocks(text: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    label: Optional[str] = None
    buf: List[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0]
        stripped = line.strip()
        if stripped.startswith(":"):
            if label is not None:
                out.append((label, "\n".join(buf)))
            label = stripped[1:].strip()
            buf = []
        elif label is not None:
            buf.append(line)
    if label is not None:
        out.append((label, "\n".join(buf)))
    return out


def parse_blocks(path: str = DEFAULT_SCRIPT) -> dict:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        raw = dict(_split_blocks(fh.read()))

    _scan = ((_RE_NARRATE_TITLE, "title"), (_RE_NARRATE, "narrate"),
             (_RE_SAYAUDIO, "say"), (_RE_SAYCHOICE, "choice"))

    out = {}
    for label, body in raw.items():
        found = []
        for rx, kind in _scan:
            for m in rx.finditer(body):
                wav = ""
                if kind == "choice":
                    idx, blob = int(m.group(1)), m.group(2)
                elif kind == "say":
                    idx, wav, blob = 0, m.group(1).strip(), m.group(2)
                else:
                    idx, blob = 0, m.group(1)
                said = _joined_strings(blob)
                if said:
                    speaker = "" if kind in ("title", "narrate") else TARGOSS_NAME
                    found.append((m.start(), speaker, said, kind, idx, wav))
        lines = [(spk, txt, k, i, w)
                 for _pos, spk, txt, k, i, w in sorted(found)]

        m_drop = _RE_DROP.search(body)
        drop = m_drop.group(1).strip() if m_drop else None

        first_line_pos = min((f[0] for f in found), default=None)
        actions = []
        for m in _RE_ACTION.finditer(body):
            raw = (m.group(2) or "").strip()
            actions.append((
                m.group(1),
                [a.strip() for a in raw.split(",")] if raw else [],
                first_line_pos is None or m.start() < first_line_pos,
            ))

        edges = []
        for cond, target in _RE_EDGE.findall(body):
            mc = _RE_COND_CHOICE.search(cond)
            ms = _RE_COND_SECONDS.search(cond)
            if mc:
                edges.append(("choice", int(mc.group(1)), target))
            elif ms:
                edges.append(("seconds", float(ms.group(1)), target))
            else:
                edges.append(("other", cond.strip(), target))
        out[label] = {"lines": lines, "drop": drop, "edges": edges,
                      "actions": actions}
    return out


_PENDING_CHOICE: dict = {}

CHOICE_TIMEOUT_S = 30.0

MAX_BLOCK_VISITS = 4


STORY_OP_CHOICE_PICKED = 0x7C
STORY_OP_CLOSE = 0x7D
STORY_OP_HINT = 0x7E
STORY_OP_RESEND_BLOCK = 0x7F


STORY_OPS = (STORY_OP_CHOICE_PICKED, STORY_OP_CLOSE,
             STORY_OP_HINT, STORY_OP_RESEND_BLOCK)


def parse_choice_picked(payload: bytes) -> Optional[tuple]:
    import struct as _struct
    if len(payload) < 10 or payload[0] != STORY_OP_CHOICE_PICKED:
        return None
    inst, choice, offered = _struct.unpack(">IbI", payload[1:10])
    return int(inst), int(choice), int(offered)


def on_choice(avatar_auid: int, choice_index: int) -> bool:
    key = int(avatar_auid) & 0xFFFFFFFF
    fut = _PENDING_CHOICE.get(key)
    if fut is None or fut.done():
        return False
    fut.set_result(int(choice_index))
    logger.debug("Choice %d received for avatar 0x%08x.", choice_index, key)
    return True


_CURRENT_BLOCK: dict = {}

_DROPPED: set = set()


async def on_story_op(live_avatars: dict, avatar_auid: int,
                      payload: bytes) -> bool:
    if not payload:
        return False
    op = payload[0]
    auid = int(avatar_auid) & 0xFFFFFFFF
    try:
        if op == STORY_OP_CHOICE_PICKED:
            parsed = parse_choice_picked(payload)
            if parsed is None:
                logger.warning(
                    "0x7C ChoicePicked frame malformed (%d bytes): %s",
                    len(payload), payload[:16].hex())
                return False
            inst, choice, offered = parsed
            logger.debug("0x7C ChoicePicked instance=%d choice=%d "
                         "offeredBy=0x%08x avatar=0x%08x",
                         inst, choice, offered, auid)
            if not on_choice(auid, choice):
                logger.debug("Choice %d arrived with no story waiting on "
                             "this avatar.", choice)
            return True

        if op == STORY_OP_CLOSE:
            logger.info("Player 0x%08x dropped the tutorial "
                        "(0x7D CloseStory).", auid)
            _DROPPED.add(auid)
            fut = _PENDING_CHOICE.get(auid)
            if fut is not None and not fut.done():
                fut.cancel()
            return True

        if op == STORY_OP_HINT:
            logger.debug('Hint requested by 0x%08x.', auid)
            return True

        if op == STORY_OP_RESEND_BLOCK:
            await _resend_current_block(live_avatars, auid)
            return True
    except Exception as exc:
        logger.error("Story op 0x%02X dropped: %r", op, exc)
        return False
    return False


async def _resend_current_block(live_avatars: dict, auid: int) -> None:
    cur = _CURRENT_BLOCK.get(auid)
    if not cur:
        logger.debug("0x7F resend for 0x%08x with no current block.", auid)
        return
    label, section, lines, script_path = cur
    writer = _writer_for(live_avatars, auid)
    if writer is None:
        logger.debug("0x7F resend for 0x%08x with no open writer.", auid)
        return
    logger.debug("0x7F resend block %r (%d line(s)) for 0x%08x",
                 label, len(lines), auid)
    sec = section
    for speaker, text, kind, cidx, wav in lines:
        if kind == "title":
            sec = text
            pkt = _build_narrate(text, sec, auid,
                                 AUCOMM_TYPE_NARRATE_TITLE)
        elif kind == "narrate":
            pkt = _build_narrate(text, sec, auid, AUCOMM_TYPE_NARRATE)
        elif kind == "choice":
            pkt = _build_line(text, speaker, auid,
                              AUCOMM_TYPE_CHAT_CHOICE, cidx)
        else:
            pkt = _build_line(text, speaker, auid, AUCOMM_TYPE_CHAT_STORY)
        try:
            await write_framed(writer, pkt)
        except Exception as exc:
            logger.warning("0x7F resend stopped: %r", exc)
            return
        await _send_audio(writer, wav, script_path, auid)


async def _await_choice(auid: int, timeout: float):
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    _PENDING_CHOICE[auid] = fut
    try:
        return await asyncio.wait_for(fut, timeout)
    except Exception:
        return None
    finally:
        _PENDING_CHOICE.pop(auid, None)


async def _run_actions(live_avatars: dict, avatar_auid: int, actions,
                       pre: bool, *, spawn_world_flag,
                       save, avatar_dna, _DYNAMIC_SCENE_AUIDS) -> bool:
    dropped = False
    if not actions:
        return dropped
    from openshores.gameplay import story_npc as _npc
    for verb, args, is_pre in actions:
        if bool(is_pre) != bool(pre):
            continue
        try:
            if verb == "spawn":
                angle = float(args[0]) if len(args) >= 1 else 180.0
                dist = float(args[1]) if len(args) >= 2 else 50.0
                await _npc.spawn(
                    live_avatars, avatar_auid, angle, dist,
                    save=save, avatar_dna=avatar_dna,
                    _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)
            elif verb == "stay":
                await _npc.stay(avatar_auid)
            elif verb in ("followPerson", "gotoPerson"):
                await _npc.follow_person(avatar_auid)
            elif verb == "moveBack":
                await _npc.move_back(avatar_auid,
                                     float(args[0]) if args else 4.0)
            elif verb == "equip":
                if len(args) >= 2:
                    quality = 1
                    if len(args) >= 3:
                        try:
                            quality = max(1, min(100, int(args[-1])))
                        except Exception:
                            quality = 1
                    await _npc.equip(live_avatars, avatar_auid,
                                     args[0], args[1], quality)
            elif verb == "drop":
                await _drop_torch(live_avatars, avatar_auid,
                                  spawn_world_flag=spawn_world_flag)
                dropped = True
        except Exception as exc:
            logger.warning("char.%s%r failed; the story goes on: %r",
                           verb, tuple(args), exc)
    return dropped


async def _race_conditions(live_avatars: dict, avatar_auid: int, edges,
                           timeout: float, *, augear_states, actor_cursor
                           ) -> Optional[str]:
    from openshores.gameplay import story_npc as _npc
    if not edges:
        return None
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.0, float(timeout))
    logger.debug("Racing %d live condition(s) for %.0fs: %s",
                 len(edges), timeout,
                 ", ".join("%s -> %s" % (c, t) for c, t in edges))
    while loop.time() < deadline:
        await _npc.pump(live_avatars)
        for cond, target in edges:
            if _npc.evaluate_condition(
                    live_avatars, avatar_auid, cond,
                    augear_states=augear_states,
                    actor_cursor=actor_cursor) is True:
                d = _npc.distance_ft(live_avatars, avatar_auid)
                logger.debug("Condition %r fired -> %r (Targoss %s ft away)",
                             cond, target,
                             "%.1f" % d if d is not None else "?")
                return target
        await asyncio.sleep(CONDITION_POLL_S)
    return None


async def _drop_torch(live_avatars: dict, avatar_auid: int, *,
                      spawn_world_flag) -> None:
    auid = int(avatar_auid) & 0xFFFFFFFF
    entry = live_avatars.get(auid)
    if not isinstance(entry, dict):
        logger.debug("Torch drop skipped: avatar 0x%08x is not live.", auid)
        return
    parent = entry.get("parent_world")
    xyz = entry.get("xyz")
    if not parent or not xyz:
        logger.debug("Torch drop skipped: parent=%r xyz=%r", parent, xyz)
        return
    if isinstance(parent, (bytes, bytearray)):
        parent = int.from_bytes(bytes(parent), "big")
    from openshores.gameplay.natives.village import _offset_xyz as _tangent
    xyz = _tangent(tuple(xyz), TORCH_DROP_DIST_FT, 0.0)
    try:
        new_auid = await spawn_world_flag(
            actor_auid=auid, parent_world_auid=int(parent),
            flag_cid=TORCH_CID, quality=100, xyz=tuple(xyz))
        logger.info("Targoss dropped a Torch (cid=%d) -> DaItem %s",
                    TORCH_CID,
                    ("0x%08x" % new_auid) if new_auid else "FAILED")
    except Exception as exc:
        logger.warning("Torch drop failed; the story goes on: %r", exc)


def _qstr_be(text: str, limit: int = 256) -> bytes:
    import struct as _struct
    body = text[:limit].encode("utf-16-be")
    return _struct.pack(">i", len(body)) + body


def _build_line(text: str, speaker: str, target_auid: int,
                type_byte: int = AUCOMM_TYPE_CHAT_STORY,
                choice_index: int = 0) -> bytes:
    import struct as _struct
    tb = int(type_byte)
    qstr = _qstr_be(text)
    from openshores.gameplay import story_npc as _npc
    sender_auid = _npc.atom_auid(int(target_auid) & 0xFFFFFFFF) \
        or TARGOSS_AUID
    if tb == AUCOMM_TYPE_CHAT_CHOICE:
        tail = (bytes([int(choice_index) & 0xFF])
                + _struct.pack(">i", STORY_ID)
                + qstr
                + _struct.pack(">I", int(target_auid) & 0xFFFFFFFF))
    elif tb == AUCOMM_TYPE_CHAT_STORY:
        tail = _struct.pack(">i", STORY_ID) + qstr
    else:
        tail = qstr
    return build_chat_aucomm_v4(
        type_byte=tb,
        body_after_parent=tail,
        sender_auid_int=sender_auid,
        sender_name=speaker or TARGOSS_NAME,
        target_auid_int=int(target_auid) & 0xFFFFFFFF,
        channel_index=VOICE_CHANNEL_INDEX,
        flags_byte=0x0F,
        scope=(NARRATOR_SCOPE if tb == AUCOMM_TYPE_CHAT_STORY else VOICE_SCOPE),
    )


def _build_narrate(text: str, title: str, target_auid: int,
                   type_byte: int = AUCOMM_TYPE_NARRATE,
                   choice_index: int = 0) -> bytes:
    import struct as _struct
    tb = int(type_byte)
    tail = _struct.pack(">i", STORY_ID) + _qstr_be(text)
    if tb == AUCOMM_TYPE_NARRATE_CHOICE:
        tail = bytes([int(choice_index) & 0xFF]) + tail
    return build_chat_aucomm_v4(
        type_byte=tb,
        body_after_parent=tail,
        sender_auid_int=0,
        sender_name="",
        target_auid_int=int(target_auid) & 0xFFFFFFFF,
        channel_name=title or DEFAULT_SECTION_TITLE,
        flags_byte=0x0F,
        scope=NARRATOR_SCOPE,
    )


AUDIO_LARGE_THRESHOLD = 0xFC00

_WAV_CACHE: dict = {}


def _audio_dir(script_path: str) -> str:
    return os.path.dirname(os.path.abspath(script_path))


def _wav_is_playable(data: bytes) -> Optional[str]:
    import struct as _struct
    if len(data) < 44:
        return "shorter than a WAV header (%d B)" % len(data)
    if data[0:4] != b"RIFF":
        return "no RIFF magic"
    if data[8:12] != b"WAVE":
        return "no WAVE magic"
    if data[12:16] != b"fmt ":
        return ("first chunk is %r, not 'fmt ' -- the client parser does not "
                "scan for it" % data[12:16])
    try:
        fmt_len = _struct.unpack("<i", data[16:20])[0]
        audio_fmt, channels, rate = _struct.unpack("<hhi", data[20:28])
        bits = _struct.unpack("<h", data[34:36])[0]
    except Exception as exc:
        return "unreadable fmt chunk: %r" % (exc,)
    if audio_fmt not in (1, 0xFFFE):
        return "audioFormat %d is not PCM -- alBufferData would get garbage" \
            % audio_fmt
    if bits not in (8, 16):
        return "bitsPerSample %d (the client would read it as 16-bit)" % bits
    if channels not in (1, 2):
        return "channels %d (the client would read it as stereo)" % channels
    off, tries = 20 + fmt_len, 10
    while off + 8 <= len(data) and data[off:off + 4] != b"data":
        if tries == 0:
            return "more than 10 chunks before 'data'"
        tries -= 1
        off += 8 + _struct.unpack("<i", data[off + 4:off + 8])[0]
    if off + 8 > len(data) or data[off:off + 4] != b"data":
        return "no 'data' chunk"
    _ = (rate,)
    return None


def _load_wav(name: str, script_path: str) -> Optional[bytes]:
    if not name:
        return None
    key = (os.path.abspath(script_path), name)
    if key in _WAV_CACHE:
        return _WAV_CACHE[key]
    path = os.path.join(_audio_dir(script_path), name)
    data = None
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except Exception as exc:
        logger.warning("Story audio %r unreadable at %s (%r); the line stays "
                       "text-only.", name, path, exc)
        _WAV_CACHE[key] = None
        return None
    why = _wav_is_playable(data)
    if why is not None:
        logger.warning("Story audio %r rejected: %s; the line stays "
                       "text-only.", name, why)
        _WAV_CACHE[key] = None
        return None
    if len(data) > AUDIO_LARGE_THRESHOLD:
        logger.debug("Story audio %r is %d B (> IsDataLarge 0x%X); "
                     "sending whole.", name, len(data), AUDIO_LARGE_THRESHOLD)
    _WAV_CACHE[key] = data
    return data


def _build_narrate_audio(wav: bytes, target_auid: int) -> bytes:
    import struct as _struct
    tail = (_struct.pack(">I", len(wav)) + bytes(wav)
            + _struct.pack(">i", STORY_ID)
            + _struct.pack(">i", 0))
    return build_chat_aucomm_v4(
        type_byte=AUCOMM_TYPE_NARRATE_AUDIO,
        body_after_parent=tail,
        sender_auid_int=0,
        sender_name="",
        target_auid_int=int(target_auid) & 0xFFFFFFFF,
        channel_name="",
        flags_byte=0x0F,
        scope=NARRATOR_SCOPE,
    )


async def _send_audio(writer, wav_name: str, script_path: str,
                      target_auid: int) -> bool:
    if not wav_name:
        return False
    data = _load_wav(wav_name, script_path)
    if not data:
        return False
    from openshores.gameplay import story_npc as _npc
    op, pkt = _npc.build_audio_packet(
        data, int(target_auid) & 0xFFFFFFFF, STORY_ID)
    if pkt is None:
        pkt = _build_narrate_audio(data, int(target_auid) & 0xFFFFFFFF)
        op = AUCOMM_TYPE_NARRATE_AUDIO
    try:
        await write_framed(writer, pkt)
    except Exception as exc:
        logger.warning("Story audio %r not sent; the line stands without it: "
                       "%r", wav_name, exc)
        return False
    logger.debug("  +audio %s (%d B) as 0x%02X", wav_name, len(data), op)
    return True


def _writer_for(live_avatars: dict, auid: int):
    entry = live_avatars.get(auid)
    if not isinstance(entry, dict):
        return None
    return _chat_only_writer(entry)


async def play(live_avatars: dict, avatar_auid: int,
               script_path: Optional[str] = None,
               lead_in_s: float = 6.0, *, spawn_world_flag,
               save, avatar_dna, _DYNAMIC_SCENE_AUIDS,
               augear_states, actor_cursor) -> None:
    path = script_path or DEFAULT_SCRIPT
    try:
        blocks = parse_blocks(path)
    except Exception as exc:
        logger.error("Targoss script unreadable at %r (%r). No tutorial will "
                     "be told.", path, exc)
        return
    if ENTRY_LABEL not in blocks:
        logger.error("Targoss script has no ':%s' block. No tutorial will be "
                     "told.", ENTRY_LABEL)
        return

    auid = int(avatar_auid) & 0xFFFFFFFF
    section = catalyst_meta(path)["title"] or DEFAULT_SECTION_TITLE
    logger.info("Targoss: %d block(s) for avatar 0x%08x "
                "(lead-in %.0fs, source=%r, tab=%r, instance=%d)",
                len(blocks), auid, lead_in_s, path, section, STORY_ID)
    await asyncio.sleep(lead_in_s)

    label = ENTRY_LABEL
    visits: dict = {}
    _DROPPED.discard(auid)
    while label and label in blocks:
        if auid in _DROPPED:
            logger.info("Targoss stopping at %r: the player dropped the "
                        "story.", label)
            break
        visits[label] = visits.get(label, 0) + 1
        if visits[label] > MAX_BLOCK_VISITS:
            logger.warning("Targoss stopping: block %r revisited %dx, so the "
                           "script is cycling.", label, visits[label])
            return
        blk = blocks[label]
        _CURRENT_BLOCK[auid] = (label, section, blk["lines"], path)

        dropped_in_actions = await _run_actions(
            live_avatars, auid, blk.get("actions"), pre=True,
            spawn_world_flag=spawn_world_flag, save=save,
            avatar_dna=avatar_dna,
            _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS)

        for speaker, text, kind, cidx, wav in blk["lines"]:
            writer = _writer_for(live_avatars, auid)
            if writer is None:
                logger.info("Targoss stopped in %r: the avatar has no open "
                            "chat writer.", label)
                return
            if kind == "title":
                section = text
                pkt = _build_narrate(text, section, auid,
                                     AUCOMM_TYPE_NARRATE_TITLE)
            elif kind == "narrate":
                pkt = _build_narrate(text, section, auid,
                                     AUCOMM_TYPE_NARRATE)
            elif kind == "choice":
                pkt = _build_line(text, speaker, auid,
                                  AUCOMM_TYPE_CHAT_CHOICE, cidx)
            else:
                pkt = _build_line(text, speaker, auid,
                                  AUCOMM_TYPE_CHAT_STORY)
            try:
                await write_framed(writer, pkt)
                logger.debug("Targoss [%s] %-7s%s: %r",
                             label, kind,
                             (" %d" % cidx) if kind == "choice" else "",
                             text[:64])
            except Exception as exc:
                logger.warning("Targoss stopped in %r; the line did not "
                               "send: %r", label, exc)
                return
            await _send_audio(writer, wav, path, auid)

        if await _run_actions(live_avatars, auid, blk.get("actions"),
                              pre=False,
                              spawn_world_flag=spawn_world_flag, save=save,
                              avatar_dna=avatar_dna,
                              _DYNAMIC_SCENE_AUIDS=_DYNAMIC_SCENE_AUIDS):
            dropped_in_actions = True

        if (blk["drop"] and "torch" in blk["drop"].lower()
                and not dropped_in_actions):
            await _drop_torch(live_avatars, auid,
                              spawn_world_flag=spawn_world_flag)

        edges = blk["edges"]
        choice_edges = [(a, t) for k, a, t in edges if k == "choice"]
        seconds_edge = next(((a, t) for k, a, t in edges
                             if k == "seconds" and t != label), None)
        any_edge = next((t for k, a, t in edges if t != label), None)

        if choice_edges:
            logger.debug("Targoss waiting on a choice in %r "
                         "(%d option(s), %.0fs)",
                         label, len(choice_edges), CHOICE_TIMEOUT_S)
            picked = await _await_choice(auid, CHOICE_TIMEOUT_S)
            nxt = None
            if picked is not None:
                nxt = next((t for a, t in choice_edges if a == picked), None)
                if nxt is None:
                    logger.warning("Choice %d has no edge in %r; the script "
                                   "cannot honour it.", picked, label)
            if nxt is None:
                nxt = seconds_edge[1] if seconds_edge else choice_edges[0][1]
                logger.debug("No choice made in %r; taking %r.", label, nxt)
            label = nxt
            continue

        from openshores.gameplay import story_npc as _npc
        real_edges = [
            (c, t) for k, c, t in edges
            if k == "other" and t != label and c
            and _npc.evaluate_condition(
                live_avatars, auid, c,
                augear_states=augear_states,
                actor_cursor=actor_cursor) is not None]

        if real_edges:
            budget = (min(float(seconds_edge[0]), CONDITION_TIMEOUT_S)
                      if seconds_edge else CONDITION_TIMEOUT_S)
            nxt = await _race_conditions(
                live_avatars, auid, real_edges, budget,
                augear_states=augear_states, actor_cursor=actor_cursor)
            if nxt is None:
                nxt = (seconds_edge[1] if seconds_edge
                       else real_edges[0][1])
                logger.debug("No condition fired in %r within %.0fs; "
                             "taking %r.", label, budget, nxt)
            label = nxt
            continue

        if seconds_edge:
            await asyncio.sleep(seconds_edge[0])
            label = seconds_edge[1]
            continue

        if any_edge:
            await asyncio.sleep(DEFAULT_DWELL_S)
            label = any_edge
            continue

        logger.info("Targoss finished at %r for 0x%08x", label, auid)
        return


if __name__ == "__main__":
    _b = parse_blocks()
    logger.info("%d block(s)", len(_b))
    for _lbl, _d in _b.items():
        if not _lbl:
            continue
        _e = ", ".join(
            "%s%s->%s" % (_k, ("(%s)" % _a) if _a is not None else "", _t)
            for _k, _a, _t in _d["edges"]) or "(none)"
        logger.info(":%s   edges: %s%s",
                    _lbl, _e,
                    ("   DROP=%s" % _d["drop"]) if _d["drop"] else "")
        for _v, _a, _pre in _d.get("actions", ()):
            logger.info("   %s char.%s(%s)", "^" if _pre else "v", _v,
                        ", ".join(_a))
        for _spk, _txt, _kind, _ci, _wav in _d["lines"]:
            logger.info("   %s %-8s %-16s %s",
                        "*" if _kind == "choice" else " ", _spk or "(narr)",
                        _wav or "-", _txt[:56])

    _script = DEFAULT_SCRIPT
    _wavs = []
    for _d in _b.values():
        for _l in _d["lines"]:
            if _l[4] and _l[4] not in _wavs:
                _wavs.append(_l[4])
    logger.info("Audio: %d distinct file(s) named, dir=%r",
                len(_wavs), _audio_dir(_script))
    _bad = 0
    for _w in _wavs:
        _data = _load_wav(_w, _script)
        if _data is None:
            _bad += 1
        else:
            logger.info("Ok %-18s %7d B -> 0x4B frame %d B",
                        _w, len(_data),
                        len(_build_narrate_audio(_data, 0x00DE908D)))
    logger.info("Audio: %d unusable", _bad)


AUJOB_TYPE_STORY = 0x1F


def _qstring(s: str) -> bytes:
    import struct as _struct
    b = (s or "").encode("utf-16-be")
    return _struct.pack(">I", len(b)) + b


def _qdatetime_utc(when=None) -> bytes:
    import struct as _struct
    import datetime as _dt
    t = when or _dt.datetime.now(_dt.timezone.utc)
    a = (14 - t.month) // 12
    y = t.year + 4800 - a
    m = t.month + 12 * a - 3
    jd = (t.day + (153 * m + 2) // 5 + 365 * y + y // 4
          - y // 100 + y // 400 - 32045)
    ms = ((t.hour * 60 + t.minute) * 60 + t.second) * 1000 + t.microsecond // 1000
    return _struct.pack(">IIb", jd & 0xFFFFFFFF, ms & 0xFFFFFFFF, 1)


def catalyst_meta(path: Optional[str] = None) -> dict:
    p = path or DEFAULT_SCRIPT
    meta = {"title": "Getting Started", "author": "Haxus", "brief": ""}
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            head = dict(_split_blocks(fh.read())).get("", "")
        for key in ("title", "author", "brief"):
            m = re.search(r"story\.%s\s*\(\s*(.*?)\)\s*;" % key, head, re.DOTALL)
            if m:
                val = _joined_strings(m.group(1))
                if val:
                    meta[key] = val
    except Exception as exc:
        logger.warning('Catalyst meta unreadable (%r).', exc)
    return meta


def build_job_blob(path: Optional[str] = None,
                   story_instance: int = STORY_ID) -> bytes:
    import struct as _struct
    meta = catalyst_meta(path)
    entry = (bytes([AUJOB_TYPE_STORY])
             + _qdatetime_utc()
             + _qstring(meta["author"])
             + _qstring(meta["brief"])
             + bytes([0])
             + _struct.pack(">i", int(story_instance))
             + _qstring(meta["title"]))
    return _struct.pack(">h", 1) + entry


