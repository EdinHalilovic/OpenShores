
from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Iterable, Optional

from openshores.gameplay.gear_wear import test_failure, test_quality
from openshores.protocol.rng import AuDice


ZONE_RESOURCE_SIZE = 0x60


class AuZoneResource:

    __slots__ = ("raw",)

    def __init__(self, raw: Optional[bytes] = None) -> None:
        if raw is None:
            self.raw = bytearray(ZONE_RESOURCE_SIZE)
        else:
            if len(raw) != ZONE_RESOURCE_SIZE:
                raise ValueError(
                    "AuZoneResource is %d bytes, got %d"
                    % (ZONE_RESOURCE_SIZE, len(raw)))
            self.raw = bytearray(raw)

    def u8(self, off: int) -> int:
        return self.raw[off]

    def set_u8(self, off: int, value: int) -> None:
        self.raw[off] = value & 0xFF

    def i32(self, off: int) -> int:
        v = int.from_bytes(self.raw[off:off + 4], "little")
        return v - 0x100000000 if v >= 0x80000000 else v

    def set_i32(self, off: int, value: int) -> None:
        self.raw[off:off + 4] = (value & 0xFFFFFFFF).to_bytes(4, "little")

    @property
    def atmosphere_type(self) -> int:
        return self.i32(0x54)

    @property
    def climate_class(self) -> int:
        return self.i32(0x58)

    @property
    def size_class(self) -> int:
        return self.raw[0x5C]

    @property
    def star_type(self) -> int:
        return self.raw[0x5D]

    def copy(self) -> "AuZoneResource":
        return AuZoneResource(bytes(self.raw))

    def __eq__(self, other) -> bool:
        return isinstance(other, AuZoneResource) and self.raw == other.raw

    def __repr__(self) -> str:
        return ("AuZoneResource(climate=%d size=%d star=%d atm=%d "
                "atmDensity=%d sunlight=%d water=%d foliage=%d)"
                % (self.climate_class, self.size_class, self.star_type,
                   self.atmosphere_type, self.raw[0x06], self.raw[0x42],
                   self.raw[0x4C], self.raw[0x46]))


CID_AIR = 5
CID_ATMOSPHERE_DENSITY = 0x57
CID_WATER_IN_ENVIRONMENT = 0x58
CID_VEGETATION_DENSITY = 0x59
CID_SUNLIGHT = 0x5E
CID_LAVA_IN_ENVIRONMENT = 0x93
CID_SUPERCOOLED_IN_ENVIRONMENT = 0x94
CID_INFERNO_ATMOSPHERE_DENSITY = 0x95
CID_FRIGID_ATMOSPHERE_DENSITY = 0x96

FETCH_ELIGIBLE_CIDS = frozenset({
    CID_ATMOSPHERE_DENSITY, CID_WATER_IN_ENVIRONMENT, CID_VEGETATION_DENSITY,
    CID_SUNLIGHT, CID_LAVA_IN_ENVIRONMENT, CID_SUPERCOOLED_IN_ENVIRONMENT,
    CID_INFERNO_ATMOSPHERE_DENSITY, CID_FRIGID_ATMOSPHERE_DENSITY,
})


def _c_div(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _mid_band(value: int) -> bool:
    return ((value - 20) & 0xFF) <= 20


def fetch_probability(zr: AuZoneResource, cid: int) -> int:
    b = zr.raw

    if cid == CID_AIR or cid == 0x2C:
        return b[0x06]

    if cid in (0x8E, 0x96):
        if zr.i32(0x58) != 4 and not _mid_band(b[0x5C]):
            return 0
        return _c_div(b[0x06] * zr.i32(0x54), 0x4B)

    if cid in (0x8A, 0x95):
        if zr.i32(0x58) != 0:
            return 0
        if _mid_band(b[0x5C]):
            return 0
        return _c_div(b[0x06] * zr.i32(0x54), 0x4B)

    gated_climate = 0 if _mid_band(b[0x5C]) else zr.i32(0x58)
    generic = b[0x4C]
    ore_scaled = b[0x14] * 5
    ice_scaled = (b[0x4C] + 1) * gated_climate

    def _normalised(numerator: int) -> int:
        denom = (b[0x00] + b[0x40] * 40 + b[0x0A] + b[0x0D] + b[0x0F]
                 + b[0x12] + b[0x1E] + b[0x2C] + b[0x2F] + b[0x36]
                 + b[0x38] + b[0x3A] + b[0x3C] + b[0x48] + b[0x4A]
                 + ice_scaled + ore_scaled * 8)
        if denom == 0:
            raise ZeroDivisionError(
                "FetchProbability denominator is 0 for cid %d. The zone record is uninitialised or mis-parsed" % cid)
        r = _c_div(numerator, denom)
        return r if r != 0 else 1

    _SCALED = {
        0x16: 0x0D, 0x17: 0x0F, 0x39: 0x0F, 0x18: 0x12, 0x25: 0x1E,
        0x35: 0x2F, 0x3B: 0x36, 0x42: 0x3C, 0x4C: 0x40, 0x6F: 0x2C,
        0x89: 0x4A, 0x8C: 0x38, 0x8D: 0x0A, 0x90: 0x3A, 0x261: 0x00,
        0x263: 0x48,
    }
    off = _SCALED.get(cid)
    if off is not None:
        return _normalised(b[off] * 100) if b[off] != 0 else 0

    if cid == 0x2D:
        return _normalised(ice_scaled * 100) if ice_scaled != 0 else 0
    if cid == 0x86:
        return _normalised(ore_scaled * 800) if ore_scaled != 0 else 0
    if cid == 0x264:
        return b[0x1A]

    if cid == CID_ATMOSPHERE_DENSITY:
        return b[0x06]
    if cid == CID_VEGETATION_DENSITY:
        return b[0x46]
    if cid == CID_SUNLIGHT:
        return b[0x42]

    if cid in (0x53, CID_WATER_IN_ENVIRONMENT):
        if (zr.i32(0x58) & 0xFFFFFFFB) == 0:
            return 0
        return 0 if _mid_band(b[0x5C]) else generic
    if cid in (0x8B, CID_LAVA_IN_ENVIRONMENT):
        if zr.i32(0x58) != 0:
            return 0
        return 0 if _mid_band(b[0x5C]) else generic
    if cid in (0x8F, CID_SUPERCOOLED_IN_ENVIRONMENT):
        if zr.i32(0x58) == 4:
            return generic
        return generic if _mid_band(b[0x5C]) else 0

    if cid == 0x10F:
        return (5 - zr.i32(0x58)) * 2 if b[0x5C] == 0 else 0
    if cid == 0x110:
        if _mid_band(b[0x5C]):
            return (b[0x5C] // 10 - 1) * (7 - b[0x5D])
        return 0

    return 0


QUALITY_OFFSETS = {
    5: 0x02, 14: 0x04, 15: 0x09, 20: 0x50, 22: 0x0E, 23: 0x10, 24: 0x13,
    26: 0x51, 29: 0x52, 30: 0x17, 33: 0x19, 35: 0x1D, 37: 0x1F, 38: 0x21,
    39: 0x23, 42: 0x25, 43: 0x27, 44: 0x28, 45: 0x2A, 52: 0x53, 53: 0x30,
    57: 0x33, 58: 0x35, 59: 0x37, 66: 0x3D, 74: 0x3F, 76: 0x41, 81: 0x45,
    83: 0x4D, 86: 0x4F, 87: 0x07, 88: 0x4D, 89: 0x47, 94: 0x43, 111: 0x2D,
    130: 0x47, 134: 0x15, 137: 0x4B, 138: 0x2B, 139: 0x2E, 140: 0x39,
    141: 0x0B, 142: 0x11, 143: 0x31, 144: 0x3B, 147: 0x4D, 148: 0x4D,
    149: 0x07, 150: 0x07, 271: 0x05, 272: 0x0C, 609: 0x01, 611: 0x49,
    612: 0x1B,
}


def quality(zr: AuZoneResource, cid: int) -> int:
    off = QUALITY_OFFSETS.get(cid)
    return zr.raw[off] if off is not None else 0


def fetch(zr: AuZoneResource, cid: int, dice: AuDice) -> int:
    if cid not in FETCH_ELIGIBLE_CIDS:
        return 0

    if cid == CID_WATER_IN_ENVIRONMENT:
        if not (0 <= zr.i32(0x58) - 1 <= 2):
            return 0
        if _mid_band(zr.raw[0x5C]):
            return 0

    p = fetch_probability(zr, cid)
    if p == 0:
        return 0
    return 1 if dice.roll(1, 100) <= p else 0


def resource_zones(size_class: int) -> int:
    return 3 if size_class > 2 else 1


def resource_zone(longitude_rad: float, zone_count: int) -> int:
    if zone_count <= 0:
        raise ValueError("zone_count must be positive, got %r" % (zone_count,))
    d = longitude_rad + math.pi
    while d < 0.0:
        d += 2.0 * math.pi
    return int(zone_count * d / (2.0 * math.pi)) % zone_count


@dataclass
class GlobeProperties:

    climate_class: int
    size_class: int
    star_type: int = 0
    atmosphere_type: int = 0
    hydrographics: int = 0
    msl_atmosphere_density: int = 0
    average_foliage: int = 0
    can_have_fauna: bool = False
    is_satellite: bool = False

    def habitable_size(self) -> bool:
        if self.size_class == 2:
            return not self.is_satellite
        return ((self.size_class - 2) & 0xFF) < 0x0B


def _s8(v: int) -> int:
    v = int(v) & 0xFF
    return v - 256 if v >= 128 else v


def msl_atmosphere_density(globe: "GlobeProperties") -> float:
    return _f32(float(_s8(globe.msl_atmosphere_density)) / 100.0)


def can_have_flora(globe: "GlobeProperties") -> bool:
    if not globe.habitable_size():
        return False
    if _s8(globe.msl_atmosphere_density) <= 9:
        return False
    if (int(globe.atmosphere_type) & 0xFF) >= 3:
        return False
    return ((int(globe.climate_class) - 1) & 0xFF) < 3


def average_foliage(globe: "GlobeProperties") -> int:
    if not can_have_flora(globe):
        return 0
    term = _f32(msl_atmosphere_density(globe) * 100.0)
    hydro = int(globe.hydrographics) & 0xFF
    v = _f32(_f32(_f32(float(hydro)) * term) * 100.0)
    n = int(_f32(v / 50.0)) & 0xFFFFFFFF
    zone = int(globe.climate_class) & 0xFF
    if zone == 1:
        return min((n * 3 & 0xFFFFFFFF) >> 2, 100)
    if zone == 3:
        n = (n * 2 & 0xFFFFFFFF) // 3
    return min(n, 100)


def _roll_quality(dice: AuDice) -> int:
    return dice.roll(2, 0x80, -1)


def query_natural_resources(globe: GlobeProperties, zone: int,
                            seed: int) -> AuZoneResource:
    n = resource_zones(globe.size_class)
    if not 0 <= zone < n:
        raise ValueError("Zone %d out of range for a %d-zone world"
                         % (zone, n))

    dice = AuDice(seed)
    zones = [AuZoneResource() for _ in range(n)]
    z0 = zones[0]
    foliage = min(globe.average_foliage, 100)

    for i, z in enumerate(zones):
        if i == 0:
            z.set_i32(0x54, globe.atmosphere_type)
            z.set_i32(0x58, globe.climate_class)
            z.set_u8(0x5C, globe.size_class)
            z.set_u8(0x5D, globe.star_type)
            z.set_u8(0x06, int(_f32(msl_atmosphere_density(globe) * 100.0)))
            z.set_u8(0x07, _roll_quality(dice))
            z.set_u8(0x02, _roll_quality(dice))
            z.set_u8(0x11, _roll_quality(dice))
            z.set_u8(0x28, _roll_quality(dice))
            z.set_u8(0x2B, _roll_quality(dice))
            z.set_u8(0x42, globe.climate_class * -20 + 90)
            t = _roll_quality(dice)
            z.set_u8(0x43, t if t > 10 else 10)
        else:
            for off in (0x54, 0x58):
                z.set_i32(off, z0.i32(off))
            for off in (0x5C, 0x5D, 0x06, 0x07, 0x02, 0x11, 0x28, 0x2B,
                        0x42, 0x43):
                z.set_u8(off, z0.raw[off])

        z.set_u8(0x46, foliage)
        z.set_u8(0x47, _roll_quality(dice))

        f = z.raw[0x46]
        if f == 0:
            for prob, qual in ((0x08, 0x09), (0x16, 0x17), (0x1C, 0x1D),
                               (0x20, 0x21), (0x22, 0x23), (0x24, 0x25),
                               (0x26, 0x27), (0x34, 0x35), (0x3E, 0x3F),
                               (0x44, 0x45)):
                z.set_u8(prob, 0)
                z.set_u8(qual, _roll_quality(dice))
            z.set_u8(0x4E, 0)
        else:
            half = (f + 1) >> 1
            third = (f + 2) // 3
            z.set_u8(0x08, dice.roll(1, half));  z.set_u8(0x09, _roll_quality(dice))
            z.set_u8(0x16, dice.roll(1, f));     z.set_u8(0x17, _roll_quality(dice))
            z.set_u8(0x1C, dice.roll(1, half));  z.set_u8(0x1D, _roll_quality(dice))
            z.set_u8(0x20, dice.roll(1, f));     z.set_u8(0x21, _roll_quality(dice))
            z.set_u8(0x22, dice.roll(1, third)); z.set_u8(0x23, _roll_quality(dice))
            z.set_u8(0x24, dice.roll(1, half));  z.set_u8(0x25, _roll_quality(dice))
            z.set_u8(0x26, dice.roll(1, third, -2))
            z.set_u8(0x27, _roll_quality(dice))
            z.set_u8(0x34, dice.roll(1, half));  z.set_u8(0x35, _roll_quality(dice))
            z.set_u8(0x3E, dice.roll(1, half));  z.set_u8(0x3F, _roll_quality(dice))
            z.set_u8(0x44, dice.roll(1, half));  z.set_u8(0x45, _roll_quality(dice))
            z.set_u8(0x4E, dice.roll(1, half))

        z.set_u8(0x4F, _roll_quality(dice))
        z.set_u8(0x03, dice.roll(1, f) if globe.can_have_fauna else 0)
        z.set_u8(0x04, _roll_quality(dice))
        for off in (0x50, 0x51, 0x52, 0x53):
            z.set_u8(off, _roll_quality(dice))

        if (0 <= globe.climate_class - 1 <= 2) and globe.hydrographics != 0:
            z.set_u8(0x18, dice.roll(1, globe.hydrographics))
            z.set_u8(0x19, _roll_quality(dice))
        else:
            z.set_u8(0x18, 0)
            z.set_u8(0x19, 0)

        z.set_u8(0x40, dice.roll(1, 100, _c_div(foliage * -2, 3)))
        if z.raw[0x40] < 0x0B:
            z.set_u8(0x40, 10)
        z.set_u8(0x41, _roll_quality(dice))

        z.set_u8(0x12, dice.roll(1, z.raw[0x40]))
        if z.raw[0x12] < 3:
            z.set_u8(0x12, 2)
        z.set_u8(0x13, _roll_quality(dice))

        if z.raw[0x06] < 15:
            z.set_u8(0x14, dice.roll(2, z.raw[0x40], -z.raw[0x06]))
            if z.raw[0x14] < 2:
                z.set_u8(0x14, 1)
        else:
            z.set_u8(0x14, 0)
        z.set_u8(0x15, _roll_quality(dice))

        z.set_u8(0x1E, dice.roll(1, z.raw[0x40]))
        if z.raw[0x1E] < 3:
            z.set_u8(0x1E, 2)
        z.set_u8(0x1F, _roll_quality(dice))

        z.set_u8(0x29, 0 if globe.climate_class == 0 else 100)
        z.set_u8(0x2A, _roll_quality(dice))

        u = globe.climate_class * 2
        if globe.habitable_size():
            u -= 4
        z.set_u8(0x2C, 0 if u < 2 else dice.roll(2, u, -2))
        z.set_u8(0x2D, _roll_quality(dice))

        for prob, qual in ((0x2F, 0x30), (0x36, 0x37), (0x3C, 0x3D)):
            z.set_u8(prob, dice.roll(1, z.raw[0x40]))
            if z.raw[prob] < 3:
                z.set_u8(prob, 2)
            z.set_u8(qual, _roll_quality(dice))

        z.set_u8(0x4C, globe.hydrographics)
        z.set_u8(0x4D, _roll_quality(dice))
        z.set_u8(0x2E, _roll_quality(dice))
        z.set_u8(0x31, _roll_quality(dice))
        if i != 0:
            for off in (0x4D, 0x2E, 0x31):
                z.set_u8(off, z0.raw[off])

        for off in (0x0B, 0x39, 0x3B, 0x4B):
            z.set_u8(off, _roll_quality(dice))

        if globe.climate_class == 0:
            z.set_u8(0x0A, 0)
            z.set_u8(0x3A, 0)
            t = dice.roll(1, globe.size_class >> 1, -1)
            z.set_u8(0x38, t if t > 0 else 0)
            if globe.habitable_size():
                z.set_u8(0x4A, dice.roll(1, globe.size_class - 2, -1))
            else:
                z.set_u8(0x4A, 0)
        else:
            if globe.climate_class == 4:
                if globe.habitable_size():
                    z.set_u8(0x0A, dice.roll(1, globe.size_class - 2, -1))
                else:
                    z.set_u8(0x0A, 0)
                z.set_u8(0x38, 0)
                t = dice.roll(1, globe.size_class >> 1, -1)
                z.set_u8(0x3A, t if t > 0 else 0)
            else:
                z.set_u8(0x0A, 0)
                z.set_u8(0x38, 0)
                z.set_u8(0x3A, 0)
            z.set_u8(0x4A, 0)

        if globe.climate_class in (1, 2, 3, 4):
            a = dice.roll(2, globe.size_class, -1)
            b = dice.roll(2, globe.size_class, -1)
            c = dice.roll(2, globe.size_class, -1)
        else:
            a = b = c = 0
        for value, prob, qual in ((a, 0x0D, 0x0E), (b, 0x0F, 0x10),
                                  (c, 0x32, 0x33)):
            value = min(value, 100)
            z.set_u8(prob, value if value > 0 else 0)
            z.set_u8(qual, _roll_quality(dice))

    for i, z in enumerate(zones):
        if i == 0:
            z.set_u8(0x05, _roll_quality(dice))
            z.set_u8(0x0C, _roll_quality(dice))
        else:
            z.set_u8(0x05, z0.raw[0x05])
            z.set_u8(0x0C, z0.raw[0x0C])
        if z.raw[0x46] == 0:
            z.set_u8(0x08, dice.roll(1, 30))
            z.set_u8(0x16, dice.roll(1, 60))
            z.set_u8(0x1C, dice.roll(1, 30))
            z.set_u8(0x20, dice.roll(1, 60))
            z.set_u8(0x22, dice.roll(1, 20))
            z.set_u8(0x24, dice.roll(1, 30))
            z.set_u8(0x26, dice.roll(1, 20, -2))
            z.set_u8(0x34, dice.roll(1, 30))
            z.set_u8(0x3E, dice.roll(1, 30))
            z.set_u8(0x44, dice.roll(1, 30))
            z.set_u8(0x4E, dice.roll(1, 30))

    return zones[zone]


@dataclass
class ProcessComponent:

    commodity: int
    required: int = 0
    have: int = 0
    quality: int = 0
    effect: int = 5


@dataclass
class NaturalItem:

    commodity: int
    quality: int
    quantity: int
    uses: int = 1


def apply_material(component: ProcessComponent, item: NaturalItem,
                   dice: AuDice) -> tuple:
    changed = False

    if component.required != 0:
        if item.quantity == 1:
            gained = 1 if test_quality(item.quality, dice) else 0
            consumed = 1
        else:
            shortfall = component.required - component.have
            successes = test_failure(item.quality, shortfall, dice)
            consumed = shortfall * 2 - successes
            gained = shortfall
            if item.quantity < consumed:
                if shortfall < consumed:
                    scaled = (float(shortfall) / float(consumed)
                              * float(item.quantity))
                    gained = int(math.floor(scaled + 0.5))
                    if gained == 0:
                        gained = 1
                consumed = item.quantity

        if gained != 0:
            if (item.quality < component.quality or component.quality == 0
                    or component.have == 0):
                component.quality = item.quality
            component.have += gained
            changed = True

        if consumed == 0:
            return 0, changed
        item.quantity = (item.quantity - consumed
                         if consumed < item.quantity else 0)
        return consumed, changed

    if item.uses == 0:
        item.quantity = item.quantity - 1 if item.quantity >= 2 else 0
        return 1, changed

    if not test_quality(item.quality, dice):
        item.uses -= 1
        if item.uses == 0:
            item.quantity = item.quantity - 1 if item.quantity >= 2 else 0
            return 1, changed
    component.have = 1
    return 0, True


def apply_natural_manufacturing_resources(components: Iterable[ProcessComponent],
                                          zr: AuZoneResource,
                                          dice: AuDice) -> tuple:
    changed = False
    applied = 0
    for c in components:
        want = (c.have == 0) if c.required == 0 else (c.have < c.required)
        if not want:
            continue
        n = fetch(zr, c.commodity, dice)
        if n <= 0:
            continue
        item = NaturalItem(c.commodity, quality(zr, c.commodity), n, uses=1)
        consumed, did = apply_material(c, item, dice)
        applied += consumed
        changed = changed or did
    return applied, changed


NO_WATER_QUALITY_INDUSTRIES = frozenset({0x22, 0x33, 0x34, 0x3E, 0x59})
NO_SUNLIGHT_QUALITY_INDUSTRIES = frozenset({0x42})

ENCLOSURE_NONE = 0
ENCLOSURE_NEEDED = 1
ENCLOSURE_UNDERWATER = 2


def fetch_manufacturing_materials(components: Iterable[ProcessComponent],
                                  zr: AuZoneResource,
                                  industry: int,
                                  enclosure: int,
                                  sunlight_available: bool,
                                  dice: AuDice) -> tuple:
    zr = zr.copy()
    sunlight_quality = zr.raw[0x43]
    water_quality = zr.raw[0x4D]

    if industry in NO_WATER_QUALITY_INDUSTRIES:
        water_quality = 0
    elif industry in NO_SUNLIGHT_QUALITY_INDUSTRIES:
        sunlight_quality = 0

    if enclosure == ENCLOSURE_UNDERWATER:
        zr.set_u8(0x42, 0)
        zr.set_u8(0x06, 0)
    elif not sunlight_available:
        zr.set_u8(0x42, 0)

    applied, changed = apply_natural_manufacturing_resources(
        components, zr, dice)
    return applied, changed, sunlight_quality, water_quality
