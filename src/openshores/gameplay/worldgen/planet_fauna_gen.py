from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from openshores.core.logging import configure, get_logger
from openshores.database.repositories import animal as _rows
from openshores.protocol.dhdna import AuDice, DhDNA

logger = get_logger(__name__)


ATMTYPE_NAMES = {0: "Standard", 1: "Tainted", 2: "Exotic",
                 3: "Corrosive", 4: "Insidious"}
HABITABLE_ATM_TYPES = {0x00, 0x01}

HABITABLE_ZONES = {1, 2, 3}


def is_planet_habitable(globe_row: dict) -> bool:
    z = _byte_or_int(globe_row.get("orbitZone"))
    a = _byte_or_int(globe_row.get("atmType"))
    d = _byte_or_int(globe_row.get("atmDensity"))
    w = _byte_or_int(globe_row.get("water"))
    if z is None or a is None or d is None or w is None:
        return False
    if z not in HABITABLE_ZONES:
        return False
    if a not in HABITABLE_ATM_TYPES:
        return False
    if not (15 <= d <= 85):
        return False
    if w == 0:
        return False
    return True


def _byte_or_int(v) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray, memoryview)):
        b = bytes(v)
        if len(b) == 0:
            return None
        return b[0]
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _roster_size(globe_row: dict, dice: AuDice) -> int:
    z = _byte_or_int(globe_row.get("orbitZone")) or 2
    w = _byte_or_int(globe_row.get("water")) or 0
    base = max(2, w // 10)
    if z == 3:
        base += 1
    base += dice.roll(1, 3, -1)
    return max(3, min(12, base))


@dataclass
class RosterEntry:

    dna: DhDNA
    name: str = ""
    max_instances_per_visit: int = 5

    def to_bytes(self) -> bytes:
        return self.dna.to_bytes()

    def to_string(self) -> str:
        return self.dna.to_string()


POSE_STANDING = 0x24
POSE_SLEEPING = 0x20
POSE_DIGGING  = 0x16
POSE_SWIMMING = 0x2A
POSE_FLYING   = 0x18

DNA_BIT_CAN_FLY = 0x0800
DNA_BIT_WATER   = 0x1000
DNA_BIT_BURROW  = 0x2000


@dataclass
class SpawnIndividual:

    species_idx: int
    individual_idx: int
    dna: DhDNA
    xyz: tuple
    yaw_rad: float
    pose: int
    hp: int
    max_hp: int
    stamina: int
    hunger: int
    sex: int
    adult: bool


def _decide_pose(dna: DhDNA) -> int:
    if dna.can_fly():
        return POSE_FLYING
    if dna.is_water():
        return POSE_SWIMMING
    if dna.is_burrow():
        return POSE_DIGGING
    return POSE_STANDING


def _density_cap(land_value: int) -> int:
    return (max(0, int(land_value)) // 0x14 + 3) * 5


def _hunger_init(dna: DhDNA, max_hp: int, dice: AuDice) -> int:
    return max(1, (int(max_hp) * 2 * dice.roll(1, 100)) // 100)


def roll_individuals(
    roster: list[RosterEntry],
    *,
    spawn_anchor_xyz: tuple,
    dice: AuDice,
    per_species: int = 3,
    max_total: int = 20,
    jitter_m: float = 30.0,
    land_value: int = 50,
    max_hp_default: int = 100,
) -> list[SpawnIndividual]:
    cap_density = _density_cap(land_value)
    cap = min(max_total, cap_density)
    out: list[SpawnIndividual] = []
    ax, ay, az = spawn_anchor_xyz
    j = max(1, int(jitter_m))
    sides = j * 2
    for sp_idx, entry in enumerate(roster):
        if len(out) >= cap:
            break
        n_ind = min(per_species, entry.max_instances_per_visit)
        pose = _decide_pose(entry.dna)
        for ind in range(n_ind):
            if len(out) >= cap:
                break
            dx = dice.roll(1, sides, -j)
            dy = dice.roll(1, sides, -j)
            dz = 0.0
            xyz = (float(ax + dx), float(ay + dy), float(az + dz))
            yaw_rad = (dice.roll(1, 360) * 3.14159265 / 180.0)
            sex = dice.roll(1, 2) - 1
            adult = bool(dice.roll(1, 2) - 1)
            hp = max_hp_default
            hunger = _hunger_init(entry.dna, max_hp_default, dice)
            out.append(SpawnIndividual(
                species_idx=sp_idx,
                individual_idx=ind,
                dna=entry.dna,
                xyz=xyz,
                yaw_rad=float(yaw_rad),
                pose=pose,
                hp=hp,
                max_hp=max_hp_default,
                stamina=0x7F,
                hunger=hunger,
                sex=sex,
                adult=adult,
            ))
    return out


def roll_planet_roster(
    globe_row: dict,
    *,
    planet_auid: Optional[int] = None,
    force: bool = False,
) -> list[RosterEntry]:
    if not force and not is_planet_habitable(globe_row):
        return []

    seed = planet_auid if planet_auid is not None else int(globe_row["id"])
    seed32 = seed & 0xFFFFFFFF
    dice = AuDice(seed=seed32 or 1)

    n = _roster_size(globe_row, dice)
    z = _byte_or_int(globe_row.get("orbitZone")) or 2
    tod = z & 3

    _wsize = _byte_or_int(globe_row.get("radius")) or 0
    _gas = 0x14 <= _wsize <= 0x28
    if _wsize == 0x32:
        _size_mod = 0
    elif _gas:
        _size_mod = 2 + 8
    else:
        _size_mod = 8 - _wsize
        if z == 1:
            _size_mod += 4
        elif z == 3:
            _size_mod += 2

    roster: list[RosterEntry] = []
    for _ in range(n):
        d = DhDNA()
        d.randomize(
            dice,
            phylum=0,
            sentient=False,
            tod=tod,
            randomize_w4_low3=False,
        )

        _sz = min(31, abs(dice.roll(2, 31, _size_mod - 31)))
        d.w[3] = (d.w[3] & ~0xf800 & 0xFFFFFFFF) | ((_sz or 1) << 11)
        per_visit = max(1, dice.roll(1, 5))
        roster.append(RosterEntry(dna=d, max_instances_per_visit=per_visit))
    return roster


SCHEMA_A_ANIMAL = """
CREATE TABLE IF NOT EXISTS a_Animal (
    id          INTEGER PRIMARY KEY,
    idp         INTEGER,
    locX        REAL,
    locY        REAL,
    locZ        REAL,
    rotX        REAL,
    rotY        REAL,
    rotZ        REAL,
    timeCreate  INTEGER,
    timeModified INTEGER,
    timeTick    INTEGER,
    timeTock    INTEGER,
    timeDeath   INTEGER,
    name        TEXT,
    allegiance  INTEGER,
    arenaTeam   INTEGER,
    conditions  BLOB,
    hunger      INTEGER,
    seatIndex   INTEGER,
    hp          INTEGER,
    sex         INTEGER,
    dna         BLOB,
    islefty     INTEGER,
    pose        INTEGER,
    whichConsole INTEGER,
    atRest      INTEGER,
    vecX        REAL,
    vecY        REAL,
    vecZ        REAL,
    stamina     INTEGER,
    minsToFullGrown INTEGER,
    parent_atom INTEGER
)
"""


async def ensure_schema(conn) -> None:
    await _rows.ensure_schema(conn)


async def register_species(conn, dna, name, creator_id=0) -> bool:
    return await _rows.register_species(conn, dna.to_bytes(), name)


def _self_test() -> None:
    logger.info("planet_fauna_gen self-test")
    habitable = {"id": 1494406, "orbitZone": bytes([0x02]),
                 "atmType": bytes([0x00]), "atmDensity": bytes([0x1e]),
                 "water": bytes([0x14])}
    assert is_planet_habitable(habitable), (
        "A zone-2, breathable, wet planet must support wildlife")
    toxic = dict(habitable, atmType=bytes([0x02]))
    assert not is_planet_habitable(toxic), "AtmType 2 is toxic, not habitable"
    airless = dict(habitable, atmDensity=bytes([0x00]))
    assert not is_planet_habitable(airless)
    dry = dict(habitable, water=bytes([0x00]))
    assert not is_planet_habitable(dry)
    frozen = dict(habitable, orbitZone=bytes([0x07]))
    assert not is_planet_habitable(frozen)
    roster = roll_planet_roster(habitable)
    assert roster, "A habitable planet must roll a non-empty roster"
    logger.info("Roster: %d species", len(roster))
    for i, e in enumerate(roster):
        logger.info("  [%d] sentient=%s fly=%s role=%s",
                    i, e.dna.is_sentient(), e.dna.can_fly(), e.dna.eco_role())
    individuals = roll_individuals(
        roster,
        spawn_anchor_xyz=(0.0, 0.0, 6_400_000.0),
        dice=AuDice(seed=1494406),
        per_species=2,
        max_total=10,
        jitter_m=30.0,
        land_value=50)
    for ind in individuals:
        pose_name = {0x18: "fly", 0x2A: "swim", 0x16: "dig",
                     0x24: "stand"}.get(ind.pose, hex(ind.pose))
        logger.info("Spawn sp%d#%d pose=%s sex=%d adult=%s hp=%d hunger=%d xyz=(%+.1f,%+.1f,%.1f)",
                    ind.species_idx, ind.individual_idx, pose_name,
                    ind.sex, ind.adult, ind.hp, ind.hunger,
                    ind.xyz[0], ind.xyz[1], ind.xyz[2])
    logger.info("OK")


if __name__ == "__main__":
    configure()
    _self_test()
