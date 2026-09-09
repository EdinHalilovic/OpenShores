from __future__ import annotations

from openshores.gameplay import gd_tables as _gd
from openshores.gameplay import gear_wear as _gw
from openshores.gameplay import manufacturing as _mfg

CID_ANIMAL_CARCASS = 14
CID_FISH = 33
CID_LEATHER = 47
CID_ANIMAL_MEAT = 49
CID_FISH_MEAT = 100
CID_BONE = 233
CID_HEAD = 332

CID_DNA_KIT = 0x11c
CID_DNA_SAMPLE = 0x11d

KNIFE_CIDS = frozenset({0x74, 0x97, 0x98})

SKIN_YIELD = {
    CID_ANIMAL_CARCASS: (CID_ANIMAL_MEAT,
                         CID_LEATHER,
                         CID_BONE),
    CID_FISH: (CID_FISH_MEAT,),
}

SKIN_MPID = {
    (CID_ANIMAL_CARCASS, CID_ANIMAL_MEAT): 100,
    (CID_ANIMAL_CARCASS, CID_LEATHER): 101,
    (CID_ANIMAL_CARCASS, CID_BONE): 406,
    (CID_FISH, CID_FISH_MEAT): 99,
}

SKIN_EXCLUDED = {CID_ANIMAL_CARCASS: (CID_HEAD,)}

SKIN_OUTPUT_QTY = 1

THOUGHT_SKIN_ONE = "Skinning the %1 produced %2."
THOUGHT_SKIN_THREE = "Skinning the %1 produced %2, %3 and %4."
THOUGHT_DNA_OK = "DNA collected from %1."
THOUGHT_DNA_REFUSED = "DNA cannot be collected from %1."
THOUGHT_DNA_NOT_VIABLE = "DNA collection failed. The DNA of %1 is not viable."
THOUGHT_DNA_NONE = "DNA collection failed. %1 has no DNA."

OUTCOME_SKINNED = "skinned"
OUTCOME_DNA = "dna"
OUTCOME_NOT_SKINNABLE = "not_skinnable"
OUTCOME_WRONG_TOOL = "wrong_tool"
OUTCOME_DNA_NONE = "dna_none"
OUTCOME_DNA_NOT_VIABLE = "dna_not_viable"

DNA_MIN_BYTES = 24


class Output:

    __slots__ = ("cid", "quantity", "quality", "mpid")

    def __init__(self, cid, quantity=SKIN_OUTPUT_QTY, quality=0, mpid=0):
        self.cid = int(cid) & 0xFFFF
        self.quantity = max(1, int(quantity))
        self.quality = max(0, min(255, int(quality)))
        self.mpid = int(mpid)

    @property
    def name(self):
        return commodity_name(self.cid)

    def __eq__(self, other):
        return (isinstance(other, Output) and self.cid == other.cid
                and self.quantity == other.quantity
                and self.quality == other.quality)

    def __repr__(self):
        return ("Output(cid=%d %r x%d Q%d)"
                % (self.cid, self.name, self.quantity, self.quality))


class Result:

    __slots__ = ("outcome", "target_cid", "tool_cid", "outputs",
                 "input_consumed", "tool_spared", "dna")

    def __init__(self, outcome, target_cid=0, tool_cid=0, outputs=(),
                 input_consumed=0, tool_spared=True, dna=b""):
        self.outcome = outcome
        self.target_cid = int(target_cid) & 0xFFFF
        self.tool_cid = int(tool_cid) & 0xFFFF
        self.outputs = tuple(outputs)
        self.input_consumed = int(input_consumed)
        self.tool_spared = bool(tool_spared)
        self.dna = bytes(dna or b"")

    @property
    def produced(self):
        return self.outcome in (OUTCOME_SKINNED, OUTCOME_DNA)

    @property
    def thought(self):
        if self.outcome == OUTCOME_SKINNED:
            return (THOUGHT_SKIN_THREE if len(self.outputs) == 3
                    else THOUGHT_SKIN_ONE)
        if self.outcome == OUTCOME_DNA:
            return THOUGHT_DNA_OK
        if self.outcome == OUTCOME_DNA_NONE:
            return THOUGHT_DNA_NONE
        if self.outcome == OUTCOME_DNA_NOT_VIABLE:
            return THOUGHT_DNA_NOT_VIABLE
        return ""

    def __repr__(self):
        return ("Result(%s target=%d outputs=%r)"
                % (self.outcome, self.target_cid, list(self.outputs)))


def is_skinning_tool(cid) -> bool:
    return (int(cid) & 0xFFFF) in KNIFE_CIDS


def is_dna_tool(cid) -> bool:
    return (int(cid) & 0xFFFF) == CID_DNA_KIT


def is_skinnable(cid) -> bool:
    return (int(cid) & 0xFFFF) in SKIN_YIELD


def yields_for(cid):
    return SKIN_YIELD.get(int(cid) & 0xFFFF, ())


def commodity_name(cid, default=None):
    name = _gd.commodity_name(int(cid) & 0xFFFF)
    if name:
        return name
    return default if default is not None else "cid %d" % (int(cid) & 0xFFFF)


def output_quality(input_quality, tool_quality=0) -> int:
    iq = max(0, min(255, int(input_quality)))
    tq = max(0, min(255, int(tool_quality)))
    if not tq:
        return iq if iq >= 1 else 1
    return int(_mfg.output_quality(0, tq, [(iq, 1)]))


def skin(target_cid, target_quality=0, tool_cid=0x74, tool_quality=0,
         dice=None) -> Result:
    target_cid = int(target_cid) & 0xFFFF
    tool_cid = int(tool_cid) & 0xFFFF
    if not is_skinning_tool(tool_cid):
        return Result(OUTCOME_WRONG_TOOL, target_cid, tool_cid)
    outs = yields_for(target_cid)
    if not outs:
        return Result(OUTCOME_NOT_SKINNABLE, target_cid, tool_cid)
    q = output_quality(target_quality, tool_quality)
    outputs = [Output(cid, SKIN_OUTPUT_QTY, q,
                      mpid=SKIN_MPID.get((target_cid, cid), 0))
               for cid in outs]
    return Result(OUTCOME_SKINNED, target_cid, tool_cid, outputs,
                  input_consumed=1,
                  tool_spared=_tool_spared(tool_quality, dice))


def collect_dna(target_cid, dna=b"", tool_cid=CID_DNA_KIT,
                target_quality=0, viable=True) -> Result:
    target_cid = int(target_cid) & 0xFFFF
    tool_cid = int(tool_cid) & 0xFFFF
    if not is_dna_tool(tool_cid):
        return Result(OUTCOME_WRONG_TOOL, target_cid, tool_cid)
    blob = bytes(dna or b"")
    if len(blob) < DNA_MIN_BYTES:
        return Result(OUTCOME_DNA_NONE, target_cid, tool_cid)
    if not viable:
        return Result(OUTCOME_DNA_NOT_VIABLE, target_cid, tool_cid, dna=blob)
    sample = Output(CID_DNA_SAMPLE, 1, max(1, int(target_quality) & 0xFF))
    return Result(OUTCOME_DNA, target_cid, tool_cid, [sample],
                  input_consumed=0, tool_spared=False, dna=blob)


def use_tool_on_carcass(target_cid, tool_cid, target_quality=0,
                        tool_quality=0, dna=b"", viable=True,
                        dice=None) -> Result:
    if is_skinning_tool(tool_cid):
        return skin(target_cid, target_quality, tool_cid, tool_quality,
                    dice=dice)
    if is_dna_tool(tool_cid):
        return collect_dna(target_cid, dna, tool_cid, target_quality, viable)
    return Result(OUTCOME_WRONG_TOOL, target_cid, tool_cid)


def _tool_spared(tool_quality, dice=None) -> bool:
    return bool(_gw.test_quality(int(tool_quality) & 0xFF, dice))


def describe_output(out) -> str:
    return "%d %s Q%d" % (out.quantity, out.name, out.quality)


def thought_for(result, target_name=None):
    tmpl = result.thought
    if not tmpl:
        return None, ()
    name = target_name if target_name is not None else commodity_name(
        result.target_cid)
    if result.outcome == OUTCOME_SKINNED:
        return tmpl, tuple([name] + [describe_output(o)
                                     for o in result.outputs])
    return tmpl, (name,)


CARCASS_PER_KILL = 1

DEFAULT_CARCASS_QUALITY = 100


def carcass_from_kill(d):
    if d is None:
        return []
    if getattr(d, "alive", True):
        return []
    q = int(getattr(d, "quality", 0) or 0) & 0xFF
    if getattr(d, "is_citizen", False):
        return [(CID_HEAD, 1, q or DEFAULT_CARCASS_QUALITY),
                (CID_ANIMAL_CARCASS, CARCASS_PER_KILL,
                 q or DEFAULT_CARCASS_QUALITY)]
    return [(CID_ANIMAL_CARCASS, CARCASS_PER_KILL,
             q or DEFAULT_CARCASS_QUALITY)]
