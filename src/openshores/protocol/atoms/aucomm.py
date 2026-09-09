
from __future__ import annotations

import logging
import struct
from typing import Optional

from openshores.protocol.encryption import au_crypt, net_crypt_key
from openshores.protocol.stream import QDS

logger = logging.getLogger(__name__)


CHAT_CHANNEL_TABLE = (
    'Hail',
    'Galactic',
    'Voice',
    'Intercom',
    'Crew',
    'Trade',
    'Friend',
    'Help',
    'Diplomacy',
    'Empire',
    'Government',
    'Fleet',
    'Company',
    'Recruit',
    'Thoughts',
    'Agent',
    'Programmer',
    'Architect',
    'Galaktika',
    'Galaxie',
    'Galaxia',
    'Galaktischen',
)


def _parse_AuCommChat(body):
    try:
        p = 0
        ci = struct.unpack('>b', body[p:p+1])[0]; p += 1
        if ci == -1:
            ln = struct.unpack('>i', body[p:p+4])[0]; p += 4
            channel = body[p:p+ln].decode('utf-16-be') if ln > 0 else ''
            p += max(0, ln)
        else:
            channel = (CHAT_CHANNEL_TABLE[ci]
                       if 0 <= ci < len(CHAT_CHANNEL_TABLE) else '')
        flags = body[p]; p += 1
        galaxy = flags & 0x1F
        has_galaxy = bool(flags & 0x20)
        has_range = bool(flags & 0x40)
        has_aux = bool(flags & 0x80)
        sender_auid = struct.unpack('>I', body[p:p+4])[0]; p += 4
        nl = struct.unpack('>i', body[p:p+4])[0]; p += 4
        if nl > 0:
            sender_name = body[p:p+nl].decode('utf-16-be')
            p += nl
        else:
            sender_name = ''
        target_auid = struct.unpack('>I', body[p:p+4])[0]; p += 4
        cur_range = max_range = 0
        if has_range:
            rb = body[p]; p += 1
            cur_range = rb & 0x0F
            max_range = (rb >> 4) & 0x0F
        scope = body[p]; p += 1
        aux = 0
        if has_aux:
            aux = struct.unpack('>i', body[p:p+4])[0]; p += 4
        tl = struct.unpack('>i', body[p:p+4])[0]; p += 4
        if tl > 0:
            text = body[p:p+tl].decode('utf-16-be', errors='replace')
            p += tl
        else:
            text = ''
        return dict(channel=channel, galaxy=galaxy, has_galaxy=has_galaxy,
                    sender_auid=sender_auid, sender_name=sender_name,
                    target_auid=target_auid, cur_range=cur_range,
                    max_range=max_range, scope=scope, aux=aux,
                    text=text, raw_flags=flags)
    except Exception as exc:
        logger.warning(
            "Malformed AuCommChat from a client; message dropped: %r "
            "body_hex=%s", exc, body[:64].hex() if body else '')
        return None


def _parse_aucomm_header(body: bytes) -> tuple[dict, int]:
    p = 0
    ci = struct.unpack('>b', body[p:p+1])[0]; p += 1
    if ci == -1:
        ln = struct.unpack('>i', body[p:p+4])[0]; p += 4
        channel = body[p:p+ln].decode('utf-16-be', errors='replace') if ln > 0 else ''
        p += max(0, ln)
    else:
        channel = (CHAT_CHANNEL_TABLE[ci]
                   if 0 <= ci < len(CHAT_CHANNEL_TABLE) else '')
    flags = body[p]; p += 1
    has_range = bool(flags & 0x40)
    has_aux = bool(flags & 0x80)
    sender_auid = struct.unpack('>I', body[p:p+4])[0]; p += 4
    nl = struct.unpack('>i', body[p:p+4])[0]; p += 4
    if nl > 0:
        sender_name = body[p:p+nl].decode('utf-16-be', errors='replace')
        p += nl
    else:
        sender_name = ''
    target_auid = struct.unpack('>I', body[p:p+4])[0]; p += 4
    cur_range = max_range = 0
    if has_range:
        rb = body[p]; p += 1
        cur_range = rb & 0x0F
        max_range = (rb >> 4) & 0x0F
    scope = body[p]; p += 1
    aux = 0
    if has_aux:
        aux = struct.unpack('>i', body[p:p+4])[0]; p += 4
    return (dict(channel=channel, raw_flags=flags,
                 sender_auid=sender_auid, sender_name=sender_name,
                 target_auid=target_auid, cur_range=cur_range,
                 max_range=max_range, scope=scope, aux=aux), p)


def _read_qstring(body: bytes, p: int) -> tuple[str, int]:
    n = struct.unpack('>i', body[p:p+4])[0]
    p += 4
    if n <= 0:
        return ('', p)
    s = body[p:p+n].decode('utf-16-be', errors='replace')
    return (s, p + n)


def _read_qauidlist(body: bytes, p: int) -> tuple[list, int]:
    n = struct.unpack('>i', body[p:p+4])[0]; p += 4
    ids = []
    for _ in range(max(0, n)):
        ids.append(struct.unpack('>I', body[p:p+4])[0])
        p += 4
    return (ids, p)


def _read_qstringlist(body: bytes, p: int) -> tuple[list, int]:
    n = struct.unpack('>i', body[p:p+4])[0]; p += 4
    out = []
    for _ in range(max(0, n)):
        s, p = _read_qstring(body, p)
        out.append(s)
    return (out, p)


def parse_aucomm_invite_to_empire(body: bytes) -> Optional[dict]:
    try:
        hdr, p = _parse_aucomm_header(body)
        invitee_auid = struct.unpack('>I', body[p:p+4])[0]; p += 4
        invitee_name, p = _read_qstring(body, p)
        empire_id = struct.unpack('>I', body[p:p+4])[0]; p += 4
        return dict(hdr,
                    invitee_auid=invitee_auid,
                    invitee_name=invitee_name,
                    empire_id=empire_id)
    except Exception as exc:
        logger.warning(
            "Malformed AuCommInviteToEmpire; packet ignored: %r "
            "body_hex=%s", exc, body[:64].hex())
        return None


def parse_aucomm_accept_invite_to_empire(body: bytes) -> Optional[dict]:
    try:
        hdr, p = _parse_aucomm_header(body)
        empire_id = struct.unpack('>I', body[p:p+4])[0]; p += 4
        return dict(hdr, empire_id=empire_id)
    except Exception as exc:
        logger.warning(
            "Malformed AuCommAcceptInviteToEmpire; packet ignored: %r "
            "body_hex=%s", exc, body[:64].hex())
        return None


def parse_aucomm_announcement(body: bytes) -> Optional[dict]:
    try:
        hdr, p = _parse_aucomm_header(body)
        text, p = _read_qstring(body, p)
        return dict(hdr, announcement=text[:256])
    except Exception as exc:
        logger.warning(
            "Malformed AuCommAnnouncement; packet ignored: %r "
            "body_hex=%s", exc, body[:64].hex())
        return None


def parse_aucomm_diplomatic_message(body: bytes) -> Optional[dict]:
    try:
        hdr, p = _parse_aucomm_header(body)
        msg, p = _read_qstring(body, p)
        return dict(hdr, message=msg[:256])
    except Exception as exc:
        logger.warning(
            "Malformed AuCommDiplomaticMessage; packet ignored: %r "
            "body_hex=%s", exc, body[:64].hex())
        return None


def parse_aucomm_city_surrender_offered(body: bytes) -> Optional[dict]:
    try:
        hdr, p = _parse_aucomm_header(body)
        city_ids, p = _read_qauidlist(body, p)
        city_names, p = _read_qstringlist(body, p)
        from_empire = struct.unpack('>I', body[p:p+4])[0]; p += 4
        to_empire = struct.unpack('>I', body[p:p+4])[0]; p += 4
        return dict(hdr,
                    city_ids=city_ids, city_names=city_names,
                    from_empire=from_empire, to_empire=to_empire)
    except Exception as exc:
        logger.warning(
            "Malformed AuCommCitySurrenderOffered; packet ignored: %r "
            "body_hex=%s", exc, body[:64].hex())
        return None


def parse_aucomm_city_surrender_accepted(body: bytes) -> Optional[dict]:
    try:
        hdr, p = _parse_aucomm_header(body)
        city_ids, p = _read_qauidlist(body, p)
        src_empire = struct.unpack('>I', body[p:p+4])[0]; p += 4
        dst_empire = struct.unpack('>I', body[p:p+4])[0]; p += 4
        return dict(hdr,
                    city_ids=city_ids,
                    source_empire=src_empire,
                    target_empire=dst_empire)
    except Exception as exc:
        logger.warning(
            "Malformed AuCommCitySurrenderAccepted; packet ignored: %r "
            "body_hex=%s", exc, body[:64].hex())
        return None


def parse_aucomm_citizen_order(body: bytes) -> Optional[dict]:
    try:
        hdr, p = _parse_aucomm_header(body)
        order_enum = body[p]; p += 1
        target_id = struct.unpack('>I', body[p:p+4])[0]; p += 4
        x = struct.unpack('>d', body[p:p+8])[0]; p += 8
        y = struct.unpack('>d', body[p:p+8])[0]; p += 8
        z = struct.unpack('>d', body[p:p+8])[0]; p += 8
        rc = struct.unpack('>h', body[p:p+2])[0]; p += 2
        recipients = []
        for _ in range(max(0, rc)):
            recipients.append(struct.unpack('>I', body[p:p+4])[0])
            p += 4
        extra_text = ''
        if order_enum == 0x29:
            extra_text, p = _read_qstring(body, p)
        return dict(hdr,
                    order_enum=order_enum, target_id=target_id,
                    x=x, y=y, z=z,
                    recipients=recipients, extra_text=extra_text)
    except Exception as exc:
        logger.warning(
            "Malformed AuCommCitizenOrder; packet ignored: %r "
            "body_hex=%s", exc, body[:64].hex())
        return None


def _q_compress(data: bytes) -> bytes:
    import zlib
    return struct.pack(">i", len(data)) + zlib.compress(data)


def _q_uncompress(blob):
    import zlib
    if len(blob) < 4:
        raise ValueError('qUncompress: blob too short')
    declared = struct.unpack('>i', blob[:4])[0]
    out = zlib.decompress(blob[4:])
    if declared >= 0 and len(out) != declared:
        raise ValueError('qUncompress: length mismatch %d vs %d' % (
            declared, len(out)))
    return out


def build_chat_aucomm_v4(
        type_byte: int,
        body_after_parent: bytes,
        sender_auid_int: int,
        sender_name: str,
        target_auid_int: int,
        channel_index: int = 0x0F,
        flags_byte: int = 0x4F,
        range_byte: int = 0x55,
        scope: int = 0,
        aux_i32: int = 0,
        crypt_key: int = 0x6E32,
        msg_header: int = None,
        channel_name: str = None,
) -> bytes:
    import time as _t
    pt = QDS()
    pt.write_u8(int(type_byte) & 0xFF)
    if channel_name is not None:
        pt.write_u8(0xFF)
        _cn = str(channel_name).encode("utf-16-be")
        pt.write_i32(len(_cn))
        pt.buf += _cn
    else:
        pt.write_u8(int(channel_index) & 0xFF)
    pt.write_u8(int(flags_byte) & 0xFF)
    pt.write_i32(int(sender_auid_int) & 0xFFFFFFFF)
    if sender_name:
        _nm = sender_name.encode("utf-16-be")
        pt.write_i32(len(_nm))
        pt.buf += _nm
    else:
        pt.write_i32(0)
    pt.write_i32(int(target_auid_int) & 0xFFFFFFFF)
    if (int(flags_byte) & 0x40):
        pt.write_u8(int(range_byte) & 0xFF)
    pt.write_u8(int(scope) & 0xFF)
    if (int(flags_byte) & 0x80):
        pt.write_i32(int(aux_i32) & 0xFFFFFFFF)
    pt.buf += bytes(body_after_parent)
    plaintext = pt.getvalue()

    compressed = _q_compress(plaintext)
    ciphertext = au_crypt(compressed, int(crypt_key) & 0xFFFF)

    if msg_header is None:
        msg_header = int(_t.time() * 1000) & 0xFFFFFFFF

    out = bytearray()
    out.append(0x0A)
    out += struct.pack(">i", len(ciphertext))
    out += ciphertext
    return bytes(out)


def build_chat_citizen_order_get_that_v4(
        item_auid_int: int,
        item_xyz: tuple,
        recipient_auid_int: int,
        sender_auid_int: int = 0,
        sender_name: str = "Robert",
        target_auid_int: int = 0x00DE908D,
        crypt_key: int = 0x6E32,
        order_type: int = 0x0D,
) -> bytes:
    if sender_auid_int == 0:
        sender_auid_int = recipient_auid_int
    tail = QDS()
    tail.write_u8(int(order_type) & 0xFF)
    tail.write_i32(int(item_auid_int) & 0xFFFFFFFF)
    tail.buf += struct.pack(">d", float(item_xyz[0]))
    tail.buf += struct.pack(">d", float(item_xyz[1]))
    tail.buf += struct.pack(">d", float(item_xyz[2]))
    tail.write_i16(1)
    tail.write_i32(int(recipient_auid_int) & 0xFFFFFFFF)
    return build_chat_aucomm_v4(
        type_byte=0x2E,
        body_after_parent=tail.getvalue(),
        sender_auid_int=sender_auid_int,
        sender_name=sender_name,
        target_auid_int=target_auid_int,
        channel_index=0x0F,
        flags_byte=0x4F,
        range_byte=0x55,
        scope=0,
        crypt_key=crypt_key,
    )


def build_chat_citizen_order_get_that_v3(
        item_auid_int: int,
        item_xyz: tuple,
        recipient_auid_int: int,
        sender_auid_int: int = 0,
        sender_name: str = "",
        order_type: int = 0x0D,
        channel_index: int = 0,
        flags_byte: int = 0,
        scope: int = 0,
        nonce: int = None,
        encrypt_key: int = 0,
) -> bytes:
    import time as _t3
    pt = QDS()
    pt.write_u8(0x2E)
    pt.write_u8(int(channel_index) & 0xFF)
    pt.write_u8(int(flags_byte) & 0xFF)
    pt.write_i32(int(sender_auid_int) & 0xFFFFFFFF)
    if sender_name:
        _nm = sender_name.encode("utf-16-be")
        pt.write_i32(len(_nm))
        pt.buf += _nm
    else:
        pt.write_i32(0)
    pt.write_i32(int(recipient_auid_int) & 0xFFFFFFFF)
    if (int(flags_byte) & 0x40):
        pt.write_u8(0)
    pt.write_u8(int(scope) & 0xFF)
    if (int(flags_byte) & 0x80):
        pt.write_i32(0)
    pt.write_u8(int(order_type) & 0xFF)
    pt.write_i32(int(item_auid_int) & 0xFFFFFFFF)
    pt.buf += struct.pack(">d", float(item_xyz[0]))
    pt.buf += struct.pack(">d", float(item_xyz[1]))
    pt.buf += struct.pack(">d", float(item_xyz[2]))
    pt.write_i16(1)
    pt.write_i32(int(recipient_auid_int) & 0xFFFFFFFF)
    body = pt.getvalue()
    if int(encrypt_key) != 0:
        body = au_crypt(body, net_crypt_key(int(encrypt_key)))

    if nonce is None:
        nonce = int(_t3.time() * 1000) & 0xFFFFFFFF

    out = bytearray()
    out.append(0x0A)
    out += struct.pack(">I", int(nonce) & 0xFFFFFFFF)
    out += b"\x00\x00\x00"
    out += body
    return bytes(out)


def _parse_aucomm_avatar_body(body: bytes, label: str):
    try:
        hdr, p = _parse_aucomm_header(body)
        avatar_auid = struct.unpack('>I', body[p:p + 4])[0]; p += 4
        avatar_name, p = _read_qstring(body, p)
        return dict(hdr, avatar_auid=avatar_auid, avatar_name=avatar_name)
    except Exception as exc:
        logger.warning(
            "Malformed AuComm %s; packet ignored: %r body_hex=%s",
            label, exc, body[:64].hex())
        return None


def parse_aucomm_offer_avatar(body: bytes) -> Optional[dict]:
    return _parse_aucomm_avatar_body(body, 'OfferAvatar')


def parse_aucomm_accept_avatar(body: bytes) -> Optional[dict]:
    return _parse_aucomm_avatar_body(body, 'AcceptAvatar')


def build_scene_auccomm_empty(subtype: int, session_lo: int = 1) -> bytes:
    pt = QDS()
    pt.write_u8(subtype & 0xFF)
    pt.write_u8(0x00)
    pt.write_i32(0)
    pt.write_i32(0)
    pt.write_i32(0)
    pt.write_u8(0x00)
    plaintext = pt.getvalue()
    ciphertext = au_crypt(plaintext, net_crypt_key(session_lo))
    out = QDS()
    out.write_u8(0x0A)
    out.write_i32(len(ciphertext))
    out.buf += ciphertext
    return out.getvalue()


def build_scene_citizen_order_get_that(
        item_auid_int: int,
        item_xyz: tuple,
        recipient_auid_int: int,
        sender_auid_int: int = 0,
        sender_name: str = "",
        session_lo: int = 1,
        order_type: int = 0x0D,
) -> bytes:
    pt = QDS()
    pt.write_u8(0x2E)
    pt.write_u8(0x00)
    pt.write_u8(0x00)
    pt.write_i32(int(sender_auid_int) & 0xFFFFFFFF)
    if sender_name:
        _nm = sender_name.encode("utf-16-be")
        pt.write_i32(len(_nm))
        pt.buf += _nm
    else:
        pt.write_i32(0)
    pt.write_i32(int(recipient_auid_int) & 0xFFFFFFFF)
    pt.write_u8(0x00)
    pt.write_u8(int(order_type) & 0xFF)
    pt.write_i32(int(item_auid_int) & 0xFFFFFFFF)
    pt.buf += struct.pack(">d", float(item_xyz[0]))
    pt.buf += struct.pack(">d", float(item_xyz[1]))
    pt.buf += struct.pack(">d", float(item_xyz[2]))
    pt.write_i16(1)
    pt.write_i32(int(recipient_auid_int) & 0xFFFFFFFF)
    plaintext = pt.getvalue()

    ciphertext = au_crypt(plaintext, net_crypt_key(session_lo))

    out = QDS()
    out.write_u8(0x0A)
    out.write_i32(len(ciphertext))
    out.buf += ciphertext
    return out.getvalue()


def build_scene_citizen_order_get_that_v2(
        item_auid_int: int,
        item_xyz: tuple,
        recipient_auid_int: int,
        sender_auid_int: int = 0,
        sender_name: str = "",
        session_lo: int = 1,
        order_type: int = 0x0D,
        channel_index: int = 0,
        flags_byte: int = 0,
        scope: int = 0,
) -> bytes:
    pt = QDS()
    pt.write_u8(0x2E)
    pt.write_u8(int(channel_index) & 0xFF)
    pt.write_u8(int(flags_byte) & 0xFF)
    pt.write_i32(int(sender_auid_int) & 0xFFFFFFFF)
    if sender_name:
        _nm = sender_name.encode("utf-16-be")
        pt.write_i32(len(_nm))
        pt.buf += _nm
    else:
        pt.write_i32(0)
    pt.write_i32(int(recipient_auid_int) & 0xFFFFFFFF)
    if (int(flags_byte) & 0x40):
        pt.write_u8(0)
    pt.write_u8(int(scope) & 0xFF)
    if (int(flags_byte) & 0x80):
        pt.write_i32(0)
    pt.write_u8(int(order_type) & 0xFF)
    pt.write_i32(int(item_auid_int) & 0xFFFFFFFF)
    pt.buf += struct.pack(">d", float(item_xyz[0]))
    pt.buf += struct.pack(">d", float(item_xyz[1]))
    pt.buf += struct.pack(">d", float(item_xyz[2]))
    pt.write_i16(1)
    pt.write_i32(int(recipient_auid_int) & 0xFFFFFFFF)
    plaintext = pt.getvalue()
    if int(session_lo) == 0:
        ciphertext = plaintext
    else:
        ciphertext = au_crypt(plaintext, net_crypt_key(int(session_lo)))
    out = QDS()
    out.write_u8(0x0A)
    out.write_i32(len(ciphertext))
    out.buf += ciphertext
    return out.getvalue()


CHAT_CHANNEL_SCOPE = (
    5,
    5,
    15,
    9,
    2,
    5,
    7,
    13,
    3,
    4,
    8,
    6, 16, 5, 14, 0, 11, 1, 5, 5, 5, 5,
)

CHAT_SCOPE_HAS_DATA = frozenset({2, 4, 6, 7, 8, 12, 16})
CHAT_CHANNELS_WITH_RANGE = frozenset({'Voice', 'Intercom', 'Thoughts'})

CHAT_RANGE_NAMES = ('Close', 'Hail', 'System', 'Sector', 'Galaxy', 'Universe')


SYSTEM_SENDER_AUID = 1
SYSTEM_SENDER_NAME = "SYSTEM"
SYSTEM_CHANNEL = "Thoughts"
AUCOMM_TYPE_CHAT = 0x29
AUCOMM_TYPE_CHAT_CONTINUED = 0x2C
CHAT_TEXT_LIMIT = 256
AUCOMM_TYPE_THOUGHT = 0x82


AUCOMM_TYPE_OFFER_AVATAR = 0x50
AUCOMM_TYPE_ACCEPT_AVATAR = 0x01


def build_aucomm_avatar_packet(type_byte: int, avatar_auid: int,
                               avatar_name: str, sender_auid: int,
                               sender_name: str, target_auid: int) -> bytes:
    tail = QDS()
    tail.write_u32(int(avatar_auid) & 0xFFFFFFFF)
    tail.write_qstring(avatar_name or "")
    idx = CHAT_CHANNEL_TABLE.index('Hail')
    return build_chat_aucomm_v4(
        type_byte=int(type_byte), body_after_parent=tail.getvalue(),
        sender_auid_int=int(sender_auid) & 0xFFFFFFFF,
        sender_name=sender_name or "",
        target_auid_int=int(target_auid) & 0xFFFFFFFF,
        channel_index=idx, scope=CHAT_CHANNEL_SCOPE[idx])


SUBTYPE_INVITE_TELEPORT = 0x9C
SUBTYPE_ACCEPT_TELEPORT = 0x9D


def _parse_base_header(plaintext: bytes) -> dict:
    s = QDS(plaintext)
    sub = s.read_u8()
    channel_idx = s.read_i8()
    channel_name = None
    if channel_idx == -1:
        channel_name = s.read_qstring()
    flags = s.read_u8()
    sender_id = s.read_u32()
    sender_name = s.read_qstring()
    target_id = s.read_u32()
    range_byte = None
    if flags & 0x40:
        range_byte = s.read_u8()
    enum30 = s.read_u8()
    extra_u32 = None
    if flags & 0x80:
        extra_u32 = s.read_u32()
    return {
        "subType": sub,
        "channelIdx": channel_idx,
        "channelName": channel_name,
        "flags": flags,
        "senderId": sender_id,
        "senderName": sender_name or "",
        "targetId": target_id,
        "rangeByte": range_byte,
        "enum30": enum30,
        "extra_u32": extra_u32,
        "bytes_consumed": s.pos,
    }


def _parse_aucomm_invite_teleport_tail(plaintext: bytes,
                                       header: dict) -> dict:
    s = QDS(plaintext)
    s.pos = header["bytes_consumed"]
    dest_auid = s.read_u32()
    dest_text = s.read_qstring() or ""
    return {
        "destAuId": dest_auid,
        "destText": dest_text,
    }


def _build_accept_teleport_ack(*, sender_id: int, sender_name: str,
                               target_id: int, dest_auid: int,
                               dest_text: str, session_lo: int) -> bytes:
    pt = QDS()
    pt.write_u8(SUBTYPE_ACCEPT_TELEPORT)
    pt.write_u8(0)
    pt.write_u8(0)
    pt.write_i32(int(sender_id) & 0xFFFFFFFF)
    pt.write_qstring(sender_name)
    pt.write_i32(int(target_id) & 0xFFFFFFFF)
    pt.write_u8(0)
    pt.write_i32(int(dest_auid) & 0xFFFFFFFF)
    pt.write_qstring(dest_text)
    plaintext = pt.getvalue()

    cipher = au_crypt(plaintext, net_crypt_key(int(session_lo)))
    out = QDS()
    out.write_u8(0x0A)
    out.write_i32(len(cipher))
    out.buf += cipher
    return out.getvalue()
