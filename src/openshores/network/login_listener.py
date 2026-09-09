
from __future__ import annotations

import asyncio

from openshores.core.logging import get_logger
from openshores.network.login_ops import (apply_player_unit_born,
                                          apply_player_unit_died,
                                          apply_player_unit_dna_changed,
                                          apply_player_unit_renamed,
                                          apply_set_player_unit, delete_avatar,
                                          note_logout, remember_login,
                                          roster_for_peer)
from openshores.network.login_roster import build_query_avatars_reply
from openshores.network.peer_ip_state import _reset_session_state_for_ip
from openshores.network.session_reset import _reset_session_state
from openshores.protocol.encryption import VERSION_STRING
from openshores.protocol.framing import read_framed, write_framed
from openshores.protocol.login import parse_login_request
from openshores.protocol.login_ops import (TYPE_DELETE_PLAYER_UNIT,
                                           TYPE_LIST_PLAYER_UNITS, TYPE_LOGOUT,
                                           TYPE_NAMES, TYPE_PLAYER_UNIT_BORN,
                                           TYPE_PLAYER_UNIT_DIED,
                                           TYPE_PLAYER_UNIT_DNA_CHANGED,
                                           TYPE_PLAYER_UNIT_RENAMED,
                                           TYPE_REQUEST_CONTACTS,
                                           TYPE_SET_PLAYER_UNIT,
                                           build_contacts_reply,
                                           build_list_player_units_reply,
                                           parse_delete_player_unit,
                                           parse_list_player_units,
                                           parse_logout,
                                           parse_player_unit_born,
                                           parse_player_unit_died,
                                           parse_player_unit_dna_changed,
                                           parse_player_unit_renamed,
                                           parse_set_player_unit)

logger = get_logger(__name__)


async def handle_login(reader, writer, *, conn, _live_avatars: dict,
                       session_usernames_by_ip: dict,
                       scene_connect_n_by_ip: dict,
                       variant_b_handled_by_ip: dict,
                       force_closed_once_by_ip: dict,
                       save, _dispatch_login):
    peer = writer.get_extra_info("peername")
    _announced_login = False
    try:
        payload = await read_framed(reader)
        if not _announced_login:
            logger.info(f"[login] {peer} connected")
            _announced_login = True
        tpe = payload[0] if payload else -1
        _tname = TYPE_NAMES.get(tpe)
        logger.debug(f"[login] <- TYPE=0x{tpe:02X}"
                     f"{' ' + _tname if _tname else ''} ({len(payload)}B): "
                     f"{payload[:64].hex()}{'...' if len(payload) > 64 else ''}")

        try:
            _peer_host_for_login = (peer[0]
                                    if isinstance(peer, tuple) else "")
        except Exception:                               # noqa: BLE001
            _peer_host_for_login = ""

        if tpe == 0x03:
            req = parse_login_request(payload)
            logger.info(f"[login]   version={req.version!r} user={req.username!r} "
                        f"pwhash={len(req.password_hash)}B")
            if req.version != VERSION_STRING:
                logger.warning(f'[login]   version mismatch: {req.version!r} vs {VERSION_STRING!r}.')
            remember_login(_peer_host_for_login, req.username or "")
            _reset_session_state(_live_avatars)
            _reset_session_state_for_ip(
                _peer_host_for_login,
                scene_connect_n_by_ip=scene_connect_n_by_ip,
                variant_b_handled_by_ip=variant_b_handled_by_ip,
                force_closed_once_by_ip=force_closed_once_by_ip)
            reply = await _dispatch_login(req, peer_host=_peer_host_for_login)
            logger.debug(f"[login]   -> reply ({len(reply)}B, opcode=0x{reply[0]:02x})")
            await write_framed(writer, reply)

        elif tpe == 0x1C:
            logger.info("[login] QueryAvatars. Replying with empty 0x1B+0x1C")
            writer.write(await build_query_avatars_reply(
                conn, peer_host=_peer_host_for_login,
                session_usernames_by_ip=session_usernames_by_ip, save=save))
            await writer.drain()

        elif tpe == TYPE_LOGOUT:
            info = parse_logout(payload)
            res = await note_logout(
                _live_avatars, conn, _peer_host_for_login,
                session_usernames_by_ip=session_usernames_by_ip,
                scene_connect_n_by_ip=scene_connect_n_by_ip,
                variant_b_handled_by_ip=variant_b_handled_by_ip,
                force_closed_once_by_ip=force_closed_once_by_ip)
            logger.info(f"[login]   Logout from {_peer_host_for_login!r} "
                        f"user={res.get('username')!r} "
                        f"marked offline: {[hex(a) for a in res.get('offline', [])]}"
                        f"{'' if info else '  (short packet, fields unread)'}")

        elif tpe == TYPE_DELETE_PLAYER_UNIT:
            req = parse_delete_player_unit(payload)
            if req is None:
                logger.warning(f'[login]   DeletePlayerUnit: malformed ({len(payload)}B, want >=13).')
            else:
                res = await delete_avatar(
                    _live_avatars, conn, req["auid"],
                    peer_host=_peer_host_for_login,
                    session_usernames_by_ip=session_usernames_by_ip)
                if res["deleted"]:
                    logger.warning(f"[login]   DeletePlayerUnit 0x{req['auid']:08x} "
                                   f"{res['name']!r} DELETED "
                                   f"(roster={res['roster_user']!r}, "
                                   f"empires={res['empires']})")
                else:
                    logger.warning(f"[login] DeletePlayerUnit 0x{req['auid']:08x} refused: {res['reason']}")

        elif tpe == TYPE_REQUEST_CONTACTS:
            reply = build_contacts_reply()
            logger.info(f"[login] RequestContacts. Replying with an empty contact list ({len(reply)}B)")
            await write_framed(writer, reply)

        elif tpe == TYPE_LIST_PLAYER_UNITS:
            req = parse_list_player_units(payload)
            units = await roster_for_peer(
                conn, _peer_host_for_login,
                session_usernames_by_ip=session_usernames_by_ip)
            reply = build_list_player_units_reply(units)
            logger.info(f"[login]   ListPlayerUnits args="
                        f"{(req or {}).get('arg0')},{(req or {}).get('arg1')} -> "
                        f"{len(units)} unit(s): "
                        f"{[(hex(a), n) for a, n in units]} ({len(reply)}B)")
            await write_framed(writer, reply)

        elif tpe == TYPE_PLAYER_UNIT_RENAMED:
            req = parse_player_unit_renamed(payload)
            if req is None:
                logger.warning(f"[login] PlayerUnitRenamed: malformed ({len(payload)}B). Ignoring")
            else:
                res = await apply_player_unit_renamed(
                    conn, req["auid"], req["name"],
                    peer_host=_peer_host_for_login,
                    session_usernames_by_ip=session_usernames_by_ip)
                logger.info(f"[login] PlayerUnitRenamed 0x{req['auid']:08x} -> {req['name']!r}: {('ok' if res['applied'] else 'refused: ' + res['reason'])}")

        elif tpe == TYPE_PLAYER_UNIT_DNA_CHANGED:
            req = parse_player_unit_dna_changed(payload)
            if req is None:
                logger.warning(f'[login]   PlayerUnitDNAChanged: malformed ({len(payload)}B).')
            else:
                res = await apply_player_unit_dna_changed(
                    conn, req["auid"], req["dna"],
                    peer_host=_peer_host_for_login,
                    session_usernames_by_ip=session_usernames_by_ip)
                logger.info(f"[login] PlayerUnitDNAChanged 0x{req['auid']:08x} ({len(req['dna'])}B): {('ok' if res['applied'] else 'refused: ' + res['reason'])}")

        elif tpe == TYPE_PLAYER_UNIT_DIED:
            req = parse_player_unit_died(payload)
            if req is None:
                logger.warning(f"[login] PlayerUnitDied: malformed ({len(payload)}B). Ignoring")
            else:
                res = await apply_player_unit_died(
                    conn, req["auid"], peer_host=_peer_host_for_login,
                    session_usernames_by_ip=session_usernames_by_ip)
                logger.info(f"[login] PlayerUnitDied 0x{req['auid']:08x}: {('timeDeath stamped' if res['applied'] else 'refused: ' + res['reason'])}")

        elif tpe == TYPE_PLAYER_UNIT_BORN:
            req = parse_player_unit_born(payload)
            if req is None:
                logger.warning(f"[login] PlayerUnitBorn: malformed ({len(payload)}B). Ignoring")
            else:
                res = await apply_player_unit_born(
                    conn, req["auid"], req["name"], req["dna"], req["sex"],
                    req["lefty"], peer_host=_peer_host_for_login,
                    session_usernames_by_ip=session_usernames_by_ip)
                logger.info(f"[login]   PlayerUnitBorn 0x{req['auid']:08x} "
                            f"{req['name']!r} sex={req['sex']} "
                            f"lefty={req['lefty']}: "
                            f"{'reconciled' if res['applied'] else 'skipped: ' + res['reason']}"
                            f"{' (roster linked)' if res['linked'] else ''}")

        elif tpe == TYPE_SET_PLAYER_UNIT:
            req = parse_set_player_unit(payload)
            if req is None:
                logger.warning(f"[login] SetPlayerUnit: malformed ({len(payload)}B). Ignoring")
            else:
                res = await apply_set_player_unit(
                    conn, req["auid"], req["name"], req["dna"], req["sex"],
                    req["lefty"], peer_host=_peer_host_for_login,
                    session_usernames_by_ip=session_usernames_by_ip)
                logger.info(f"[login]   SetPlayerUnit 0x{req['auid']:08x} "
                            f"{req['name']!r} sex={req['sex']} "
                            f"lefty={req['lefty']} acct=({req['arg0']},{req['arg1']}): "
                            f"{'reconciled' if res['applied'] else 'skipped: ' + res['reason']}"
                            f"{' (roster linked)' if res['linked'] else ''}")

        elif tpe == 0x1A:
            logger.warning("[login] TransferPlayerUnit. Accepted, no reply (state discarded)")

        else:
            _n = TYPE_NAMES.get(tpe)
            logger.warning(f"[login] unhandled TYPE 0x{tpe:02X}{(' (' + _n + ')' if _n else ' (unknown)')}, dropping")
    except asyncio.IncompleteReadError:
        if _announced_login:
            logger.info(f"[login] {peer} closed (incomplete read)")
    except Exception as e:                              # noqa: BLE001
        logger.error(f"[login] {peer} error: {e!r}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception as _close_exc:                 # noqa: BLE001
            logger.debug(f"[login] {peer} close err: {_close_exc!r}")
        if _announced_login:
            logger.info(f"[login] {peer} disconnected")
