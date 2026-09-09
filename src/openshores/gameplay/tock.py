
from __future__ import annotations

MS_SECOND = 1000
MS_GAMES = 2000
MS_FLAG_TAKEOVER = 2000
MS_DEVELOPMENT = 10000
MS_EMPLOY = 30000
MS_SENSORS = 60000
MS_IMPORTS = 360000
MS_TRADE_CHANNEL = 960000
MS_BOUNTY = 3600000
MS_DEAD_CITY = 240000
PIRATE_DECAY_RAW = 0xF7313FF
MS_PIRATE_DECAY = 72 * 3600 * 1000

CITY_CYCLE_SEC = 5400.0 / 7.0
MS_CITY_CYCLE = CITY_CYCLE_SEC * 1000.0


def bucket_rolled(last_ms, now_ms, interval_ms, city_id=0, stagger=False):
    if interval_ms <= 0:
        return True
    off = int(city_id) if stagger else 0
    a = (int(last_ms) + off) // int(interval_ms)
    b = (int(now_ms) + off) // int(interval_ms)
    return b != a and b - a >= 0


def elapsed_reached(last_ms, now_ms, interval_ms):
    if not last_ms:
        return True
    return (int(now_ms) - int(last_ms)) >= int(interval_ms)


def second_of(ms):
    return int(ms) // MS_SECOND


def imports_due(last_ms, now_ms, city_id):
    if not bucket_rolled(last_ms, now_ms, MS_SENSORS):
        return False, False
    m = ((int(now_ms) // MS_SENSORS) + int(city_id)) % 60
    return (m % 6 == 0), (m == 0)


class TockState:

    __slots__ = ("last_tock_ms", "employ_ms", "city_cycle_ms",
                 "trade_channel_ms", "no_capitol_since_ms", "founded_ms")

    def __init__(self, now_ms=0):
        self.last_tock_ms = int(now_ms)
        self.employ_ms = 0
        self.city_cycle_ms = int(now_ms)
        self.trade_channel_ms = 0
        self.no_capitol_since_ms = 0
        self.founded_ms = int(now_ms)


def due(state, now_ms, *, city_id=0, has_capitol=True, jobs=0,
        is_pirate=False, owned=True):
    last = state.last_tock_ms
    out = {k: False for k in (
        "flag_queue", "transporters", "shield_charge", "bay_weapons",
        "games", "games_minute", "flag_takeover", "development", "employ",
        "city_cycle", "sensors", "imports", "shipments_hour", "trade_channel",
        "bounty", "dead_city", "pirate_decay")}

    out["flag_queue"] = True
    out["transporters"] = True

    if bucket_rolled(last, now_ms, MS_SECOND):
        sec = second_of(last)
        if has_capitol:
            out["shield_charge"] = True
            out["bay_weapons"] = True
            if sec & 1:
                out["games"] = True
                out["games_minute"] = bucket_rolled(last, now_ms, MS_SENSORS)
        if owned and not (sec & 1):
            out["flag_takeover"] = True

    if not has_capitol:
        out["dead_city"] = elapsed_reached(state.no_capitol_since_ms, now_ms,
                                           MS_DEAD_CITY)

    if is_pirate and not owned:
        out["pirate_decay"] = elapsed_reached(state.founded_ms, now_ms,
                                              MS_PIRATE_DECAY)

    out["trade_channel"] = elapsed_reached(state.trade_channel_ms, now_ms,
                                           MS_TRADE_CHANNEL)

    out["sensors"] = bucket_rolled(last, now_ms, MS_SENSORS)
    out["imports"], out["shipments_hour"] = imports_due(last, now_ms, city_id)

    if not bucket_rolled(last, now_ms, MS_DEVELOPMENT,
                         city_id=city_id, stagger=True):
        return out
    out["development"] = True

    out["bounty"] = bucket_rolled(last, now_ms, MS_BOUNTY,
                                  city_id=city_id, stagger=True)

    if elapsed_reached(state.employ_ms, now_ms, MS_EMPLOY) or int(jobs) < 0:
        out["employ"] = True
        secs = (int(now_ms) - int(state.city_cycle_ms)) / 1000.0
        if secs >= CITY_CYCLE_SEC:
            out["city_cycle"] = True

    return out


def commit(state, now_ms, fired):
    if fired.get("employ"):
        state.employ_ms = int(now_ms)
    if fired.get("city_cycle"):
        state.city_cycle_ms = int(now_ms)
    if fired.get("trade_channel"):
        state.trade_channel_ms = int(now_ms)
    state.last_tock_ms = int(now_ms)


IMPORT_RULES = {
    0x65: ("broker",  lambda lv: min(lv * 2, 0x50)),
    0x67: ("grocery", lambda lv: min(lv, 0x28)),
    0x68: ("retail",  lambda lv: min(lv, 0x28)),
    0x69: ("cantina", lambda lv: min((lv + 1) // 2, 0x14)),
}


def import_amounts(levels_by_industry):
    out = {}
    for ind, (name, fn) in IMPORT_RULES.items():
        lv = int(levels_by_industry.get(ind, 0))
        if lv > 0:
            out[name] = fn(lv)
    return out
