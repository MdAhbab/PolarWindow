"""POST /sites/{site_id}/dispersion -- slope and illumination across a landing ellipse."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.v1 import deps
from app.api.v1.schemas.dispersion import DispersionRequest, DispersionResponse
from app.services import dispersion_service

router = APIRouter(tags=["dispersion"])


@router.post(
    "/sites/{site_id}/dispersion",
    response_model=DispersionResponse,
    summary="Slope and illumination across a landing ellipse at a site",
)
async def post_dispersion(
    site_id: str,
    body: DispersionRequest,
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    try:
        return await dispersion_service.dispersion_at(
            session,
            site_id,
            body.ellipse.model_dump(),
            body.lander.model_dump(),
            body.samples,
        )
    except dispersion_service.NoTerrain as exc:
        raise deps.problem(
            422,
            "no-terrain",
            "No elevation model covers this ellipse",
            str(exc),
            "Everything else for this site can still be read; try a smaller ellipse.",
        ) from exc
    except Exception as exc:
        raise deps.to_http(exc) from exc
