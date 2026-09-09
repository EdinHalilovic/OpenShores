
from __future__ import annotations

import time as _t

import asyncpg

from openshores.core.accounts import default_store
from openshores.core.logging import get_logger
from openshores.database.pool import Error
from openshores.database.repositories.empire import (
    emperor_for_empire,
    invalidate_empire_membership_cache,
)
from openshores.database.repositories.login_ops import (
    _strip_from_empire_citizens,
    _update_person,
    delete_person,
    person_names,
    select_person_name,
    update_person_identity,
)
from openshores.database.repositories.person import mark_offline
from openshores.protocol.login_ops import ROSTER_SLOTS

from openshores.network.peer_ip_state import (
    _reset_session_state_for_ip,
)

logger = get_logger(__name__)


async def roster_for_peer(conn: asyncpg.Connection, peer_host: str = "",
                          username: str = "", *,
                          session_usernames_by_ip: dict) -> list:
    if not username and peer_host:
        username = username_for_peer(
            peer_host, session_usernames_by_ip=session_usernames_by_ip)

    ids: list = []
    if username:
        try:
            ids = [int(a) for a in default_store().list_avatars(username)]
        except Exception as exc:
            logger.warning("Roster lookup failed for %r: %r. That account's "
                           "picker will be empty.", username, exc)
            ids = []

    names: dict = {}
    if ids:
        names = await person_names(conn, ids)
        ids = [i for i in ids if i in names]

    out = []
    for auid in ids[:ROSTER_SLOTS]:
        out.append((auid, names[auid]))
    return out


LOGIN_USER_BY_IP: dict = {}


def remember_login(peer_host: str, username: str) -> None:
    if peer_host and username:
        LOGIN_USER_BY_IP[str(peer_host)] = str(username)


def username_for_peer(peer_host: str, *,
                      session_usernames_by_ip: dict) -> str:
    if not peer_host:
        return ""
    u = session_usernames_by_ip.get(peer_host, "")
    if u:
        return u
    return LOGIN_USER_BY_IP.get(str(peer_host), "")


def _authorize_avatar(auid: int, username: str, peer_host: str, *,
                      session_usernames_by_ip: dict):
    if not username and peer_host:
        username = username_for_peer(
            peer_host, session_usernames_by_ip=session_usernames_by_ip)
    store = default_store()
    if not username:
        return (False, username, store,
                "no account bound to this peer; refusing an "
                "unauthenticated change")
    try:
        roster = [int(a) for a in store.list_avatars(username)]
    except Exception as exc:
        return False, username, store, f"roster lookup failed ({exc!r})"
    if int(auid) & 0xFFFFFFFF not in roster:
        return (False, username, store,
                f"avatar 0x{int(auid) & 0xFFFFFFFF:08x} is not on "
                f"{username!r}'s roster {[hex(a) for a in roster]}")
    return True, username, store, ""


async def delete_avatar(live_avatars: dict, conn: asyncpg.Connection,
                        auid: int, *, username: str = "",
                        peer_host: str = "",
                        session_usernames_by_ip: dict) -> dict:
    auid = int(auid) & 0xFFFFFFFF
    out = {"auid": auid, "deleted": False, "reason": "", "name": None,
           "empires": [], "roster_user": None}
    if not auid:
        out["reason"] = "auid 0"
        return out

    if auid in live_avatars:
        out["reason"] = "avatar is currently online"
        return out

    ok, username, store, reason = _authorize_avatar(
        auid, username, peer_host,
        session_usernames_by_ip=session_usernames_by_ip)
    if not ok:
        out["reason"] = reason
        return out
    out["roster_user"] = username

    try:
        row = await select_person_name(conn, auid)
        out["name"] = row[0] if row else None
        if row:
            await delete_person(conn, auid)
        out["empires"] = await _strip_from_empire_citizens(conn, auid)
    except Error as exc:
        out["reason"] = f"delete failed ({exc!r})"
        return out

    if store is not None and username:
        try:
            store.remove_avatar(username, auid)
        except Exception as exc:
            logger.error('Roster cleanup failed for %r avatar 0x%08x: %r.',
                         username, auid, exc)

    invalidate_empire_membership_cache()

    out["deleted"] = True
    return out


DHDNA_LEN = 24


async def apply_player_unit_renamed(conn: asyncpg.Connection, auid: int,
                                    name: str, *, username: str = "",
                                    peer_host: str = "",
                                    session_usernames_by_ip: dict) -> dict:
    out = {"auid": int(auid) & 0xFFFFFFFF, "name": name,
           "applied": False, "reason": ""}
    if not out["auid"]:
        out["reason"] = "auid 0"
        return out
    if not name or not name.strip():
        out["reason"] = "empty name"
        return out
    ok, _u, _s, reason = _authorize_avatar(
        out["auid"], username, peer_host,
        session_usernames_by_ip=session_usernames_by_ip)
    if not ok:
        out["reason"] = reason
        return out
    ok, reason = await _update_person(conn, out["auid"], "name", name)
    out["applied"], out["reason"] = ok, reason
    return out


async def apply_player_unit_dna_changed(conn: asyncpg.Connection, auid: int,
                                        dna: bytes, *, username: str = "",
                                        peer_host: str = "",
                                        session_usernames_by_ip: dict) -> dict:
    out = {"auid": int(auid) & 0xFFFFFFFF, "dna_len": len(dna or b""),
           "applied": False, "reason": ""}
    if not out["auid"]:
        out["reason"] = "auid 0"
        return out
    if len(dna or b"") != DHDNA_LEN:
        out["reason"] = (f"DhDNA is {len(dna or b'')}B, expected "
                         f"{DHDNA_LEN}B -- refusing")
        return out
    ok, _u, _s, reason = _authorize_avatar(
        out["auid"], username, peer_host,
        session_usernames_by_ip=session_usernames_by_ip)
    if not ok:
        out["reason"] = reason
        return out
    ok, reason = await _update_person(conn, out["auid"], "dna", bytes(dna))
    out["applied"], out["reason"] = ok, reason
    return out


async def apply_player_unit_died(conn: asyncpg.Connection, auid: int, *,
                                 username: str = "", peer_host: str = "",
                                 session_usernames_by_ip: dict) -> dict:
    out = {"auid": int(auid) & 0xFFFFFFFF, "applied": False, "reason": ""}
    if not out["auid"]:
        out["reason"] = "auid 0"
        return out
    ok, _u, _s, reason = _authorize_avatar(
        out["auid"], username, peer_host,
        session_usernames_by_ip=session_usernames_by_ip)
    if not ok:
        out["reason"] = reason
        return out
    ok, reason = await _update_person(conn, out["auid"], "timeDeath",
                                      int(_t.time() * 1000))
    out["applied"], out["reason"] = ok, reason
    if ok:
        await mark_offline(conn, out["auid"])
    return out


async def apply_set_player_unit(conn: asyncpg.Connection, auid: int, name: str,
                                dna: bytes, sex: int, lefty: bool, *,
                                username: str = "", peer_host: str = "",
                                session_usernames_by_ip: dict) -> dict:
    return await apply_player_unit_born(
        conn, auid, name, dna, sex, lefty, username=username,
        peer_host=peer_host, session_usernames_by_ip=session_usernames_by_ip)


async def apply_player_unit_born(conn: asyncpg.Connection, auid: int,
                                 name: str, dna: bytes, sex: int, lefty: bool,
                                 *, username: str = "", peer_host: str = "",
                                 session_usernames_by_ip: dict) -> dict:
    auid = int(auid) & 0xFFFFFFFF
    out = {"auid": auid, "applied": False, "linked": False, "reason": ""}
    if not auid:
        out["reason"] = "auid 0"
        return out
    if len(dna or b"") != DHDNA_LEN:
        out["reason"] = (f"DhDNA is {len(dna or b'')}B, expected "
                         f"{DHDNA_LEN}B -- refusing")
        return out
    ok, username, store, reason = _authorize_avatar(
        auid, username, peer_host,
        session_usernames_by_ip=session_usernames_by_ip)
    if not ok:
        out["reason"] = reason
        return out

    try:
        if not await update_person_identity(conn, auid, name, dna, sex, lefty):
            out["reason"] = ("no a_Person row yet; creation belongs to the "
                             "scene-side variant-B path, not here")
            return out
        out["applied"] = True
    except Error as exc:
        out["reason"] = f"update failed ({exc!r})"
        return out

    if store is not None and username:
        try:
            out["linked"] = bool(store.add_avatar(username, auid))
        except Exception as exc:
            logger.error('Roster link failed for %r avatar 0x%08x: %r.',
                         username, auid, exc)
    return out


_PENDING_AVATAR_OFFERS: dict = {}


def avatar_offer_timeout_sec() -> float:
    return 300.0


def _username_for_avatar(auid: int) -> str:
    want = int(auid) & 0xFFFFFFFF
    store = default_store()
    try:
        users = list(store.list_users())
    except Exception:                               # noqa: BLE001
        return ""
    for u in users:
        roster = []
        try:
            entries = list(store.list_avatars(u))
        except Exception:                           # noqa: BLE001
            return ""
        for entry in entries:
            if isinstance(entry, (int, float)):
                roster.append(int(entry))
                continue
            text = str(entry).strip()
            if not text.lstrip("-").isdigit():
                return ""
            roster.append(int(text))
        if want in roster:
            return u
    return ""


def record_avatar_offer(avatar_auid: int, giver_auid: int,
                        target_auid: int) -> dict:
    out = {"avatar": int(avatar_auid) & 0xFFFFFFFF, "ok": False, "reason": ""}
    if not out["avatar"] or not int(giver_auid) or not int(target_auid):
        out["reason"] = "offer is missing the avatar, giver or target"
        return out
    if int(giver_auid) == int(target_auid):
        out["reason"] = "cannot offer an avatar to yourself"
        return out
    owner = _username_for_avatar(out["avatar"])
    giver_owner = _username_for_avatar(int(giver_auid) & 0xFFFFFFFF)
    if owner and giver_owner and owner != giver_owner:
        out["reason"] = (f"avatar 0x{out['avatar']:08x} belongs to {owner!r}, "
                         f"not to the offering account {giver_owner!r}")
        return out
    _PENDING_AVATAR_OFFERS[out["avatar"]] = (
        int(giver_auid) & 0xFFFFFFFF, int(target_auid) & 0xFFFFFFFF,
        _t.monotonic())
    out["ok"] = True
    return out


async def transfer_avatar(live_avatars: dict, conn: asyncpg.Connection,
                          avatar_auid: int, accepter_auid: int, *,
                          empire_for_avatar,
                          _CITIZEN_EMPIRE_OVERRIDE: dict) -> dict:
    avatar_auid = int(avatar_auid) & 0xFFFFFFFF
    accepter_auid = int(accepter_auid) & 0xFFFFFFFF
    out = {"avatar": avatar_auid, "from_user": None, "to_user": None,
           "moved": False, "reason": ""}

    pend = _PENDING_AVATAR_OFFERS.get(avatar_auid)
    if pend is None:
        out["reason"] = "no pending offer for this avatar"
        return out
    giver_auid, target_auid, ts = pend
    if _t.monotonic() - ts > avatar_offer_timeout_sec():
        _PENDING_AVATAR_OFFERS.pop(avatar_auid, None)
        out["reason"] = "the offer expired"
        return out
    if target_auid != accepter_auid:
        out["reason"] = (f"offer was made to 0x{target_auid:08x}, not to "
                         f"0x{accepter_auid:08x}")
        return out

    if avatar_auid in live_avatars:
        out["reason"] = "avatar is currently online"
        return out

    emp = int(await empire_for_avatar(
        conn, avatar_auid,
        _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)) & 0xFFFFFFFF
    if emp and int(await emperor_for_empire(conn, emp)) & 0xFFFFFFFF == avatar_auid:
        out["reason"] = (
            f"avatar 0x{avatar_auid:08x} is the emperor of empire "
            f"0x{emp:08x}; transferring it hands over the empire.")
        return out

    from_user = _username_for_avatar(avatar_auid)
    to_user = live_avatars.get(accepter_auid, {}).get("username") or ""
    if not to_user:
        to_user = _username_for_avatar(accepter_auid)
    out["from_user"], out["to_user"] = from_user or None, to_user or None
    if not to_user:
        out["reason"] = ("cannot resolve the accepting account; refusing to "
                         "move an avatar to nowhere")
        return out
    if from_user == to_user:
        _PENDING_AVATAR_OFFERS.pop(avatar_auid, None)
        out["reason"] = "giver and accepter are the same account"
        return out

    try:
        store = default_store()
        store.add_avatar(to_user, avatar_auid)
        if from_user:
            store.remove_avatar(from_user, avatar_auid)
    except Exception as exc:
        out["reason"] = f"roster move failed ({exc!r})"
        return out

    _PENDING_AVATAR_OFFERS.pop(avatar_auid, None)
    out["moved"] = True
    return out


async def note_logout(live_avatars: dict, conn: asyncpg.Connection,
                      peer_host: str = "", *,
                      session_usernames_by_ip: dict,
                      scene_connect_n_by_ip: dict,
                      variant_b_handled_by_ip: dict,
                      force_closed_once_by_ip: dict) -> dict:
    out = {"peer_host": peer_host, "username": None, "offline": []}
    out["username"] = session_usernames_by_ip.get(peer_host) or None

    for auid, ent in list(live_avatars.items()):
        addr = ent.get("remote_addr")
        host = addr[0] if isinstance(addr, tuple) else addr
        if peer_host and host and str(host) != str(peer_host):
            continue
        out["offline"].append(int(auid) & 0xFFFFFFFF)

    for auid in out["offline"]:
        try:
            await mark_offline(conn, auid)
        except Exception as exc:
            logger.warning('Marking avatar 0x%08x offline failed: %r.', auid, exc)
    _reset_session_state_for_ip(
        peer_host,
        scene_connect_n_by_ip=scene_connect_n_by_ip,
        variant_b_handled_by_ip=variant_b_handled_by_ip,
        force_closed_once_by_ip=force_closed_once_by_ip)
    return out
