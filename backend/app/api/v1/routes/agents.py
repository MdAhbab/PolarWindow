"""Agent endpoints, plus the run log the demo shows.

Every endpoint returns 200 with a `status` field rather than an HTTP error when
the agent cannot answer. That is deliberate: `insufficient_data` and `degraded`
are *answers*, the UI has states for both, and turning them into 4xx/5xx would
make a working guard look like a broken service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.agents.base import AgentOutcome, AgentRuntime, agent_runtime
from app.api.v1 import deps
from app.api.v1.schemas.agents import (
    AdviseRequest,
    AgentResponse,
    AgentRunList,
    AskRequest,
    BriefRequest,
    ExplainRequest,
)
from app.config import ENGINE_VERSION, Settings
from app.services import settings_service

router = APIRouter(prefix="/agents", tags=["agents"])

#: The four AI panels cost model quota, so they need a session. The run log is
#: a record anyone may read, as before.
signed_in = [Depends(deps.project_manager)]


async def _runtime(session: Any) -> AgentRuntime:
    """The project manager's AI settings, applied to this one request."""
    ai = await settings_service.ai_settings(session)
    return AgentRuntime(enabled=ai.enabled, models=ai.models, models_light=ai.models_light)


def _iso(dt: Any) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def _envelope(outcome: AgentOutcome, s: Settings) -> dict[str, Any]:
    return {
        "status": outcome.status
        if outcome.status in ("ok", "insufficient_data", "degraded")
        else "degraded",
        "run_status": outcome.status,
        "reason": outcome.reason,
        "result": outcome.result,
        "provenance": outcome.provenance,
        "tool_calls": [
            {
                "seq": c.seq,
                "tool": c.tool,
                "args": c.args,
                "latency_ms": round(c.latency_ms, 2),
                "error": c.error,
                "number_count": len(c.numbers),
            }
            for c in outcome.tool_calls
        ],
        "run_id": outcome.run_id,
        "attempts": outcome.attempts,
        "latency_ms": round(outcome.latency_ms, 1),
        "guard_failures": outcome.guard_failures,
        "meta": agent_meta(s, model=outcome.model),
    }


def agent_meta(s: Settings, model: str | None = None) -> dict[str, Any]:
    """The `meta` block every agent response and the run log carry.

    `model` is the one that answered this run, which the fallback chain can
    make a later one than the first choice; the run log names the first choice.
    """
    notes = [
        "Numbers come only from the tools the agent called; the model computes none.",
        "A number that does not trace to a tool result is rejected; after one failed "
        "repair the answer is replaced by a summary built from the measurements.",
    ]
    if s.offline:
        notes.append("OFFLINE=1: the model is not called; answers come from the measurements.")
    elif not s.gemini_api_key:
        notes.append("No model API key is configured; answers come from the measurements.")
    return {
        "computed_at": datetime.now(UTC),
        "resolution": {
            "time_step_s": s.default_step_s,
            "azimuth_deg": s.azimuth_step_deg,
            "ephemeris": "de440 + moon_pa_de440 (MOON_ME)",
            "source": "tool results of this run",
        },
        "uncertainty": {"grounded": True, "notes": notes},
        "engine_version": ENGINE_VERSION,
        "model": model or s.agent_model,
        "agents_configured": s.agents_enabled,
        "offline": s.offline,
        "notice": (
            "Every number in this answer is checked against the tool results that "
            "produced it. Numbers that do not trace to a measurement are rejected."
        ),
    }


@router.post(
    "/explain", response_model=AgentResponse, dependencies=signed_in, summary="A1 Site Explainer"
)
async def explain(
    body: ExplainRequest,
    session: Any = Depends(deps.db),
    s: Settings = Depends(deps.settings),
) -> dict[str, Any]:
    from app.agents.explainer import explain as run

    try:
        with agent_runtime(await _runtime(session)):
            outcome = await run(session, body.site_id, _iso(body.start), _iso(body.end))
    except Exception as exc:
        raise deps.to_http(exc) from exc
    return _envelope(outcome, s)


@router.post(
    "/advise", response_model=AgentResponse, dependencies=signed_in, summary="A2 Trade-off Advisor"
)
async def advise(
    body: AdviseRequest,
    session: Any = Depends(deps.db),
    s: Settings = Depends(deps.settings),
) -> dict[str, Any]:
    from app.agents.advisor import advise as run

    try:
        with agent_runtime(await _runtime(session)):
            outcome = await run(session, body.requirement, _iso(body.start), _iso(body.end))
    except Exception as exc:
        raise deps.to_http(exc) from exc
    return _envelope(outcome, s)


@router.post(
    "/brief", response_model=AgentResponse, dependencies=signed_in, summary="A3 Audience Writer"
)
async def write_brief(
    body: BriefRequest,
    session: Any = Depends(deps.db),
    s: Settings = Depends(deps.settings),
) -> dict[str, Any]:
    from app.agents.writer import brief as run

    try:
        with agent_runtime(await _runtime(session)):
            outcome = await run(session, body.site_id, _iso(body.start), _iso(body.end))
    except Exception as exc:
        raise deps.to_http(exc) from exc
    return _envelope(outcome, s)


@router.post(
    "/ask", response_model=AgentResponse, dependencies=signed_in, summary="A4 Question Answerer"
)
async def ask(
    body: AskRequest,
    session: Any = Depends(deps.db),
    s: Settings = Depends(deps.settings),
) -> dict[str, Any]:
    from app.agents.asker import ask as run

    try:
        with agent_runtime(await _runtime(session)):
            outcome = await run(session, body.question)
    except Exception as exc:
        raise deps.to_http(exc) from exc
    return _envelope(outcome, s)


@router.get("/runs", response_model=AgentRunList, summary="Recent agent runs (the demo log)")
async def runs(
    limit: int = Query(50, ge=1, le=200),
    agent: str | None = Query(None),
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    """Every agent invocation, whatever its outcome.

    Shown in the demo. It is the proof that the AI layer is real, bounded and
    checked -- including the runs where the guard rejected an answer, which are
    the interesting ones.
    """
    from app.services.agent_log import recent_runs

    return {
        "items": await recent_runs(session, limit=limit, agent=agent),
        "meta": agent_meta(deps.settings()),
    }
