
from __future__ import annotations

from typing import NamedTuple, Optional

from openshores.core.logging import get_logger
from openshores.database.repositories.person import _lookup_person_by_auid
from openshores.protocol.login_reply import (
    _default_dna,
    build_login_ok_reply_for_avatars,
)

logger = get_logger(__name__)


class AvatarRecord(NamedTuple):
    auid: int
    name: str
    dna: bytes
    sex: int
    lefty: bool


async def _resolve_avatar_record(conn, auid: int, *,
                                 save,
                                 last_avatar_dna: bytes) -> AvatarRecord:
    if int(auid) == int(save.person_auid):
        return AvatarRecord(
            int(auid),
            save.person_name,
            save.person_dna24 or last_avatar_dna or _default_dna(),
            1, False)
    try:
        _row = await _lookup_person_by_auid(conn, int(auid))
    except Exception as exc:
        logger.warning('[login]   a_Person lookup for avatar 0x%08x failed (%r).', int(auid) & 0xFFFFFFFF, exc)
        _row = None
    if _row:
        _row_dna = _row.get("dna") if isinstance(_row, dict) else None
        if _row_dna and any(b != 0 for b in _row_dna):
            _dna = bytes(_row_dna)
        else:
            _dna = (save.person_dna24 or last_avatar_dna or _default_dna())
        _sex = _row.get("sex")
        _lefty = _row.get("islefty")
        return AvatarRecord(
            int(auid),
            _row["name"] or ("Avatar 0x%08x" % int(auid)),
            _dna,
            1 if _sex is None else int(_sex),
            False if _lefty is None else bool(_lefty))
    return AvatarRecord(
        int(auid), f"Avatar {auid:#x}", _default_dna(), 1, False)


def build_login_ok_reply(active_player_unit: int = 0,
                         screen_name: Optional[str] = None, *,
                         save,
                         last_avatar_name: Optional[str],
                         last_avatar_dna: bytes) -> bytes:
    name = last_avatar_name or screen_name or save.person_name
    dna = last_avatar_dna or save.person_dna24 or _default_dna()
    auid = int(save.person_auid)
    logger.info(f"[login]   legacy open-mode reply: slot0 auid=0x{auid:08x} "
                f"name={name!r}")
    return build_login_ok_reply_for_avatars(active_player_unit, [(auid, name, dna)])
