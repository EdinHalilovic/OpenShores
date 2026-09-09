
from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from openshores.core.logging import get_logger
from openshores.database.repositories.empire import (
    _update_empire,
    empire_office_rows,
    office_table_exists,
    read_empire_row,
    read_person_names,
    upsert_empire_office,
)
from openshores.database.repositories.empire import (
    remove_office as _remove_office_row,
)
from openshores.protocol.stream import QDS

logger = get_logger(__name__)


def _s32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


def _qimage(w: QDS, png: bytes) -> None:
    if not png:
        w.write_i32(0)
    else:
        w.write_i32(1)
        w.write_raw(png)


def _qcolor(w: QDS, argb: Optional[Tuple[int, int, int, int]]) -> None:
    if argb is None:
        w.write_u8(0)
        w.write_u16(0xFFFF)
        w.write_u16(0); w.write_u16(0); w.write_u16(0); w.write_u16(0)
        return
    a, r, g, b = argb
    w.write_u8(1)
    for c in (a, r, g, b, 0):
        w.write_u16((c * 257) & 0xFFFF if c <= 0xFF else c & 0xFFFF)


PERMISSION_BIT = {
    "CanAcceptCitySurrender": (0, 0), "CanDelegate": (0, 1),
    "CanInviteCitizens": (0, 2), "CanKickCitizens": (0, 3),
    "CanManageDossier": (0, 4), "CanManageTrade": (0, 5),
    "CanSendEmpireMail": (0, 6), "CanSetAnnouncements": (0, 7),
    "CanSetCapital": (1, 0), "CanSetColorTheme": (1, 1),
    "CanSetCommerce": (1, 2), "CanSetContrailColor": (1, 3),
    "CanSetDebtPolicy": (1, 4), "CanSetEmpireFlag": (1, 5),
    "CanSetFounderDomain": (1, 6), "CanSetFounderOffice": (1, 7),
    "CanSetImmigrationPolicy": (2, 0), "CanSetJoinPolicy": (2, 1),
    "CanSetJoinStatement": (2, 2), "CanSetPoliticalStance": (2, 3),
    "CanSetRewards": (2, 4), "CanSetRightToFound": (2, 5), "CanSetTax": (2, 6),
    "CanSetTrespassPolicy": (3, 0), "CanSetWarCriteria": (3, 1),
    "CanSetZoneBuildPolicy": (3, 2), "CanUseDiplomacyChannel": (3, 3),
    "CanAccessGovtAccount": (3, 4), "CanLoadOfficer": (3, 6),
    "CanSetPlaceNames": (4, 1), "CanSetSectorCapital": (4, 3),
    "CanSurrenderCity": (4, 4), "CanReceiveFleetMessages": (4, 5),
}
OFFICE_PERMISSIONS: Tuple[str, ...] = tuple(PERMISSION_BIT)

RIGHTS_FULL = 0xFFFFFFFF
RIGHTS_NONE = 0x00000000


def pack_office_rights(b10: int, b11: int, b12: int, b13: int,
                       b14: int) -> Tuple[int, int]:
    uVar11 = b11; bVar2 = b13; uVar10 = b14; bVar3 = b10
    bVar4 = b12; uVar9 = b12; bVar1 = b11
    uVar5 = 0x1000 if b13 >= 0x80 else 0
    uVar6 = 0x8000000 if b10 >= 0x80 else 0
    uVar7 = 0x800 if b11 >= 0x80 else 0
    uVar8 = 0x20 if b12 >= 0x80 else 0
    t = uVar11 & 1
    t = t * 2 | bVar1 & 0xc
    t = t * 2 | bVar3 & 1
    t = t << 5 | uVar11 & 2
    t = t * 2 | uVar10 & 0x20
    t = t << 2 | uVar10 & 0x40 | bVar3 & 2
    t = t * 2 | bVar2 & 1 | uVar10 & 0x10
    t = t * 2 | bVar2 & 4
    t = t << 2 | bVar2 & 0x40
    t = t * 2 | uVar10 & 7
    t = t << 2 | uVar9 & 0x20
    t = t << 5 | uVar11 & 0x10
    t = t << 2 | bVar4 & 1 | bVar2 & 0x30 | bVar3 & 0xc
    t = t << 3 | uVar9 & 2
    tail = (bVar1 >> 1 & 0x10 | bVar2 & 8) >> 3 | (uVar9 & 4) << 0x1d | \
        uVar5 | uVar6 | uVar7 | uVar8 | uVar9 & 8
    word1 = (t * 2 | tail) & 0xFFFFFFFF
    word2 = ((b12 >> 2 & 0x14 | b14 & 8 | b11 & 0x40) >> 2 |
             (((b13 & 2) << 3 | b10 & 0x20) * 2 | b10 & 0x10) * 2
             | b10 >> 3 & 8) & 0xFFFFFFFF
    return word1, word2


def unpack_office_rights(a: int, b: int) -> Tuple[int, int, int, int, int]:
    a &= 0xFFFFFFFF; b &= 0xFFFFFFFF
    b10 = b11 = b12 = b13 = b14 = 0
    b13 &= 2; b14 &= 0x88; b10 &= 0x70
    v = (a >> 0x18) & 0xFF
    b13 = (((((((a >> 0x14) & 1) * 2 | (a >> 9) & 1) * 2 | (a >> 8) & 1) * 2 | a & 1) * 2 |
            (a >> 0x12) & 1) << 2 | ((a >> 0xc) & 1) << 7 | b13 & 0xba | (a >> 0x11) & 1) & 0xFF
    b14 = ((b14 | ((((v & 1) * 2 | v >> 1 & 1) * 2 | (a >> 0x15) & 1) << 2 |
                   (a >> 0xf) & 1) * 2 | (a >> 0xe) & 1) * 2 | (a >> 0xd) & 1) & 0xFF
    b11 &= 0x40; b12 &= 0x50
    b10 = (b10 | (((v >> 3 << 4 | (a >> 7) & 1) * 2 | (a >> 6) & 1) * 2 |
                  (a >> 0x13) & 1) * 2 | v >> 2 & 1) & 0xFF
    b11 = (((((((a >> 1) & 1) * 2 | (a >> 10) & 1) * 2 | v >> 6 & 1) * 2 | v >> 5 & 1) * 2 |
            (a >> 0x16) & 1) * 2 | ((a >> 0xb) & 1) << 7 | b11 & 0xf0 | v >> 4 & 1) & 0xFF
    b12 = ((((((a >> 0x10) & 1) << 2 | (a >> 3) & 1) * 2 | v >> 7) * 2 | (a >> 2) & 1) * 2 |
           ((a >> 5) & 1) << 7 | (a >> 4) & 1 | b12 & 0xdb) & 0xFF
    b14 &= 0xf7; b11 &= 0xbf; b12 &= 0xaf; b13 &= 0xfd; b10 &= 0x8f
    b14 = (b14 | ((b >> 1) & 1) << 3) & 0xFF
    b12 = (b12 | (((b >> 2) & 1) << 2 | b & 1) << 4) & 0xFF
    b11 = (b11 | ((b >> 4) & 1) << 6) & 0xFF
    b13 = (b13 | ((b >> 6) & 1) * 2) & 0xFF
    b10 = (b10 | ((((b >> 3) & 1) * 2 | (b >> 7) & 1) * 2 | (b >> 5) & 1) << 4) & 0xFF
    return b10, b11, b12, b13, b14


def office_rights(*permissions: str) -> Tuple[int, int]:
    five = [0, 0, 0, 0, 0]
    for name in permissions:
        bi, bit = PERMISSION_BIT[name]
        five[bi] |= (1 << bit)
    return pack_office_rights(*five)


def decode_office_rights(rights1: int, rights2: int) -> List[str]:
    five = unpack_office_rights(rights1, rights2)
    return sorted(n for n, (bi, bit) in PERMISSION_BIT.items()
                  if five[bi] >> bit & 1)


DEFAULTS = {
    "immigration":    0x01,
    "city_debt":      0x01,
    "default_stance": 0x01,
    "right_to_found": 0x03,
    "trespass":       0x01,
    "zone_build":     0x00,
    "role":           0x00,
    "contrail_hue":   0xAA,
    "contrail_sat":   0x7F,
    "tax_income":     0x14,
    "tax_sales":      0x0A,
    "tax_subsidy":    0x05,
    "founder_byte":   0x02,
}

THEME_DEFAULT: List[Tuple[int, int, int, int]] = [
    (255, 0x19, 0x36, 0x80),
    (255, 0x0D, 0x0D, 0x0D),
    (255, 0x40, 0x55, 0x80),
    (255, 0x19, 0x36, 0x80),
    (255, 0x0D, 0x0D, 0x0D),
    (255, 0x40, 0x55, 0x80),
]

REWARD_COLUMNS: Tuple[str, ...] = (
    "rewCapBase", "rewCapCapital", "rewCapCapitalSector", "rewCapCity",
    "rewCapSpaceport", "rewCapSpaceship", "rewCapStarship", "rewDmgSpaceport",
    "rewDmgSpaceship", "rewDmgStarShip", "rewDiscHabitable", "rewDiscWorm",
    "rewKillEnemy", "rewSalary", "rewSpotCity", "rewSpotEnemy",
)


@dataclass
class EmpireOffice:
    title: str = ""
    rights1: int = RIGHTS_NONE
    rights2: int = RIGHTS_NONE
    role_id: int = 0

    @property
    def is_emperor(self) -> bool:
        return (self.role_id & 0xFFFFFFFF) == 0

    def permission_names(self) -> List[str]:
        return decode_office_rights(self.rights1, self.rights2)


@dataclass
class EmpireMember:
    auid: int
    name: str
    office: Optional[EmpireOffice] = None

    @property
    def is_emperor(self) -> bool:
        return self.office is not None and self.office.is_emperor

    @property
    def title(self) -> str:
        if self.office is None or not self.office.title:
            return "Emperor" if self.is_emperor else "Citizen"
        return self.office.title


@dataclass
class EmpireStatus:
    tax_income: int = DEFAULTS["tax_income"]
    tax_sales: int = DEFAULTS["tax_sales"]
    tax_subsidy: int = DEFAULTS["tax_subsidy"]
    default_stance: int = DEFAULTS["default_stance"]
    right_to_found: int = DEFAULTS["right_to_found"]
    trespass: int = DEFAULTS["trespass"]
    city_debt: int = DEFAULTS["city_debt"]
    zone_build: int = DEFAULTS["zone_build"]
    immigration: int = DEFAULTS["immigration"]
    contrail_hue: int = DEFAULTS["contrail_hue"]
    contrail_sat: int = DEFAULTS["contrail_sat"]
    role: int = DEFAULTS["role"]
    founder_byte: int = DEFAULTS["founder_byte"]
    rewards: List[int] = field(default_factory=lambda: [0] * 16)
    theme: List[Tuple[int, int, int, int]] = field(
        default_factory=lambda: list(THEME_DEFAULT))
    flag_png: bytes = b""
    capital_name: str = "Capital"


@dataclass
class EmpireRecord:
    empire_id: int
    name: str
    name_short: str
    status: EmpireStatus = field(default_factory=EmpireStatus)
    members: List[EmpireMember] = field(default_factory=list)
    player_avatar_id: int = 0

    @property
    def emperor(self) -> Optional[EmpireMember]:
        for m in self.members:
            if m.is_emperor:
                return m
        return None

    @property
    def titled_members(self) -> List[EmpireMember]:
        return [m for m in self.members
                if m.office is not None and m.office.title]


def default_db_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hazeron.db")


OFFICE_SCHEMA = """
CREATE TABLE IF NOT EXISTS g_EmpireOffice (
    empire_id  INTEGER NOT NULL,
    avatar_id  INTEGER NOT NULL,
    title      TEXT    NOT NULL DEFAULT '',
    rights1    INTEGER NOT NULL DEFAULT 0,
    rights2    INTEGER NOT NULL DEFAULT 0,
    role_id    INTEGER NOT NULL DEFAULT 0,
    boss_id    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (empire_id, avatar_id)
);
"""


def ensure_schema(db_path: Optional[str] = None) -> None:
    raise NotImplementedError(
        "The g_EmpireOffice DDL moved out of gameplay.")


async def _has_office_table(conn) -> bool:
    return await office_table_exists(conn)


async def set_office(conn, empire_id: int, avatar_id: int, title: str = "",
                     rights1: int = RIGHTS_FULL, rights2: int = RIGHTS_FULL,
                     role_id: Optional[int] = None, boss_id: int = 0,
                     permissions: Optional[List[str]] = None,
                     db_path: Optional[str] = None) -> None:
    empire_id &= 0xFFFFFFFF
    avatar_id &= 0xFFFFFFFF
    if permissions is not None:
        rights1, rights2 = office_rights(*permissions)
    if role_id is None:
        role_id = avatar_id
    await upsert_empire_office(conn, empire_id, avatar_id, title,
                               rights1, rights2, role_id, boss_id)


async def remove_office(conn, empire_id: int, avatar_id: int,
                        db_path: Optional[str] = None) -> None:
    await _remove_office_row(conn, empire_id, avatar_id)


async def _office_rows(conn, empire_id: int):
    return await empire_office_rows(conn, empire_id)


async def _load_offices(conn, empire_id: int) -> dict:
    if not await _has_office_table(conn):
        return {}
    out = {}
    for aid, title, r1, r2, role, _boss in await _office_rows(conn, empire_id):
        out[int(aid) & 0xFFFFFFFF] = EmpireOffice(
            title=str(title or ""),
            rights1=int(r1) & 0xFFFFFFFF,
            rights2=int(r2) & 0xFFFFFFFF,
            role_id=int(role) & 0xFFFFFFFF)
    return out


_EMPIRE_COLUMNS: Tuple[str, ...] = (
    "name", "taxIncome", "taxSales", "taxSubsidy", "defaultStance",
    "rightToFound", "trespass", "cityDebt", "zoneBuildPolicy", "immig",
    "contrailHue", "contrailSat", "role",
) + REWARD_COLUMNS + ("theme", "flag", "capturemsg", "citizens")


def _col(row, name: str):
    return row.get(name) if row else None


def _byte(v, default: int) -> int:
    if v is None:
        return default & 0xFF
    if isinstance(v, (bytes, bytearray)):
        return v[0] if len(v) else (default & 0xFF)
    try:
        return int(v) & 0xFF
    except (TypeError, ValueError):
        return default & 0xFF


def _int32(v) -> int:
    if v is None:
        return 0
    if isinstance(v, (bytes, bytearray)):
        if len(v) >= 4:
            return struct.unpack(">i", bytes(v[:4]))[0]
        return int.from_bytes(bytes(v), "big") if v else 0
    try:
        return int(v) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return 0


def _parse_theme(blob) -> Optional[List[Tuple[int, int, int, int]]]:
    if not blob:
        return None
    try:
        b = bytes(blob)
        pos = 0
        count = b[pos]; pos += 1
        colors: List[Tuple[int, int, int, int]] = []
        for _ in range(count):
            spec = b[pos]; pos += 1
            if spec == 0:
                colors.append((0, 0, 0, 0)); continue
            vals = struct.unpack_from(">5H", b, pos); pos += 10
            a, r, g, bl, _pad = vals
            colors.append((a >> 8, r >> 8, g >> 8, bl >> 8))
        while len(colors) < 6:
            colors.append((255, 0, 0, 0))
        return colors[:6]
    except Exception:
        return None


def _parse_citizens(blob) -> List[int]:
    out: List[int] = []
    if not blob:
        return out
    b = bytes(blob)
    if len(b) < 4:
        return out
    count = struct.unpack(">I", b[:4])[0]
    for i in range(count):
        off = 4 + i * 16
        if off + 4 > len(b):
            break
        aid = struct.unpack(">I", b[off:off + 4])[0]
        if aid:
            out.append(aid)
    return out


def _person_name(names: dict, auid: int) -> str:
    name = names.get(auid & 0xFFFFFFFF)
    return name if name else f"0x{auid & 0xFFFFFFFF:08x}"


async def load_empire(conn, empire_id: int, db_path: Optional[str] = None,
                      player_avatar_id: int = 0) -> EmpireRecord:
    empire_id &= 0xFFFFFFFF
    db_path = db_path or default_db_path()
    row = await read_empire_row(conn, empire_id, _EMPIRE_COLUMNS)
    name = _col(row, "name") or f"Empire {empire_id}"
    st = EmpireStatus()
    st.tax_income    = _byte(_col(row, "taxIncome"),   DEFAULTS["tax_income"])
    st.tax_sales     = _byte(_col(row, "taxSales"),    DEFAULTS["tax_sales"])
    st.tax_subsidy   = _byte(_col(row, "taxSubsidy"),  DEFAULTS["tax_subsidy"])
    st.default_stance= _byte(_col(row, "defaultStance"),DEFAULTS["default_stance"])
    st.right_to_found= _byte(_col(row, "rightToFound"),DEFAULTS["right_to_found"])
    st.trespass      = _byte(_col(row, "trespass"),    DEFAULTS["trespass"])
    st.city_debt     = _byte(_col(row, "cityDebt"),    DEFAULTS["city_debt"])
    st.zone_build    = _byte(_col(row, "zoneBuildPolicy"),DEFAULTS["zone_build"])
    st.immigration   = _byte(_col(row, "immig"),       DEFAULTS["immigration"])
    st.contrail_hue  = _byte(_col(row, "contrailHue"), DEFAULTS["contrail_hue"])
    st.contrail_sat  = _byte(_col(row, "contrailSat"), DEFAULTS["contrail_sat"])
    st.role          = _byte(_col(row, "role"),        DEFAULTS["role"])
    st.rewards = [_int32(_col(row, c)) for c in REWARD_COLUMNS]
    st.theme = _parse_theme(_col(row, "theme")) or list(THEME_DEFAULT)
    _flag = _col(row, "flag")
    if _flag and bytes(_flag) != b"\xff\xff\xff\xff":
        st.flag_png = bytes(_flag)
    _cap = _col(row, "capturemsg")
    st.capital_name = _cap if _cap else "Capital"

    offices = await _load_offices(conn, empire_id)
    citizen_ids = _parse_citizens(_col(row, "citizens"))
    names = await read_person_names(conn, citizen_ids)
    members: List[EmpireMember] = []
    for idx, aid in enumerate(citizen_ids):
        nm = _person_name(names, aid)
        off = offices.get(aid)
        if off is None:
            if idx == 0:
                off = EmpireOffice(title="Emperor",
                                   rights1=RIGHTS_FULL, rights2=RIGHTS_FULL,
                                   role_id=0)
            else:
                off = EmpireOffice(title="", rights1=RIGHTS_NONE,
                                   rights2=RIGHTS_NONE, role_id=aid)
        members.append(EmpireMember(auid=aid, name=nm, office=off))
    return EmpireRecord(
        empire_id=empire_id,
        name=name,
        name_short=(name[:30] if name else f"E{empire_id}"),
        status=st, members=members,
        player_avatar_id=player_avatar_id & 0xFFFFFFFF)


async def write_status(conn, empire_id: int, status: EmpireStatus,
                       db_path: Optional[str] = None) -> None:
    empire_id &= 0xFFFFFFFF
    cols = {
        "taxIncome": status.tax_income, "taxSales": status.tax_sales,
        "taxSubsidy": status.tax_subsidy,
        "defaultStance": status.default_stance,
        "rightToFound": status.right_to_found, "trespass": status.trespass,
        "cityDebt": status.city_debt, "zoneBuildPolicy": status.zone_build,
        "immig": status.immigration, "contrailHue": status.contrail_hue,
        "contrailSat": status.contrail_sat, "role": status.role,
    }
    for i, v in enumerate(status.rewards[:16]):
        cols[REWARD_COLUMNS[i]] = _s32(v)
    await _update_empire(conn, empire_id, **cols)


def _write_office(w: QDS, office: EmpireOffice) -> None:
    w.write_i32(office.rights1)
    w.write_i32(office.rights2)
    w.write_i16(0)
    w.write_u32(office.role_id & 0xFFFFFFFF)
    w.write_qstring(office.title or None)


def _write_citizen(w: QDS, m: EmpireMember) -> None:
    w.write_u32(m.auid & 0xFFFFFFFF)
    w.write_qstring(m.name or "")
    w.write_u8(0x88)
    _write_office(w, m.office or EmpireOffice(role_id=m.auid))


def _nested(inner: bytes) -> bytes:
    return struct.pack(">I", len(inner)) + inner


def serialize_dg_empire(rec: EmpireRecord, *,
                        player_avatar_id: Optional[int] = None,
                        auid_wire_bytes: int = 16) -> bytes:
    pav = (player_avatar_id if player_avatar_id is not None
           else rec.player_avatar_id) & 0xFFFFFFFF
    st = rec.status
    w = QDS()

    w.write_i32(rec.empire_id)
    w.write_qstring(rec.name)
    w.write_qstring(rec.name_short)
    w.write_u8(st.immigration)
    _qimage(w, st.flag_png)

    for i in range(16):
        w.write_i32(st.rewards[i] if i < len(st.rewards) else 0)

    w.write_u8(st.tax_income)
    w.write_u8(st.tax_sales)
    w.write_u8(st.tax_subsidy)
    w.write_u8(st.default_stance)

    _inner = QDS()
    _inner.write_i16(0)
    _inner.write_u8(0)
    _inner.write_i16(0)
    inner = _inner.getvalue()
    w.write_bytes(inner)

    for c in (st.theme + THEME_DEFAULT)[:6]:
        _qcolor(w, c)

    w.write_bytes(b"")

    cz = QDS()
    cz.write_i16(len(rec.members))
    for m in rec.members:
        _write_citizen(cz, m)
    w.write_bytes(cz.getvalue())

    _city_hash = QDS()
    _city_hash.write_i16(0)
    w.write_bytes(_city_hash.getvalue())

    if auid_wire_bytes == 16:
        w.write_u32(pav)
        w.write_u32(0)
        w.write_u32(0)
        w.write_u32(0)
    else:
        w.write_u32(pav)
    w.write_bytes(bytes(24))

    w.write_u8(st.right_to_found)
    w.write_u8(st.founder_byte)
    _write_office(w, rec.emperor.office if rec.emperor
                  else EmpireOffice(title="", role_id=0,
                                    rights1=RIGHTS_FULL, rights2=RIGHTS_FULL))
    w.write_u8(st.trespass)
    w.write_u8(st.contrail_hue)
    w.write_u8(st.contrail_sat)
    w.write_u8(st.city_debt)
    w.write_u8(st.zone_build)
    w.write_qstring(st.capital_name)

    return w.getvalue()


_STANCE = {0: "Self", 1: "Ally", 2: "Friend", 3: "Neutral",
           4: "Suspicious", 5: "Enemy"}
_RTF = {0: "Anyone", 1: "Citizens", 2: "Officers", 3: "Nobody"}


def describe(rec: EmpireRecord) -> str:
    st = rec.status
    L = []
    L.append(f'Empire {rec.empire_id}  "{rec.name}"  (short: {rec.name_short})')
    L.append("  STATUS / OPTIONS")
    L.append(f"    taxes        income={st.tax_income}  sales={st.tax_sales}  "
             f"subsidy={st.tax_subsidy}")
    L.append(f"    default stance  {_STANCE.get(st.default_stance, st.default_stance)}")
    L.append(f"    right to found  {_RTF.get(st.right_to_found, st.right_to_found)}")
    L.append(f"    policies     trespass={st.trespass}  cityDebt={st.city_debt}  "
             f"zoneBuild={st.zone_build}  immigration={st.immigration}")
    L.append(f"    contrail     hue={st.contrail_hue} sat={st.contrail_sat}   "
             f"role={st.role}")
    L.append(f"    flag         {'PNG %dB' % len(st.flag_png) if st.flag_png else '(none)'}"
             f"    capital={st.capital_name!r}")
    rew = ", ".join(f"{REWARD_COLUMNS[i]}={st.rewards[i]}"
                    for i in range(len(st.rewards)) if st.rewards[i])
    L.append(f"    rewards      {rew or '(all default 0)'}")
    L.append(f"  MEMBERS ({len(rec.members)})")
    for m in rec.members:
        tag = "  <EMPEROR>" if m.is_emperor else ""
        powers = ""
        if m.office and m.office.title and not m.is_emperor:
            np = len(m.office.permission_names())
            powers = f"  [{np} powers]" if np else "  [ceremonial]"
        L.append(f"    0x{m.auid:08x}  {m.name:<22} {m.title}{tag}{powers}")
    titled = rec.titled_members
    if titled:
        L.append("  TITLED OFFICERS: " +
                 ", ".join(f"{m.name} ({m.office.title})" for m in titled))
    return "\n".join(L)


if __name__ == "__main__":
    import asyncio
    import sys

    from openshores.database.pool import connect

    async def _main() -> None:
        eid = int(sys.argv[1], 0) if len(sys.argv) > 1 else 370624
        pool = await connect()
        async with pool.acquire() as conn:
            rec = await load_empire(conn, eid)
        logger.info("%s", describe(rec))
        payload = serialize_dg_empire(
            rec, player_avatar_id=(rec.members[0].auid if rec.members else 1))
        logger.info("0x31 DgEmpire payload = %d bytes (head %s ...)",
                    len(payload), payload[:24].hex())

    asyncio.run(_main())
