"""Liveness and readiness.

Returns **200 when degraded** and 503 only when SPICE or the database is
unavailable. The rule lives in ``services.health_service``; this route only
serialises it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response

from app.api.v1.deps import db
from app.api.v1.schemas.health import HealthResponse
from app.services import health_service

router = APIRouter(tags=["health"])


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Liveness plus kernel-loaded check",
)
async def healthz(response: Response, session: Any = Depends(db)) -> dict[str, Any]:
    code, body = await health_service.report(session)
    response.status_code = code
    return body
