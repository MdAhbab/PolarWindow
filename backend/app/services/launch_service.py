"""Launch (T2, D1/D2): the launch a mission flew, or the opportunities it has.

Heavy, so a job (ADR-12): the first request answers 202 and the compute
worker works it out (``workers/handlers/launch.py``). A mission with nothing
to work from (no pad, vehicle or landing spot) is answered at once, saying
which is missing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import engine_closure
from app.core import landing_windows
from app.core.quantity import Quantity
from app.data import catalogues
from app.db.repositories.missions import MissionRecord, MissionRepository
from app.db.repositories.pm import PmRepository
from app.services import ascent, job_service, lifecycle
from app.services.mission_service import MissionNotFound

KIND = "launch"
DEFAULT_DAYS = 90
MAX_DAYS = 180
#: Vehicles with no reconstructed lunar launch whose climb is taken from another,
#: with the reason (said in each opportunity's note).
CLIMB_OF: dict[str, str] = {"falcon-heavy": "falcon-9"}


class BadDates(ValueError):
    pass


def _source(m: MissionRecord, field: str) -> str | None:
    fs = (m.lifecycle or {}).get("field_sources") or {}
    url = fs.get(field)
    if url:
        return str(url)
    return str(m.sources[0]["url"]) if m.sources else None


def pads(pad_id: str) -> list[dict[str, Any]]:
    s = catalogues.load("launch_sites").get(pad_id)
    return [
        {
            "id": s.id,
            "name": s.name,
            "lat_deg": s.lat_deg,
            "lon_deg": s.lon_deg,
            "operator": s.operator or "not published",
        }
    ]


def landing_rule(
    par: dict[str, Any], days: float | None
) -> tuple[landing_windows.Rule, dict[str, Any]]:
    """The landing rule the calendar applies, and its contract shape (``landing_rule``)."""
    lo, hi = par.get("landing_sun_min_deg"), par.get("landing_sun_max_deg")

    def band(v: float | None, pid: str) -> dict[str, Any]:
        if v is None:
            return lifecycle.missing(
                "deg",
                "Not entered. Until it is, any landing with the Sun up and rising counts.",
                provenance="entered",
            )
        return lifecycle.q(
            Quantity(
                value=float(v),
                unit="deg",
                provenance="entered",
                no_margin_reason="A limit the project set.",
                source=par.get(f"{pid}__by"),
            )
        )

    parts = ["The Sun must be above the skyline and rising at landing, and the Earth up."]
    if lo is None and hi is None:
        parts.append("No Sun-height band has been entered (Settings, Project).")
    if days is not None:
        parts.append(f"The Sun must then stay up at least {days:g} days.")
    else:
        parts.append("The planned days on the surface are not known, so that is not required.")
    parts.append(
        "Near the poles the lighting decides; the lunar orbit's plane passing over the spot "
        "is not checked."
    )
    rule = landing_windows.Rule(
        sun_min_deg=None if lo is None else float(lo),
        sun_max_deg=None if hi is None else float(hi),
        surface_days=None if days is None else float(days),
    )
    return rule, {
        "sun_elevation_min_deg": band(lo, "landing_sun_min_deg"),
        "sun_elevation_max_deg": band(hi, "landing_sun_max_deg"),
        "earth_required": True,
        "note": " ".join(parts),
    }


async def _parameters(session: AsyncSession) -> dict[str, Any]:
    stored = await PmRepository(session).parameters()
    out: dict[str, Any] = {}
    for pid in ("landing_sun_min_deg", "landing_sun_max_deg", "surface_days"):
        row = stored.get(pid)
        out[pid] = None if row is None else float(row["value"])
        out[f"{pid}__by"] = None if row is None else row["changed_by"]
    return out


def _dates(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime, str]:
    if start is None and end is None:
        s = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return s, s + timedelta(days=DEFAULT_DAYS), f"The next {DEFAULT_DAYS} days."
    if start is not None:
        s = start
    else:
        assert end is not None
        s = end - timedelta(days=DEFAULT_DAYS)
    e = end or (s + timedelta(days=DEFAULT_DAYS))
    if e <= s:
        raise BadDates("to must be after from")
    if (e - s) > timedelta(days=MAX_DAYS):
        raise BadDates(f"launch opportunities are worked out over at most {MAX_DAYS} days")
    return s, e, "The dates you chose."


def _none(
    m: MissionRecord, reason: str, params: dict[str, Any], pad_id: str | None
) -> dict[str, Any]:
    _, rule = landing_rule(params, m.planned_surface_days)
    lc = m.lifecycle or {}
    t0 = lc.get("t0")
    return {
        "data": {
            "none_reason": reason,
            "start": None,
            "end": None,
            "dates_note": None,
            "vehicle_id": lc.get("vehicle_id"),
            "pads": pads(pad_id) if pad_id else [],
            "opportunities": [],
            "landing_rule": rule,
            "published_t0": (lifecycle.published_date(t0, _source(m, "t0") or "") if t0 else None),
        },
        "meta": lifecycle.meta(engines=("lw",), sources=[], parts=[("No calendar", reason)]),
    }


async def reconstructed_flights(session: AsyncSession) -> tuple[list[list[str]], dict[str, str]]:
    """The reconstructed flights ``[mission, vehicle, pad, liftoff]`` and their names."""
    repo = MissionRepository(session)
    out, names = [], {}
    for mid in ascent.RECONSTRUCTED:
        r = await repo.get(mid)
        lc = (r.lifecycle or {}) if r else {}
        if r and lc.get("t0") and lc.get("vehicle_id") and lc.get("pad_id"):
            out.append([mid, lc["vehicle_id"], lc["pad_id"], lc["t0"]["date"]])
            names[mid] = r.name
    return out, names


async def published_windows(session: AsyncSession) -> dict[str, list[str]]:
    """The launch window each reconstructed flight was published with, ``[open, close]``
    (equal ends for a single instant)."""
    repo = MissionRepository(session)
    out: dict[str, list[str]] = {}
    for mid in ascent.RECONSTRUCTED:
        r = await repo.get(mid)
        t0 = ((r.lifecycle or {}) if r else {}).get("t0") or {}
        if t0.get("window_open") and t0.get("window_close"):
            out[mid] = [t0["window_open"], t0["window_close"]]
    return out


async def launch(
    session: AsyncSession,
    mission_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
    requested_by: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """``(200, section)`` when stored or when there is nothing to work out, else ``(202, job)``."""
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    params = await _parameters(session)
    lc = m.lifecycle or {}
    pad_id, vehicle_id, t0 = lc.get("pad_id"), lc.get("vehicle_id"), lc.get("t0")
    if m.status in ("cancelled", "reassigned"):
        return 200, _none(m, "This delivery was cancelled.", params, pad_id)
    flights, names = await reconstructed_flights(session)
    base: dict[str, Any] = {
        "names": names,
        "mission_id": m.id,
        "data_version": m.data_version,
        "pad_id": pad_id,
        "vehicle_id": vehicle_id,
        "site_id": m.site_id,
        "site_lat_deg": (m.target or {}).get("lat_deg"),
        "t0": t0,
        "t0_source": _source(m, "t0"),
        "landing": m.landing,
        "landing_source": str(m.sources[0]["url"]) if m.sources else "",
        "parameters": params,
        "surface_days": m.planned_surface_days
        if m.planned_surface_days is not None
        else params.get("surface_days"),
        "flights": flights,
        "windows": await published_windows(session),
        "catalogues": [
            catalogues.load("launch_sites").version,
            catalogues.load("vehicles").version,
        ],
    }
    if m.id in ascent.RECONSTRUCTED and t0 and pad_id and vehicle_id:
        params_ = {
            **base,
            "basis": "flown",
            "from": None,
            "to": None,
            "dates_note": "The launch it flew.",
        }
    else:
        missing = [
            w
            for w, v in (
                ("launch pad", pad_id),
                ("launch vehicle", vehicle_id),
                ("landing spot", m.site_id),
            )
            if not v
        ]
        if missing:
            return 200, _none(
                m,
                f"The {' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not "
                "published, so launch opportunities cannot be worked out.",
                params,
                pad_id,
            )
        s, e, note = _dates(start, end)
        climb = (
            vehicle_id
            if any(f[1] == vehicle_id for f in flights)
            else CLIMB_OF.get(str(vehicle_id))
        )
        if climb is None:
            name = catalogues.load("vehicles").get(str(vehicle_id)).name
            return 200, _none(
                m,
                f"No lunar launch of {name} has been reconstructed here, so how it climbs to "
                "orbit is not known and launch instants cannot be worked out.",
                params,
                pad_id,
            )
        same = [
            f[0]
            for f in flights
            if (r := await MissionRepository(session).get(f[0])) and r.lander == m.lander
        ]
        precedents = {}
        for f in flights:
            r = await MissionRepository(session).get(f[0])
            precedents[f[0]] = r.landing if r else None
        params_ = {
            **base,
            "basis": "design",
            "from": lifecycle.iso(s),
            "to": lifecycle.iso(e),
            "dates_note": note,
            "ascent_vehicle": climb,
            "same_lander": same,
            "precedents": precedents,
        }
    ans = await job_service.answer_or_enqueue(
        session,
        kind=KIND,
        closure=engine_closure("lw", "traj", "vis"),
        params=params_,
        mission_id=m.id,
        requested_by=requested_by,
    )
    if ans.assessment is None:
        assert ans.job is not None
        return 202, ans.job
    return 200, ans.assessment.result
