from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List
from openshores.gameplay import gd_tables as _gd
from openshores.gameplay.city_report_native import (
    home_triple_is_fatal,
    industries_from_developments,
)
from openshores.gameplay.city_sim import build_service_needs, city_job_total, unmet_services
from openshores.gameplay.design_report import city_industry_summary, homes_from_reports

EVENT_STARVATION = "starvation"
EVENT_SUFFOCATION = "suffocation"
EVENT_BIRTHS = "births"
EVENT_NO_POWER = "no_power"
EVENT_UNDERSERVED = "underserved"
EVENT_DECAY = "decay"
EVENT_HOUSING = "housing"


@dataclass
class CityReport:
    t: int = 0
    city_auid: int = 0
    name: str = ""
    population: int = 0
    jobs: int = 0
    population_before: int = 0
    births: int = 0
    deaths_food: int = 0
    deaths_air: int = 0
    satisfaction: int = 0
    satisfaction_delta: int = 0
    food_ate: int = 0
    starving: bool = False
    suffocating: bool = False
    no_power: bool = False
    services_wanted: list = field(default_factory=list)
    housing_penalty: int = 0
    service_penalty: int = 0
    salaries_paid: float = 0.0
    income_tax: float = 0.0
    sales_tax: float = 0.0
    tribute: float = 0.0
    bank: float = 0.0
    treasury: float = 0.0
    produced: dict = field(default_factory=dict)
    events: List[dict] = field(default_factory=list)
    industries: dict = field(default_factory=dict)
    lat: float = None
    lon: float = None
    homes_large: int = 0
    homes_medium: int = 0
    homes_small: int = 0
    jobs_manufacturing: int = 0
    jobs_service: int = 0
    unemployed: int = 0

    @property
    def deaths_total(self) -> int:
        return int(self.deaths_food) + int(self.deaths_air)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["deaths_total"] = self.deaths_total
        return d


def _ev(kind: str, count: int = 0, detail: str = "") -> dict:
    return {"kind": kind, "count": int(count), "detail": detail}


def _withheld_housing_note(rep) -> str:
    try:
        if not home_triple_is_fatal(rep.homes_large, rep.homes_medium,
                                    rep.homes_small):
            return ""
    except Exception:
        return ""
    return ("Housing: %d small homes, %d medium, %d large. The Homes lines "
            "below read 0 because the client divides by "
            "medium + 2 x large. Add one medium or large home to any design "
            "in this city to show them."
            % (rep.homes_small, rep.homes_medium, rep.homes_large))


def _services_wanted(result, state) -> list:
    try:
        return unmet_services(build_service_needs(state))
    except Exception:
        return []


def _job_total(state) -> int:
    try:
        return int(city_job_total(state) or 0)
    except Exception:
        return 0


def _industry_summary(buildings, design_reports):
    if not design_reports or not buildings:
        return None, 0, 0
    try:
        table = _gd.load_industries()
        if not table:
            return None, 0, 0
        pairs = []
        for b, rep in zip(buildings, design_reports):
            if not isinstance(b, dict) or b.get("kind", "building") != "building":
                continue
            cpid = int(b.get("cpid") or 0)
            if not cpid:
                continue
            pairs.append((_gd.construction_process_industry(cpid) or cpid, rep))
        if not pairs:
            return None, 0, 0
        levels, mfg, svc = city_industry_summary(pairs, table)
        return ({int(k): int(v) for k, v in levels.items()} or None), mfg, svc
    except Exception:
        return None, 0, 0


def _industries(buildings) -> dict:
    try:
        return {int(k): int(v)
                for k, v in (industries_from_developments(buildings) or {}).items()}
    except Exception:
        return {}


def _mean_location(buildings):
    lats, lons = [], []
    for b in (buildings or []):
        if not isinstance(b, dict):
            continue
        if b.get("lat") is None or b.get("lon") is None:
            continue
        try:
            lats.append(float(b["lat"])); lons.append(float(b["lon"]))
        except (TypeError, ValueError):
            continue
    if not lats:
        return None, None
    return sum(lats) / len(lats), sum(lons) / len(lons)


def build_report(city_auid: int, name: str, pop_before: int, result: dict,
                 state_after, now_ms: int, buildings=None,
                 design_reports=None) -> CityReport:
    needs = result.get("needs") or {}
    deaths = result.get("deaths") or {}
    wages = result.get("wages") or {}
    df = int(deaths.get("food_deaths", 0))
    da = int(deaths.get("air_deaths", 0))
    births = int(result.get("growth", 0))

    rep = CityReport(
        t=int(now_ms), city_auid=int(city_auid) & 0xFFFFFFFF, name=name or "",
        population=int(getattr(state_after, "population", 0)),
        population_before=int(pop_before),
        births=births, deaths_food=df, deaths_air=da,
        satisfaction=int(getattr(state_after, "satisfaction", 0)),
        satisfaction_delta=int(needs.get("sat_delta", 0)),
        food_ate=int(needs.get("food_ate", 0)),
        starving=bool(needs.get("starving", False)),
        suffocating=bool(needs.get("suffocating", False)),
        no_power=not bool(getattr(state_after, "has_power", True)),
        housing_penalty=int(needs.get("housing_penalty", 0)),
        service_penalty=int(needs.get("service_penalty", 0)),
        services_wanted=_services_wanted(result, state_after),
        salaries_paid=float(wages.get("wages", 0.0)),
        income_tax=float(wages.get("income_tax", 0.0)),
        sales_tax=float(getattr(state_after, "govt_sales_tax", 0.0)),
        tribute=float(getattr(state_after, "last_tribute", 0.0)),
        bank=float(getattr(state_after, "bank", 0.0)),
        treasury=float(getattr(state_after, "govt", 0.0)),
        produced=dict(result.get("produced") or {}),
        jobs=_job_total(state_after),
        industries=_industries(buildings),
    )
    _lv, _mfg, _svc = _industry_summary(buildings, design_reports)
    if _lv:
        rep.industries = _lv
    rep.jobs_manufacturing, rep.jobs_service = _mfg, _svc
    try:
        _employed = sum(int(getattr(b, "employed", 0) or 0)
                        for b in (getattr(state_after, "buildings", None) or ()))
        rep.unemployed = max(0, int(rep.population) - _employed)
    except Exception:
        rep.unemployed = 0
    rep.lat, rep.lon = _mean_location(buildings)
    rep.homes_large, rep.homes_medium, rep.homes_small = \
        homes_from_reports(design_reports or ())
    if df:
        rep.events.append(_ev(EVENT_STARVATION, df, "died of starvation"))
    if da:
        rep.events.append(_ev(EVENT_SUFFOCATION, da, "died from lack of air"))
    if births:
        rep.events.append(_ev(EVENT_BIRTHS, births, "new residents"))
    if rep.no_power:
        rep.events.append(_ev(EVENT_NO_POWER, 0, "no electricity"))
    _housing_note = _withheld_housing_note(rep)
    if _housing_note:
        rep.events.append(_ev(EVENT_HOUSING, rep.homes_small, _housing_note))
    if rep.service_penalty < 0:
        rep.events.append(_ev(EVENT_UNDERSERVED, -rep.service_penalty,
                              "city services short of demand"))
    return rep


def format_report_text(rep: CityReport) -> str:
    lines = [f"City report: {rep.name or ('0x%08x' % rep.city_auid)}"]
    net = rep.population - rep.population_before
    sign = "+" if net >= 0 else ""
    lines.append(f"Population {rep.population} ({sign}{net})  "
                 f"satisfaction {rep.satisfaction} "
                 f"({rep.satisfaction_delta:+d})")
    if rep.births:
        lines.append(f"  {rep.births} new resident(s)")
    if rep.deaths_food:
        lines.append(f"  {rep.deaths_food} starved (no food)")
    if rep.deaths_air:
        lines.append(f"  {rep.deaths_air} suffocated (no air)")
    if rep.no_power:
        lines.append("  no electricity")
    if rep.service_penalty < 0:
        lines.append("  city services short of demand")
    if rep.tribute:
        lines.append(f"  tribute paid: {rep.tribute:.0f}")
    return "\n".join(lines)


def is_noteworthy(rep: CityReport) -> bool:
    return bool(rep.deaths_total or rep.starving or rep.suffocating or rep.no_power)


import html as _html


def _row(label: str, value) -> str:
    return (f'<tr><td class="l">{_html.escape(str(label))}</td>'
            f'<td class="v">{_html.escape(str(value))}</td></tr>')


def format_report_html(rep: "CityReport") -> str:
    title = rep.name or ("City 0x%08x" % rep.city_auid)
    net = rep.population - rep.population_before
    net_s = ("+%d" % net) if net >= 0 else str(net)
    sat_s = "%+d" % rep.satisfaction_delta

    _homes_total = rep.homes_small + rep.homes_medium + rep.homes_large
    housing = ""
    if _homes_total:
        housing = _row("Homes", "%d  (small %d / medium %d / large %d)"
                       % (_homes_total, rep.homes_small, rep.homes_medium,
                          rep.homes_large))
    vitals = "".join([
        _row("Population", f"{rep.population}  ({net_s})"),
        _row("Satisfaction", f"{rep.satisfaction}  ({sat_s})"),
        _row("Meals served", rep.food_ate),
        housing,
    ])

    ev_rows = []
    if rep.births:
        ev_rows.append(f"<li>{rep.births} new resident(s) born</li>")
    if rep.deaths_food:
        ev_rows.append(f"<li>{rep.deaths_food} citizen(s) starved (no food)</li>")
    if rep.deaths_air:
        ev_rows.append(f"<li>{rep.deaths_air} citizen(s) suffocated (no air)</li>")
    if rep.no_power:
        ev_rows.append("<li>City has no electricity</li>")
    if rep.service_penalty < 0:
        if rep.services_wanted:
            for _ind, _nm, _short in rep.services_wanted:
                ev_rows.append("<li>%s wanted</li>" % _nm)
        else:
            ev_rows.append("<li>City services are short of demand</li>")
    if rep.housing_penalty < 0:
        ev_rows.append("<li>%d Homelessness Penalty. More homes needed.</li>"
                       % rep.housing_penalty)
    events_html = ("<ul>" + "".join(ev_rows) + "</ul>") if ev_rows else \
        "<p><i>No notable events this cycle.</i></p>"

    econ = "".join([
        _row("City treasury", f"{rep.treasury:,.0f}"),
        _row("Citizen bank", f"{rep.bank:,.0f}"),
        _row("Salaries paid", f"{rep.salaries_paid:,.0f}"),
        _row("Income tax", f"{rep.income_tax:,.0f}"),
        _row("Sales tax", f"{rep.sales_tax:,.0f}"),
        _row("Tribute paid", f"{rep.tribute:,.0f}"),
    ])
    produced = ""
    if rep.produced:
        items = "".join(_row(f"produced {k}", v) for k, v in sorted(rep.produced.items()))
        produced = f'<h3>Production</h3><table>{items}</table>'

    return (
        "<html><head><style>"
        "body{font-family:sans-serif;font-size:13px;}"
        "h2{margin:0 0 4px;} h3{margin:12px 0 2px;}"
        "table{border-collapse:collapse;} td{padding:1px 10px 1px 0;}"
        "td.l{color:#555;} td.v{font-weight:bold;}"
        "</style></head><body>"
        f"<h2>{_html.escape(title)} &mdash; City Report</h2>"
        f"<h3>Population</h3><table>{vitals}</table>"
        f"<h3>Events</h3>{events_html}"
        f"<h3>Treasury</h3><table>{econ}</table>"
        f"{produced}"
        "</body></html>"
    )


def report_from_dict(d: dict) -> "CityReport":
    fields = getattr(CityReport, "__dataclass_fields__", {})
    kw = {k: v for k, v in (d or {}).items() if k in fields}
    return CityReport(**kw)


def format_history_line(d: dict) -> str:
    pop = d.get("population", 0)
    df = d.get("deaths_food", 0); da = d.get("deaths_air", 0)
    births = d.get("births", 0); sat = d.get("satisfaction", 0)
    bits = [f"pop {pop}", f"sat {sat}"]
    if births:
        bits.append(f"+{births} born")
    if df:
        bits.append(f"{df} starved")
    if da:
        bits.append(f"{da} suffocated")
    return "  - " + ", ".join(bits)
