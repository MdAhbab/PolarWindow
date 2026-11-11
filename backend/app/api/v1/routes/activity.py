"""What is being worked out now, for the activity tray. Public."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.v1 import deps
from app.api.v1.schemas.scenarios import ActivityOut
from app.services import activity_service

router = APIRouter(tags=["activity"])


@router.get(
    "/activity",
    response_model=ActivityOut,
    summary="Jobs and scenarios being worked out, and those finished in the last 15 minutes",
)
async def activity(session: Any = Depends(deps.db)) -> dict[str, Any]:
    return await activity_service.activity(session)
