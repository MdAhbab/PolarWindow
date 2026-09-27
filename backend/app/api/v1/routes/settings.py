"""The project manager's settings: the AI assistant, the run log and the cache.

Every route here needs the project manager's session. Each change applies to
everyone using this server, so each one can be undone or is harmless to
repeat: the AI settings reset to the configured defaults, cached results are
worked out again on the next request, and the run log only ever records.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.agents import base
from app.api.v1 import deps
from app.api.v1.schemas.settings import AiSettingsIn, Cleared, SettingsOut
from app.config import get_settings
from app.services import auth_service, health_service, settings_service

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(deps.project_manager)],
)


def _ai(ai: settings_service.AiSettings) -> dict[str, Any]:
    return {
        "enabled": ai.enabled,
        "configured": get_settings().agents_enabled,
        "customised": ai.customised,
        "models": base.model_states(ai.models),
        "models_light": base.model_states(ai.models_light),
    }


async def _view(session: Any) -> dict[str, Any]:
    _, health = await health_service.report(session)
    return {
        "ai": _ai(await settings_service.ai_settings(session)),
        "system": {
            "status": health["status"],
            "moon_data": bool(health["dem"]["regional_present"]),
            "sun_earth_data": bool(health["kernels"]["loaded"]),
            "database": health["db"] == "ok",
            "cache": health["redis"] == "ok",
            "counts": await settings_service.counts(session),
        },
    }


@router.get("", response_model=SettingsOut, summary="Everything the Settings panel shows")
async def read(session: Any = Depends(deps.db)) -> dict[str, Any]:
    return await _view(session)


@router.put("/ai", response_model=SettingsOut, summary="Turn the AI on or off and order its models")
async def save_ai(
    body: AiSettingsIn,
    session: Any = Depends(deps.db),
    who: auth_service.Claims = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        await settings_service.save_ai_settings(
            session, body.enabled, body.models, body.models_light, who.actor[:64]
        )
    except settings_service.BadSetting as exc:
        raise deps.problem(
            422,
            "bad-setting",
            "That setting was not saved",
            str(exc),
            "The previous settings are still in force.",
            action="Adjust the list",
        ) from exc
    return await _view(session)


@router.post(
    "/ai/reset",
    response_model=SettingsOut,
    summary="Back to the configured defaults",
    dependencies=[Depends(deps.named_manager)],
)
async def reset_ai(session: Any = Depends(deps.db)) -> dict[str, Any]:
    await settings_service.reset_ai_settings(session)
    return await _view(session)


@router.post(
    "/ai/retry",
    response_model=SettingsOut,
    summary="Try skipped models again now",
    dependencies=[Depends(deps.named_manager)],
)
async def retry_models(session: Any = Depends(deps.db)) -> dict[str, Any]:
    """Forget every model's cooldown, e.g. after the key's quota was raised."""
    base.reset_model_cooldowns()
    return await _view(session)


@router.delete(
    "/agent-runs",
    response_model=Cleared,
    summary="Clear the AI activity log",
    dependencies=[Depends(deps.named_manager)],
)
async def clear_run_log(session: Any = Depends(deps.db)) -> dict[str, Any]:
    runs, calls = await settings_service.clear_run_log(session)
    return {
        "what": "agent_runs",
        "removed": runs,
        "message": f"Removed {runs} AI runs and their {calls} data look-ups.",
    }


@router.delete(
    "/cache",
    response_model=Cleared,
    summary="Clear cached results",
    dependencies=[Depends(deps.named_manager)],
)
async def clear_cache() -> dict[str, Any]:
    n = await settings_service.clear_cache()
    return {
        "what": "cache",
        "removed": n,
        "message": (
            f"Removed {n} cached results. Each one is worked out again when it is next needed."
            if n is not None
            else "The cache is not in use, so there was nothing to remove."
        ),
    }
