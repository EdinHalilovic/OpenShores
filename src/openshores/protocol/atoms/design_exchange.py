from __future__ import annotations
import struct

def u8(v):  return struct.pack(">B", v & 0xFF)
def i16(v): return struct.pack(">h", v)
def i32(v): return struct.pack(">i", v)
def f64(v): return struct.pack(">d", v)
def auid(v): return struct.pack(">I", v & 0xFFFFFFFF) + b"\x00" * 12
def qstr(s):
    if s is None: return struct.pack(">i", -1)
    r = s.encode("utf-16-be"); return struct.pack(">I", len(r)) + r
def aupoint(x=0.0,y=0.0,z=0.0): return f64(x)+f64(y)+f64(z)

def _sysvol(): return i16(0) + u8(1) + i32(0)
def _hash():   return i16(0)
def _deproc_comp_component(commodity=0, qty=1):
    return i16(commodity) + u8(0) + u8(0) + i32(0) + i32(qty) + u8(0)
def _deproc_comp_array(n=1):
    return u8(n) + _deproc_comp_component() * n
def _deconstruction(proc_id=0):
    return u8(proc_id & 0x7f) + u8(0) + i16(0) + _deproc_comp_array() + u8(0) + i16(0) + u8(0)

def aubdreport_min(name="Default", design_id=0, proc_id=0, ver=0x0d, architect_id=0):
    b = b""
    b += u8(ver)
    b += auid(architect_id or design_id)
    b += qstr(name)
    b += i32(design_id)
    b += qstr("")
    b += _hash()
    b += u8(0)
    b += _sysvol()
    b += aupoint()*4
    b += i32(0)*4
    b += _hash()
    b += _sysvol()
    b += i32(0)
    b += i32(0)*3
    b += _sysvol()
    b += i32(0)*2
    b += _sysvol()
    b += i32(0)
    b += _sysvol()
    b += _sysvol()
    b += i32(0)
    b += _hash()
    b += u8(1)
    b += i16(0)
    b += u8(1)
    b += _deconstruction(proc_id)
    b += _hash()
    b += _hash() + _hash()
    b += _hash()
    b += _hash()
    b += _hash()
    b += _hash()
    b += _hash()
    b += _hash()
    b += _hash() + _hash()
    b += i16(0)*4 + i16(0) + i16(0)
    b += f64(0)*2 + f64(0)
    b += i32(0)*3
    b += f64(2.0)
    b += i32(0)
    b += f64(0)
    b += i32(0)
    b += i32(0)*3
    b += f64(0)
    b += i32(0)*2
    b += qstr("")
    b += i32(0)
    b += f64(0)
    b += i32(0)*2
    return b

def exchange_entry(name, design_id=0, empire=0, proc_id=0, price=0, state=0,
                   can_copy=True, can_view=True, use_once=False, min_stance=0,
                   architect_id=0):
    flags = (min_stance & 0xF) | (0x80 if can_copy else 0) | (0x40 if can_view else 0) | (0x20 if use_once else 0)
    return (u8(flags) + i32(price) + u8(state) + i32(empire)
            + aubdreport_min(name, design_id, proc_id, architect_id=architect_id))

def exchange_qhash(entries):
    b = i32(len(entries))
    for did, name in entries:
        b += i32(did) + exchange_entry(name, design_id=did)
    return b


def qimage_null():
    return struct.pack(">i", 0)


def bd_exchange_reply(entries, empire=0, architect_id=0):
    b = u8(0xDE) + u8(0x00) + i32(len(entries))
    for e in entries:
        did, name = e[0], e[1]
        proc = e[2] if len(e) > 2 else 0
        b += exchange_entry(name, design_id=did, empire=empire, proc_id=proc,
                            architect_id=architect_id)
        b += qimage_null()
    return b


def exchange_entry_real(report_bytes, empire=0, price=0, state=1,
                        can_copy=True, can_view=True, use_once=False, min_stance=0):
    flags = (state & 0xF) | (0x80 if can_copy else 0) | (0x40 if can_view else 0) | (0x20 if use_once else 0)
    return u8(flags) + i32(empire) + u8(min_stance) + i32(price) + bytes(report_bytes)

def bd_exchange_reply_real(reports, empire=0):
    b = u8(0xDE) + u8(0x00) + i32(len(reports))
    for r in reports:
        rep, st = r if isinstance(r, tuple) else (r, 0)
        b += exchange_entry_real(rep, empire=empire, state=st) + qimage_null()
    return b

def bd_design_push(design_blob):
    return u8(0xDF) + bytes(design_blob[1:])

ITEM_TYPECODE_STORAGE_MEDIA = 0x16

def auitem_base(cid, quality=100, kind=1, count=1, name=None):
    f = 0
    body = b""
    f |= 0x01; body_count = i32(count)
    f |= 0x04; body_qual  = u8(quality & 0xFF)
    if name is not None: f |= 0x08
    out  = u8(f) + i16(cid)
    out += body_count
    out += body_qual
    if name is not None: out += qstr(name)
    out += u8(kind if kind else 1)
    return out

def storage_media_body(bd_entries=None, sc_entries=None, cid=0, quality=100, kind=1):
    b = auitem_base(cid, quality, kind)
    flags = 0
    secs = b""
    if bd_entries:
        flags |= 0x08
        secs += exchange_qhash(bd_entries)
    b += u8(flags) + secs
    return b
