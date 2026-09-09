
from __future__ import annotations

from openshores.gameplay.design_requests import on_design_loaded_notify
from openshores.gameplay.empire_office import _make_capture_handler
from openshores.network.empire_diplomacy_ops import (
    on_dossier,
    on_founder_domain,
    on_per_empire_stance,
    on_war_criteria,
)
from openshores.network.empire_office_ops import (
    on_emperor,
    on_rewards,
    on_role,
)
from openshores.network.empire_policy_ops import (
    SINGLE_BYTE_POLICY_OP,
    _make_policy_handler,
    on_assign_office,
    on_change_boss,
    on_commerce,
    on_contrail_set,
    on_kick_renounce,
    on_resign_office,
    on_revoke_office,
    on_theme_color,
    on_zonebuild,
)
from openshores.network.blueprint_serve import (on_blueprint_request,
                                               on_design_request)
from openshores.network.city_report_ops import on_city_report_request
from openshores.network.demolish_ops import (_on_work_site_fetch,
                                             _on_work_site_labor)
from openshores.network.found_ops import (
    on_create_empire,
    on_found_city,
    on_found_town_square,
)
from openshores.network.handcraft_ops import on_handcraft
from openshores.network.manufacture_ops import (
    on_bd_manufacture,
    on_bd_set_min_quality,
    on_bd_set_shops,
)

CHAT_DIRECT_HANDLERS: dict = {
    0xBA: ("EmpireChgRole", on_role),
    0xB7: ("EmpireChgEmperor", on_emperor),
    0xA8: ("GovSetCommerce", on_commerce),
    0xAD: ("GovSetRewards", on_rewards),
    0xD5: ("GovSetThemeColor", on_theme_color),
    0x98: ("GovSetContrailColor", on_contrail_set),
    0xB1: ("GovSetZoneBuildPermit", on_zonebuild),
    0x4E: ("KickRenounce", on_kick_renounce),
    0x94: ("AssignOffice", on_assign_office),
    0xA5: ("ChangeBoss", on_change_boss),
    0xA1: ("RevokeOffice", on_revoke_office),
    0xA0: ("ResignOffice", on_resign_office),
    0xCA: ("CreateEmpire", on_create_empire),
    0xE3: ("FoundCity", on_found_city),
    0x07: ("FoundTownSquare", on_found_town_square),
    0xDE: ("BlueprintRequest", on_blueprint_request),
    0xDF: ("BdDesignRequest", on_design_request),
    0xE0: ("BdDesignLoadedNotify", on_design_loaded_notify),
    0x79: ("BdManufactureMPID", on_bd_manufacture),
    0x71: ("BdManufactureCitizenEnabledMPID", on_bd_set_shops),
    0xC9: ("BdManufactureProcessSetMinQMPID",
           on_bd_set_min_quality),
    0xCC: ("Dossier", on_dossier),
    0xAC: ("PerEmpireStance", on_per_empire_stance),
    0xCD: ("WarCriteria", on_war_criteria),
    0xCB: ("FounderDomain", on_founder_domain),
    0x50: ("CityReportRequest", on_city_report_request),
    0x76: ("Handcraft", on_handcraft),
    0x74: ("WorkSiteFetchOrPoll", _on_work_site_fetch),
    0x75: ("WorkSiteLaborOrMfgGo", _on_work_site_labor),
}


def loop_built_entries(
        *, conn, _CITIZEN_EMPIRE_OVERRIDE, _live_avatars, name_long: str,
        name_short: str, capital_name: str, _EMPIRE_NAME_OVERRIDE,
        _EMPIRE_TAX_OVERRIDE) -> dict:
    entries: dict = {
        0x99: ("SetOffice", _make_capture_handler(
            0x99, "SetOffice", conn=conn,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE)),
    }
    for _pop, (_pcol, _plabel) in SINGLE_BYTE_POLICY_OP.items():
        entries[_pop] = ("GovSet" + _plabel, _make_policy_handler(
            _pop, _pcol, _plabel,
            _live_avatars=_live_avatars, conn=conn,
            _CITIZEN_EMPIRE_OVERRIDE=_CITIZEN_EMPIRE_OVERRIDE,
            name_long=name_long, name_short=name_short,
            capital_name=capital_name,
            _EMPIRE_NAME_OVERRIDE=_EMPIRE_NAME_OVERRIDE,
            _EMPIRE_TAX_OVERRIDE=_EMPIRE_TAX_OVERRIDE))
    return entries
