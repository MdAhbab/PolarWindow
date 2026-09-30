"""The only place an agent touches the system.

Ten tools, each with a typed argument model and a JSON schema: six over the
sites (the brief's), and four over the missions' sections (ADR-6, amended),
whose results are cut to at most 200 numbers (``compact.py``). Agents cannot
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
from app.services import (
    compare_service,
    contact_service,
    job_service,
    launch_service,
    mission_service,
    ready_service,
    return_service,
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
            "The four key numbers for one site over a window: sunlit seconds, "
            "Earth-contact seconds, longest unbroken dark gap, longest unbroken "
            "comms blackout, plus the autonomy packet. Durations are SECONDS."
        ),
        "parameters": tool_parameters(WindowArgs.model_json_schema()),
    },
    {
        "name": "get_windows",
        "description": (
            "The individual lit/dark and link/blackout intervals for one site, each "
            "with its timing tolerance and, for blocked stretches, the bearing of the "
            "terrain doing the blocking."
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
            "Rank up to eight sites over one shared window by one of the four "
            "metrics. Each item has a rank, or rank=null with a rank_range when a "
            "lower-bound (censored) value or an untimeable edge makes its place "
            "unknowable; never call such a site best. Also returns ties."
        ),
        "parameters": tool_parameters(CompareArgs.model_json_schema()),
    },
    {
        "name": "list_missions",
        "description": (
            "The CLPS missions: id, name, provider, lander, status, target site and "
            "published launch and landing dates. Use it to find a mission's id."
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
                "reference_summary": _summary(summaries.get(site_args.site_id)),
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
            # actually reasons about.
            def top(body: dict[str, Any]) -> dict[str, Any]:
                arcs = sorted(body["arcs"], key=lambda x: -x["duration_s"])[:6]
                return {
                    "up_s": body["up_s"],
                    "down_s": body["down_s"],
                    "fraction_up": body["fraction_up"],
                    "longest_down_s": body["longest_down_s"],
                    "longest_down_tolerance_s": body["longest_down_tolerance_s"],
                    "grazing": body["grazing"],
                    "longest_arcs": arcs,
                }

            result = {
                "site_id": payload["site_id"],
                "start": payload["start"],
                "end": payload["end"],
                "sun": top(payload["sun"]),
                "earth": top(payload["earth"]),
                "worst_compound_s": payload["worst_compound_s"],
                "compound_count": len(payload["compound"]),
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
            result = {
                "rank_by": payload["rank_by"],
                "ties": payload["ties"],
                "unavailable": [u["site_id"] for u in payload["unavailable"]],
                "items": [
                    {
                        "site_id": it["site_id"],
                        # A null rank is the answer, not a gap: a lower bound or
                        # an untimeable edge means the place cannot be stated,
                        # and the range is all that can be said (C2).
                        "rank": it["rank"],
                        "rank_range": it["rank_range"],
                        "censored": it["censored"],
                        "incomparable_with": it["incomparable_with"],
                        **_trim(it["metrics"], (*SUMMARY_KEYS, "worst_compound_s")),
                    }
                    for it in payload["items"]
                ],
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
                        "launch": (m.launch or {}).get("date"),
                        "landing": (m.landing or {}).get("date"),
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
