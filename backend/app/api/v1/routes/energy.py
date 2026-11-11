"""POST /sites/{site_id}/energy -- battery state of charge and bus temperature."""

from __future__ import annotations

from datetime import UTC, timedelta
from typing import Any

from fastapi import APIRouter, Depends

from app.api.v1 import deps
from app.api.v1.schemas.energy import EnergyRequest, EnergyResponse
from app.config import Settings
from app.services import energy_service

router = APIRouter(tags=["energy"])


@router.post(
    "/sites/{site_id}/energy",
    response_model=EnergyResponse,
    summary="Battery state of charge and bus temperature for a lander at a site",
)
async def post_energy(
    site_id: str,
    body: EnergyRequest,
    session: Any = Depends(deps.db),
    s: Settings = Depends(deps.settings),
) -> dict[str, Any]:
    start = body.start or s.reference_window_start
    end = body.end or (start + timedelta(days=s.reference_window_days))
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    lander = body.lander.model_dump(exclude_none=True)
    try:
        return await energy_service.energy(
            session,
            site_id,
            start,
            end,
            body.step_s or s.default_step_s,
            lander,
            body.lander_example_id,
            body.ground_radius_m,
        )
    except energy_service.BadFigure as exc:
        raise deps.problem(
            422,
            "bad-lander-figure",
            "A lander figure is missing or out of range",
            str(exc),
            "Everything else can still be read; add or correct that figure and ask again.",
            errors=[{"field": f"lander.{exc.field}", "message": exc.why}],
        ) from exc
    except Exception as exc:
        raise deps.to_http(exc) from exc
