"""Scenarios: what a step would show if its missing facts were assumed.

A scenario never changes the mission. Reading is public; asking the AI to read a
prompt needs a session (it spends model quota); starting and deleting need a name.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response
from fastapi.exceptions import HTTPException

from app.agents import scenario_reader
from app.agents.base import AgentRuntime, agent_runtime
from app.api.v1 import deps
from app.api.v1.schemas.scenarios import (
    InterpretedOut,
    InterpretIn,
    ScenarioDeletedOut,
    ScenarioGapsOut,
    ScenarioIn,
    ScenarioListOut,
    ScenarioOut,
)
from app.services import auth_service, job_service, scenario_service, settings_service

router = APIRouter(tags=["scenarios"])


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, scenario_service.ScenarioNotFound):
        return deps.problem(
            404,
            "scenario-not-found",
            "That scenario isn't there",
            f"'{exc.args[0]}' is not a scenario, or it was deleted.",
            "Every mission and its published numbers are unaffected.",
            action="Back to the mission",
        )
    if isinstance(exc, scenario_service.BadScenario):
        return deps.problem(
            422,
            "bad-scenario",
            "That scenario cannot be worked out",
            str(exc),
            "Nothing was changed, and the mission's record is untouched.",
            action="Adjust the assumptions",
        )
    if isinstance(exc, scenario_service.Refused):
        return deps.problem(
            409, "scenario-refused", "That cannot be done", str(exc), "Nothing was changed."
        )
    if isinstance(exc, job_service.QueueFull):
        return deps.problem(
            503,
            "queue-full",
            "Too much is being worked out right now",
            f"{exc.queued} answers are already waiting for a compute worker.",
            "Everything already worked out can still be read.",
            retryable=True,
            action="Try again in a few minutes",
        )
    return deps.to_http(exc)


@router.get(
    "/missions/{mission_id}/scenarios/gaps",
    response_model=ScenarioGapsOut,
    summary="What a mission's record lacks for each step, the fields a scenario can set, presets",
)
async def gaps(mission_id: str, session: Any = Depends(deps.db)) -> dict[str, Any]:
    try:
        return await scenario_service.gaps(session, mission_id)
    except Exception as exc:
        raise _http(exc) from exc


@router.post(
    "/missions/{mission_id}/scenarios/interpret",
    response_model=InterpretedOut,
    summary="Read plain words into assumptions (nothing is worked out or saved)",
)
async def interpret(
    mission_id: str,
    body: InterpretIn,
    session: Any = Depends(deps.db),
    _who: auth_service.Claims = Depends(deps.project_manager),
) -> dict[str, Any]:
    try:
        ctx = await scenario_reader.context(session, mission_id)
        ai = await settings_service.ai_settings(session)
        rt = AgentRuntime(enabled=ai.enabled, models=ai.models, models_light=ai.models_light)
        with agent_runtime(rt):
            reading = await scenario_reader.read(session, body.prompt, ctx, body.section)
        return await scenario_service.interpreted(session, mission_id, reading, body.section)
    except Exception as exc:
        raise _http(exc) from exc


@router.post(
    "/missions/{mission_id}/scenarios",
    response_model=ScenarioOut,
    status_code=201,
    summary="Start a scenario, or join the one with the same assumptions",
)
async def start(
    mission_id: str,
    body: ScenarioIn,
    response: Response,
    session: Any = Depends(deps.db),
    who: auth_service.Claims = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        created, out = await scenario_service.start(
            session, who, mission_id, body.model_dump(exclude_none=False)
        )
    except Exception as exc:
        raise _http(exc) from exc
    response.status_code = 201 if created else 200
    return out


@router.get(
    "/missions/{mission_id}/scenarios",
    response_model=ScenarioListOut,
    summary="A mission's scenarios, presets first, then newest",
)
async def listing(mission_id: str, session: Any = Depends(deps.db)) -> dict[str, Any]:
    try:
        return await scenario_service.listing(session, mission_id)
    except Exception as exc:
        raise _http(exc) from exc


@router.get(
    "/scenarios/{scenario_id}",
    response_model=ScenarioOut,
    summary="A scenario: its progress, then its answer, always with its assumptions",
)
async def one(scenario_id: str, session: Any = Depends(deps.db)) -> dict[str, Any]:
    try:
        return await scenario_service.get(session, scenario_id)
    except Exception as exc:
        raise _http(exc) from exc


@router.delete(
    "/scenarios/{scenario_id}",
    response_model=ScenarioDeletedOut,
    summary="Delete a scenario (never a preset)",
)
async def remove(
    scenario_id: str,
    session: Any = Depends(deps.db),
    who: auth_service.Claims = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await scenario_service.delete(session, who, scenario_id)
    except Exception as exc:
        raise _http(exc) from exc
