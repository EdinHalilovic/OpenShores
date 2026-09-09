

from __future__ import annotations


SCENE_OP_NAMES = {
    0x0A: "AuCommPacket(encrypted)",
    0x18: "ServerTimeUpdated ACK (C->S echo of S->C 0x18 heartbeat)",
    0x22: "DnBuilding",
    0x23: "DnSpaceShip",
    0x24: "EstablishFirstEmpire (TX) / DnDetail (RX)",
    0x25: "int16+int16",
    0x26: "int16+int16",
    0x28: "DnDetail (variant)",
    0x2E: "RequestBasicGameData (C->S, no payload)",
    0x38: "ResumeEmpire (scene hello)",
    0x39: "DnRoom",
    0x3B: "ActivateUnit/StartScene (AuId)",
    0x3E: "C->S unknown, empty payload",
    0x42: "PlayerUnitDeltaTick (C->S, 50ms, flags=int16)",
    0x47: "Net2 keepalive (61s idle)",
    0x60: "MoveGearItemToSlot (C->S, gear right-click action)",
    0x77: "Net1 keepalive",
}


_ACK_OPCODES: frozenset = frozenset({0x18, 0x42})
