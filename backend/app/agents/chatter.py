"""A5 Ask: a quick chat answer about whatever page the person is on.

The asker's tools, in a quick mode: the light model chain, at most three
rounds, two to four sentences. What the question is about is first worked out
by simple rules (a mission named in it or open on the page, a step, the space
weather, a site) and those tools are called before the model sees anything, so
the grounding pool is never empty and the answer without a model is a real one:
built from the same tool results with the same sentences the other agents'
fallbacks use, and checked by the same guard.

``actions`` (links into the app) are built here from the tool calls and the
page, never by the model.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from app.agents import base, guards, tools
from app.agents.asker import SPEC as ASKER
from app.agents.base import AgentOutcome, AgentSpec, model_chain, run_agent
from app.agents.schemas import Status
from app.agents.tools import Session

SYSTEM = """\
You answer quick questions in a lunar mission planning app, about the page the
person is on: one of NASA's commercial Moon landings (CLPS) and its six steps
(Ready, Launch, Trip, Surface, Contact, Return), a landing site, a comparison of
sites, a scenario (a what-if worked out from assumed values), or the space
weather now.

Answer in two to four plain sentences. Fill `interpreted_as` with how you read
the question (which mission, step, site, scenario or dates), and `follow_ups`
with up to three short next questions the person might ask, each ending with a
question mark, in the same plain words and with no numbers in them. Do not
write links or paths: the app adds them.

Rules:
- Use ONLY numbers and dates that appear in tool results. Never calculate new
  ones.
- Give every duration in hours with its margin, copied from the tool's hours
  fields or its `in_words` phrase, for example "64 h ± 0.3 h". Never write
  seconds. Write "at least" where the tool does (the dates cut it short). Where
  a figure has no margin, say why, as the tool says.
- Say where a number comes from: worked out, published, entered by your team,
  or assumed in a scenario.
- Name missions, sites and scenarios by their names ("IM-3", "Connecting
  Ridge"), never by their ids.
- Never write a field name or anything with an underscore. Use these words:
  steps (not sections); Time in sunlight; Time in contact with Earth; Longest
  night (not darkness or dark period); Longest time without contact (not
  blackout); Longest time dark and out of contact; Time working alone (not
  autonomy); Battery time needed; Longest message wait (counting relays);
  Time a ground station can hear the lander; skyline (not horizon mask);
  margin, or "how sure" (not uncertainty); dates (not window); landing spot
  (a mission's target); launch opportunity; NASA's deep-space dishes (Deep
  Space Network); magnetic storm level (Kp); fast protons; X-ray flares.
- Never write these words: best, safest, recommended, score, likely, chance,
  overall rank.
- When a scenario is open (get_scenario was called), the answer is about that
  scenario: say so and name it in quotes. Give each assumed value with its
  label as the tool gives it (You, Published, Live or Default). A result in a
  scenario is worked out from those assumed values: say "worked out in this
  scenario". Never present a scenario value as the mission's record.
- When sites are compared, answer about the compared sites, say which one
  number they are ordered by, and when the tool says sites are too close to
  call, say so. A site whose rank is null has a place that cannot be stated
  (a value cut short by the dates, or a moment that cannot be timed): say so,
  and never call it first or last. A place in that order is not a verdict on
  the site.
- A step that says it is not worked out yet, or has no data, is an answer: say so.
- Never give a verdict: no go/no-go, "safe", readiness percentage, risk score or
  overall chance. Say what each number or rule shows; people decide.
- If the data cannot answer it, set status to "insufficient_data" and say what
  is missing. Do not guess.
- The prompt gives today's date. A date before it has passed: never call it
  upcoming or next, and go by each mission's status. Do not write today's date
  in the answer.
"""


class ChatAnswer(BaseModel):
    """What the model (or the rules, without one) writes. Links are added afterwards."""

    model_config = ConfigDict(extra="forbid")

    status: Status
    reason: str | None = None
    answer: str | None = Field(default=None, description="Two to four plain sentences.")
    interpreted_as: str | None = None
    follow_ups: list[str] = Field(default_factory=list, max_length=3)


#: The asker's tools, and what a page can hold that the asker does not read: when
#: the nights and the times without contact happen, what a scenario may assume,
#: and the scenario open on the page.
CHAT_TOOLS: tuple[str, ...] = (
    *ASKER.tool_names,
    "get_windows",
    "list_scenario_options",
    "get_scenario",
)

SPEC = AgentSpec(
    name="chatter",
    system_prompt=SYSTEM,
    tool_names=CHAT_TOOLS,
    output_model=ChatAnswer,
    max_rounds=3,
)

#: The hub's address for each step (``landing`` is shown as Surface).
SECTION_SLUG = {
    "ready": "ready",
    "launch": "launch",
    "launch_weather": "launch",
    "trip": "trip",
    "landing": "surface",
    "contact": "contact",
    "return": "return",
}
SECTION_LABEL = {
    "ready": "Ready",
    "launch": "Launch",
    "launch_weather": "Launch",
    "trip": "Trip",
    "landing": "Surface",
    "contact": "Contact",
    "return": "Return",
}
STATE_WORDS = {
    "available": "answered",
    "computing": "being worked out",
    "no_data": "no data",
    "needs_input": "needs input",
    "not_applicable": "does not apply",
}
_SECTION_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (s, re.compile(p, re.IGNORECASE))
    for s, p in (
        ("ready", r"\bready\b|\breadiness\b|\brisks?\b|\bparts?\b|\bmilestones?\b"),
        ("launch", r"\blaunch\w*|\blift[- ]?off\b|\brocket\b|\bpad\b"),
        ("trip", r"\btrip\b|\btransit\b|\bcruise\b|\bburns?\b|\btrajector\w+|\bradiation\b"),
        (
            "contact",
            r"\bcontact\b|\bdsn\b|\bdeep[- ]space (?:network|dishes)\b|\bground stations?\b|"
            r"\brelays?\b|\bradio\b|\bcomms?\b|\bmessages?\b",
        ),
        ("return", r"\breturn\b|\bbooster\b|\brecovery\b|\bsplash\w*"),
        ("landing", r"\bsurface\b|\blanding\b|\bsunlight\b|\bsunlit\b|\bdark\w*|\bnight\b"),
    )
)
_SPACE_WEATHER = re.compile(
    r"space weather|\bsolar\b|\bflares?\b|\bkp\b|geomagnetic|\bprotons?\b|\bcmes?\b|"
    r"\bstorms?\b|\bsun now\b",
    re.IGNORECASE,
)
_SITE_WORDS = re.compile(
    r"\bsites?\b|\bsunlight\b|\bsunlit\b|\bdark\w*\b|\bskyline\b|\bhorizon\b|\bearth\b",
    re.IGNORECASE,
)
#: A question about when something happens: the stretches themselves (get_windows).
_WHEN = re.compile(r"\bwhen\b|\bstarts?\b|\bbegins?\b|\bwhat time\b|\bwhich days?\b", re.I)
#: A question about what a scenario assumes, rather than what it worked out.
_ASSUMES = re.compile(r"\bassum\w*|\bcome from\b|\bbased on\b|\bwhat if\b", re.I)
#: The one number a comparison is ordered by, from the question's words; the most
#: specific first ("without contact" before "contact").
_MEASURES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (k, re.compile(p, re.IGNORECASE))
    for k, p in (
        ("longest_blackout_s", r"without contact|out of contact|lose contact|\bblackouts?\b"),
        ("longest_dark_s", r"\bnights?\b|\bdark\w*"),
        ("earth_contact_s", r"\bcontact\b|\bearth\b"),
        ("sunlit_s", r"\bsun\w*|\blight\b"),
    )
)
#: The figures a site's numbers hold, by API name, in the glossary's words.
SITE_FIGURES: dict[str, str] = {
    "sunlit": "Time in sunlight",
    "sun_fraction_up": "Time in sunlight",
    "earth_contact": "Time in contact with Earth",
    "earth_fraction_up": "Time in contact with Earth",
    "longest_dark": "Longest night",
    "longest_blackout": "Longest time without contact",
    "worst_compound": "Longest time dark and out of contact",
    "required_autonomy": "Time working alone",
    "survival_needed": "Battery time needed",
}
#: The Compare page's `rank` address word for each number it can order by
#: (`frontend/src/screens/CompareScreen.tsx` RANK_PARAM).
COMPARE_RANK_PARAM: dict[str, str] = {
    "sunlit_s": "sunlight",
    "earth_contact_s": "earth",
    "longest_dark_s": "night",
    "longest_blackout_s": "blackout",
}
#: The figure a question is about, from its words (the most specific first).
_FIGURE_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (k, re.compile(p, re.IGNORECASE))
    for k, p in (
        ("required_autonomy", r"\balone\b|\bautonom\w*"),
        ("survival_needed", r"\bbattery\b"),
        ("worst_compound", r"dark and out of contact|dark and without contact"),
        ("longest_blackout", r"without contact|out of contact|\bblackouts?\b"),
        ("longest_dark", r"\bnights?\b|\bdark\w*"),
        ("earth_contact", r"\bcontact\b|\bearth\b"),
        ("sunlit", r"\bsun\w*|\blight\b"),
    )
)
#: The steps a scenario works out (Ready is never assumed).
SCENARIO_STEPS = frozenset({"launch", "trip", "landing", "contact", "return"})
#: Steps whose own answer get_mission_section reads (Surface is the site's numbers).
SECTION_TOOL_STEPS = frozenset({"ready", "launch", "trip", "contact", "return"})
#: Mission statuses with nothing flown yet: the questions about them look ahead.
NOT_FLOWN = frozenset({"planned", "cancelled", "reassigned"})
#: Most characters of one prefetched result shown in the prompt (the guard sees all of it).
PROMPT_RESULT_MAX = 6000
#: A scenario carries its assumptions, its steps and a result: give it more room.
PROMPT_RESULT_MAX_BY_TOOL = {"get_scenario": 10000, "compare_sites": 12000, "get_windows": 8000}


@dataclass
class Intent:
    """What the question was read as being about, by rules."""

    mission_id: str | None = None
    mission_name: str | None = None
    mission_status: str | None = None
    mission_site_id: str | None = None
    section: str | None = None
    site_id: str | None = None
    site_name: str | None = None
    space_weather: bool = False
    scenario_id: str | None = None
    scenario_name: str | None = None
    #: The page had a scenario open that could not be read: the answer is the record's.
    scenario_unread: bool = False
    compare_ids: list[str] = field(default_factory=list)
    compare_names: list[str] = field(default_factory=list)
    rank_by: str | None = None
    figure_key: str | None = None
    names: dict[str, str] = field(default_factory=dict)


def _word_re(name: str) -> re.Pattern[str]:
    body = re.escape(name).replace(r"\ ", r"[\s-]*").replace(r"\-", r"[\s-]*")
    return re.compile(rf"(?<![\w]){body}(?![\w])", re.IGNORECASE)


def section_of(question: str) -> str | None:
    for section, pat in _SECTION_WORDS:
        if pat.search(question):
            return section
    return None


def mission_named(question: str, missions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The mission the question names (its name or id), longest name first."""
    cands: list[tuple[int, dict[str, Any]]] = []
    for m in missions:
        for n in {str(m.get("name") or ""), str(m.get("mission_id") or "")}:
            if len(n) >= 3 and _word_re(n).search(question):
                cands.append((len(n), m))
    return max(cands, key=lambda c: c[0])[1] if cands else None


async def route(
    session: Session, question: str, ctx: dict[str, Any]
) -> tuple[Intent, list[tools.ToolCallLog]]:
    """Read the question by rules and fetch what it is about, as logged tool calls."""
    calls: list[tools.ToolCallLog] = []

    async def call(name: str, args: dict[str, Any]) -> tools.ToolCallLog:
        c = await tools.execute(session, name, args, len(calls) + 1)
        calls.append(c)
        return c

    figure = figure_of(ctx.get("figure_key"))
    # A figure asked about from its tile belongs to the step it is shown on.
    section = (
        (ctx.get("section") if figure and ctx.get("section") else None)
        or section_of(question)
        or ctx.get("section")
    )
    intent = Intent(section=section, figure_key=figure)
    dates = {k: str(ctx[k]) for k in ("start", "end") if ctx.get(k)}
    listing = await call("list_missions", {})
    missions = [m for m in (listing.result or {}).get("missions") or [] if isinstance(m, dict)]
    intent.names = {str(m["mission_id"]): str(m["name"]) for m in missions if m.get("mission_id")}
    named = mission_named(question, missions)
    if named is not None:
        intent.mission_id = str(named["mission_id"])
    elif ctx.get("mission_id") and str(ctx["mission_id"]) in intent.names:
        intent.mission_id = str(ctx["mission_id"])
    if intent.mission_id:
        intent.mission_name = intent.names.get(intent.mission_id)
        row = next((m for m in missions if m.get("mission_id") == intent.mission_id), {})
        intent.mission_status = str(row.get("status") or "") or None
        intent.mission_site_id = str(row.get("site_id") or "") or None
    intent.space_weather = bool(_SPACE_WEATHER.search(question))
    if intent.space_weather:
        await call("get_space_weather", {})

    # The scenario open on the page is what the answer is about (e7), unless the
    # question names another mission.
    scenario_id = ctx.get("scenario_id")
    if scenario_id and (named is None or intent.mission_id == ctx.get("mission_id")):
        args: dict[str, Any] = {"scenario_id": str(scenario_id)}
        if intent.section in SCENARIO_STEPS:
            args["section"] = intent.section
        read = await call("get_scenario", args)
        if not read.error and read.result:
            intent.scenario_id = str(scenario_id)
            intent.scenario_name = str(read.result.get("name") or "") or None
            mid = str(read.result.get("mission_id") or "")
            if not intent.mission_id and mid in intent.names:
                intent.mission_id, intent.mission_name = mid, intent.names[mid]
        else:
            intent.scenario_unread = True
    in_scenario = intent.scenario_id is not None and intent.section in SCENARIO_STEPS
    if intent.mission_id and not in_scenario:
        await call("get_mission_sections", {"mission_id": intent.mission_id})
        # A figure from a step's tile: that step's own answer holds it.
        if (
            figure
            and figure not in SITE_FIGURES
            and not intent.scenario_id
            and intent.section in SECTION_TOOL_STEPS
        ):
            await call(
                "get_mission_section", {"mission_id": intent.mission_id, "section": intent.section}
            )

    # Compare: the compared sites, by one number; the page's own site is only the
    # last one opened there, so it is not what the question is about.
    compare_ids = [str(s) for s in ctx.get("compare_ids") or [] if s]
    if compare_ids and not intent.mission_id and not intent.space_weather:
        intent.compare_ids = compare_ids
        intent.rank_by = measure_of(question) or ctx.get("rank_by") or "longest_dark_s"
        compared = await call(
            "compare_sites", {"site_ids": compare_ids, "rank_by": intent.rank_by, **dates}
        )
        intent.compare_names = [
            str(it["name"])
            for it in (compared.result or {}).get("items") or []
            if isinstance(it, dict) and it.get("name")
        ]

    site_id = None if intent.compare_ids else ctx.get("site_id")
    # A mission's Surface step is its landing spot's numbers (in a scenario, the
    # scenario's own Surface result holds them instead).
    from_mission = False
    if (
        not site_id
        and intent.mission_id
        and not intent.scenario_id
        and (intent.section == "landing" or (figure in SITE_FIGURES))
        and intent.mission_site_id
    ):
        site_id, from_mission = intent.mission_site_id, True
    if not site_id and not intent.mission_id and not intent.space_weather and not compare_ids:
        found = await call("search_sites", {"limit": 50})
        rows = [r for r in (found.result or {}).get("sites") or [] if isinstance(r, dict)]
        hits = [r for r in rows if r.get("name") and _word_re(str(r["name"])).search(question)]
        if hits:
            site_id = str(max(hits, key=lambda r: len(str(r["name"])))["site_id"])
    about_site = figure in SITE_FIGURES or bool(_SITE_WORDS.search(question))
    if site_id and (from_mission or not intent.mission_id or about_site):
        intent.site_id = str(site_id)
        site = await call("get_site", {"site_id": intent.site_id})
        if not site.error and site.result:
            intent.site_name = str(site.result.get("name") or "") or None
        window = {"site_id": intent.site_id, **dates}
        await call("get_metrics", window)
        if _WHEN.search(question):
            await call("get_windows", window)
    return intent, calls


def figure_of(key: Any) -> str | None:
    """The figure a tile asked about, by its API name: the last part of a path, without
    its unit or margin suffix ("data.longest_dark_s" -> "longest_dark")."""
    if not isinstance(key, str) or not key.strip():
        return None
    parts = [p for p in re.sub(r"\[\d*\]", "", key).split(".") if p]
    parts = [p for p in parts if p not in ("value", "pm", "lo", "hi", "factor")] or parts
    name = parts[-1] if parts else key
    for suffix in ("_tolerance_s", "_tolerance_h", "_tolerance", "_s", "_h", "_pct"):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def measure_of(question: str) -> str | None:
    """The one number a comparison question asks to order by, if its words say."""
    return next((k for k, pat in _MEASURES if pat.search(question)), None)


def figure_in(question: str) -> str | None:
    """The site figure a question is about, from its words."""
    return next((k for k, pat in _FIGURE_WORDS if pat.search(question)), None)


#: Figures a step's tiles show, in the words of their labels (`lib/fieldWords.ts`).
STEP_FIGURES: dict[str, str] = {
    "heard": "Time a ground station can hear the lander",
    "station_hears": "Time a ground station can hear the lander",
    "longest_unheard": "Longest time without contact",
    "longest_message_wait": "Longest message wait",
    "via_relay": "Time through a relay",
    "dark_and_unheard": "Time dark and out of contact at once",
    "sunlight": "Time in sunlight",
    "sunlight_after": "Sunlight after landing",
    "longest_shadow": "Longest time in shadow",
    "belt_hours": "Time in the radiation belts",
    "flight_days": "Flight time",
    "orbit_wait_days": "Wait in orbit around the Moon",
    "wave_height": "Wave height",
    "wind": "Wind speed",
}
_UNIT_SUFFIX = re.compile(r"_(?:m_s|km_s|mgy_d|mgy|nt|deg|km|m|days|min)$")


def figure_words(key: str) -> str:
    """A figure's name for the person: the glossary's words, never the API name."""
    bare = _UNIT_SUFFIX.sub("", key)
    return SITE_FIGURES.get(key) or STEP_FIGURES.get(bare) or bare.replace("_", " ")


# ---------------------------------------------------------------------------
# The answer without a model
# ---------------------------------------------------------------------------


def _pool(calls: list[tools.ToolCallLog], req: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"seq": 0, "tool": guards.USER_REQUEST_TOOL, "result": req},
        *(c.as_dict() for c in calls),
    ]


def _grounded(text: str, pool: list[dict[str, Any]]) -> bool:
    return guards.check({"answer": text}, pool).ok


def _value(q: Any) -> float | None:
    v = q.get("value") if isinstance(q, dict) else None
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def space_weather_sentences(result: dict[str, Any]) -> list[str]:
    """Space weather now in words, from the tool's own values; a missing one says why."""
    now = ((result.get("data") or {}).get("now")) or {}
    out: list[str] = []
    parts: list[str] = []
    kp = _value(now.get("kp"))
    if kp is not None:
        parts.append(f"magnetic storm level {kp:.1f} of 9 (Kp)")
    p10 = _value(now.get("proton_10mev_pfu"))
    if p10 is not None:
        parts.append(f"fast protons {p10:.2f} pfu")
    wind = _value(now.get("solar_wind_km_s"))
    if wind is not None:
        parts.append(f"solar wind {wind:.0f} km/s")
    xray = now.get("xray_class")
    if isinstance(xray, str) and xray:
        parts.append(f"X-ray flares class {xray}")
    if parts:
        out.append("Space weather now (NOAA): " + ", ".join(parts) + ".")
    else:
        why = (
            (now.get("kp") or {}).get("missing_reason") if isinstance(now.get("kp"), dict) else None
        )
        out.append(
            "No space weather reading is recorded yet"
            + (f": {str(why).rstrip('.')}." if why else ".")
        )
    alerts = [a for a in now.get("alerts") or [] if isinstance(a, str) and a]
    if alerts:
        out.append(f"NOAA's latest alert in the last day: {alerts[0].rstrip('.')}.")
    return out


def _label(row: dict[str, Any]) -> str:
    return SECTION_LABEL.get(str(row["section"]), str(row["section"]))


def _state(row: dict[str, Any]) -> str:
    return STATE_WORDS.get(str(row.get("state")), str(row.get("state")))


def mission_sentences(
    result: dict[str, Any], name: str, focus: str | None, pool: list[dict[str, Any]]
) -> list[str]:
    """A mission's steps in words: the one asked about first, with its own summary."""
    rows = [s for s in result.get("sections") or [] if isinstance(s, dict) and s.get("section")]
    if not rows:
        return []
    out: list[str] = []
    focus_row = next((s for s in rows if s["section"] == focus), None) if focus else None
    if focus_row is not None:
        label = SECTION_LABEL.get(focus_row["section"], focus_row["section"])
        summary = str(focus_row.get("summary") or "").strip().rstrip(".")
        line = f"{label} for {name}: {summary}." if summary else ""
        if not line or not _grounded(line, pool):
            state = STATE_WORDS.get(str(focus_row.get("state")), str(focus_row.get("state")))
            line = f"{label} for {name}: {state}."
        out.append(line)
    others = [s for s in rows if s is not focus_row]
    listed = "; ".join(f"{_label(s)} {_state(s)}" for s in others)
    if listed:
        out.append(
            f"{'The other steps' if focus_row is not None else f'The steps for {name}'}: {listed}."
        )
    if focus_row is None:
        for s in rows:
            if s.get("state") != "available" or len(out) >= 3:
                continue
            summary = str(s.get("summary") or "").strip().rstrip(".")
            line = f"{SECTION_LABEL.get(s['section'], s['section'])}: {summary}."
            if summary and _grounded(line, pool):
                out.append(line)
    return out


def _first_letter_down(label: str) -> str:
    return label[:1].lower() + label[1:]


def _soft_lower(text: str) -> str:
    """A sentence's first word in lower case after a colon, unless it is a name ("IM-2")."""
    return _first_letter_down(text) if text[:2].istitle() and text[1:2].islower() else text


#: The person's own values first when only a few assumptions are told.
_BASIS_ORDER = {"You": 0, "Live": 1, "Default": 2, "Published": 3}


def _joined(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


#: The order a site's numbers are told in, after the one asked about.
_SITE_ORDER = (
    "Longest night",
    "Longest time without contact",
    "Time in sunlight",
    "Time in contact with Earth",
)


def _told(label: str, phrase: str) -> str:
    """One figure in a list, as "longest night: 64 h ± 0.3 h" (or ": none (...)")."""
    return f"{_first_letter_down(label)}: {phrase}"


def _in_order(words: dict[str, Any], figure: str | None) -> list[str]:
    """The labels a site's numbers are told under: the one asked about first."""
    first = SITE_FIGURES.get(figure or "")
    return [lb for lb in dict.fromkeys([first, *_SITE_ORDER]) if lb and lb in words]


def site_sentences(result: dict[str, Any], figure: str | None) -> list[str]:
    """A site's numbers in hours with their margins, the one asked about first (R3)."""
    words = result.get("in_words")
    if not isinstance(words, dict) or not words:
        return []
    labels = _in_order(words, figure)
    if not labels:
        return []
    name = str(result.get("name") or "this site")
    dates = result.get("dates")
    where = f" at {name}" + (f", {dates}" if dates else "")
    out = [f"{labels[0]}{where}: {words[labels[0]]}, worked out."]
    rest = [_told(lb, words[lb]) for lb in labels[1:]]
    if rest:
        out.append(f"Also worked out there, {'; '.join(rest)}.")
    return out


def windows_sentences(result: dict[str, Any], figure: str | None) -> list[str]:
    """When the stretch asked about happens, as the windows tool words it."""
    sun, earth = tools._dict(result.get("sun")), tools._dict(result.get("earth"))
    both = result.get("longest_dark_and_out_of_contact")
    picks: list[tuple[str, Any]] = []
    if figure in ("worst_compound", "required_autonomy"):
        picks.append(("The longest time dark and out of contact", both))
    elif figure == "longest_blackout":
        picks.append(("The longest time without contact", earth.get("longest_down")))
    picks.append(("The longest night", sun.get("longest_down")))
    for lead, arc in picks:
        if isinstance(arc, dict) and arc.get("in_words"):
            return [f"{lead} is {arc['in_words']}."]
    return []


def _place(item: dict[str, Any]) -> str:
    """A compared site's place when the order cannot state it: the range, or why not."""
    if item.get("rank") is not None:
        return ""
    rr = item.get("rank_range")
    if isinstance(rr, list) and len(rr) == 2 and all(isinstance(x, int) for x in rr):
        return f" (somewhere from place {rr[0]} to {rr[1]} in this order)"
    return " (its place in this order cannot be stated)"


def compare_sentences(result: dict[str, Any]) -> list[str]:
    """Compared sites in the one order asked for, with their margins; ties said as such."""
    items = [i for i in result.get("items") or [] if isinstance(i, dict)]
    label = SITE_FIGURES.get(str(result.get("rank_by") or "")[:-2])
    if not items or not label:
        return []
    shown = [
        it
        for it in items
        if it.get("name") and isinstance(it.get("in_words"), dict) and label in it["in_words"]
    ]
    if not shown:
        return []
    listed = [f"{it['name']}, {it['in_words'][label]}{_place(it)}" for it in shown]
    order = _first_letter_down(str(result.get("ordered_by") or label))
    dates = result.get("dates")
    out = [f"Ordered by {order}{f' ({dates})' if dates else ''}: {'; '.join(listed)}."]
    if any(it.get("rank") is None for it in shown):
        out.append(
            "A place is not known exactly where a value is cut short by the dates or a "
            "moment cannot be timed."
        )
    for group in result.get("too_close_to_call") or []:
        if isinstance(group, list) and len(group) > 1:
            out.append(
                f"{_joined([str(g) for g in group])} are too close to call on this number: "
                "their margins overlap."
            )
    return out


def scenario_step_sentence(
    result: dict[str, Any], focus: str | None, figure: str | None = None
) -> str | None:
    """The step asked about, as the open scenario worked it out: the figure asked about
    when its tile named one, else the Surface numbers in hours, else the step's own
    summary, else how far the step got."""
    if focus not in SCENARIO_STEPS:
        return None
    label = SECTION_LABEL[focus]
    res = (result.get("results") or {}).get(label)
    data = res.get("data") if isinstance(res, dict) else None
    if figure and figure not in SITE_FIGURES and isinstance(res, dict):
        line = figure_sentence(res, figure, f"{label} in this scenario")
        if line:
            return line
    if isinstance(data, dict) and isinstance(data.get("in_words"), dict) and data["in_words"]:
        w = data["in_words"]
        told = "; ".join(_told(lb, w[lb]) for lb in _in_order(w, figure))
        dates = f", {data['dates']}" if data.get("dates") else ""
        return f"{label} in this scenario{dates}, worked out from its assumed values, {told}."
    summary = (result.get("summaries") or {}).get(label)
    if summary:
        return f"{label} in this scenario: {str(summary).rstrip('.')}."
    steps = [s for s in result.get("steps") or [] if isinstance(s, dict)]
    state = next((s for s in steps if s.get("step") == label), None)
    if state is None:
        return f"{label} is not one of the steps this scenario works out."
    detail = _soft_lower(str(state.get("detail") or "").strip().rstrip("."))
    return f"{label} in this scenario: {state.get('state')}" + (f", {detail}." if detail else ".")


def scenario_sentences(
    result: dict[str, Any], focus: str | None, question: str, figure: str | None = None
) -> list[str]:
    """The open scenario: what it is, what it assumes (with each value's label), and the
    step asked about, never told as the mission's record (e7)."""
    name = str(result.get("name") or "the open scenario")
    kind = "a ready-made what-if" if result.get("ready_made") else "a what-if"
    head = (
        f'This is about the scenario "{name}": {kind} worked out from assumed values, '
        "never the mission's record."
    )
    asked_assumptions = bool(_ASSUMES.search(question))
    rows = [
        a
        for a in result.get("assumptions") or []
        if isinstance(a, dict) and a.get("value") not in (None, "", [])
    ]
    if not asked_assumptions:
        # Not what was asked: the person's own values first, and only a few.
        rows = sorted(rows, key=lambda a: _BASIS_ORDER.get(str(a.get("basis")), 9))[:3]
    assumed = []
    for a in rows:
        src = f", {a['source']}" if a.get("source") and asked_assumptions else ""
        assumed.append(f"{a.get('label')} {a.get('value')} ({a.get('basis')}{src})")
    assumes = (
        (
            f"It assumes: {'; '.join(assumed)}."
            if asked_assumptions
            else f"Among its assumed values: {'; '.join(assumed)}."
        )
        if assumed
        else ""
    )
    step_line = scenario_step_sentence(result, focus, figure) or ""
    lines = [head, assumes, step_line] if asked_assumptions else [head, step_line, assumes]
    message = str(result.get("message") or "").strip().rstrip(".")
    # "Worked out" alone says nothing a step line has not; "Worked out, except
    # launch, which could not be" does.
    if message and message.lower() != "worked out":
        lines.append(f"The scenario as a whole: {_soft_lower(message)}.")
    return [s for s in lines if s]


_PROVENANCE_WORDS = {
    "computed": "worked out",
    "published": "published",
    "entered": "entered by your team",
    "assumed": "assumed",
}


def _figure_quantity(obj: Any, figure: str) -> dict[str, Any] | None:
    """The quantity a step's answer holds under the figure's name, wherever it sits."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict) and "value" in v and "unit" in v and figure_of(k) == figure:
                return v
            found = _figure_quantity(v, figure)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _figure_quantity(v, figure)
            if found is not None:
                return found
    return None


def _num_text(v: float) -> str:
    return f"{v:.0f}" if abs(v) >= 100 else f"{v:.1f}" if abs(v) >= 10 else f"{v:.2f}"


def figure_sentence(result: dict[str, Any], figure: str, name: str) -> str | None:
    """One figure of a step, with its unit, margin and where it comes from."""
    q = _figure_quantity(result, figure)
    value = tools._number(q.get("value")) if q else None
    if q is None or value is None:
        return None
    unit = str(q.get("unit") or "")
    shown = (tools.hours_text(value) if unit == "h" else _num_text(value)) + (
        f" {unit}" if unit else ""
    )
    pm = tools._number(q.get("pm"))
    if pm is not None and unit == "h":
        # One decimal of margin; below that no digit is written that no tool gave
        # (a margin in minutes would be a number worked out here).
        margin = f" ± {pm:.1f} h" if round(pm, 1) >= 0.1 else " ± less than a tenth of an hour"
    elif pm is not None:
        margin = f" ± {_num_text(pm)}" + (f" {unit}" if unit else "")
    elif q.get("no_margin_reason"):
        margin = f" ({str(q['no_margin_reason']).rstrip('.')})"
    else:
        margin = ""
    source = _PROVENANCE_WORDS.get(str(q.get("provenance")), str(q.get("provenance") or ""))
    return f"{figure_words(figure)} for {name}: {shown}{margin}" + (
        f", {source}." if source else "."
    )


def deterministic_answer(
    calls: list[tools.ToolCallLog], reason: str, req: dict[str, Any]
) -> dict[str, Any]:
    """The answer from the tool results alone, in the chat's contract (no model)."""
    pool = _pool(calls, req)
    names: dict[str, str] = {}
    statuses: dict[str, str] = {}
    for c in calls:
        if c.tool == "list_missions" and not c.error:
            for m in (c.result or {}).get("missions") or []:
                if isinstance(m, dict) and m.get("mission_id"):
                    names[str(m["mission_id"])] = str(m.get("name") or m["mission_id"])
                    statuses[str(m["mission_id"])] = str(m.get("status") or "")
    ctx = tools._dict(req.get("context"))
    question = str(req.get("question") or "")
    focus = req.get("section")
    figure = figure_of(ctx.get("figure_key")) or figure_in(question)
    weather: list[str] = []
    scenario: list[str] = []
    compared: list[str] = []
    mission: list[str] = []
    site: list[str] = []
    about: list[str] = []
    site_name: str | None = None
    # A step the open scenario covers is told from the scenario, not the record.
    in_scenario = focus in SCENARIO_STEPS and any(
        c.tool == "get_scenario" and not c.error for c in calls
    )
    if any(c.tool == "get_scenario" and c.error for c in calls) and not in_scenario:
        # The page's hatch says a scenario is open; the answer must not pass the record
        # off as it (e7).
        scenario.append(
            "The scenario open on the page could not be read, so this answer is from the "
            "mission's record."
        )
    for c in calls:
        if c.error:
            continue
        r = c.result or {}
        if c.tool == "get_scenario":
            scenario += scenario_sentences(r, focus, question, figure)
            owner = names.get(str(r.get("mission_id")))
            about.append(
                f"{owner + ', ' if owner else ''}"
                + (f"{SECTION_LABEL[focus]}, " if focus in SECTION_LABEL else "")
                + f'in the scenario "{r.get("name")}"'
            )
        elif c.tool == "get_mission_sections" and not in_scenario:
            mid = str(r.get("mission_id"))
            name = names.get(mid, "this mission")
            mission += mission_sentences(r, name, focus, pool)
            about.append(name + (f", {SECTION_LABEL[focus]}" if focus in SECTION_LABEL else ""))
        elif c.tool == "get_mission_section" and figure:
            line = figure_sentence(r, figure, names.get(str(r.get("mission_id")), "this mission"))
            if line:
                mission.insert(0, line)
        elif c.tool == "get_space_weather":
            weather += space_weather_sentences(r)
            about.append("the space weather now")
        elif c.tool == "compare_sites":
            compared += compare_sentences(r)
            shown = [str(i.get("name")) for i in r.get("items") or [] if i.get("name")]
            if shown:
                about.append(f"comparing {_joined(shown)}")
        elif c.tool == "get_metrics":
            site += site_sentences(r, figure)
            site_name = site_name or (str(r["name"]) if r.get("name") else None)
        elif c.tool == "get_windows":
            site[1:1] = windows_sentences(r, figure)
        elif c.tool == "get_horizon_profile":
            top, bearing = r.get("max_el_deg"), r.get("max_el_bearing_deg")
            if isinstance(top, int | float) and isinstance(bearing, int | float):
                site.append(
                    f"The skyline is highest at {top:.2f} degrees, at a bearing of "
                    f"{bearing:.0f} degrees."
                )
        elif c.tool == "search_sites":
            found = [str(row.get("name")) for row in r.get("sites") or [] if row.get("name")]
            if found and not site:
                site.append("The search found: " + ", ".join(found) + ".")
        elif c.tool == "get_site" and r.get("name"):
            site_name = site_name or str(r["name"])
    if site_name:
        about.append(site_name)
    site_first = figure in SITE_FIGURES or focus == "landing" or not mission
    sentences = [
        *weather,
        *scenario,
        *compared,
        *(site + mission if site_first else mission + site),
    ]
    sentences = [s for s in sentences if _grounded(s, pool)][:4]
    if not sentences:
        return {
            "status": "insufficient_data",
            "reason": (
                f"{reason} Nothing in the question or on this page matched a mission, a site "
                "or the space weather in the data, so there is nothing to answer from."
            ).strip(),
            "answer": None,
            "interpreted_as": "Read by simple rules: no mission, site or space weather matched.",
            "follow_ups": [
                "Which missions land near the south pole?",
                "What is the space weather now?",
            ],
        }
    subjects = [a for a in dict.fromkeys(about) if a and a.strip()]
    interpreted = (
        "Read by simple rules (the written answer is unavailable): about "
        + "; ".join(subjects)
        + "."
    )
    # Nothing named (asked from Home, say): no "about ." with an empty subject.
    if not subjects or not _grounded(interpreted, pool):
        interpreted = "Read by simple rules (the written answer is unavailable)."
    return {
        "status": "ok",
        "reason": reason,
        "answer": " ".join(sentences),
        "interpreted_as": interpreted,
        "follow_ups": [
            f
            for f in follow_ups(
                names,
                req,
                status=statuses.get(str(req.get("mission_id"))),
                scenario=bool(scenario),
                site=bool(site),
                compare=bool(compared),
            )
            if _grounded(f, pool)
        ][:3],
    }


def follow_ups(
    names: dict[str, str],
    req: dict[str, Any],
    *,
    status: str | None = None,
    scenario: bool = False,
    site: bool = False,
    compare: bool = False,
) -> list[str]:
    """Next questions in the glossary's words, with no number in them; a flown mission
    gets none about its future."""
    if scenario:
        return [
            "What does this scenario assume, and where does each value come from?",
            "Which steps did this scenario work out, and which not?",
            "What does the mission's record say instead?",
        ]
    if compare:
        return [
            "Which of these keeps contact with Earth longest?",
            "Which of these has the shortest longest night?",
            "Why are some too close to call?",
        ]
    mid = req.get("mission_id")
    name = names.get(str(mid)) if mid else None
    if name and status not in ("cancelled", "reassigned"):
        asked = req.get("section")
        flown = status is not None and status not in NOT_FLOWN
        dishes = "NASA's deep-space dishes (Deep Space Network)"
        options = [
            (
                "launch",
                f"When did {name} launch?"
                if flown
                else f"When are {name}'s next launch opportunities?",
            ),
            (
                "contact",
                f"How long could {dishes} hear {name}?"
                if flown
                else f"When can {dishes} hear {name}?",
            ),
            (
                "landing",
                f"How much sunlight did {name} have on the surface?"
                if flown
                else f"How much sunlight would {name} get on the surface?",
            ),
            (
                "trip",
                f"How long did {name}'s trip take?"
                if flown
                else f"What does {name} go through on the way?",
            ),
        ]
        return [q for s, q in options if s != asked]
    if site:
        return [
            "What blocks the Sun here?",
            "How long must a lander work alone here?",
            "How sure are these numbers?",
        ]
    return ["Which missions are planned next?", "What is the space weather now?"]


base.FALLBACKS[ChatAnswer.__name__] = deterministic_answer


# ---------------------------------------------------------------------------
# Links into the app (built here, never by the model)
# ---------------------------------------------------------------------------


def actions(
    calls: list[tools.ToolCallLog], ctx: dict[str, Any], intent: Intent
) -> list[dict[str, str]]:
    """Up to three in-app places holding the full answer: from the tools called and the page.

    Every label is a name ("IM-2", "Connecting Ridge"), never an id (e1): a place
    whose name no tool gave is left out rather than shown as "mission-im-2".
    """
    out: list[dict[str, str]] = []
    names = dict(intent.names)
    statuses: dict[str, str] = {}
    site_names: dict[str, str] = {}
    scenario: dict[str, Any] | None = None
    for c in calls:
        if c.error:
            continue
        r = c.result or {}
        if c.tool == "list_missions":
            for m in r.get("missions") or []:
                if isinstance(m, dict) and m.get("mission_id") and m.get("name"):
                    names.setdefault(str(m["mission_id"]), str(m["name"]))
                    statuses[str(m["mission_id"])] = str(m.get("status") or "")
        if c.tool in ("get_site", "get_metrics", "get_windows") and r.get("name"):
            site_names[str(r.get("site_id"))] = str(r["name"])
        if c.tool == "compare_sites":
            for it in r.get("items") or []:
                if isinstance(it, dict) and it.get("name"):
                    site_names[str(it.get("site_id"))] = str(it["name"])
        if c.tool == "search_sites":
            for row in r.get("sites") or []:
                if isinstance(row, dict) and row.get("name"):
                    site_names[str(row.get("site_id"))] = str(row["name"])
        if c.tool == "get_scenario" and r.get("scenario_id"):
            scenario = r

    def add(label: str | None, href: str) -> None:
        if label and href not in {a["href"] for a in out}:
            out.append({"label": label, "href": href})

    def mission_href(mid: str, section: str | None = None, scenario_id: str | None = None) -> str:
        href = f"/missions/{quote(mid, safe='')}"
        if section in SECTION_SLUG:
            href += f"/{SECTION_SLUG[section]}"
        return href + (f"?scenario={quote(scenario_id, safe='')}" if scenario_id else "")

    if scenario is not None:
        mid = str(scenario.get("mission_id") or "")
        covered = [s for s in scenario.get("step_ids") or [] if s in SCENARIO_STEPS]
        step = intent.section if intent.section in covered else (covered[0] if covered else None)
        if mid and names.get(mid) and step:
            add(
                f"{names[mid]} · {SECTION_LABEL[step]} in this scenario",
                mission_href(mid, step, str(scenario["scenario_id"])),
            )
    for c in calls:
        if c.error:
            continue
        if c.tool in ("get_mission_section", "get_mission_sections"):
            mid = str(c.args.get("mission_id") or "")
            name = names.get(mid)
            if not mid or not name:
                continue
            section = c.args.get("section") or intent.section
            if section in SECTION_SLUG:
                add(f"{name} · {SECTION_LABEL[section]}", mission_href(mid, section))
            add(name, mission_href(mid))
        elif c.tool == "get_space_weather":
            # The open mission's Launch step has the row; else Home's Live block (e6).
            mid = intent.mission_id or ""
            if names.get(mid) and statuses.get(mid) == "planned":
                add(f"{names[mid]} · Launch: space weather now", mission_href(mid, "launch"))
            else:
                add("Space weather now", "/home#home-live")
        elif c.tool == "compare_sites":
            # The Compare page reads its sites and its order from the address.
            ids = [str(s) for s in c.args.get("site_ids") or [] if s]
            rank = str(c.args.get("rank_by") or "longest_dark_s")
            query = f"?sites={quote(','.join(ids), safe=',')}" if ids else ""
            if rank in COMPARE_RANK_PARAM:
                query += f"{'&' if query else '?'}rank={COMPARE_RANK_PARAM[rank]}"
            label = SITE_FIGURES.get(rank[:-2])
            by = f"Compare by {_first_letter_down(label)}" if label else "Compare"
            add(by, f"/compare{query}")
        elif c.tool in ("get_site", "get_metrics", "get_horizon_profile", "get_windows"):
            sid = str(c.args.get("site_id") or "")
            if sid:
                add(site_names.get(sid), f"/site?site={quote(sid, safe='')}")
    if not out and ctx.get("mission_id"):
        mid = str(ctx["mission_id"])
        add(names.get(mid), mission_href(mid))
    return out[:3]


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _prompt(
    messages: list[dict[str, Any]],
    ctx: dict[str, Any],
    intent: Intent,
    calls: list[tools.ToolCallLog],
    today: str | None = None,
) -> str:
    where = [f"page {ctx.get('path') or 'unknown'}"]
    if intent.mission_id:
        where.append(f"mission {intent.mission_name or intent.mission_id} (id {intent.mission_id})")
    # A step belongs to a mission: on a site or Compare page, "night" or "contact"
    # in the question names a number, not a step.
    if intent.section and (intent.mission_id or intent.scenario_id):
        where.append(f"step {SECTION_LABEL.get(intent.section, intent.section)}")
    if intent.scenario_id:
        where.append(
            f'the scenario "{intent.scenario_name or "open on the page"}" is open (id '
            f"{intent.scenario_id}): answer about this scenario, say so, and name it"
        )
    elif intent.scenario_unread:
        where.append(
            "a scenario is open on the page but could not be read: answer from the "
            "mission's record and say so"
        )
    if intent.site_id:
        where.append(f"site {intent.site_name or 'on the page'} (id {intent.site_id})")
    if intent.compare_ids:
        order = tools.ORDER_WORDS.get(intent.rank_by or "", intent.rank_by or "")
        compared = _joined(intent.compare_names) if intent.compare_names else "the sites"
        where.append(
            f"comparing {compared} (ids {', '.join(intent.compare_ids)}), ordered by "
            f"{_first_letter_down(order)}: answer about these sites"
        )
    if intent.figure_key:
        where.append(
            f'asked about one figure from its tile: "{figure_words(intent.figure_key)}"; '
            "answer about that figure first, with its margin"
        )
    if ctx.get("start") or ctx.get("end"):
        where.append(f"dates {ctx.get('start') or '…'} to {ctx.get('end') or '…'}")
    talk = "\n".join(
        f"{'Person' if m['role'] == 'user' else 'You'}: {m['text']}" for m in messages[:-1]
    )

    def shown(c: tools.ToolCallLog) -> str:
        # Unescaped, so the model reads "±" as written and copies it.
        cap = PROMPT_RESULT_MAX_BY_TOOL.get(c.tool, PROMPT_RESULT_MAX)
        return json.dumps(c.result, default=str, ensure_ascii=False)[:cap]

    facts = "\n".join(f"[{c.seq}] {c.tool}({json.dumps(c.args)}) -> {shown(c)}" for c in calls)
    return (
        (f"Today is {today} (UTC).\n" if today else "")
        + f"Where the person is: {'; '.join(where)}.\n"
        + (f"Conversation so far, oldest first:\n{talk}\n" if talk else "")
        + f"Question: {messages[-1]['text']}\n\n"
        f"Already retrieved:\n{facts}\n\n"
        "Answer in two to four sentences."
    )


def result_of(outcome: AgentOutcome, ctx: dict[str, Any], intent: Intent) -> dict[str, Any] | None:
    """The contract's ``ChatResult`` from the agent's answer, with the app's links added."""
    r = outcome.result
    if r is None:
        return None
    answer = (r.get("answer") or "").strip() or (r.get("reason") or "").strip()
    return {
        "answer": answer or "This cannot be answered from the data here.",
        "interpreted_as": (r.get("interpreted_as") or "").strip()
        or "How the question was read was not given.",
        "follow_ups": [str(f) for f in r.get("follow_ups") or []][:3],
        "actions": actions(outcome.tool_calls, ctx, intent),
    }


async def chat(
    session: Session, messages: list[dict[str, Any]], context: dict[str, Any] | None
) -> AgentOutcome:
    """One quick answer. ``outcome.result`` is the contract's ``ChatResult`` (or None)."""
    ctx = dict(context or {})
    question = str(messages[-1]["text"])
    intent, prefetched = await route(session, question, ctx)
    # Only the person's own words may be quoted: an earlier answer of ours is not a
    # source, so the numbers in it must come from this run's tools again.
    request = {
        "question": question,
        "earlier_questions": [str(m["text"]) for m in messages[:-1] if m["role"] == "user"],
        "context": ctx,
        "mission_id": intent.mission_id,
        "section": intent.section,
    }
    spec = replace(SPEC, models=model_chain(light=True))
    outcome = await run_agent(
        session,
        spec,
        _prompt(messages[-12:], ctx, intent, prefetched, datetime.now(UTC).date().isoformat()),
        request,
        prefetched=prefetched,
    )
    outcome.result = result_of(outcome, ctx, intent)
    return outcome
