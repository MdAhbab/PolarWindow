"""CLPS mission endpoints (contract v2). Parse, delegate, serialise."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query

from app.api.v1 import deps
from app.api.v1.schemas.missions import InstrumentType, MissionDetail, MissionList, MissionStatus
from app.services import mission_service

router = APIRouter(prefix="/missions", tags=["missions"])


@router.get("", response_model=MissionList, summary="List CLPS missions")
async def list_missions(
    status: list[MissionStatus] | None = Query(None, description="Any of these statuses."),
    provider: str | None = Query(None),
    payload_type: list[InstrumentType] | None = Query(
        None, description="Missions carrying at least one payload of any of these types."
    ),
    region: str | None = Query(None, description="south_polar, nearside, farside, polar_other"),
    date_from: datetime | None = Query(
        None, alias="from", description="Landing (else launch) on or after."
    ),
    date_to: datetime | None = Query(
        None, alias="to", description="Landing (else launch) on or before."
    ),
    q: str | None = Query(None, description="Substring of name, provider, target or task order."),
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    try:
        return await mission_service.list_missions(
            session,
            statuses=list(status) if status else None,
            provider=provider,
            payload_types=list(payload_type) if payload_type else None,
            region=region,
            date_from=date_from,
            date_to=date_to,
            q=q,
        )
    except Exception as exc:
        raise deps.to_http(exc) from exc


@router.get("/{mission_id}", response_model=MissionDetail, summary="One mission, fully sourced")
async def get_mission(
    mission_id: Annotated[str, Path(description="Mission slug, e.g. `im-2`.")],
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    try:
        return await mission_service.get_mission(session, mission_id)
    except Exception as exc:
        raise deps.to_http(exc) from exc
