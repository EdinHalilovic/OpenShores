from __future__ import annotations

import re

from openshores.world.entities import CITIZEN_KINDS

VICTIM_UNIT = "unit"
VICTIM_CITIZEN = "citizen"
VICTIM_AVATAR = "avatar"
VICTIM_OFFICER = "officer"
VICTIM_CREW = "crew"
VICTIM_TROOP = "troop"
VICTIM_PASSENGER = "passenger"
VICTIM_WORKER = "worker"

ALL_VICTIM_KINDS = (VICTIM_UNIT, VICTIM_CITIZEN, VICTIM_AVATAR, VICTIM_OFFICER,
                    VICTIM_CREW, VICTIM_TROOP, VICTIM_PASSENGER, VICTIM_WORKER)

DOC_CLASS = {
    VICTIM_UNIT: "AuDocUnitKilled",
    VICTIM_CITIZEN: "AuDocCitizenKilled",
    VICTIM_AVATAR: "AuDocAvatarKilled",
    VICTIM_OFFICER: "AuDocOfficerKilled",
    VICTIM_CREW: "AuDocCrewKilled",
    VICTIM_TROOP: "AuDocTroopKilled",
    VICTIM_PASSENGER: "AuDocPassengerKilled",
    VICTIM_WORKER: "AuDocWorkerKilled",
}

RAISED_BY = {
    VICTIM_UNIT: "DaUnit",
    VICTIM_CITIZEN: "DaCitizen",
    VICTIM_AVATAR: "DaPerson",
    VICTIM_OFFICER: "DaCitOfficer",
    VICTIM_CREW: "DaCitCrew",
    VICTIM_TROOP: "DaCitTroop",
    VICTIM_PASSENGER: "DaCitPassenger",
    VICTIM_WORKER: "DaCitWorker",
}

DOC_ICON = {
    VICTIM_UNIT: ":data/DocUnitKilled.png",
    VICTIM_CITIZEN: ":data/DocCitizenKilled.png",
    VICTIM_AVATAR: ":data/DocAvatarKilled.png",
    VICTIM_OFFICER: ":data/DocOfficerKilled.png",
    VICTIM_CREW: ":data/DocCrewKilled.png",
    VICTIM_TROOP: ":data/DocTroopKilled.png",
    VICTIM_PASSENGER: ":data/DocPassengerKilled.png",
    VICTIM_WORKER: ":data/DocWorkerKilled.png",
}

DOC_TYPE = {
    VICTIM_UNIT: 0x05,
    VICTIM_CITIZEN: 0x0F,
    VICTIM_AVATAR: 0x1E,
    VICTIM_OFFICER: 0x1F,
    VICTIM_CREW: 0x20,
    VICTIM_TROOP: 0x21,
    VICTIM_PASSENGER: 0x22,
    VICTIM_WORKER: 0x23,
}
DOC_TYPE_IS_DERIVED = True

STATE_NEW = 0
STATE_OPEN = 1
STATE_PEND = 2
STATE_CLOSE = 3
STATE_DROPPED = 4
STATE_QUESTION = 5

STATE_ICONS = {
    STATE_NEW: ":data/new12x12.png",
    STATE_OPEN: ":data/fire10x10.png",
    STATE_PEND: ":data/postponed10x10.png",
    STATE_CLOSE: ":data/required10x10.png",
    STATE_DROPPED: ":data/dropped10.png",
    STATE_QUESTION: ":data/question10x10.png",
}

STATE_NAMES = {
    STATE_NEW: "New",
    STATE_OPEN: "Open",
    STATE_PEND: "Pend",
    STATE_CLOSE: "Close",
    STATE_DROPPED: "Dropped",
    STATE_QUESTION: "Question",
}

VARIANT_PLACE = 0
VARIANT_SYSTEM = 1
VARIANT_WIDE = 2

VARIANT_NAMES = {VARIANT_PLACE: "place", VARIANT_SYSTEM: "system",
                 VARIANT_WIDE: "wide"}


class Location:

    __slots__ = ("place", "system", "region", "galaxy")

    def __init__(self, place="", system="", region="", galaxy=""):
        self.place = str(place or "")
        self.system = str(system or "")
        self.region = str(region or "")
        self.galaxy = str(galaxy or "")

    @property
    def variant(self):
        if self.place and self.system:
            return VARIANT_PLACE
        if self.system:
            return VARIANT_SYSTEM
        return VARIANT_WIDE

    def __repr__(self):
        return ("Location(place=%r system=%r region=%r galaxy=%r -> %s)"
                % (self.place, self.system, self.region, self.galaxy,
                   VARIANT_NAMES[self.variant]))


TEMPLATES = {
    VICTIM_CITIZEN: (
        "<p>Star Date %1</p><p>Subject: %7 Killed</p><p>Status: <img src=\"qrc%9\"> %10</p><p>One of our citizens was killed today at %3 in the %4 system, %5, %6. A funeral was held for the victim, whose name was %7.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %8.</p>",
        "<p>Star Date %1</p><p>Subject: %6 Killed</p><p>Status: <img src=\"qrc%8\"> %9</p><p>One of our citizens was killed today in the %3 system, %4, %5. A funeral was held for the victim, whose name was %6.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %7.</p>",
        "<p>Star Date %1</p><p>Subject: %5 Killed</p><p>Status: <img src=\"qrc%7\"> %8</p><p>One of our citizens was killed today in %3, %4. A funeral was held for the victim, whose name was %5.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %6.</p>",
    ),
    VICTIM_AVATAR: (
        "<p>Star Date %1</p><p>Subject: %7 Killed</p><p>Status: <img src=\"qrc%9\"> %10</p><p>One of our avatars was killed today at %3 in the %4 system, %5, %6. The victim's name was %7.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %8.</p>",
        "<p>Star Date %1</p><p>Subject: %6 Killed</p><p>Status: <img src=\"qrc%8\"> %9</p><p>One of our avatars was killed today in the %3 system, %4, %5. The victim's name was %6.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %7.</p>",
        "<p>Star Date %1</p><p>Subject: %5 Killed</p><p>Status: <img src=\"qrc%7\"> %8</p><p>One of our avatars was killed today in %3, %4. The victim's name was %5.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %6.</p>",
    ),
    VICTIM_OFFICER: (
        "<p>Star Date %1</p><p>Subject: %7 Killed</p><p>Status: <img src=\"qrc%10\"> %11</p><p>One of our officers was killed today at %3 in the %4 system, %5, %6. The victim was %7, from %9.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %8.</p>",
        "<p>Star Date %1</p><p>Subject: %6 Killed</p><p>Status: <img src=\"qrc%9\"> %10</p><p>One of our officers was killed today in the %3 system, %4, %5. The victim was %6, from %8.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %7.</p>",
        "<p>Star Date %1</p><p>Subject: %5 Killed</p><p>Status: <img src=\"qrc%8\"> %9</p><p>One of our officers was killed today in %3, %4. The victim was %5, from %7.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %6.</p>",
    ),
    VICTIM_CREW: (
        "<p>Star Date %1</p><p>Subject: %7 Killed</p><p>Status: <img src=\"qrc%9\"> %10</p><p>One of our starmen was killed today at %3 in the %4 system, %5, %6. The victim's name was %7.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %8.</p>",
        "<p>Star Date %1</p><p>Subject: %6 Killed</p><p>Status: <img src=\"qrc%8\"> %9</p><p>One of our starmen was killed today in the %3 system, %4, %5. The victim's name was %6.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %7.</p>",
        "<p>Star Date %1</p><p>Subject: %5 Killed</p><p>Status: <img src=\"qrc%7\"> %9</p><p>One of our starmen was killed today in %3, %4. The victim's name was %5.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %6.</p>",
    ),
    VICTIM_TROOP: (
        "<p>Star Date %1</p><p>Subject: %7 Killed</p><p>Status: <img src=\"qrc%9\"> %10</p><p>One of our troops was killed today at %3 in the %4 system, %5, %6. The victim's name was %7.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %8.</p>",
        "<p>Star Date %1</p><p>Subject: %6 Killed</p><p>Status: <img src=\"qrc%8\"> %9</p><p>One of our troops was killed today in the %3 system, %4, %5. The victim's name was %6.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %7.</p>",
        "<p>Star Date %1</p><p>Subject: %5 Killed</p><p>Status: <img src=\"qrc%7\"> %8</p><p>One of our troops was killed today in %3, %4. The victim's name was %5.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %6.</p>",
    ),
    VICTIM_PASSENGER: (
        "<p>Star Date %1</p><p>Subject: %7 Killed</p><p>Status: <img src=\"qrc%9\"> %10</p><p>A passenger of a spacecraft bearing our flag was killed today at %3 in the %4 system, %5, %6. The victim's name was %7.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %8.</p>",
        "<p>Star Date %1</p><p>Subject: %6 Killed</p><p>Status: <img src=\"qrc%8\"> %9</p><p>A passenger of a spacecraft bearing our flag was killed today in the %3 system, %4, %5. The victim's name was %6.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %7.</p>",
        "<p>Star Date %1</p><p>Subject: %5 Killed</p><p>Status: <img src=\"qrc%7\"> %8</p><p>A passenger of a spacecraft bearing our flag was killed today in %3, %4. The victim's name was %5.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %6.</p>",
    ),
    VICTIM_WORKER: (
        "<p>Star Date %1</p><p>Subject: %7 Killed</p><p>Status: <img src=\"qrc%9\"> %10</p><p>One of our workers was killed today at %3 in the %4 system, %5, %6. The victim's name was %7.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %8.</p>",
        "<p>Star Date %1</p><p>Subject: %6 Killed</p><p>Status: <img src=\"qrc%8\"> %9</p><p>One of our workers was killed today in the %3 system, %4, %5. The victim's name was %6.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %7.</p>",
        "<p>Star Date %1</p><p>Subject: %5 Killed</p><p>Status: <img src=\"qrc%7\"> %8</p><p>One of our workers was killed today in %3, %4. The victim's name was %5.</p><p>With the help of trusted witnesses and DNA evidence, the murderer was positively identified as a %2 unit named %6.</p>",
    ),
    VICTIM_UNIT: (
        "<p>Star Date %1</p><p>Subject: Unit Killed by %2</p><p>Status: <img src=\"qrc%11\"> %12</p><p>One of our units was destroyed today by the %2 at %3 in the %4 system, %5, %6. Our unit was identified as %7 (%8). It was destroyed by a %2 unit named %9 (%10).</p><p>Our only recourse to this grave incident was to declare %2 to be our enemy.</p>",
        "<p>Star Date %1</p><p>Subject: Unit Killed by %2</p><p>Status: <img src=\"qrc%10\"> %11</p><p>One of our units was destroyed today by the %2 in the %3 system, %4, %5. Our unit was identified as %6 (%7). It was destroyed by a %2 unit named %8 (%9).</p><p>Our only recourse to this grave incident was to declare %2 to be our enemy.</p>",
        "<p>Star Date %1</p><p>Subject: Unit Killed by %2</p><p>Status: <img src=\"qrc%9\"> %10</p><p>One of our units was destroyed today by the %2 in %3, %4. Our unit was identified as %5 (%6). It was destroyed by a %2 unit named %8 (%8).</p><p>Our only recourse to this grave incident was to declare %2 to be our enemy.</p>",
    ),
}

TEMPLATE_BUGS = {
    (VICTIM_CREW, VARIANT_WIDE):
        "%8 missing: the state name renders into %9. Harmless.",
    (VICTIM_UNIT, VARIANT_WIDE):
        "%7 missing and %8 doubled: the killer's designation renders into the "
        "status <img src>, the icon path renders as the status text, and the "
        "state name is dropped.",
}

KINDS_WITH_FROM = frozenset({VICTIM_OFFICER})


_MARKER = re.compile(r"%(\d\d?)")


def qt_arg(template, value):
    spans = [(m.start(), m.end(), int(m.group(1)))
             for m in _MARKER.finditer(template)]
    if not spans:
        return template
    low = min(n for _s, _e, n in spans)
    out = []
    pos = 0
    for s, e, n in spans:
        if n != low:
            continue
        out.append(template[pos:s])
        out.append(str(value))
        pos = e
    out.append(template[pos:])
    return "".join(out)


def qt_args(template, values):
    s = template
    for v in values:
        s = qt_arg(s, v)
    return s


def markers(template):
    return {int(m.group(1)) for m in _MARKER.finditer(template)}


class Kill:

    __slots__ = ("victim_kind", "victim_name", "victim_type", "killer_empire",
                 "killer_name", "killer_type", "where", "officer_from",
                 "weapon", "state", "star_date")

    def __init__(self, victim_kind, victim_name="", killer_empire="",
                 killer_name="", where=None, victim_type="", killer_type="",
                 officer_from="", weapon=None, state=STATE_NEW,
                 star_date=""):
        if victim_kind not in TEMPLATES:
            raise ValueError("Unknown victim kind %r" % (victim_kind,))
        self.victim_kind = victim_kind
        self.victim_name = str(victim_name or "")
        self.victim_type = str(victim_type or "")
        self.killer_empire = str(killer_empire or "")
        self.killer_name = str(killer_name or "")
        self.killer_type = str(killer_type or "")
        self.where = where if where is not None else Location()
        self.officer_from = str(officer_from or "")
        self.weapon = weapon
        self.state = int(state)
        self.star_date = str(star_date or "")

    @property
    def doc_class(self):
        return DOC_CLASS[self.victim_kind]

    @property
    def doc_type(self):
        return DOC_TYPE[self.victim_kind]

    @property
    def variant(self):
        return self.where.variant

    def __repr__(self):
        return ("Kill(%s %r by %r/%r %r)"
                % (self.victim_kind, self.victim_name, self.killer_empire,
                   self.killer_name, VARIANT_NAMES[self.variant]))


def template_for(victim_kind, where=None):
    variant = (where.variant if where is not None else VARIANT_WIDE)
    return TEMPLATES[victim_kind][variant]


def render_args(kill):
    loc = kill.where
    variant = loc.variant
    args = [kill.star_date, kill.killer_empire]
    if variant == VARIANT_PLACE:
        args += [loc.place, loc.system]
    elif variant == VARIANT_SYSTEM:
        args += [loc.system]
    args += [loc.region, loc.galaxy]

    if kill.victim_kind == VICTIM_UNIT:
        args += [kill.victim_name, kill.victim_type,
                 kill.killer_name, kill.killer_type]
    else:
        args += [kill.victim_name, kill.killer_name]
        if kill.victim_kind in KINDS_WITH_FROM:
            args.append(kill.officer_from)

    args += [STATE_ICONS.get(kill.state, STATE_ICONS[STATE_NEW]),
             STATE_NAMES.get(kill.state, STATE_NAMES[STATE_NEW])]
    return args


def render(kill) -> str:
    return qt_args(template_for(kill.victim_kind, kill.where),
                   render_args(kill))


class Obituary:

    __slots__ = ("kill", "doc_type", "doc_class", "icon", "variant", "html")

    def __init__(self, kill):
        self.kill = kill
        self.doc_type = kill.doc_type
        self.doc_class = kill.doc_class
        self.icon = DOC_ICON[kill.victim_kind]
        self.variant = kill.variant
        self.html = render(kill)

    def __repr__(self):
        return ("Obituary(%s type=0x%02x %s)"
                % (self.doc_class, self.doc_type,
                   VARIANT_NAMES[self.variant]))


def obituary_for_kill(victim_kind, victim_name="", killer_empire="",
                      killer_name="", where=None, **kw):
    return Obituary(Kill(victim_kind, victim_name=victim_name,
                         killer_empire=killer_empire,
                         killer_name=killer_name, where=where, **kw))


def victim_kind_for_damageable(d):
    if d is None:
        return None
    kind = getattr(d, "kind", None)
    if kind in CITIZEN_KINDS:
        return VICTIM_CITIZEN
    return None


def dossier_row(obit, knower_empire, known_empire, timestamp_ms,
                actor_avatar=0):
    return {
        "knower_empire_id": int(knower_empire) & 0xFFFFFFFF,
        "known_empire_id": int(known_empire) & 0xFFFFFFFF,
        "doc_type": int(obit.doc_type),
        "timestamp_ms": int(timestamp_ms),
        "actor_avatar_id": int(actor_avatar) & 0xFFFFFFFF,
        "actor_empire_id": int(known_empire) & 0xFFFFFFFF,
        "text_a": obit.kill.victim_name,
        "text_b": obit.kill.killer_name,
        "text_c": obit.kill.where.place or obit.kill.where.system,
        "doc_state": int(obit.kill.state),
    }


