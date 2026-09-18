"""The only place an agent touches the system.

Six tools, each with a typed argument model and a JSON schema. Agents cannot
reach a service or a repository directly -- an import-linter contract forbids it
-- so this module is the complete, auditable surface area of what an LLM can do
here. It reads; nothing in it writes.

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

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schema_convert import tool_parameters
from app.config import get_settings
from app.core.metrics import METRIC_KEYS
from app.services import compare_service, site_service

log = logging.getLogger(__name__)


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
    limit: int = Field(default=20, ge=1, le=50)


class CompareArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_ids: list[str] = Field(min_length=1, max_length=8)
    start: str | None = None
    end: str | None = None
    rank_by: str = Field(default="longest_dark_s")


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
            "Find sites by name, region, latitude band, or coarse metric thresholds. "
            "Metric filters are evaluated against the reference window, not an "
            "arbitrary one."
        ),
        "parameters": tool_parameters(SearchArgs.model_json_schema()),
    },
    {
        "name": "compare_sites",
        "description": (
            "Rank up to eight sites over one shared window by one of the four "
            "metrics. Returns each site's full metrics plus any ties."
        ),
        "parameters": tool_parameters(CompareArgs.model_json_schema()),
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


async def execute(
    session: AsyncSession, name: str, raw_args: dict[str, Any], seq: int
) -> ToolCallLog:
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
                "reference_summary": summaries.get(site_args.site_id),
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
                    "autonomy",
                ),
            )

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
            from app.db.repositories.sites import SiteRepository

            sites, _total = await SiteRepository(session).list_sites(
                q=search_args.q,
                region=search_args.region,
                lat_min=search_args.lat_min,
                lat_max=search_args.lat_max,
                limit=search_args.limit,
            )
            summaries = await site_service.reference_summaries(session, [x.id for x in sites])
            rows = []
            for site in sites:
                summary = summaries.get(site.id)
                if search_args.min_sun_fraction is not None and (
                    summary is None or summary["sun_fraction_up"] < search_args.min_sun_fraction
                ):
                    continue
                if search_args.max_longest_dark_s is not None and (
                    summary is None or summary["longest_dark_s"] > search_args.max_longest_dark_s
                ):
                    continue
                rows.append(
                    {
                        "site_id": site.id,
                        "name": site.name,
                        "region": site.region,
                        "lat_deg": site.lat_deg,
                        "elev_m": site.elev_m,
                        "summary": summary,
                    }
                )
            result = {"count": len(rows), "sites": rows}

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
                        "rank": it["rank"],
                        **_trim(
                            it["metrics"],
                            (
                                "sunlit_s",
                                "earth_contact_s",
                                "longest_dark_s",
                                "longest_blackout_s",
                                "sun_fraction_up",
                                "earth_fraction_up",
                                "worst_compound_s",
                            ),
                        ),
                    }
                    for it in payload["items"]
                ],
            }
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
