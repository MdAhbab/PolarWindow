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
from app.db.repositories.feeds import FeedRepository
from app.db.repositories.missions import MissionRecord, MissionRepository
from app.db.repositories.pm import PmRepository
from app.db.repositories.sites import SiteRepository
from app.services import audit_service, job_service, lifecycle, mission_service
from app.services.auth_service import Claims
from app.services.mission_service import MissionNotFound

KIND = "contact"
STEP_S = 120
SITE_STEP_S = 900


#: The longest single booking taken: a Deep Space Network track is a few hours,
#: so anything longer is a typing slip, not a pass.
MAX_BOOKING = timedelta(hours=24)


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


def _extra_relays(m: MissionRecord, asked: list[str] | None) -> list[str]:
    """Relays asked for beyond the mission's own, checked against the catalogue."""
    if not asked:
        return []
    cat = catalogues.load("relays")
    own = set(((m.lifecycle or {}).get("comms") or {}).get("relays") or [])
    out: list[str] = []
    for rid in dict.fromkeys(x.strip() for x in asked if x.strip()):
        try:
            rec = cat.get(rid)
        except KeyError:
            known = ", ".join(r.id for r in cat.records if r.role == "relay")
            raise BadRequest(f"No relay '{rid}' in the catalogue. Relays: {known}.") from None
        if rec.role != "relay":
            raise BadRequest(
                f"{rec.name} is a real orbiter used only to check the pass calculation; "
                "it offers no relay service to landers."
            )
        if rid not in own:
            out.append(rid)
    if len(out) > 3:
        raise BadRequest("At most three relays can be added at a time.")
    return sorted(out)


async def _orbiters(
    session: AsyncSession, mission_id: str, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    """For each real orbiter: the recorded Horizons trajectory that covers most of the dates.

    The feeds worker keeps one from a week ago to 30 days ahead, and one for
    each flown mission's surface days; the snapshot id goes into the job key,
    so a newer trajectory makes a new answer.
    """
    repo = FeedRepository(session)
    out: list[dict[str, Any]] = []
    for rec in catalogues.load("relays").records:
        if rec.role != "validation_only" or rec.naif_id is None:
            continue
        best: tuple[timedelta, Any] | None = None
        spans: list[str] = []
        for key in (f"{rec.id}@{mission_id}", rec.id):
            span = await repo.latest_ok_span("horizons", "vectors", key)
            if span is None:
                continue
            sid, v0, v1, fetched = span
            if v0 is None or v1 is None:
                continue
            if v1 <= v0:  # Horizons had nothing for the dates asked
                spans.append(f"none after {v1:%Y-%m-%d}")
                continue
            spans.append(f"{v0:%Y-%m-%d} to {v1:%Y-%m-%d}")
            cover = min(end, v1) - max(start, v0)
            if cover > timedelta(0) and (best is None or cover > best[0]):
                best = (cover, (sid, fetched))
        if best is not None:
            out.append(
                {
                    "id": rec.id,
                    "snapshot_id": best[1][0],
                    "fetched_at": lifecycle.iso(best[1][1]),
                    "missing": None,
                }
            )
        else:
            out.append(
                {
                    "id": rec.id,
                    "snapshot_id": None,
                    "fetched_at": None,
                    "missing": "No JPL Horizons trajectory is recorded for these dates"
                    + (f" (recorded: {'; '.join(spans)})." if spans else " yet."),
                }
            )
    return out


def _params(
    m: MissionRecord, start: datetime, end: datetime, note: str, extra: list[str]
) -> dict[str, Any]:
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
        "extra_relays": extra,
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
    relays: list[str] | None = None,
) -> tuple[int, dict[str, Any]]:
    """``(200, section)`` when stored, else ``(202, job ref)``.

    ``relays``: planned relays to add to the mission's own, to compare what
    each would add (they are marked as not planned for this mission).
    """
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
    params = _params(m, s, e, note, _extra_relays(m, relays))
    params["orbiters"] = await _orbiters(session, m.id, s, e)
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
    if end - start > MAX_BOOKING:
        raise BadRequest("a booked pass is at most 24 hours; book a longer track as several")
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


# ---------------------------------------------------------------------------
# Rover <-> lander line of sight (F5)
# ---------------------------------------------------------------------------

ROVER_KIND = "rover"
#: The polar elevation models (LOLA LDEM 80S, 20 m and 80 m) reach 80 deg S.
POLAR_DEM_EDGE_LAT = -80.0
DEFAULT_RADIUS_M = 500.0
DEFAULT_LANDER_ANTENNA_M = 2.0
DEFAULT_ROVER_ANTENNA_M = 0.5
DEFAULT_FREQ_MHZ = 2400.0


class NoRover(ValueError):
    """The mission carries no rover; the message says so."""


def _rovers(m: MissionRecord) -> list[dict[str, str]]:
    """Rovers the mission record names: payloads that move, and listed rovers."""
    out: dict[str, str] = {}
    for p in m.payloads:
        if "rover_mobility" in p.instrument_types:
            out[p.id] = p.name
    for r in (m.lifecycle or {}).get("rovers") or []:
        out.setdefault(r["id"], r["name"])
    return [{"id": k, "name": v} for k, v in out.items()]


async def rover(
    session: AsyncSession,
    mission_id: str,
    rover_id: str | None,
    *,
    radius_m: float | None = None,
    lander_antenna_m: float | None = None,
    rover_antenna_m: float | None = None,
    freq_mhz: float | None = None,
    requested_by: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """``(200, section)`` when stored or not resolvable, else ``(202, job ref)``."""
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    rovers = _rovers(m)
    if not rovers:
        raise NoRover("This mission carries no rover.")
    if rover_id is None:
        rv = rovers[0]
    else:
        found = [r for r in rovers if r["id"] == rover_id]
        if not found:
            raise BadRequest(
                f"No rover '{rover_id}' on this mission. Rovers: "
                + ", ".join(r["id"] for r in rovers)
                + "."
            )
        rv = found[0]
    if m.site_id is None:
        raise NoContact("No landing spot is published for this mission.")
    site = await SiteRepository(session).get(m.site_id)
    if site is None:
        raise NoContact("The landing spot is not in the site list.")
    if site.lat_deg > POLAR_DEM_EDGE_LAT:
        why = (
            f"{site.name} is outside the polar terrain model (south of 80°S), so the ground "
            "between the rover and the lander is not known well enough to say."
        )
        short = f"{site.name} is outside the polar terrain model."
        data = {
            "rover": rv,
            "share_basis": None,
            "radius_m": None,
            "viewshed": None,
            "viewshed_tile": None,
            "out_of_sight_share": lifecycle.missing("%", short),
            "radio_not_clear_share": lifecycle.missing("%", short),
            "longest_out_of_sight_m": lifecycle.missing("m", short),
            "resolvable": False,
            "reason": why,
            "assumptions": None,
            "terrain": None,
            "note": None,
        }
        meta = lifecycle.meta(
            engines=("los",),
            sources=[],
            parts=[("Terrain", why)],
            compute_ms=None,
            computed_at=datetime.now(UTC),
        )
        return 200, lifecycle.jsonable({"data": data, "meta": meta})
    r = DEFAULT_RADIUS_M if radius_m is None else float(radius_m)
    if not 50.0 <= r <= 5000.0:
        raise BadRequest("radius_m must be between 50 and 5000.")
    la = DEFAULT_LANDER_ANTENNA_M if lander_antenna_m is None else float(lander_antenna_m)
    ra = DEFAULT_ROVER_ANTENNA_M if rover_antenna_m is None else float(rover_antenna_m)
    f = DEFAULT_FREQ_MHZ if freq_mhz is None else float(freq_mhz)
    if not (0.0 <= la <= 50.0 and 0.0 <= ra <= 50.0):
        raise BadRequest("Antenna heights must be between 0 and 50 m.")
    if not 30.0 <= f <= 100_000.0:
        raise BadRequest("freq_mhz must be between 30 and 100000.")
    params = {
        "mission_id": m.id,
        "data_version": m.data_version,
        "site_id": site.id,
        "lat_deg": site.lat_deg,
        "lon_deg": site.lon_deg,
        "surface_engine": ENGINE_VERSION,
        "rover": rv,
        "radius_m": r,
        "lander_antenna_m": la,
        "rover_antenna_m": ra,
        "freq_mhz": f,
        "given": {
            "lander_antenna_m": lander_antenna_m is not None,
            "rover_antenna_m": rover_antenna_m is not None,
            "freq_mhz": freq_mhz is not None,
        },
    }
    ans = await job_service.answer_or_enqueue(
        session,
        kind=ROVER_KIND,
        closure=engine_closure("los"),
        params=params,
        mission_id=m.id,
        requested_by=requested_by,
    )
    if ans.assessment is None:
        assert ans.job is not None
        return 202, ans.job
    return 200, dict(ans.assessment.result)
