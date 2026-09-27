"""The mission hub and the heavy lifecycle sections (Launch, Trip, Contact, Return).

A heavy section answers 200 with ``{data, meta}`` when its answer is stored,
or 202 with a job reference while it is being worked out (ADR-12).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.v1 import deps
from app.api.v1.schemas.ready import Section
from app.api.v1.schemas.sections import SectionStatus
from app.services import sections_service

router = APIRouter(tags=["mission sections"])


@router.get(
    "/missions/{mission_id}/sections",
    response_model=Section[list[SectionStatus]],
    summary="The six steps of a mission and one plain sentence for each",
)
async def sections(mission_id: str, session: Any = Depends(deps.db)) -> dict[str, Any]:
    try:
        return await sections_service.sections(session, mission_id)
    except Exception as exc:
        raise deps.to_http(exc) from exc
