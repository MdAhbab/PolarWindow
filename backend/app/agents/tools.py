"""The only place an agent touches the system.

Twelve tools, each with a typed argument model and a JSON schema: six over the
sites (the brief's), four over the missions' sections (ADR-6, amended), whose
results are cut to at most 200 numbers (``compact.py``), and two over scenarios
(what one may assume, and one scenario read back). Durations come in hours
with their margins beside the seconds, and in words (R3). Agents cannot
reach a service or a repository directly -- an import-linter contract forbids it
-- so this module is the complete, auditable surface area of what an LLM can do
here. It reads; nothing in it writes, and it never queues a computation: a
section that is not worked out yet says so (``job_service.read_only``).

Arguments are validated by pydantic before anything runs. A model that emits
``site_id="'; DROP TABLE sites"`` fails the argument model and never reaches a
query; the failure is recorded on the run rather than raised, so the agent can
recover by calling the tool correctly.

Every result is JSON-serialisable and every numeric leaf is flattened at call
time into the grounding pool (see ``guards.py``). That means the guard's notion
of "what the tools said" is exactly what this module returned -- not a summary
of it, and not the model's recollection of it.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import orjson
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.compact import compact
from app.agents.schema_convert import tool_parameters
from app.config import get_settings
from app.core.metrics import METRIC_KEYS
from app.db.repositories.missions import MissionRepository
from app.db.repositories.scenarios import ScenarioRepository
from app.services import (
    compare_service,
    contact_service,
    job_service,
    launch_service,
    mission_service,
    ready_service,
    return_service,
    scenario_service,
    sections_service,
    site_service,
    space_weather_service,
    trip_service,
    weather_service,
)

#: The database handle agents carry through to their tools.
#:
#: The agent modules name this alias rather than SQLAlchemy's type, so the only
#: agent module that knows a database exists is this one -- which an import
#: contract enforces. An agent never calls a method on it; it hands it here.
Session = AsyncSession


# ---------------------------------------------------------------------------
# Argument models
# ---------------------------------------------------------------------------


class GetSiteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str = Field(description="Site slug, e.g. 'connecting-ridge'.")


class WindowArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str
    start: str | None = Field(
        default=None, description="ISO 8601 UTC. Omit to use the reference window."
    )
    end: str | None = None


class HorizonArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, description="Substring of the name or region.")
    region: str | None = None
    lat_min: float | None = Field(default=None, ge=-90, le=0)
    lat_max: float | None = Field(default=None, ge=-90, le=0)
    min_sun_fraction: float | None = Field(default=None, ge=0, le=1)
    max_longest_dark_s: float | None = Field(default=None, ge=0)
    kind: Literal["candidate", "mission_target", "all"] = Field(
        default="all",
        description="Derived candidate sites, CLPS mission targets, or both.",
    )
    has_mission: bool | None = Field(
        default=None, description="Only sites that stand for a CLPS mission's target."
    )
    mission_status: list[str] | None = Field(
        default=None,
        description="Mission statuses: planned, in_transit, operating, completed, "
        "partial_success, landing_failed, lost_before_landing, cancelled, reassigned.",
    )
    provider: str | None = Field(
        default=None, description="CLPS provider, e.g. 'Firefly Aerospace'."
    )
    payload_type: list[str] | None = Field(
        default=None,
        description="Instrument types carried by the mission: volatiles, geology_geophysics, "
        "heat_flow, radiation_space_weather, exosphere_dust, imaging, landing_navigation, "
        "communications, laser_retroreflector, rover_mobility, technology_demo, other.",
    )
    limit: int = Field(default=20, ge=1, le=50)


class CompareArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_ids: list[str] = Field(min_length=1, max_length=8)
    start: str | None = None
    end: str | None = None
    rank_by: str = Field(default="longest_dark_s")


class ListMissionsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(
        default=None, description="Substring of the mission's name, lander or provider."
    )
    status: list[str] | None = Field(
        default=None,
        description="Mission statuses: planned, in_transit, operating, completed, "
        "partial_success, landing_failed, lost_before_landing, cancelled, reassigned.",
    )


class MissionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_id: str = Field(description="Mission id from list_missions, e.g. 'im-2'.")


Section = Literal["ready", "launch", "launch_weather", "trip", "contact", "return"]


class SectionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_id: str = Field(description="Mission id from list_missions, e.g. 'im-2'.")
    section: Section = Field(
        description="ready: readiness items, milestones, risks. launch: the flown launch or "
        "the launch opportunities. launch_weather: each launch weather rule at the next "
        "opportunity (or the flown launch). trip: distance, shadow, burns, correction "
        "budget, radiation along the way. contact: when the Deep Space Network and relays "
        "can hear the lander. return: where the booster comes down; any capsule."
    )
    opportunity: str | None = Field(
        default=None, description="launch_weather only: an opportunity id from launch."
    )


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioOptionsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_id: str = Field(description="Mission id, e.g. 'im-3'.")


ScenarioStep = Literal["launch", "trip", "landing", "contact", "return"]


class ScenarioArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(
        max_length=64, description="The scenario open on the page, e.g. 'sc-6e203e416683'."
    )
    section: ScenarioStep | None = Field(
        default=None,
        description="Only this step's results (landing is the Surface step); omit for every "
        "step the scenario worked out.",
    )


# ---------------------------------------------------------------------------
# Declarations handed to the model
# ---------------------------------------------------------------------------

TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "get_site",
        "description": (
            "Coordinates, elevation, provenance and the coarse four numbers for one "
            "site. Use this first when the user names a site."
        ),
        "parameters": tool_parameters(GetSiteArgs.model_json_schema()),
    },
    {
        "name": "get_metrics",
        "description": (
            "The four key numbers for one site over some dates: time in sunlight, time "
            "in contact with Earth, the longest night and the longest time without "
            "contact, plus the time the lander must work alone. Each duration is given "
            "in seconds and in hours with its margin (`*_h`, `*_tolerance_h`) and as a "
            "phrase in `in_words`; quote the hours, never the seconds."
        ),
        "parameters": tool_parameters(WindowArgs.model_json_schema()),
    },
    {
        "name": "get_windows",
        "description": (
            "When the nights and the times without contact happen at one site: the "
            "longest stretches with their start and end in words and their margins, "
            "the bearing of the terrain doing the blocking, and the longest time dark "
            "and out of contact at once. Durations in hours with their margins."
        ),
        "parameters": tool_parameters(WindowArgs.model_json_schema()),
    },
    {
        "name": "get_horizon_profile",
        "description": (
            "The site's skyline: the highest and mean horizon elevation, the bearing "
            "of the worst blocker, and a coarse azimuth profile."
        ),
        "parameters": tool_parameters(HorizonArgs.model_json_schema()),
    },
    {
        "name": "search_sites",
        "description": (
            "Find sites by name, region, latitude band, coarse metric thresholds, or by "
            "the CLPS missions that target them (status, provider, payload type). "
            "Mission targets are sites too. Metric filters use the reference window."
        ),
        "parameters": tool_parameters(SearchArgs.model_json_schema()),
    },
    {
        "name": "compare_sites",
        "description": (
            "Order up to eight sites over the same dates by one of the four numbers. "
            "Each item has its name, its four numbers in hours with their margins "
            "(`in_words`), and a place in that one order, or rank=null with a "
            "rank_range when a lower-bound value or an untimeable edge makes its place "
            "unknowable. `too_close_to_call` names the sites whose margins overlap. "
            "Never call a site best and never give an overall rank."
        ),
        "parameters": tool_parameters(CompareArgs.model_json_schema()),
    },
    {
        "name": "list_missions",
        "description": (
            "The CLPS missions: id, name, provider, lander, status, target site and "
            "published launch and landing dates. A date is given only as precisely as "
            "it was published: '2026' is a year, not a day. Use it to find a mission's id."
        ),
        "parameters": tool_parameters(ListMissionsArgs.model_json_schema()),
    },
    {
        "name": "get_mission_sections",
        "description": (
            "For one mission, each section (ready, launch, trip, landing, contact, return): "
            "whether it is available, being worked out or has no data, and in words what "
            "it shows."
        ),
        "parameters": tool_parameters(MissionArgs.model_json_schema()),
    },
    {
        "name": "get_mission_section",
        "description": (
            "One section of one mission as the page shows it, cut to at most 200 numbers: "
            "each value with its unit, provenance and ± or the reason it has none. "
            "`left_out` says what was cut (plot series, the tail of long lists). A section "
            "not worked out yet says so and is not started from here."
        ),
        "parameters": tool_parameters(SectionArgs.model_json_schema()),
    },
    {
        "name": "list_scenario_options",
        "description": (
            "For one mission: today's date, the launch vehicles, launch pads, relays and "
            "transfer types a scenario can assume (id and name), the next 18 months with "
            "their first and last days, and what the mission's record already says. Use "
            "only these ids and dates when reading a what-if prompt."
        ),
        "parameters": tool_parameters(ScenarioOptionsArgs.model_json_schema()),
    },
    {
        "name": "get_scenario",
        "description": (
            "One scenario: a what-if worked out from assumed values, never the mission's "
            "record. Its name, each assumed value with its label (You, Published, Live or "
            "Default) and where it comes from, how far each step got, and the results of "
            "the steps it worked out, each cut to at most 200 numbers; durations in hours "
            "with their margins."
        ),
        "parameters": tool_parameters(ScenarioArgs.model_json_schema()),
    },
    {
        "name": "get_space_weather",
        "description": (
            "Space weather now: Kp, protons above 10 and 100 MeV, X-ray class, solar wind, "
            "SWPC's alerts and three-day outlook, recent CMEs, flares and particle events, "
            "each with its age or the reason it is missing."
        ),
        # No parameters: Gemini refuses an OBJECT schema with no properties.
    },
]

TOOL_NAMES: frozenset[str] = frozenset(d["name"] for d in TOOL_DECLARATIONS)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


@dataclass
class ToolCallLog:
    seq: int
    tool: str
    args: dict[str, Any]
    result: dict[str, Any] | None = None
    numbers: list[float] = field(default_factory=list)
    latency_ms: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "tool": self.tool,
            "args": self.args,
            "result": self.result,
            "numbers": self.numbers,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


def _window(args: WindowArgs | CompareArgs) -> tuple[datetime, datetime]:
    s = get_settings()
    start = (
        datetime.fromisoformat(args.start.replace("Z", "+00:00"))
        if args.start
        else s.reference_window_start
    )
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    end = (
        datetime.fromisoformat(args.end.replace("Z", "+00:00"))
        if args.end
        else start + timedelta(days=s.reference_window_days)
    )
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return start, end


def published_when(key: str, block: dict[str, Any] | None) -> dict[str, Any]:
    """A published date for the AI, cut to the precision it was published at.

    The record stores "late 2026" as 2026-01-01 with precision "year". Handing the
    model the stored day lets it say "on 2026-01-01": a date nobody published. So a
    year is given as "2026", a month as "2026-03", a quarter as "2026-Q1", with the
    words as published beside it; only a date known to the day keeps its day.
    """
    b = block or {}
    date = b.get("date")
    if not isinstance(date, str) or len(date) < 10:
        return {key: None}
    precision = b.get("precision")
    if precision == "year":
        shown = date[:4]
    elif precision == "month":
        shown = date[:7]
    elif precision == "quarter":
        shown = f"{date[:4]}-Q{(int(date[5:7]) - 1) // 3 + 1}"
    else:
        return {key: date}
    out: dict[str, Any] = {key: shown, f"{key}_precision": precision}
    if b.get("as_published"):
        out[f"{key}_as_published"] = b["as_published"]
    return out


def _trim(payload: dict[str, Any], keep: tuple[str, ...]) -> dict[str, Any]:
    """Return only the fields an agent should reason over.

    Not merely a size optimisation. Handing a model 2,835 raw samples invites it
    to compute its own totals, and a derived total is ungrounded by construction
    -- the guard would reject it and the run would burn its retry. Giving the
    model finished numbers and nothing to divide is what keeps grounding
    achievable rather than adversarial.
    """
    return {k: payload[k] for k in keep if k in payload}


#: What an agent sees of a site's reference summary: the four numbers, their
#: fractions, and the flags that say when a gap is only a lower bound. Nothing
#: else -- every extra numeric leaf widens the pool the grounding guard matches
#: claims against, and a wide pool grounds almost any two-digit integer (D23).
SUMMARY_KEYS: tuple[str, ...] = (
    "sunlit_s",
    "earth_contact_s",
    "longest_dark_s",
    "longest_blackout_s",
    "sun_fraction_up",
    "earth_fraction_up",
    "longest_dark_open",
    "longest_blackout_open",
)


def _summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if summary is None else _trim(summary, SUMMARY_KEYS)


def _default(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    return str(obj)


def _plain(obj: Any) -> Any:
    """JSON types only, as the endpoint would send them (times as ISO strings)."""
    opts = orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NON_STR_KEYS | orjson.OPT_UTC_Z
    return orjson.loads(orjson.dumps(obj, default=_default, option=opts))


# ---------------------------------------------------------------------------
# Durations in hours, with their margins, and in words
# ---------------------------------------------------------------------------
#
# The site tools speak seconds; people read hours. An answer that quoted
# "105645.317 seconds" with no margin (R3) was grounded and still wrong for the
# person reading it. So every duration an agent may quote also comes in hours
# with its margin, as a field the guard matches and as a phrase in the
# glossary's words that the model can copy. The seconds stay beside them: the
# other agents and the measurement-only answers read them.

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

#: The four numbers in the glossary's words: the seconds key, the label, the
#: tolerance key, the key saying the dates cut it short, the grazing key, and
#: the body whose rising and setting time it.
_FIGURES: tuple[tuple[str, str, str, str | None, str | None, str], ...] = (
    ("sunlit_s", "Time in sunlight", "sunlit_tolerance_s", None, None, "Sun"),
    (
        "earth_contact_s",
        "Time in contact with Earth",
        "earth_contact_tolerance_s",
        None,
        None,
        "Earth",
    ),
    (
        "longest_dark_s",
        "Longest night",
        "longest_dark_tolerance_s",
        "longest_dark_open",
        "longest_dark_grazing",
        "Sun",
    ),
    (
        "longest_blackout_s",
        "Longest time without contact",
        "longest_blackout_tolerance_s",
        "longest_blackout_open",
        "longest_blackout_grazing",
        "Earth",
    ),
)
_SHARE_KEY = {"sunlit_s": "sun_fraction_up", "earth_contact_s": "earth_fraction_up"}
#: The one number a comparison orders by, and which way.
ORDER_WORDS = {
    "sunlit_s": "Time in sunlight, most first",
    "earth_contact_s": "Time in contact with Earth, most first",
    "longest_dark_s": "Longest night, shortest first",
    "longest_blackout_s": "Longest time without contact, shortest first",
}
_NONE_WORDS = {
    "longest_dark_s": "none (the Sun did not set on these dates)",
    "longest_blackout_s": "none (Earth stayed in view on these dates)",
}
_NO_CROSSING = {
    "Sun": "no margin: no sunrise or sunset falls inside these dates to time",
    "Earth": "no margin: Earth neither rises nor sets inside these dates",
}
_GRAZING_WORDS = {
    "Sun": "no margin: the Sun only skims the skyline at one end, so that moment cannot be timed",
    "Earth": "no margin: Earth only skims the skyline at one end, so that moment cannot be timed",
}
#: A smooth-sphere skyline has no height error, so its zero margin is no margin
#: at all and must not be read as one.
NO_TERRAIN_WORDS = (
    "no stated margin: the terrain is not modelled here, so the skyline is a smooth Moon "
    "and real hills could only block more"
)
NO_MARGIN_WORKED_OUT = "no margin is worked out for this one"
#: Where a site's numbers come from, in the words every number says it in.
PROVENANCE_WORKED_OUT = "worked out from the terrain and the paths of the Sun and Earth"


def _dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _number(v: Any) -> float | None:
    """A finite number, or None (a boolean, a string, an untimeable infinity)."""
    if isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v):
        return float(v)
    return None


def hours_text(h: float) -> str:
    """Hours as the key-number tiles write them: whole hours from ten up, one decimal below."""
    return f"{h:.0f}" if h >= 10 else f"{h:.1f}"


def margin_of(tol_s: float, name: str) -> tuple[dict[str, float], str]:
    """A timing margin as a field and in words: hours to one decimal, minutes below that."""
    h = tol_s / 3600.0
    if round(h, 1) >= 0.1:
        return {f"{name}_tolerance_h": round(h, 1)}, f"± {h:.1f} h"
    minutes = round(tol_s / 60.0)
    if minutes >= 1:
        return {f"{name}_tolerance_min": float(minutes)}, f"± {minutes} min"
    return {}, "± under a minute"


def _with_margin(h: float, margin: str, *, open_: bool, share: str = "") -> str:
    margin_text = f" {margin}" if margin.startswith("±") else f" ({margin})"
    lead = "at least " if open_ else ""
    cut = ", cut short by the dates" if open_ else ""
    return f"{lead}{hours_text(h)} h{margin_text}{share}{cut}"


def in_hours(
    m: dict[str, Any],
    *,
    terrain_modelled: bool = True,
    missing_margin: str = "no margin comes with this result",
) -> tuple[dict[str, float], dict[str, str]]:
    """A site's four numbers and the time working alone, in hours with their margins.

    Returns the fields (``longest_dark_h``, ``longest_dark_tolerance_h`` or
    ``_tolerance_min``, ``sunlit_pct`` ...) and one phrase per figure in the
    glossary's words ("Longest night": "64 h ± 0.3 h"). A figure with no margin
    says why instead of showing none. Pure.
    """
    fields: dict[str, float] = {}
    words: dict[str, str] = {}
    for key, label, tol_key, open_key, graze_key, body in _FIGURES:
        s = _number(m.get(key))
        if s is None:
            continue
        name = key[:-2]
        h = s / 3600.0
        fields[f"{name}_h"] = round(h, 1)
        share = ""
        frac = _number(m.get(_SHARE_KEY.get(key, "")))
        if frac is not None:
            pct = round(frac * 100)
            fields[f"{name}_pct"] = float(pct)
            share = f", {pct}% of the time"
        if open_key is not None and s == 0:
            words[label] = _NONE_WORDS[key]
            continue
        open_ = bool(open_key and m.get(open_key))
        if not terrain_modelled:
            margin = NO_TERRAIN_WORDS
        elif graze_key is not None and m.get(graze_key):
            margin = _GRAZING_WORDS[body]
        elif tol_key not in m:
            margin = missing_margin
        else:
            tol = _number(m.get(tol_key))
            if tol is None:
                margin = _GRAZING_WORDS[body]
            elif tol == 0:
                margin = _NO_CROSSING[body]
            else:
                extra, margin = margin_of(tol, name)
                fields.update(extra)
        words[label] = _with_margin(h, margin, open_=open_, share=share)

    auto = _dict(m.get("autonomy"))
    wc = _number(m.get("worst_compound_s"))
    if wc is None:
        wc = _number(auto.get("worst_compound_s"))
    if wc is not None:
        fields["worst_compound_h"] = round(wc / 3600.0, 1)
        open_ = bool(m.get("worst_compound_open") or auto.get("worst_compound_open"))
        words["Longest time dark and out of contact"] = (
            "none (no stretch on these dates is both dark and out of contact)"
            if wc == 0
            else _with_margin(wc / 3600.0, NO_MARGIN_WORKED_OUT, open_=open_)
        )
    need = _number(auto.get("required_autonomy_s"))
    if need is not None:
        fields["required_autonomy_h"] = round(need / 3600.0, 1)
        share_f = _number(auto.get("margin_fraction"))
        why = "the longest time dark and out of contact"
        if share_f is not None:
            fields["safety_share_pct"] = float(round(share_f * 100))
            why += f" plus a {round(share_f * 100)}% safety share"
        words["Time working alone"] = (
            "none (no stretch on these dates is both dark and out of contact)"
            if need == 0
            else f"{hours_text(need / 3600.0)} h ({NO_MARGIN_WORKED_OUT}): {why}"
        )
    surv = _number(auto.get("survival_needed_s"))
    if surv is not None:
        fields["survival_needed_h"] = round(surv / 3600.0, 1)
        lead = "at least " if auto.get("survival_open") else ""
        words["Battery time needed"] = (
            f"{lead}{hours_text(surv / 3600.0)} h: the longest night, whatever the radio is doing"
        )
    return fields, words


def _parse_iso(v: Any) -> datetime | None:
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)


def _day(dt: datetime) -> str:
    return f"{dt.day} {_MONTHS[dt.month - 1]} {dt.year}"


def when_words(v: Any) -> str | None:
    """An ISO time as people read it: "3 Jun 2027, 04:12 UTC"."""
    dt = _parse_iso(v)
    return None if dt is None else f"{_day(dt)}, {dt:%H:%M} UTC"


def dates_words(start: Any, end: Any) -> str | None:
    """The dates a result covers: "1 Jun 2027 to 30 Jun 2027" for whole days (the end is
    exclusive, so its day before is the last), else both times."""
    a, b = _parse_iso(start), _parse_iso(end)
    if a is None or b is None:
        return None
    midnight = all((t.hour, t.minute, t.second, t.microsecond) == (0, 0, 0, 0) for t in (a, b))
    if midnight and b - a >= timedelta(days=1):
        return f"{_day(a)} to {_day(b - timedelta(days=1))}"
    return f"{when_words(start)} to {when_words(end)}"


def arc_in_hours(arc: dict[str, Any], what: str) -> dict[str, Any]:
    """One stretch (a night, a time without contact ...) with its length in hours, its
    margin, and its start and end in words."""
    h = float(arc["duration_s"]) / 3600.0
    out: dict[str, Any] = {"what": what, **arc, "duration_h": round(h, 1)}
    tol = _number(arc.get("tolerance_s"))
    if arc.get("grazing") or tol is None:
        margin = "no margin: one end only skims the skyline, so it cannot be timed"
    elif tol == 0:
        margin = "no margin: both ends are the dates' own ends"
    else:
        extra, margin = margin_of(tol, "duration")
        out.update(extra)
    starts, ends = when_words(arc.get("start")), when_words(arc.get("end"))
    if arc.get("open_start"):
        starts = f"{starts} or earlier (the dates begin inside it)"
    if arc.get("open_end"):
        ends = f"{ends} or later (the dates end inside it)"
    open_ = bool(arc.get("open_start") or arc.get("open_end"))
    out["in_words"] = f"{_with_margin(h, margin, open_=open_)}, from {starts} to {ends}"
    return out


async def _next_opportunity(session: Session, mission_id: str) -> str | None:
    """The flown launch, or the first opportunity still to come (else the last one)."""
    code, body = await launch_service.launch(session, mission_id)
    opps = body.get("data", {}).get("opportunities") or [] if code == 200 else []
    if not opps:
        return None
    now = time.time()
    ahead = [o for o in opps if (o["t0"].get("value") or 0) >= now]
    return str((ahead or opps[-1:])[0]["id"])


async def _section(session: Session, a: SectionArgs) -> dict[str, Any]:
    """The section's answer as its endpoint gives it, from stored answers only."""
    mid = a.mission_id
    try:
        with job_service.read_only():
            if a.section == "ready":
                return await ready_service.ready(session, mid)
            if a.section == "launch_weather":
                opp = a.opportunity or await _next_opportunity(session, mid)
                if opp is None:
                    return {
                        "available": False,
                        "reason": "No launch opportunity is worked out for this mission.",
                    }
                return await weather_service.launch_weather(session, mid, opp)
            if a.section == "return":
                return await return_service.recovery(session, mid)
            if a.section == "launch":
                code, body = await launch_service.launch(session, mid)
            elif a.section == "trip":
                code, body = await trip_service.trip(session, mid)
            else:
                code, body = await contact_service.contact(session, mid, None, None)
    except job_service.NotWorkedOut as exc:
        return {"available": False, "reason": str(exc)}
    if code == 202:  # a stored failure: its message is the answer
        return {"available": False, "reason": body.get("message") or body.get("error")}
    return body


#: The four bases of an assumed value, as the scenario pages label them
#: (`frontend/src/components/scenario/words.ts`).
BASIS_WORDS: dict[str, tuple[str, str]] = {
    "you": ("You", "set by you, typed or said"),
    "published": ("Published", "from the mission's record"),
    "live": ("Live", "fetched for this scenario"),
    "default": ("Default", "a named precedent or catalogue value"),
}
#: A scenario's steps by the names the step bar uses (``landing`` is Surface).
STEP_NAME = {
    "ready": "Ready",
    "launch": "Launch",
    "trip": "Trip",
    "landing": "Surface",
    "contact": "Contact",
    "return": "Return",
}
_SCENARIO_STATE = {
    "done": "worked out",
    "failed": "could not be worked out",
    "queued": "waiting to be worked out",
    "running": "being worked out",
    "skipped": "not worked out",
}


def _surface_in_hours(result: dict[str, Any]) -> dict[str, Any]:
    """A scenario's Surface result with its durations in hours and its dates in words."""
    data = result.get("data")
    if not isinstance(data, dict):
        return result
    fields, words = in_hours(
        data,
        terrain_modelled=bool(data.get("terrain_modelled", True)),
        missing_margin="no margin is worked out for this scenario's Surface result",
    )
    dates = dates_words(data.get("window_start"), data.get("window_end"))
    return {
        **result,
        "data": {**data, **fields, "in_words": words, **({"dates": dates} if dates else {})},
    }


async def _scenario(session: Session, a: ScenarioArgs) -> dict[str, Any]:
    """One scenario as an agent reads it: assumptions with their basis, steps, results.

    Read straight from its row: nothing is synced, queued or written here, and a
    scenario's values never reach the mission's record.
    """
    rec = await ScenarioRepository(session).get(a.scenario_id)
    if rec is None:
        raise LookupError(f"there is no scenario {a.scenario_id!r}")
    mission = await MissionRepository(session).get(rec.mission_id)
    assumptions: list[dict[str, Any]] = []
    for d in rec.assumptions:
        basis, means = BASIS_WORDS.get(str(d.get("basis")), (str(d.get("basis")), ""))
        src = _dict(d.get("source"))
        row: dict[str, Any] = {
            "label": d.get("label"),
            "value": d.get("display") if d.get("display") is not None else d.get("value"),
            "basis": basis,
            "basis_means": means,
        }
        if _number(d.get("value")) is not None:
            row["amount"] = d.get("value")
            row["unit"] = d.get("unit")
        if src.get("name"):
            row["source"] = src["name"]
        if d.get("note"):
            row["note"] = d["note"]
        assumptions.append(row)
    steps = [
        {
            "step": STEP_NAME.get(str(p.get("id")), p.get("label")),
            "state": _SCENARIO_STATE.get(str(p.get("state")), p.get("state")),
            "detail": p.get("detail"),
        }
        for p in rec.phases
        if isinstance(p, dict)
    ]
    wanted: list[str] = [a.section] if a.section else list(rec.sections)
    results: dict[str, Any] = {}
    done = rec.results if rec.status == "done" and rec.results else {}
    for s in wanted:
        r = done.get(s)
        if not isinstance(r, dict):
            if s in rec.sections:
                results[STEP_NAME.get(s, s)] = {
                    "available": False,
                    "reason": "This scenario has no result for this step; its steps say why.",
                }
            continue
        shown = compact(_plain(r))
        results[STEP_NAME.get(s, s)] = _surface_in_hours(shown) if s == "landing" else shown
    return {
        "scenario_id": rec.id,
        "name": rec.name,
        "what_it_is": (
            "A scenario: a what-if worked out from assumed values. Each value says where it "
            "comes from; none of them is written into the mission's record."
        ),
        "mission_id": rec.mission_id,
        "mission_name": mission.name if mission is not None else None,
        "ready_made": rec.preset,
        "made_by": rec.created_by_name,
        "asked_as": rec.prompt,
        "state": _SCENARIO_STATE.get(rec.status, rec.status),
        "message": rec.message,
        "step_ids": list(rec.sections),
        "assumptions": assumptions,
        "steps": steps,
        "summaries": {STEP_NAME.get(k, k): str(v) for k, v in rec.summaries.items()},
        "results": results,
    }


async def execute(session: Session, name: str, raw_args: dict[str, Any], seq: int) -> ToolCallLog:
    """Run one tool. Never raises: a failure is a logged result the model can see."""
    t0 = time.perf_counter()
    log_entry = ToolCallLog(seq=seq, tool=name, args=raw_args)

    try:
        if name not in TOOL_NAMES:
            raise ValueError(f"unknown tool {name!r}; available: {sorted(TOOL_NAMES)}")

        if name == "get_site":
            site_args = GetSiteArgs(**raw_args)
            site = await site_service.require_site(session, site_args.site_id)
            summaries = await site_service.reference_summaries(session, [site_args.site_id])
            summary = _summary(summaries.get(site_args.site_id))
            if summary is not None:
                hours, words = in_hours(
                    summary,
                    missing_margin="no margin with this coarse summary; the site's numbers for "
                    "the dates carry their margins",
                )
                summary = {"in_words": words, **hours, **summary}
            result: dict[str, Any] = {
                "site_id": site.id,
                "name": site.name,
                "region": site.region,
                "lat_deg": site.lat_deg,
                "lon_deg": site.lon_deg,
                "elev_m": site.elev_m,
                "slope_deg": site.slope_deg,
                "note": site.note,
                "source_note": site.source_note,
                "reference_summary": summary,
                "kind": site.kind,
                "terrain_modelled": site.terrain_modelled,
                # Mission facts an agent may repeat: names, providers, statuses and
                # published dates. No masses or costs: every extra numeric leaf
                # widens what the grounding guard would accept (D23).
                "missions": (await mission_service.missions_for_sites(session, [site.id])).get(
                    site.id, []
                ),
            }

        elif name == "get_metrics":
            metrics_args = WindowArgs(**raw_args)
            start, end = _window(metrics_args)
            payload = await site_service.cached_payload(
                session,
                "metrics",
                metrics_args.site_id,
                start,
                end,
                get_settings().default_step_s,
            )
            result = _trim(
                payload,
                (
                    "site_id",
                    "start",
                    "end",
                    "sunlit_s",
                    "earth_contact_s",
                    "longest_dark_s",
                    "longest_blackout_s",
                    "sun_fraction_up",
                    "earth_fraction_up",
                    "worst_compound_s",
                    "longest_dark_open",
                    "longest_blackout_open",
                    "autonomy",
                ),
            )
            # The margin travels with the numbers. Without it an agent had the
            # four figures and no way to say how far to trust them -- and the
            # product's rule is that every number carries its +- or says why not.
            u = payload["meta"]["uncertainty"]
            result["uncertainty"] = {
                "edge_timing_s": u["edge_timing_s"],
                "grazing": u["grazing"],
                "coverage": u["coverage"],
                # False outside 80°S: a smooth-sphere skyline, whose zero
                # margin is no margin at all, and must not be read as one.
                "terrain_modelled": u.get("terrain_modelled", True),
            }
            # The same numbers in hours with their margins, and in words: what an
            # answer quotes (R3). The name is for the person, never the id. The
            # words come first, so a prompt that cuts a long result keeps them.
            hours, words = in_hours(payload, terrain_modelled=bool(u.get("terrain_modelled", True)))
            site = await site_service.require_site(session, metrics_args.site_id)
            result = {
                "site_id": result.get("site_id"),
                "name": site.name,
                "dates": dates_words(payload.get("start"), payload.get("end")),
                "in_words": words,
                "provenance": PROVENANCE_WORKED_OUT,
                **hours,
                **{k: v for k, v in result.items() if k != "site_id"},
            }

        elif name == "get_windows":
            windows_args = WindowArgs(**raw_args)
            start, end = _window(windows_args)
            payload = await site_service.cached_payload(
                session,
                "windows",
                windows_args.site_id,
                start,
                end,
                get_settings().default_step_s,
            )

            # Arc lists can be hundreds long; the longest few are what a planner
            # actually reasons about. Each comes in hours with its margin, and its
            # start and end in words, so "when does the longest night start" is
            # answered by quoting, not by working anything out.
            def top(body: dict[str, Any], down: str, up: str) -> dict[str, Any]:
                arcs = sorted(body["arcs"], key=lambda x: -x["duration_s"])[:6]
                downs = [a for a in body["arcs"] if not a["up"]]
                longest = max(downs, key=lambda a: a["duration_s"]) if downs else None
                return {
                    "up_s": body["up_s"],
                    "down_s": body["down_s"],
                    "fraction_up": body["fraction_up"],
                    "longest_down_s": body["longest_down_s"],
                    "longest_down_tolerance_s": body["longest_down_tolerance_s"],
                    "grazing": body["grazing"],
                    "up_h": round(body["up_s"] / 3600.0, 1),
                    "up_pct": float(round(body["fraction_up"] * 100)),
                    "longest_down": arc_in_hours(longest, down) if longest else None,
                    "longest_arcs": [arc_in_hours(a, up if a["up"] else down) for a in arcs],
                }

            worst = max(payload["compound"], key=lambda c: c["duration_s"], default=None)
            worst_out: dict[str, Any] | None = None
            if worst is not None:
                wh = float(worst["duration_s"]) / 3600.0
                cut = bool(worst.get("open_start") or worst.get("open_end"))
                worst_out = {
                    **worst,
                    "duration_h": round(wh, 1),
                    "in_words": (
                        f"{_with_margin(wh, NO_MARGIN_WORKED_OUT, open_=cut)}, from "
                        f"{when_words(worst.get('start'))} to {when_words(worst.get('end'))}"
                    ),
                }
            site = await site_service.require_site(session, windows_args.site_id)
            result = {
                "site_id": payload["site_id"],
                "name": site.name,
                "start": payload["start"],
                "end": payload["end"],
                "dates": dates_words(payload["start"], payload["end"]),
                "provenance": PROVENANCE_WORKED_OUT,
                "longest_dark_and_out_of_contact": worst_out,
                "worst_compound_s": payload["worst_compound_s"],
                "worst_compound_h": round(float(payload["worst_compound_s"]) / 3600.0, 1),
                "compound_count": len(payload["compound"]),
                "sun": top(payload["sun"], "night", "sunlight"),
                "earth": top(payload["earth"], "time without contact", "contact with Earth"),
            }

        elif name == "get_horizon_profile":
            horizon_args = HorizonArgs(**raw_args)
            site = await site_service.require_site(session, horizon_args.site_id)
            rec = await site_service.require_mask(session, horizon_args.site_id)
            payload = site_service.horizon_payload(site, rec, 30.0)
            result = {
                "site_id": horizon_args.site_id,
                "max_el_deg": payload["max_el_deg"],
                "max_el_bearing_deg": payload["max_el_bearing_deg"],
                "mean_el_deg": round(rec.mean_el_deg, 4),
                "coverage": round(rec.mask.coverage, 4),
                "profile_12_bearings": {
                    f"{i * 30}": payload["el_deg"][i] for i in range(len(payload["el_deg"]))
                },
            }

        elif name == "search_sites":
            search_args = SearchArgs(**raw_args)
            # The same service `/sites` uses, so the metric filters run before
            # pagination here too and an agent sees exactly what the list shows.
            mission_filtered = bool(
                search_args.has_mission
                or search_args.mission_status
                or search_args.provider
                or search_args.payload_type
            )
            site_ids = (
                await mission_service.site_ids_with_missions(
                    session,
                    statuses=search_args.mission_status,
                    provider=search_args.provider,
                    payload_types=search_args.payload_type,
                )
                if mission_filtered
                else None
            )
            listing = await site_service.list_with_summaries(
                session,
                kind=None if search_args.kind == "all" else search_args.kind,
                site_ids=site_ids,
                q=search_args.q,
                region=search_args.region,
                lat_min=search_args.lat_min,
                lat_max=search_args.lat_max,
                min_sun_fraction=search_args.min_sun_fraction,
                max_longest_dark_s=search_args.max_longest_dark_s,
                limit=search_args.limit,
            )
            rows = [
                {
                    "site_id": site.id,
                    "name": site.name,
                    "lat_deg": site.lat_deg,
                    "kind": site.kind,
                    "summary": _summary(listing.summaries.get(site.id)),
                }
                for site in listing.sites
            ]
            result = {"count": listing.total, "sites": rows}

        elif name == "compare_sites":
            a = CompareArgs(**raw_args)
            if a.rank_by not in METRIC_KEYS:
                raise ValueError(f"rank_by must be one of {sorted(METRIC_KEYS)}; got {a.rank_by!r}")
            start, end = _window(a)
            payload = await compare_service.compare(
                session, a.site_ids, start, end, get_settings().default_step_s, a.rank_by
            )
            # Names, not ids, for the person; hours with margins, not seconds (R3).
            site_names = {
                it["site_id"]: (await site_service.require_site(session, it["site_id"])).name
                for it in payload["items"]
            }
            items = []
            for it in payload["items"]:
                m = it["metrics"]
                u = (m.get("meta") or {}).get("uncertainty") or {}
                hours, words = in_hours(m, terrain_modelled=bool(u.get("terrain_modelled", True)))
                items.append(
                    {
                        "site_id": it["site_id"],
                        "name": site_names[it["site_id"]],
                        "in_words": words,
                        # A null rank is the answer, not a gap: a lower bound or
                        # an untimeable edge means the place cannot be stated,
                        # and the range is all that can be said (C2).
                        "rank": it["rank"],
                        "rank_range": it["rank_range"],
                        "censored": it["censored"],
                        "incomparable_with": it["incomparable_with"],
                        **hours,
                        **_trim(m, (*SUMMARY_KEYS, "worst_compound_s")),
                    }
                )
            result = {
                "rank_by": payload["rank_by"],
                "ordered_by": ORDER_WORDS.get(payload["rank_by"], payload["rank_by"]),
                "dates": dates_words(start.isoformat(), end.isoformat()),
                "provenance": PROVENANCE_WORKED_OUT,
                "too_close_to_call": [
                    [site_names.get(s, s) for s in group] for group in payload["ties"]
                ],
                "ties": payload["ties"],
                # Each with why it could not be worked out, not only its id.
                "unavailable": [
                    {"site_id": u.get("site_id"), "reason": u.get("reason")}
                    for u in payload["unavailable"]
                ],
                "items": items,
            }
        elif name == "list_missions":
            lm = ListMissionsArgs(**raw_args)
            found = await MissionRepository(session).find(statuses=lm.status, q=lm.q)
            result = {
                "count": len(found),
                "missions": [
                    {
                        "mission_id": m.id,
                        "name": m.name,
                        "provider": m.provider,
                        "lander": m.lander,
                        "status": m.status,
                        "site_id": m.site_id,
                        **published_when("launch", m.launch),
                        **published_when("landing", m.landing),
                    }
                    for m in found
                ],
            }

        elif name == "get_mission_sections":
            ma = MissionArgs(**raw_args)
            body = await sections_service.sections(session, ma.mission_id)
            result = {"mission_id": ma.mission_id, "sections": _plain(body["data"])}

        elif name == "get_mission_section":
            sa = SectionArgs(**raw_args)
            result = {
                "mission_id": sa.mission_id,
                "section": sa.section,
                **compact(_plain(await _section(session, sa))),
            }

        elif name == "list_scenario_options":
            so = ScenarioOptionsArgs(**raw_args)
            result = _plain(await scenario_service.reading_context(session, so.mission_id))

        elif name == "get_scenario":
            result = await _scenario(session, ScenarioArgs(**raw_args))

        elif name == "get_space_weather":
            NoArgs(**raw_args)
            result = compact(_plain(await space_weather_service.now(session)))

        else:  # pragma: no cover - guarded above
            raise ValueError(name)

        log_entry.result = result
        from app.agents.guards import flatten_numbers

        log_entry.numbers = [v for _p, v in flatten_numbers(result)]

    except ValidationError as exc:
        log_entry.error = f"invalid arguments for {name}: {exc.errors()}"
        log_entry.result = {"error": log_entry.error}
    except Exception as exc:
        log_entry.error = f"{type(exc).__name__}: {exc}"
        log_entry.result = {"error": log_entry.error}

    log_entry.latency_ms = (time.perf_counter() - t0) * 1000.0
    return log_entry


async def scenario_context(session: Session, mission_id: str) -> dict[str, Any]:
    """What a what-if prompt can name for this mission (the reader's door to the domain)."""
    return _plain(await scenario_service.reading_context(session, mission_id))  # type: ignore[no-any-return]
