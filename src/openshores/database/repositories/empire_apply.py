
from __future__ import annotations

from typing import List

import asyncpg

from openshores.database.repositories.empire import _update_empire
from openshores.protocol.empire_chat_parse import _s32


POLICY_COLUMN = {
    0: "rightToFound",
    1: "trespass",
    2: "cityDebt",
    3: "immig",
    4: "defaultStance",
    5: "zoneBuildPolicy",
}

REWARD_COLUMNS = (
    "rewCapBase", "rewCapCapital", "rewCapCapitalSector", "rewCapCity",
    "rewCapSpaceport", "rewCapSpaceship", "rewCapStarship", "rewDmgSpaceport",
    "rewDmgSpaceship", "rewDmgStarShip", "rewDiscHabitable", "rewDiscWorm",
    "rewKillEnemy", "rewSalary", "rewSpotCity", "rewSpotEnemy",
)


async def apply_policy_toggle(conn: asyncpg.Connection, eid: int, index: int,
                              value: int) -> dict:
    col = POLICY_COLUMN.get(int(index))
    if col is None:
        return {"ok": False, "reason": f"unknown policyIndex {index}"}
    ok = await _update_empire(conn, eid, **{col: int(value) & 0xFF})
    return {"ok": ok, "column": col, "value": int(value) & 0xFF}


async def apply_contrail_color(conn: asyncpg.Connection, eid: int,
                               component: int, value: int) -> dict:
    col = {0: "contrailHue", 1: "contrailSat"}.get(int(component))
    if col is None:
        return {"ok": False,
                "reason": f"component {component} is not a contrail byte "
                          f"(theme-palette slot?)"}
    ok = await _update_empire(conn, eid, **{col: int(value) & 0xFF})
    return {"ok": ok, "column": col, "value": int(value) & 0xFF}


async def apply_role(conn: asyncpg.Connection, eid: int, role: int) -> dict:
    ok = await _update_empire(conn, eid, role=int(role) & 0xFF)
    return {"ok": ok, "role": int(role) & 0xFF}


async def apply_rewards(conn: asyncpg.Connection, eid: int,
                        rewards: List[int]) -> dict:
    cols = {REWARD_COLUMNS[i]: _s32(int(rewards[i]))
            for i in range(min(16, len(rewards)))}
    ok = await _update_empire(conn, eid, **cols)
    return {"ok": ok, "rewards": [int(x) for x in rewards[:16]]}
