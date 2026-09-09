
from __future__ import annotations

import struct

from openshores.protocol.atoms.item import _pack_qstring
from openshores.protocol.stream import QDS


def _build_dbcommodity_row(cid: int,
                            ccc_flags: int = 0,
                            damage_scalar: int = 0,
                            primary_mode: int = 0,
                            secondary_mode: int = 0,
                            name: str | None = None,
                            bitmap: str | None = None,
                            model: str | None = None,
                            description: str | None = None,
                            ammo1_qty: int = 0,
                            ammo1_type: int = 0,
                            ammo2_qty: int = 0,
                            ammo2_type: int = 0,
                            bits_wear: int = 0,
                            cap_w: int = 0,
                            cap_h: int = 0,
                            newcond: int = 0,
                            size_w: int = 0,
                            size_h: int = 0,
                            stack_limit: int = 0,
                            weight: float = 0.0,
                            wpn1_range: int = 0,
                            wpn1_effect1: int = 0,
                            wpn1_damage1: int = 0,
                            wpn1_damage_mod1: int = 0,
                            wpn1_radius1: int = 0,
                            wpn1_ap1: int = 0,
                            wpn1_st1: int = 0,
                            wpn1_effect2: int = 0,
                            wpn1_damage2: int = 0,
                            wpn1_damage_mod2: int = 0,
                            wpn1_radius2: int = 0,
                            wpn1_ap2: int = 0,
                            wpn1_st2: int = 0,
                            wpn2_range: int = 0,
                            wpn2_effect1: int = 0,
                            wpn2_damage1: int = 0,
                            wpn2_damage_mod1: int = 0,
                            wpn2_radius1: int = 0,
                            wpn2_ap1: int = 0,
                            wpn2_st1: int = 0,
                            wpn2_effect2: int = 0,
                            wpn2_damage2: int = 0,
                            wpn2_damage_mod2: int = 0,
                            wpn2_radius2: int = 0,
                            wpn2_ap2: int = 0,
                            wpn2_st2: int = 0,
                            ) -> bytes:
    b = bytearray()
    b += struct.pack(">h", int(cid) & 0xFFFF)
    b += bytes([int(ammo1_qty) & 0xFF])
    b += bytes([int(ammo1_type) & 0xFF])
    b += bytes([int(ammo2_qty) & 0xFF])
    b += bytes([int(ammo2_type) & 0xFF])
    b += bytes(17)
    b += bytes(17)
    b += bytes(4)
    b += bytes(4)
    b += bytes(1)
    b += struct.pack(">i", int(bits_wear) & 0xFFFFFFFF)
    b += bytes([int(cap_w) & 0xFF, int(cap_h) & 0xFF])
    b += struct.pack(">i", int(ccc_flags) & 0xFFFFFFFF)
    b += _pack_qstring(description)
    b += bytes(1)
    b += bytes([int(damage_scalar) & 0xFF])
    b += _pack_qstring(bitmap)
    b += _pack_qstring(model)
    b += struct.pack(">f", 0.0)
    b += struct.pack(">ddd", 0.0, 0.0, 0.0)
    b += bytes(1)
    b += _pack_qstring(name)
    b += bytes([int(newcond) & 0xFF])
    b += bytes([int(size_w) & 0xFF, int(size_h) & 0xFF])
    b += bytes([int(stack_limit) & 0xFF])
    b += bytes([int(primary_mode) & 0xFF])
    b += struct.pack(">h", int(wpn1_range)       & 0xFFFF)
    b += bytes([int(wpn1_effect1)               & 0xFF])
    b += struct.pack(">h", int(wpn1_damage1)     & 0xFFFF)
    b += bytes([int(wpn1_damage_mod1)           & 0xFF])
    b += struct.pack(">h", int(wpn1_radius1)     & 0xFFFF)
    b += bytes([int(wpn1_ap1)                   & 0xFF])
    b += struct.pack(">h", int(wpn1_st1)         & 0xFFFF)
    b += bytes([int(wpn1_effect2)               & 0xFF])
    b += struct.pack(">h", int(wpn1_damage2)     & 0xFFFF)
    b += bytes([int(wpn1_damage_mod2)           & 0xFF])
    b += struct.pack(">h", int(wpn1_radius2)     & 0xFFFF)
    b += bytes([int(wpn1_ap2)                   & 0xFF])
    b += struct.pack(">h", int(wpn1_st2)         & 0xFFFF)
    b += bytes([int(secondary_mode) & 0xFF])
    b += struct.pack(">h", int(wpn2_range)       & 0xFFFF)
    b += bytes([int(wpn2_effect1)               & 0xFF])
    b += struct.pack(">h", int(wpn2_damage1)     & 0xFFFF)
    b += bytes([int(wpn2_damage_mod1)           & 0xFF])
    b += struct.pack(">h", int(wpn2_radius1)     & 0xFFFF)
    b += bytes([int(wpn2_ap1)                   & 0xFF])
    b += struct.pack(">h", int(wpn2_st1)         & 0xFFFF)
    b += bytes([int(wpn2_effect2)               & 0xFF])
    b += struct.pack(">h", int(wpn2_damage2)     & 0xFFFF)
    b += bytes([int(wpn2_damage_mod2)           & 0xFF])
    b += struct.pack(">h", int(wpn2_radius2)     & 0xFFFF)
    b += bytes([int(wpn2_ap2)                   & 0xFF])
    b += struct.pack(">h", int(wpn2_st2)         & 0xFFFF)
    b += struct.pack(">f", float(weight))
    assert len(b) >= 156, f"DbCommodity row size {len(b)} < 156 baseline"
    return bytes(b)


def build_scene_db_commodity_0x2b(row) -> bytes:
    return bytes([0x2B]) + row.raw


def _build_dbconstructionprocess_row(row) -> bytes:
    s = QDS()
    s.write_u8(int(row.cpid) & 0xFF)
    s.write_qstring(row.name)
    s.write_u8(int(row.industry_id) & 0xFF)
    s.write_u8(int(row.unknown1) & 0xFF)
    s.write_u8(int(row.unknown2) & 0xFF)
    s.write_u8(int(row.terrain) & 0xFF)
    s.write_u8(int(row.radius) & 0xFF)
    return s.getvalue()


def build_scene_db_construction_process_0x2d(row) -> bytes:
    return bytes([0x2D]) + _build_dbconstructionprocess_row(row)


def _build_dbconstructioncomponent_row(row) -> bytes:
    s = QDS()
    s.write_u16(int(row.seq) & 0xFFFF)
    s.write_u8(int(row.cpid) & 0xFF)
    s.write_u16(int(row.commodity) & 0xFFFF)
    s.write_u8(int(row.quantity) & 0xFF)
    s.write_u8(int(row.effect) & 0xFF)
    s.write_u8(int(row.pad) & 0xFF)
    return s.getvalue()


def build_scene_db_construction_component_0x2c(row) -> bytes:
    return bytes([0x2C]) + _build_dbconstructioncomponent_row(row)


def _build_dbmanufacturingprocess_row(row) -> bytes:
    s = QDS()
    s.write_u8(int(row.flags) & 0xFF)
    s.write_i16(int(row.process_id))
    s.write_qstring(row.name if row.name else None)
    s.write_i16(int(row.commodity))
    s.write_u8(int(row.industry_id) & 0xFF)
    s.write_i16(int(row.output_qty))
    s.write_i16(int(row.work_units))
    s.write_u8(int(row.tail) & 0xFF)
    return s.getvalue()


def build_scene_db_manufacturing_process_0x34(row) -> bytes:
    return bytes([0x34]) + _build_dbmanufacturingprocess_row(row)


def _build_dbmanufacturingcomponent_row(row) -> bytes:
    s = QDS()
    s.write_i16(int(row.index))
    s.write_i16(int(row.process_id))
    s.write_i16(int(row.commodity))
    s.write_i16(int(row.quantity))
    s.write_u8(int(row.effect) & 0xFF)
    return s.getvalue()


def build_scene_db_manufacturing_component_0x33(row) -> bytes:
    return bytes([0x33]) + _build_dbmanufacturingcomponent_row(row)
