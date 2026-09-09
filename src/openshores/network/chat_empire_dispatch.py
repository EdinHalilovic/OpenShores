
from __future__ import annotations

from openshores.network.empire_admin import (
    handle_chat_change_empire_flag_player,
    handle_chat_empire_chg_flag_agent,
    handle_chat_empire_chg_name,
    handle_chat_empire_set_announcement,
    handle_chat_empire_set_taxes,
    handle_chat_rename_world,
)
from openshores.network.selfie import handle_chat_send_selfie

CHAT_DIRECT_EMPIRE_HANDLERS: dict = {
    0x4A: ("ChangeEmpireFlag (player)", handle_chat_change_empire_flag_player),
    0x4F: ("RenameWorld",               handle_chat_rename_world),
    0x64: ("SendSelfie",                handle_chat_send_selfie),
    0xA4: ("SetAnnouncement",           handle_chat_empire_set_announcement),
    0xAF: ("SetEmpireTaxes",            handle_chat_empire_set_taxes),
    0xB8: ("EmpireChgFlag (agent)",     handle_chat_empire_chg_flag_agent),
    0xB9: ("EmpireChgName (agent)",     handle_chat_empire_chg_name),
}
