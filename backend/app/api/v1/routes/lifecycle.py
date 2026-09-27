"""The mission hub and the heavy lifecycle sections (Launch, Trip, Contact, Return).

A heavy section answers 200 with ``{data, meta}`` when its answer is stored,
or 202 with a job reference while it is being worked out (ADR-12).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.v1 import deps
from app.api.v1.schemas.contact import BookingIn, BookingOut, Contact
from app.api.v1.schemas.jobs import JobRefOut
from app.api.v1.schemas.ready import Section
from app.api.v1.schemas.sections import SectionStatus
from app.api.v1.schemas.trip import Trip
from app.services import auth_service, contact_service, sections_service, trip_service
from app.services.mission_service import MissionNotFound

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


def _utc(dt: datetime | None) -> datetime | None:
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=UTC))


def _contact_http(exc: Exception) -> HTTPException:
    if isinstance(exc, MissionNotFound):
        return deps.to_http(exc)
    if isinstance(exc, contact_service.NoContact):
        return deps.problem(
            409,
            "no-contact",
            "Contact cannot be worked out",
            str(exc),
            "The mission's other sections are unaffected.",
        )
    if isinstance(exc, contact_service.BadRequest):
        return deps.problem(
            422,
            "bad-request",
            "That request cannot be answered",
            str(exc),
            "Nothing was changed.",
            action="Adjust the request",
        )
    raise exc


@router.get(
    "/missions/{mission_id}/contact",
    response_model=Section[Contact],
    responses={202: {"model": JobRefOut, "description": "Being worked out; poll the job."}},
    summary="Who can hear the lander, and how long a message waits",
)
async def contact(
    mission_id: str,
    start: datetime | None = Query(None, description="Default: the mission's surface dates."),
    end: datetime | None = Query(None),
    session: Any = Depends(deps.db),
) -> Any:
    try:
        code, body = await contact_service.contact(session, mission_id, _utc(start), _utc(end))
    except Exception as exc:
        raise _contact_http(exc) from exc
    if code == 202:
        return JSONResponse(status_code=202, content=body)
    return body


@router.get(
    "/missions/{mission_id}/contact/plan",
    response_class=PlainTextResponse,
    summary="The contact plan as CSV, or as an ION-DTN contact plan (needs a data rate)",
)
async def contact_plan(
    mission_id: str,
    fmt: Literal["csv", "ion"] = Query("csv", alias="format"),
    rate_bps: float | None = Query(None, gt=0, description="Data rate for ION, bits per second."),
    session: Any = Depends(deps.db),
) -> PlainTextResponse:
    try:
        text, media = await contact_service.plan(session, mission_id, fmt, rate_bps)
    except Exception as exc:
        raise _contact_http(exc) from exc
    ext = "csv" if fmt == "csv" else "txt"
    return PlainTextResponse(
        text,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{mission_id}-contact.{ext}"'},
    )


@router.post(
    "/missions/{mission_id}/contact/bookings",
    response_model=BookingOut,
    status_code=201,
    summary="Record a ground station pass the team has booked",
)
async def add_booking(
    mission_id: str,
    body: BookingIn,
    session: Any = Depends(deps.db),
    who: auth_service.Claims = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        start, end = _utc(body.start), _utc(body.end)
        assert start is not None and end is not None
        return await contact_service.add_booking(
            session, who, mission_id, body.station, start, end, body.note
        )
    except Exception as exc:
        raise _contact_http(exc) from exc


@router.get(
    "/missions/{mission_id}/trip",
    response_model=Section[Trip],
    responses={202: {"model": JobRefOut, "description": "Being worked out; poll the job."}},
    summary="The trip to the Moon: distance, shadow, when a station could see it",
)
async def trip(mission_id: str, session: Any = Depends(deps.db)) -> Any:
    try:
        code, body = await trip_service.trip(session, mission_id)
    except Exception as exc:
        raise deps.to_http(exc) from exc
    if code == 202:
        return JSONResponse(status_code=202, content=body)
    return body
