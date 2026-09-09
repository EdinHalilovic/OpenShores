
from __future__ import annotations

import struct

from openshores.protocol.stream import QDS

F_SHOPS_IS_ONE = 0x01
F_HAS_DNA = 0x02
F_FLAG_04 = 0x04
F_SPLIT_MINQ = 0x08
F_I32_FIELD_08 = 0x10
F_I32_FIELD_10 = 0x20
F_I32_FIELD_0C = 0x40
F_WIDE_QTY = 0x80


def _s8(v):
    v = int(v) & 0xFF
    return v - 256 if v >= 128 else v


def _minq_sent(p):
    return (int(p.minimum_quality) & 0xFF) or 1


def encode_component_array(components):
    comps = list(components or [])
    if len(comps) > 127:
        raise ValueError("DeProcessComponentArray count is i8; got %d"
                         % len(comps))
    q = QDS()
    q.write_i8(len(comps))
    for c in comps:
        q.write_i16_wrapped(c.commodity)
        q.write_i8(c.quality)
        q.write_i8(c.effect)
        q.write_i32(c.required)
        q.write_i32(c.applied)
        q.write_i8(0)
    return q.getvalue()


def encode_process(p, *, wide_qty=True):
    floor = (int(p.minimum_q_required) & 0xFF) or 1
    minq = _minq_sent(p)
    _scaled_work, _scaled_out = p.scaled()

    flags = 0
    if wide_qty:
        flags |= F_WIDE_QTY
    if p.shops_enabled == 1:
        flags |= F_SHOPS_IS_ONE
    if floor != minq:
        flags |= F_SPLIT_MINQ
    if p.shops_enabled >= 2:
        flags |= F_I32_FIELD_08
    if p.output_qty_base:
        flags |= F_I32_FIELD_10
    if p.workers_present:
        flags |= F_I32_FIELD_0C

    q = QDS()
    q.write_i32(p.auid)
    q.write_f64(0.0); q.write_f64(0.0)
    q.write_i16_wrapped(0)
    q.write_u8_wrapped(flags)
    q.write_i32(p.process_id)
    q.write_i32(_scaled_work)
    q.write_qstring(p.name)
    q.write_qdatetime(p.deadline_ms)
    q.write_u8_wrapped(p.quality)
    q.write_i32(p.quantity)
    q.write_raw(encode_component_array(p.scaled_components()))
    q.write_u8_wrapped(floor)
    if flags & F_SPLIT_MINQ:
        q.write_u8_wrapped(minq)
    q.write_u8_wrapped(0)
    q.write_u8_wrapped(_s8(p.production_boost) & 0xFF)
    q.write_i32(p.commodity)
    if flags & F_WIDE_QTY:
        q.write_i32(_scaled_work)
        q.write_i32(_scaled_out)
    else:
        q.write_i16_wrapped(_scaled_work)
        q.write_i16_wrapped(_scaled_out)
    q.write_qdatetime(p.last_run_ms)
    if flags & F_HAS_DNA:
        q.write_bytes(bytes(24))
    if flags & F_I32_FIELD_08:
        q.write_i32(p.shops_enabled)
    if flags & F_I32_FIELD_10:
        q.write_i32(p.output_qty_base)
    if flags & F_I32_FIELD_0C:
        q.write_i32(p.workers_present)
    return q.getvalue()


def encode_process_array(processes, *, wide_qty=True):
    procs = list(processes or [])
    if len(procs) > 32767:
        raise ValueError("Process array count is i16; got %d" % len(procs))
    q = QDS()
    q.write_i16_wrapped(len(procs))
    for p in procs:
        q.write_raw(encode_process(p, wide_qty=wide_qty))
    return q.getvalue()
