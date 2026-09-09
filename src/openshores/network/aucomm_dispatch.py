
from __future__ import annotations

from openshores.network.avatar_transfer import (
    handle_aucomm_accept_avatar,
    handle_aucomm_offer_avatar,
)
from openshores.network.empire_aucomm import (
    handle_aucomm_announcement,
    handle_aucomm_citizen_order,
    handle_aucomm_city_surrender_accepted,
    handle_aucomm_city_surrender_offered,
    handle_aucomm_diplomatic_message,
)
from openshores.network.empire_invite import (
    handle_aucomm_accept_invite_to_empire,
    handle_aucomm_invite_to_empire,
)
from openshores.protocol.atoms.aucomm import (
    parse_aucomm_accept_avatar,
    parse_aucomm_accept_invite_to_empire,
    parse_aucomm_announcement,
    parse_aucomm_citizen_order,
    parse_aucomm_city_surrender_accepted,
    parse_aucomm_city_surrender_offered,
    parse_aucomm_diplomatic_message,
    parse_aucomm_invite_to_empire,
    parse_aucomm_offer_avatar,
)

AUCOMM_HANDLERS: dict = {
    0x01: ("AcceptAvatar", parse_aucomm_accept_avatar,
           handle_aucomm_accept_avatar),
    0x0E: ("AcceptInviteToEmpire", parse_aucomm_accept_invite_to_empire,
           handle_aucomm_accept_invite_to_empire),
    0x50: ("OfferAvatar", parse_aucomm_offer_avatar,
           handle_aucomm_offer_avatar),
    0x14: ("Announcement", parse_aucomm_announcement,
           handle_aucomm_announcement),
    0x2E: ("CitizenOrder", parse_aucomm_citizen_order,
           handle_aucomm_citizen_order),
    0x32: ("CitySurrenderAccepted", parse_aucomm_city_surrender_accepted,
           handle_aucomm_city_surrender_accepted),
    0x33: ("CitySurrenderOffered", parse_aucomm_city_surrender_offered,
           handle_aucomm_city_surrender_offered),
    0x3B: ("DiplomaticMessage", parse_aucomm_diplomatic_message,
           handle_aucomm_diplomatic_message),
    0x42: ("InviteToEmpire", parse_aucomm_invite_to_empire,
           handle_aucomm_invite_to_empire),
}
