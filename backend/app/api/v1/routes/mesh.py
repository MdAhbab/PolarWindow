"""POST /sites/{site_id}/mesh/simulate -- the surface-to-surface mesh fallback."""

from __future__ import annotations

from datetime import UTC, timedelta
from typing import Any

from fastapi import APIRouter, Depends

from app.api.v1 import deps
from app.api.v1.schemas.mesh import MeshRequest, MeshResponse
from app.config import Settings
from app.services import mesh_service

router = APIRouter(tags=["mesh"])


@router.post(
    "/sites/{site_id}/mesh/simulate",
    response_model=MeshResponse,
    summary="Simulate peer relaying to Earth between a site's landers and rovers",
)
async def post_mesh(
    site_id: str,
    body: MeshRequest,
    session: Any = Depends(deps.db),
    s: Settings = Depends(deps.settings),
) -> dict[str, Any]:
    start = body.start or s.reference_window_start
    end = body.end or (start + timedelta(days=s.reference_window_days))
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    try:
        return await mesh_service.simulate(
            session,
            site_id,
            start,
            end,
            body.step_s or s.default_step_s,
            [n.model_dump(exclude_none=True) for n in body.nodes],
            body.radio.model_dump(),
            body.guard.model_dump(),
            body.loss_threshold_s,
        )
    except mesh_service.BadMesh as exc:
        raise deps.problem(
            422,
            "bad-mesh-figure",
            "A mesh figure is missing or out of range",
            str(exc),
            "Everything else can still be read; correct that figure and ask again.",
            errors=[{"field": exc.field, "message": exc.why}],
        ) from exc
    except Exception as exc:
        raise deps.to_http(exc) from exc
