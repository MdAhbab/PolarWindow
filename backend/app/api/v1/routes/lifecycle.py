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
from app.api.v1.schemas.contact import BookingIn, BookingOut, Contact, RoverOut
from app.api.v1.schemas.jobs import JobRefOut
from app.api.v1.schemas.launch import LaunchCalendar
from app.api.v1.schemas.ready import Section
from app.api.v1.schemas.sections import SectionStatus
from app.api.v1.schemas.space_weather import SpaceWeather
from app.api.v1.schemas.trip import Trip
from app.api.v1.schemas.weather import (
    LaunchWeather,
    LimitsIn,
    OfficialForecastIn,
    OfficialForecastOut,
    OfficialForecastRemoved,
    Return,
    ReturnLimitsIn,
    VehicleLimits,
)
from app.services import (
    auth_service,
    contact_service,
    launch_service,
    return_service,
    sections_service,
    space_weather_service,
    trip_service,
    weather_service,
)
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
    if isinstance(exc, contact_service.NoRover):
        return deps.problem(
            409,
            "no-rover",
            "No rover on this mission",
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
    relay: list[str] = Query(
        [],
        max_length=3,
        description="Planned relays (catalogue ids, e.g. `lunar-pathfinder`) to add to the "
        "mission's own, to see what each would add. Repeat for more than one.",
    ),
    session: Any = Depends(deps.db),
) -> Any:
    try:
        code, body = await contact_service.contact(
            session, mission_id, _utc(start), _utc(end), relays=relay
        )
    except Exception as exc:
        raise _contact_http(exc) from exc
    if code == 202:
        return JSONResponse(status_code=202, content=body)
    return body


@router.get(
    "/missions/{mission_id}/contact/rover",
    response_model=Section[RoverOut],
    responses={202: {"model": JobRefOut, "description": "Being worked out; poll the job."}},
    summary="Can the rover and the lander see each other, over the terrain around the lander",
)
async def contact_rover(
    mission_id: str,
    rover: str | None = Query(None, description="Rover id, e.g. `im-2/yaoki`. Default: the first."),
    radius_m: float | None = Query(None, description="How far from the lander (default 500 m)."),
    lander_antenna_m: float | None = Query(None, description="Default 2 m (assumed)."),
    rover_antenna_m: float | None = Query(None, description="Default 0.5 m (assumed)."),
    freq_mhz: float | None = Query(None, description="Default 2400 MHz (assumed)."),
    session: Any = Depends(deps.db),
) -> Any:
    try:
        code, body = await contact_service.rover(
            session,
            mission_id,
            rover,
            radius_m=radius_m,
            lander_antenna_m=lander_antenna_m,
            rover_antenna_m=rover_antenna_m,
            freq_mhz=freq_mhz,
        )
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
    start: datetime | None = Query(None, description="As for the answer: the mission's dates."),
    end: datetime | None = Query(None),
    relay: list[str] = Query(
        [],
        max_length=3,
        description="Planned relays (catalogue ids) whose contacts to list, labelled planned: "
        "a relay's contacts are for one guessed placement of its orbit, so a plan lists them "
        "only when asked. As for the answer, a relay that is not the mission's own is added.",
    ),
    session: Any = Depends(deps.db),
) -> PlainTextResponse:
    try:
        text, media = await contact_service.plan(
            session, mission_id, fmt, rate_bps, _utc(start), _utc(end), relays=relay
        )
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


@router.get(
    "/missions/{mission_id}/trip/export",
    response_class=PlainTextResponse,
    summary="The flown trajectory as a CCSDS Orbit Ephemeris Message or CSV",
)
async def trip_export(
    mission_id: str,
    fmt: Literal["oem", "csv"] = Query("oem", alias="format"),
    session: Any = Depends(deps.db),
) -> PlainTextResponse:
    try:
        text, media, ext = await trip_service.export(session, mission_id, fmt)
    except trip_service.NoExport as exc:
        raise deps.problem(
            409, "no-export", "There is no trajectory to export", str(exc), "Nothing was changed."
        ) from exc
    except Exception as exc:
        raise deps.to_http(exc) from exc
    return PlainTextResponse(
        text,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{mission_id}-trip.{ext}"'},
    )


@router.get(
    "/missions/{mission_id}/launch",
    response_model=Section[LaunchCalendar],
    responses={202: {"model": JobRefOut, "description": "Being worked out; poll the job."}},
    summary="The launch a mission flew, or its launch opportunities backed out from the landing",
)
async def launch(
    mission_id: str,
    start: datetime | None = Query(None, alias="from", description="Default: today."),
    end: datetime | None = Query(None, alias="to", description="Default: 90 days on; 180 at most."),
    session: Any = Depends(deps.db),
) -> Any:
    try:
        code, body = await launch_service.launch(session, mission_id, _utc(start), _utc(end))
    except launch_service.BadDates as exc:
        raise deps.problem(
            422,
            "bad-request",
            "Those dates cannot be used",
            str(exc),
            "Nothing was changed.",
            action="Adjust the dates",
        ) from exc
    except Exception as exc:
        raise deps.to_http(exc) from exc
    if code == 202:
        return JSONResponse(status_code=202, content=body)
    return body


def _weather_http(exc: Exception) -> HTTPException:
    if isinstance(exc, weather_service.BadRequest | return_service.BadRequest):
        return deps.problem(
            422,
            "bad-request",
            "That request cannot be answered",
            str(exc),
            "Nothing was changed.",
            action="Adjust the request",
        )
    if isinstance(exc, weather_service.VehicleNotFound):
        return deps.problem(
            404,
            "vehicle-not-found",
            "That launch vehicle isn't in the list",
            f"'{exc.args[0]}' is not a launch vehicle in this dataset.",
            "Every other vehicle and mission is available.",
            action="Back to the mission",
        )
    if isinstance(exc, weather_service.NothingToRemove):
        return deps.problem(
            404,
            "nothing-to-remove",
            "No official forecast is entered",
            str(exc),
            "Nothing was changed.",
            action="Enter a forecast first",
        )
    return deps.to_http(exc)


@router.get(
    "/missions/{mission_id}/launch/weather",
    response_model=Section[LaunchWeather],
    summary="Each launch weather rule at one launch time, with what the forecasts say",
)
async def launch_weather(
    mission_id: str,
    opportunity: str | None = Query(None, description="An opportunity id from the calendar."),
    t0: datetime | None = Query(None, description="Or a launch time, with a pad."),
    pad: str | None = Query(None),
    session: Any = Depends(deps.db),
) -> dict[str, Any]:
    try:
        return await weather_service.launch_weather(session, mission_id, opportunity, _utc(t0), pad)
    except Exception as exc:
        raise _weather_http(exc) from exc


@router.put(
    "/missions/{mission_id}/launch/official-forecast",
    response_model=OfficialForecastOut,
    summary="Enter the range's official launch weather forecast",
)
async def official_forecast(
    mission_id: str,
    body: OfficialForecastIn,
    session: Any = Depends(deps.db),
    who: auth_service.Claims = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await weather_service.set_official_forecast(
            session, who, mission_id, body.probability_pct, body.concerns, body.pdf_url
        )
    except Exception as exc:
        raise _weather_http(exc) from exc


@router.delete(
    "/missions/{mission_id}/launch/official-forecast",
    response_model=OfficialForecastRemoved,
    summary="Take back the official launch weather forecast shown",
)
async def remove_official_forecast(
    mission_id: str,
    session: Any = Depends(deps.db),
    who: auth_service.Claims = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await weather_service.remove_official_forecast(session, who, mission_id)
    except Exception as exc:
        raise _weather_http(exc) from exc


@router.get(
    "/vehicles/{vehicle_id}/limits",
    response_model=VehicleLimits,
    summary="Weather limits the team entered for a vehicle, with their notes",
)
async def read_vehicle_limits(vehicle_id: str, session: Any = Depends(deps.db)) -> dict[str, Any]:
    try:
        return await weather_service.vehicle_limits(session, vehicle_id)
    except Exception as exc:
        raise _weather_http(exc) from exc


@router.put(
    "/vehicles/{vehicle_id}/limits",
    response_model=VehicleLimits,
    summary="Enter weather limits the vehicle maker does not publish",
)
async def vehicle_limits(
    vehicle_id: str,
    body: LimitsIn,
    session: Any = Depends(deps.db),
    who: auth_service.Claims = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await weather_service.set_vehicle_limits(
            session, who, vehicle_id, [x.model_dump() for x in body.limits]
        )
    except Exception as exc:
        raise _weather_http(exc) from exc


@router.get(
    "/missions/{mission_id}/return",
    response_model=Section[Return],
    summary="Where the booster comes down, and whether anything comes back to Earth",
)
async def recovery(mission_id: str, session: Any = Depends(deps.db)) -> dict[str, Any]:
    try:
        return await return_service.recovery(session, mission_id)
    except Exception as exc:
        raise _weather_http(exc) from exc


@router.put(
    "/missions/{mission_id}/return/limits",
    response_model=Section[Return],
    summary="Enter the sea and wind limits for recovering the booster (and a capsule)",
)
async def return_limits(
    mission_id: str,
    body: ReturnLimitsIn,
    session: Any = Depends(deps.db),
    who: auth_service.Claims = Depends(deps.named_manager),
) -> dict[str, Any]:
    try:
        return await return_service.set_limits(
            session, who, mission_id, body.booster.model_dump(), body.capsule.model_dump()
        )
    except Exception as exc:
        raise _weather_http(exc) from exc


@router.get(
    "/space-weather",
    response_model=Section[SpaceWeather],
    response_model_by_alias=True,
    summary="What the Sun is doing now (NOAA SWPC, NASA DONKI), each number with its age",
)
async def space_weather(session: Any = Depends(deps.db)) -> dict[str, Any]:
    return await space_weather_service.now(session)
