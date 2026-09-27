"""Contact (T1): the stored answer, or a job to work it out; bookings; exports.

The API computes nothing here: it builds the job key from everything the
answer depends on (the mission record's version, the station and relay
catalogues' versions, the skyline engine, the dates) and either returns the
stored answer or queues the ``contact`` job (ADR-12). Passes the project
manager has booked are added to the answer when it is read, since they
change without the geometry changing.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ENGINE_VERSION, engine_closure, get_settings
from app.data import catalogues
from app.db.repositories.missions import MissionRecord, MissionRepository
from app.db.repositories.pm import PmRepository
from app.services import audit_service, job_service, lifecycle, mission_service
from app.services.auth_service import Claims
from app.services.mission_service import MissionNotFound

KIND = "contact"
STEP_S = 120
SITE_STEP_S = 900


class NoContact(ValueError):
    """Contact cannot be worked out for this mission; the message says why."""


class BadRequest(ValueError):
    pass


def window(
    m: MissionRecord, start: datetime | None, end: datetime | None
) -> tuple[datetime, datetime, str]:
    if start is not None and end is not None:
        if end <= start:
            raise BadRequest("end must be after start")
        if (end - start) > timedelta(days=60):
            raise BadRequest("contact is worked out over at most 60 days at a time")
        return start, end, "The dates you chose."
    w = mission_service.surface_window(m)
    if w.start is not None and w.end is not None:
        return w.start, w.end, w.note
    s = get_settings()
    rs = s.reference_window_start
    return (
        rs,
        rs + timedelta(days=s.reference_window_days),
        f"{w.note} The reference lunar day is used instead "
        f"({rs.date().isoformat()}, {s.reference_window_days:g} days).",
    )


def _params(m: MissionRecord, start: datetime, end: datetime, note: str) -> dict[str, Any]:
    lc = m.lifecycle or {}
    return {
        "mission_id": m.id,
        "data_version": m.data_version,
        "start": lifecycle.iso(start),
        "end": lifecycle.iso(end),
        "window_note": note,
        "step_s": STEP_S,
        "site_step_s": SITE_STEP_S,
        "surface_engine": ENGINE_VERSION,
        "stations": catalogues.load("ground_stations").version,
        "relays_version": catalogues.load("relays").version,
        "relays": list((lc.get("comms") or {}).get("relays") or []),
        "rovers": list(lc.get("rovers") or []),
        "lander_name": m.lander or m.name,
        "provider": m.provider,
        "flown": m.status in ("completed", "partial_success", "operating"),
    }


async def contact(
    session: AsyncSession,
    mission_id: str,
    start: datetime | None,
    end: datetime | None,
    requested_by: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """``(200, section)`` when stored, else ``(202, job ref)``."""
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    if m.site_id is None:
        raise NoContact(
            "No landing spot is published for this mission, so when a ground "
            "station can hear it cannot be worked out."
        )
    if m.status in ("cancelled", "reassigned"):
        raise NoContact("This delivery was cancelled.")
    if m.status == "lost_before_landing":
        raise NoContact(
            "This lander was lost before it reached the surface, so there was no contact "
            "from the landing spot to work out."
        )
    s, e, note = window(m, start, end)
    params = _params(m, s, e, note)
    ans = await job_service.answer_or_enqueue(
        session,
        kind=KIND,
        closure=engine_closure("vis", "net", "link"),
        params=params,
        mission_id=m.id,
        requested_by=requested_by,
    )
    if ans.assessment is None:
        assert ans.job is not None
        return 202, ans.job
    section = dict(ans.assessment.result)
    data = dict(section["data"])
    data["bookings"] = [
        {
            "station": b["station"],
            "start": b["start"],
            "end": b["end"],
            "entered_by": b["entered_by"],
            "note": b["note"],
        }
        for b in await PmRepository(session).bookings(m.id)
    ]
    section["data"] = data
    return 200, section


async def plan(
    session: AsyncSession, mission_id: str, fmt: str, rate_bps: float | None
) -> tuple[str, str]:
    code, section = await contact(session, mission_id, None, None)
    if code != 200:
        raise NoContact("The contact plan is still being worked out; try again shortly.")
    data = section["data"]
    t_ref = lifecycle.parse_time(data["start"])
    rows = []
    for link in data["links"]:
        for s in link["stretches"]:
            rows.append(
                (
                    link["from"],
                    link["to"],
                    lifecycle.parse_time(s["start"]),
                    lifecycle.parse_time(s["end"]),
                )
            )
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["from", "to", "start_utc", "end_utc", "hours"])
        for a, b, s, e in sorted(rows, key=lambda x: x[2]):
            w.writerow(
                [a, b, lifecycle.iso(s), lifecycle.iso(e), f"{(e - s).total_seconds() / 3600:.3f}"]
            )
        return buf.getvalue(), "text/csv"
    if rate_bps is None:
        raise BadRequest(
            "An ION contact plan needs a data rate, and the lander's is not "
            "published: add ?rate_bps= with the rate you plan for."
        )
    nodes = {n["id"]: i + 1 for i, n in enumerate(data["nodes"])}
    light = data.get("light_time_s", {}).get("max", 1.3)
    lines = [
        f"# ION contact plan for {mission_id}, from {data['start']} (time 0).",
        f"# Node numbers: {', '.join(f'{k}={v}' for k, v in nodes.items())}.",
        f"# Rate {rate_bps:.0f} bit/s as given by the user; not a published figure.",
    ]
    for a, b, s, e in sorted(rows, key=lambda x: x[2]):
        s0, e0 = (s - t_ref).total_seconds(), (e - t_ref).total_seconds()
        lines.append(f"a contact +{s0:.0f} +{e0:.0f} {nodes[a]} {nodes[b]} {rate_bps / 8:.0f}")
        lines.append(f"a range +{s0:.0f} +{e0:.0f} {nodes[a]} {nodes[b]} {max(1, round(light))}")
    return "\n".join(lines) + "\n", "text/plain"


async def add_booking(
    session: AsyncSession,
    who: Claims,
    mission_id: str,
    station: str,
    start: datetime,
    end: datetime,
    note: str | None,
) -> dict[str, Any]:
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    if station not in catalogues.load("ground_stations").ids():
        raise BadRequest(f"'{station}' is not a ground station in the catalogue")
    if end <= start:
        raise BadRequest("a booked pass ends after it starts")
    bid = await PmRepository(session).add_booking(m.id, station, start, end, note, who.actor)
    after = {
        "station": station,
        "start": lifecycle.iso(start),
        "end": lifecycle.iso(end),
        "note": note,
    }
    await audit_service.record(
        session,
        who,
        action="create",
        entity="booking",
        entity_id=str(bid),
        mission_id=m.id,
        before=None,
        after=after,
    )
    return {**after, "id": bid, "entered_by": who.actor, "entered_at": datetime.now(UTC)}
