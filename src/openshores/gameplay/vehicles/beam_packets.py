
from __future__ import annotations

import logging
import struct

import asyncpg
from dataclasses import dataclass, field
from typing import Optional, Union

from .persistence import Vehicle, load_vehicle, update_vehicle
from .spawn import SpotType, get_active_vehicle
from .wire import _pack_auid, _pack_qstring, _unpack_auid, _unpack_qstring

logger = logging.getLogger(__name__)


class BeamPacketType:
    BEAM_CITY        = 0x8B
    BEAM_COORDINATE  = 0x8C
    BEAM_OVER        = 0x8D
    BEAM_PLANET      = 0x8E
    BEAM_SHIP        = 0x8F
    BEAM_TRANSPORTER = 0x90


@dataclass
class BeamCity:
    vehicle_id: int = 0
    spot_type: int = SpotType.GROUND
    quality: int = 1
    dest_name: str = ""
    dest_auid: int = 0
    transporter_target: int = 0


@dataclass
class BeamCoordinate:
    vehicle_id: int = 0
    spot_type: int = SpotType.GROUND
    quality: int = 1
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class BeamOver:
    vehicle_id: int = 0


@dataclass
class BeamPlanet:
    vehicle_id: int = 0
    spot_type: int = SpotType.SPACE
    quality: int = 1
    latitude: float = 0.0
    longitude: float = 0.0


@dataclass
class BeamShip:
    vehicle_id: int = 0
    spot_type: int = SpotType.SPACE
    quality: int = 1
    ship_id: int = 0
    ship_name: str = ""


@dataclass
class BeamTransporter:
    vehicle_id: int = 0
    spot_type: int = SpotType.GROUND
    quality: int = 1
    pad_id: int = 0
    pad_name: str = ""


AnyBeamPacket = Union[
    BeamCity, BeamCoordinate, BeamOver, BeamPlanet, BeamShip, BeamTransporter
]


def encode_beam_city(b: BeamCity) -> bytes:
    return (
        _pack_auid(b.vehicle_id)
        + struct.pack(">BB", b.spot_type & 0xFF, b.quality & 0xFF)
        + _pack_qstring(b.dest_name)
        + _pack_auid(b.dest_auid)
        + struct.pack(">B", b.transporter_target & 0xFF)
    )


def encode_beam_coordinate(b: BeamCoordinate) -> bytes:
    return (
        _pack_auid(b.vehicle_id)
        + struct.pack(">BB", b.spot_type & 0xFF, b.quality & 0xFF)
        + struct.pack(">fff", float(b.x), float(b.y), float(b.z))
    )


def encode_beam_over(b: BeamOver) -> bytes:
    return _pack_auid(b.vehicle_id)


def encode_beam_planet(b: BeamPlanet) -> bytes:
    return (
        _pack_auid(b.vehicle_id)
        + struct.pack(">BB", b.spot_type & 0xFF, b.quality & 0xFF)
        + struct.pack(">ff", float(b.latitude), float(b.longitude))
    )


def encode_beam_ship(b: BeamShip) -> bytes:
    return (
        _pack_auid(b.vehicle_id)
        + struct.pack(">BB", b.spot_type & 0xFF, b.quality & 0xFF)
        + _pack_auid(b.ship_id)
        + _pack_qstring(b.ship_name)
    )


def encode_beam_transporter(b: BeamTransporter) -> bytes:
    return (
        _pack_auid(b.vehicle_id)
        + struct.pack(">BB", b.spot_type & 0xFF, b.quality & 0xFF)
        + _pack_auid(b.pad_id)
        + _pack_qstring(b.pad_name)
    )


def encode_beam_packet(packet_type: int, beam: AnyBeamPacket) -> bytes:
    if packet_type == BeamPacketType.BEAM_CITY:
        return encode_beam_city(beam)  # type: ignore[arg-type]
    if packet_type == BeamPacketType.BEAM_COORDINATE:
        return encode_beam_coordinate(beam)  # type: ignore[arg-type]
    if packet_type == BeamPacketType.BEAM_OVER:
        return encode_beam_over(beam)  # type: ignore[arg-type]
    if packet_type == BeamPacketType.BEAM_PLANET:
        return encode_beam_planet(beam)  # type: ignore[arg-type]
    if packet_type == BeamPacketType.BEAM_SHIP:
        return encode_beam_ship(beam)  # type: ignore[arg-type]
    if packet_type == BeamPacketType.BEAM_TRANSPORTER:
        return encode_beam_transporter(beam)  # type: ignore[arg-type]
    raise ValueError(f"Unknown beam packet type: {packet_type:#x}")


def parse_beam_city(body: bytes, offset: int = 0) -> BeamCity:
    vid, offset = _unpack_auid(body, offset)
    spot = body[offset]; offset += 1
    qual = body[offset]; offset += 1
    name, offset = _unpack_qstring(body, offset)
    dest, offset = _unpack_auid(body, offset)
    ttgt = body[offset] if offset < len(body) else 0
    return BeamCity(
        vehicle_id=vid, spot_type=spot, quality=qual,
        dest_name=name or "", dest_auid=dest,
        transporter_target=ttgt,
    )


def parse_beam_coordinate(body: bytes, offset: int = 0) -> BeamCoordinate:
    vid, offset = _unpack_auid(body, offset)
    spot = body[offset]; offset += 1
    qual = body[offset]; offset += 1
    x, y, z = struct.unpack_from(">fff", body, offset); offset += 12
    return BeamCoordinate(
        vehicle_id=vid, spot_type=spot, quality=qual,
        x=float(x), y=float(y), z=float(z),
    )


def parse_beam_over(body: bytes, offset: int = 0) -> BeamOver:
    vid, _ = _unpack_auid(body, offset)
    return BeamOver(vehicle_id=vid)


def parse_beam_planet(body: bytes, offset: int = 0) -> BeamPlanet:
    vid, offset = _unpack_auid(body, offset)
    spot = body[offset]; offset += 1
    qual = body[offset]; offset += 1
    lat, lon = struct.unpack_from(">ff", body, offset); offset += 8
    return BeamPlanet(
        vehicle_id=vid, spot_type=spot, quality=qual,
        latitude=float(lat), longitude=float(lon),
    )


def parse_beam_ship(body: bytes, offset: int = 0) -> BeamShip:
    vid, offset = _unpack_auid(body, offset)
    spot = body[offset]; offset += 1
    qual = body[offset]; offset += 1
    ship_id, offset = _unpack_auid(body, offset)
    name, _ = _unpack_qstring(body, offset)
    return BeamShip(
        vehicle_id=vid, spot_type=spot, quality=qual,
        ship_id=ship_id, ship_name=name or "",
    )


def parse_beam_transporter(body: bytes, offset: int = 0) -> BeamTransporter:
    vid, offset = _unpack_auid(body, offset)
    spot = body[offset]; offset += 1
    qual = body[offset]; offset += 1
    pad_id, offset = _unpack_auid(body, offset)
    name, _ = _unpack_qstring(body, offset)
    return BeamTransporter(
        vehicle_id=vid, spot_type=spot, quality=qual,
        pad_id=pad_id, pad_name=name or "",
    )


_DECODERS = {
    BeamPacketType.BEAM_CITY:        parse_beam_city,
    BeamPacketType.BEAM_COORDINATE:  parse_beam_coordinate,
    BeamPacketType.BEAM_OVER:        parse_beam_over,
    BeamPacketType.BEAM_PLANET:      parse_beam_planet,
    BeamPacketType.BEAM_SHIP:        parse_beam_ship,
    BeamPacketType.BEAM_TRANSPORTER: parse_beam_transporter,
}


def parse_beam_packet(packet_type: int, body: bytes) -> AnyBeamPacket:
    fn = _DECODERS.get(packet_type)
    if fn is None:
        raise ValueError(f"Unknown beam packet type: {packet_type:#x}")
    return fn(body)


def _set_transform(v: Vehicle, parent_id: int,
                   loc: tuple[float, float, float]) -> None:
    v.idp = int(parent_id)
    v.locX, v.locY, v.locZ = float(loc[0]), float(loc[1]), float(loc[2])
    v.vecX = v.vecY = v.vecZ = 0.0


async def apply_beam(beam: AnyBeamPacket, *,
                     conn: asyncpg.Connection) -> Optional[BeamOver]:
    v = get_active_vehicle(beam.vehicle_id)
    if v is None:
        v = await load_vehicle(conn, beam.vehicle_id)
        if v is None:
            logger.warning("Beam names vehicle 0x%x, which does not exist. "
                           "Beam dropped.", beam.vehicle_id)
            return None

    if isinstance(beam, BeamCoordinate):
        _set_transform(v, v.idp, (beam.x, beam.y, beam.z))
    elif isinstance(beam, BeamPlanet):
        from .terrain import get_terrain_query
        q = get_terrain_query()
        target_xyz = q.latlon_to_xyz(v.idp, beam.latitude, beam.longitude)
        _set_transform(v, v.idp, target_xyz)
    elif isinstance(beam, BeamCity):
        _set_transform(v, beam.dest_auid, (0.0, 0.0, 0.0))
        if beam.dest_name:
            logger.debug("Vehicle 0x%x beamed to city %r, parent 0x%x.",
                         v.id, beam.dest_name, beam.dest_auid)
    elif isinstance(beam, BeamShip):
        _set_transform(v, beam.ship_id, (0.0, 0.0, 0.0))
        v.motherShip = beam.ship_id
        if beam.ship_name:
            v.motherShipName = beam.ship_name
    elif isinstance(beam, BeamTransporter):
        _set_transform(v, beam.pad_id, (0.0, 0.0, 0.0))
    elif isinstance(beam, BeamOver):
        return None
    else:
        raise TypeError(f"Unsupported beam type: {type(beam).__name__}")

    await update_vehicle(conn, v)
    return BeamOver(vehicle_id=v.id)


def _selftest_roundtrip() -> None:
    cases: list[tuple[int, AnyBeamPacket]] = [
        (BeamPacketType.BEAM_CITY, BeamCity(
            vehicle_id=0x70000100, spot_type=SpotType.GROUND, quality=5,
            dest_name="New Atlantis", dest_auid=0xABCDEF,
            transporter_target=2,
        )),
        (BeamPacketType.BEAM_COORDINATE, BeamCoordinate(
            vehicle_id=0x70000200, spot_type=SpotType.SPACE, quality=3,
            x=1000.0, y=-2500.5, z=42.0,
        )),
        (BeamPacketType.BEAM_OVER, BeamOver(vehicle_id=0x70000300)),
        (BeamPacketType.BEAM_PLANET, BeamPlanet(
            vehicle_id=0x70000400, spot_type=SpotType.SPACE, quality=2,
            latitude=37.7749, longitude=-122.4194,
        )),
        (BeamPacketType.BEAM_SHIP, BeamShip(
            vehicle_id=0x70000500, spot_type=SpotType.SPACE, quality=4,
            ship_id=0x12345678, ship_name="USS Enterprise",
        )),
        (BeamPacketType.BEAM_TRANSPORTER, BeamTransporter(
            vehicle_id=0x70000600, spot_type=SpotType.GROUND, quality=1,
            pad_id=0xCAFE, pad_name="Pad-7",
        )),
    ]
    _FLOAT_FIELDS = {"x", "y", "z", "latitude", "longitude"}
    _FLOAT_TOLERANCE = 1e-4
    for ptype, beam in cases:
        encoded = encode_beam_packet(ptype, beam)
        decoded = parse_beam_packet(ptype, encoded)
        for fname in beam.__dataclass_fields__:
            ov = getattr(beam, fname)
            dv = getattr(decoded, fname)
            if fname in _FLOAT_FIELDS:
                assert abs(ov - dv) < _FLOAT_TOLERANCE, (
                    f"{type(beam).__name__}.{fname}: {ov!r} vs {dv!r}"
                )
            else:
                assert ov == dv, (
                    f"{type(beam).__name__}.{fname}: {ov!r} vs {dv!r}"
                )


if __name__ == "__main__":
    logger.info("Beam packet self-test starting.")
    _selftest_roundtrip()
    logger.info("Beam packet self-test passed.")
