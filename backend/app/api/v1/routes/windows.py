"""Window endpoints: what Sun and Earth do at a site over a span of time.

Timeline, arcs (windows), the four numbers (metrics) and the calendar all take
a site and a window, and all go through the same memoised geometry, so the
views can never disagree about a number. Routes parse, delegate and serialise.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query

from app.api.v1 import deps
from app.api.v1.schemas.sites import (
    CalendarResponse,
    MetricsResponse,
    TimelineResponse,
    WindowsResponse,
)
from app.services import site_service

router = APIRouter(prefix="/sites", tags=["sites"])

SiteId = Annotated[str, Path(description="Site slug, e.g. `connecting-ridge`.")]
Window = Annotated[tuple[datetime, datetime, int], Depends(deps.window_params)]


@router.get("/{site_id}/timeline", response_model=TimelineResponse, summary="Sun and Earth track")
async def get_timeline(
    site_id: SiteId,
    window: Window,
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    start, end, step_s = window
    try:
        return await site_service.cached_payload(session, "timeline", site_id, start, end, step_s)
    except Exception as exc:
        raise deps.to_http(exc) from exc


@router.get(
    "/{site_id}/windows",
    response_model=WindowsResponse,
    summary="Lit/dark and link/blackout intervals",
)
async def get_windows(
    site_id: SiteId,
    window: Window,
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    start, end, step_s = window
    try:
        return await site_service.cached_payload(session, "windows", site_id, start, end, step_s)
    except Exception as exc:
        raise deps.to_http(exc) from exc


@router.get("/{site_id}/metrics", response_model=MetricsResponse, summary="The four key numbers")
async def get_metrics(
    site_id: SiteId,
    window: Window,
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    start, end, step_s = window
    try:
        return await site_service.cached_payload(session, "metrics", site_id, start, end, step_s)
    except Exception as exc:
        raise deps.to_http(exc) from exc


@router.get(
    "/{site_id}/calendar",
    response_model=CalendarResponse,
    summary="Sun and Earth by day or month, for choosing dates",
)
async def calendar(
    site_id: SiteId,
    start: datetime | None = Query(
        None, description="ISO 8601 UTC. Defaults to the reference start."
    ),
    end: datetime | None = Query(None, description="ISO 8601 UTC; at most 730 days after start."),
    bucket: Literal["day", "month"] = Query("month"),
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    s = deps.settings()
    begin = start or s.reference_window_start
    finish = end or begin + timedelta(days=365)
    try:
        return await site_service.calendar_payload(session, site_id, begin, finish, bucket)
    except Exception as exc:
        raise deps.to_http(exc) from exc
