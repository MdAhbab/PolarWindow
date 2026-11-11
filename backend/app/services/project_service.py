"""Projects: missions the team enters, saved as mission records (``origin = 'project'``).

A project is written in the same shape as a CLPS record from
``data/missions.json`` (dates with their precision and words, the target, the
v2 ``lifecycle`` facts), so the six section services work on it unchanged.
What the person did not give stays null and is listed in ``unconfirmed_fields``;
nothing is filled in. Its sources say who entered it, and which file it was
read from when the form was filled from one.

A target is an existing site, or a coordinate. A new coordinate becomes a site
of kind ``mission_target`` (``project-<slug>``) and its skyline is built by the
compute worker: a ``site_build`` job with params ``{site_id}``.

Every write needs a named session and goes to the change history.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ENGINE_VERSION, engine_closure, get_settings
from app.data import catalogues
from app.data.ingest_missions import (
    NESTED_NULLABLE,
    NULLABLE_FIELDS,
    NULLABLE_FIELDS_V2,
    is_terrain_covered,
    region_of,
    site_code,
)
from app.db.repositories.jobs import JobRepository
from app.db.repositories.missions import PROJECT, MissionRecord, MissionRepository
from app.db.repositories.projects import ProjectRepository
from app.db.repositories.sites import MaskRepository, SiteRecord, SiteRepository
from app.services import audit_service, job_service, mission_service, settings_service
from app.services.auth_service import Claims
from app.services.mission_service import MissionNotFound

#: The job that builds a new target's skyline (the compute worker's handler).
SITE_BUILD = "site_build"
SITE_BUILD_CLOSURE = engine_closure("hz", "vis")
#: Cheap and a prerequisite for Surface and Contact: ahead of trips and launches.
SITE_BUILD_PRIORITY = 2
#: A project's own target site: ``project-<slug of the project id>``.
SITE_PREFIX = "project-"

ACCEPTED_EXTENSIONS = ("pdf", "docx", "txt", "md", "csv", "json")

INSTRUMENT_WORDS: dict[str, str] = {
    "volatiles": "Volatiles (water, ice, gases)",
    "geology_geophysics": "Geology and geophysics",
    "heat_flow": "Heat flow",
    "radiation_space_weather": "Radiation and space weather",
    "exosphere_dust": "Exosphere and dust",
    "imaging": "Imaging",
    "landing_navigation": "Landing and navigation",
    "communications": "Communications",
    "laser_retroreflector": "Laser retroreflector",
    "rover_mobility": "Rover and mobility",
    "technology_demo": "Technology demonstration",
    "other": "Other",
}

_RANGE_WORDS = {
    "eastern": "Eastern Range, Florida",
    "western": "Western Range, California",
    "tanegashima": "Tanegashima, Japan",
    "sriharikota": "Sriharikota, India",
    "guiana": "Guiana Space Centre",
    "wenchang": "Wenchang, China",
}
_MONTHS = (
    "January February March April May June July August September October November December"
).split()


class BadProject(ValueError):
    """The form cannot be saved as it is. ``field`` is the dotted path, ``message`` the why."""

    def __init__(self, message: str, field: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.field = field

    @property
    def errors(self) -> list[dict[str, str]]:
        return [{"field": self.field or "name", "message": self.message}]


class NotAProject(PermissionError):
    """A catalogue record was asked to change through the projects endpoints."""


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def slug(text: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")


def free_id(base: str, taken: set[str]) -> str:
    """``base``, or ``base-2``, ``base-3`` ... whichever is not taken."""
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def project_id_base(name: str) -> str:
    return "p-" + (slug(name)[:56].strip("-") or "project")


def _parse(text: str) -> datetime:
    t = text.strip().replace("Z", "+00:00").replace("z", "+00:00")
    if re.fullmatch(r"\d{4}", t):
        t += "-01-01"
    elif re.fullmatch(r"\d{4}-\d{2}", t):
        t += "-01"
    try:
        dt = datetime.fromisoformat(t if "T" in t or " " in t else t + "T00:00:00+00:00")
    except ValueError as exc:
        raise BadProject(f"'{text}' is not an ISO date or datetime") from exc
    return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)


def as_published(at: datetime, precision: str) -> str:
    """The words for a date the team gave, at its precision: 'Q3 2027', '14 March 2027'."""
    if precision == "year":
        return f"{at.year}"
    if precision == "quarter":
        return f"Q{(at.month - 1) // 3 + 1} {at.year}"
    if precision == "month":
        return f"{_MONTHS[at.month - 1]} {at.year}"
    day = f"{at.day} {_MONTHS[at.month - 1]} {at.year}"
    if precision == "day":
        return day
    if precision == "minute":
        return f"{day}, {at:%H:%M} UTC"
    return f"{day}, {at:%H:%M:%S} UTC"


def normalise_date(d: dict[str, Any] | None, field: str = "date") -> dict[str, Any] | None:
    """``{date, precision, as_published}`` stored as the mission file stores dates.

    The date is cut to its precision (a month is its first day, a quarter its
    first month), and ``as_published`` is written in words when it was not given.
    """
    if d is None:
        return None
    precision = str(d["precision"])
    try:
        at = _parse(str(d["date"]))
    except BadProject as exc:
        raise BadProject(exc.message, f"{field}.date" if field != "date" else "date") from exc
    if precision == "year":
        text = f"{at.year:04d}-01-01"
    elif precision == "quarter":
        text = f"{at.year:04d}-{(at.month - 1) // 3 * 3 + 1:02d}-01"
    elif precision == "month":
        text = f"{at.year:04d}-{at.month:02d}-01"
    elif precision == "day":
        text = f"{at:%Y-%m-%d}"
    elif precision == "minute":
        at = at.replace(second=0, microsecond=0)
        text = f"{at:%Y-%m-%dT%H:%M:00Z}"
    else:
        at = at.replace(microsecond=0)
        text = f"{at:%Y-%m-%dT%H:%M:%SZ}"
    words = (d.get("as_published") or "").strip() or as_published(at, precision)
    return {"date": text, "precision": precision, "as_published": words}


def _start(d: dict[str, Any] | None) -> datetime | None:
    return None if d is None else _parse(d["date"])


def lifecycle_of(
    lc: dict[str, Any] | None,
    status: str,
    launch: dict[str, Any] | None,
    intake_id: int | None,
) -> dict[str, Any]:
    """The v2 facts in the stored shape (``ingest_missions.lifecycle_of``), from the form.

    ``t0`` is the launch instant of a mission that has launched: set only when the
    status says it flew and the launch was given to the minute or better.
    """
    lc = lc or {}
    transfer = None
    if (
        lc.get("transfer_type")
        or lc.get("flight_days") is not None
        or (lc.get("lunar_orbit_days") is not None)
    ):
        transfer = {
            "type": lc.get("transfer_type") or "unknown",
            "flight_days": lc.get("flight_days"),
            "lunar_orbit_days": lc.get("lunar_orbit_days"),
        }
    descent = None
    if lc.get("sun_el_min_deg") is not None or lc.get("sun_el_max_deg") is not None:
        descent = {
            "sun_el_min_deg": lc.get("sun_el_min_deg"),
            "sun_el_max_deg": lc.get("sun_el_max_deg"),
            "earth_required": None,
        }
    bands = list(lc.get("bands") or [])
    stations = list(lc.get("ground_stations") or [])
    relays = list(lc.get("relays") or [])
    radio = {
        "eirp_dbw": lc.get("eirp_dbw"),
        "gt_dbk": lc.get("gt_dbk"),
        "frequency_mhz": lc.get("frequency_mhz"),
        "data_rates_kbps": list(lc.get("data_rates_kbps") or []),
        "required_ebn0_db": lc.get("required_ebn0_db"),
        "required_margin_db": lc.get("required_margin_db"),
        "eirp_tol_db": lc.get("eirp_tol_db"),
    }
    stated = any(v not in (None, []) for v in radio.values())
    comms = (
        {"bands": bands, "ground_stations": stations, "relays": relays, **radio}
        if bands or stations or relays or stated
        else None
    )
    mass = lc.get("mass_kg")
    spacecraft = {"mass_kg": mass, "area_m2": None, "cr": None} if mass is not None else None
    t0 = None
    if status != "planned" and launch is not None and launch["precision"] in ("minute", "second"):
        t0 = {
            "date": launch["date"],
            "precision": "minute",
            "as_published": launch["as_published"],
        }
    out: dict[str, Any] = {
        "vehicle_id": lc.get("vehicle_id"),
        "pad_id": lc.get("pad_id"),
        "t0": t0,
        "transfer": transfer,
        "descent": descent,
        "comms": comms,
        "spacecraft": spacecraft,
        "rovers": [],
        "returns": lc.get("returns"),
        # Entered facts have no URL; the mission's sources say who entered them.
        "field_sources": {},
    }
    if intake_id is not None:
        out["intake_id"] = intake_id
    return out


def unconfirmed(row: dict[str, Any], payloads: list[dict[str, Any]]) -> list[str]:
    """Every field left unknown, named as the mission file names them."""
    lc = row["lifecycle"]
    out = [f for f in NULLABLE_FIELDS if row.get(f) is None]
    out += [f for f in NULLABLE_FIELDS_V2 if lc.get(f) is None]
    for key, subs in NESTED_NULLABLE.items():
        value = lc.get(key)
        if value is not None:
            out += [f"{key}.{s}" for s in subs if value.get(s) is None]
    if not payloads:
        out.append("payloads")
    return sorted(out)


def data_version(row: dict[str, Any], payloads: list[dict[str, Any]]) -> str:
    """A content hash, so a changed fact gives every section a new key."""
    body = {k: v for k, v in row.items() if k not in ("sort_at", "data_version")}
    canonical = json.dumps(
        {"row": body, "payloads": payloads}, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def payload_rows(mission_id: str, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    taken: set[str] = set()
    for i, p in enumerate(payloads):
        pid = free_id(f"{mission_id}/{slug(p['name'])[:56].strip('-') or 'payload'}", taken)
        taken.add(pid)
        out.append(
            {
                "id": pid,
                "mission_id": mission_id,
                "position": i,
                "name": p["name"].strip(),
                "acronym": (p.get("acronym") or "").strip() or None,
                "organisation": (p.get("organisation") or "").strip() or None,
                "instrument_types": list(dict.fromkeys(p.get("instrument_types") or [])),
                "purpose": (p.get("purpose") or "").strip(),
                "source_url": "",
                "unconfirmed": False,
            }
        )
    return out


def _clean(text: Any) -> str | None:
    s = " ".join(str(text).split()) if text is not None else ""
    return s or None


def build_row(
    data: dict[str, Any],
    *,
    mission_id: str,
    target: dict[str, Any] | None,
    site_id: str | None,
    sources: list[dict[str, Any]],
    intake_id: int | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The mission row and payload rows for one project form (no I/O)."""
    status = data.get("status") or "planned"
    launch = normalise_date(data.get("launch"), "launch")
    landing = normalise_date(data.get("landing"), "landing")
    eom = normalise_date(data.get("end_of_mission"), "end_of_mission")
    _check_order(launch, landing, eom)
    lc = data.get("lifecycle") or {}
    lo, hi = lc.get("sun_el_min_deg"), lc.get("sun_el_max_deg")
    if lo is not None and hi is not None and lo > hi:
        raise BadProject(
            "the lowest Sun elevation is above the highest", "lifecycle.sun_el_min_deg"
        )
    first = landing or launch
    row: dict[str, Any] = {
        "id": mission_id,
        "name": " ".join(str(data["name"]).split()),
        "vehicle_name": _clean(data.get("vehicle_name")),
        "task_order": _clean(data.get("task_order")),
        "provider": _clean(data.get("provider")),
        "lander": _clean(data.get("lander")),
        "status": status,
        "outcome_note": "",
        "region": None if target is None else region_of(target["lat_deg"], target["lon_deg"]),
        "target_name": None if target is None else target["name"],
        "target": target,
        "ellipse": None,
        "launch": launch,
        "landing": landing,
        "end_of_mission": eom,
        "planned_surface_days": data.get("planned_surface_days"),
        "sort_at": None if first is None else _parse(first["date"]),
        "site_id": site_id,
        "sources": sources,
        "notes": [n.strip() for n in data.get("notes") or [] if n and n.strip()],
        "lifecycle": lifecycle_of(lc, status, launch, intake_id),
    }
    payloads = payload_rows(mission_id, list(data.get("payloads") or []))
    row["unconfirmed_fields"] = unconfirmed(row, payloads)
    row["data_version"] = data_version(row, payloads)
    return row, payloads


def _check_order(*dates: dict[str, Any] | None) -> None:
    """Launch, landing and end of mission, where each is known to the day, in order."""
    names = ("launch", "landing", "end_of_mission")
    exact = [
        (n, _parse(d["date"]))
        for n, d in zip(names, dates, strict=True)
        if d is not None and d["precision"] in ("second", "minute", "day")
    ]
    for (a, ta), (b, tb) in itertools.pairwise(exact):
        if tb.date() < ta.date():
            raise BadProject(f"{b.replace('_', ' ')} is before {a.replace('_', ' ')}", f"{b}.date")


def coordinate_name(lat: float, lon: float) -> str:
    return f"{abs(lat):.3f}° {'S' if lat < 0 else 'N'}, {lon % 360.0:.3f}° E"


def site_row(
    site_id: str, lat: float, lon: float, name: str, project_name: str, actor: str
) -> dict[str, Any]:
    """A new coordinate as a site of kind ``mission_target``, as ``ingest_missions`` writes one."""
    covered = is_terrain_covered(lat, lon)
    terrain = (
        "Inside the polar elevation model: the skyline is built from terrain by the compute "
        "worker."
        if covered
        else "No elevation model covers this point: height, slope and terrain are not modelled."
    )
    return {
        "id": site_id,
        "code": site_code(site_id),
        "name": name[:160],
        "region": region_of(lat, lon),
        "lat_deg": round(lat, 5),
        "lon_deg": round(lon % 360.0, 5),
        "elev_m": None,
        "slope_deg": None,
        "note": f"Target of the project {project_name}."[:2000],
        "anchor_lat_deg": lat,
        "anchor_lon_deg": lon % 360.0,
        "search_kind": "entered",
        "search_inner_km": 0.0,
        "search_outer_km": 0.0,
        "offset_from_anchor_km": 0.0,
        "source": f"Entered by {actor}"[:160],
        "source_url": "",
        "source_note": f"The coordinate as entered for this project; used as given, not "
        f"searched. {terrain}",
        "kind": "mission_target",
        "coordinate_rule": "published",
        "terrain_modelled": covered,
        "is_active": True,
    }


def _check_catalogue_ids(lc: dict[str, Any] | None) -> None:
    if not lc:
        return
    wanted = (
        ("vehicles", "lifecycle.vehicle_id", [lc.get("vehicle_id")]),
        ("launch_sites", "lifecycle.pad_id", [lc.get("pad_id")]),
        ("relays", "lifecycle.relays", list(lc.get("relays") or [])),
        ("ground_stations", "lifecycle.ground_stations", list(lc.get("ground_stations") or [])),
    )
    for cat, field, given in wanted:
        ids = [str(i) for i in given if i]
        if not ids:
            continue
        try:
            known = set(catalogues.load(cat).ids())
        except catalogues.CatalogueError as exc:
            raise BadProject(
                f"cannot be checked: the {cat} catalogue is unreadable", field
            ) from exc
        bad = [i for i in ids if i not in known]
        if bad:
            raise BadProject(f"{', '.join(bad)} is not in the {cat} catalogue", field)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def options(session: AsyncSession) -> dict[str, Any]:
    """Every choice the form offers: from the catalogues, the sites and the missions."""
    s = get_settings()

    def records(name: str) -> tuple[Any, ...]:
        try:
            return catalogues.load(name).records
        except catalogues.CatalogueError:
            return ()

    vehicles = [{"value": v.id, "label": v.name, "hint": v.provider} for v in records("vehicles")]
    pads = [
        {
            "value": p.id,
            "label": p.name,
            "hint": ", ".join(str(x) for x in (p.operator, _RANGE_WORDS.get(p.launch_range)) if x)
            or None,
        }
        for p in records("launch_sites")
    ]
    relays = [
        {
            "value": r.id,
            "label": r.name,
            "hint": ", ".join(str(x) for x in (r.operator, r.status.replace("_", " ")) if x)
            or None,
        }
        for r in records("relays")
        if r.role == "relay"
    ]
    sites, _ = await SiteRepository(session).list_sites(kind=None, limit=1000)
    site_opts = [
        {
            "value": x.id,
            "label": x.name,
            "hint": coordinate_name(x.lat_deg, x.lon_deg),
            "lat_deg": x.lat_deg,
            "lon_deg": x.lon_deg,
            "kind": x.kind if x.kind in ("candidate", "mission_target") else "mission_target",
        }
        for x in sorted(sites, key=lambda x: (x.kind != "candidate", x.name.lower()))
    ]
    missions = await MissionRepository(session).find()
    ai = await settings_service.ai_settings(session)
    return {
        "vehicles": vehicles,
        "pads": pads,
        "sites": site_opts,
        "providers": sorted({m.provider for m in missions if m.provider}, key=str.lower),
        "landers": sorted({m.lander for m in missions if m.lander}, key=str.lower),
        "instrument_types": [
            {"value": k, "label": v, "hint": None} for k, v in INSTRUMENT_WORDS.items()
        ],
        "relays": relays,
        "max_upload_bytes": s.max_upload_bytes,
        "accepted_extensions": list(ACCEPTED_EXTENSIONS),
        "model_reading": bool(s.agents_enabled and ai.enabled),
    }


async def list_projects(session: AsyncSession) -> dict[str, Any]:
    """The team's projects, newest first."""
    found = await MissionRepository(session).find(origin=PROJECT)
    floor = datetime.min.replace(tzinfo=UTC)
    found.sort(key=lambda m: (m.created_at or floor, m.id), reverse=True)
    items = await mission_service.briefs(session, found)
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


async def _sources(
    session: AsyncSession, who: Claims, intake_id: int | None
) -> list[dict[str, Any]]:
    today = datetime.now(UTC).date().isoformat()
    out: list[dict[str, Any]] = [
        {
            "url": "",
            "title": f"Entered in POLAR WINDOW by {who.actor}",
            "publisher": who.actor,
            "accessed": today,
            "kind": "entered",
        }
    ]
    if intake_id is not None:
        intake = await ProjectRepository(session).get_intake(intake_id)
        if intake is None:
            raise BadProject(f"there is no file reading {intake_id}", "intake_id")
        out.append(
            {
                "url": "",
                "title": intake.filename,
                "publisher": who.actor,
                "accessed": intake.created_at.date().isoformat(),
                "kind": "file",
            }
        )
    return out


async def _target(
    session: AsyncSession, who: Claims, mission_id: str, name: str, t: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, str | None, SiteRecord | dict[str, Any] | None, bool]:
    """(target JSON, site id, the site, whether its coordinate is new or changed)."""
    if t is None:
        return None, None, None, False
    if t.get("site_id"):
        site = await SiteRepository(session).get(t["site_id"])
        if site is None:
            raise BadProject(f"there is no site '{t['site_id']}'", "target.site_id")
        target = {
            "name": _clean(t.get("name")) or site.name,
            "lat_deg": site.lat_deg,
            "lon_deg": site.lon_deg % 360.0,
            "coordinate_kind": "planned_target",
            "source_url": site.source_url or "",
            "feature_id": None,
        }
        return target, site.id, site, False
    lat, lon = float(t["lat_deg"]), float(t["lon_deg"]) % 360.0
    site_id = SITE_PREFIX + mission_id.removeprefix("p-")
    label = _clean(t.get("name")) or coordinate_name(lat, lon)
    target = {
        "name": label,
        "lat_deg": lat,
        "lon_deg": lon,
        "coordinate_kind": "planned_target",
        "source_url": "",
        "feature_id": None,
    }
    existing = await SiteRepository(session).get(site_id)
    moved = existing is None or (
        abs(existing.lat_deg - round(lat, 5)) > 1e-9 or abs(existing.lon_deg - round(lon, 5)) > 1e-9
    )
    row = site_row(site_id, lat, lon, label, name, who.actor)
    await SiteRepository(session).upsert_many([row])
    if moved and existing is not None:
        # The old skyline and numbers describe another place now.
        await MaskRepository(session).delete(site_id)
        await ProjectRepository(session).forget_site_numbers(site_id)
    return target, site_id, row, moved


async def _site_job(
    session: AsyncSession, who: Claims, mission_id: str, site_id: str | None, moved: bool
) -> dict[str, Any] | None:
    """Queue the skyline of a target that has none (or whose coordinate just changed)."""
    if site_id is None:
        return None
    if not moved and await MaskRepository(session).get(site_id, ENGINE_VERSION) is not None:
        return None
    params = {"site_id": site_id}
    job = await JobRepository(session).enqueue(
        kind=SITE_BUILD,
        params=params,
        params_hash=job_service.params_hash(SITE_BUILD, SITE_BUILD_CLOSURE, params),
        closure=SITE_BUILD_CLOSURE,
        mission_id=mission_id,
        requested_by=who.user_id,
        priority=SITE_BUILD_PRIORITY,
    )
    return job_service.job_ref(job)


def _audit_view(row: dict[str, Any], payloads: list[dict[str, Any]]) -> dict[str, Any]:
    keep = {k: v for k, v in row.items() if k not in ("sort_at", "sources")}
    return {**keep, "payloads": [p["name"] for p in payloads]}


def _record_view(m: MissionRecord) -> dict[str, Any]:
    return {
        "name": m.name,
        "status": m.status,
        "provider": m.provider,
        "lander": m.lander,
        "site_id": m.site_id,
        "launch": m.launch,
        "landing": m.landing,
        "data_version": m.data_version,
    }


async def _drop_own_site(session: AsyncSession, mission_id: str, site_id: str | None) -> None:
    """Remove a project's own target site once nothing targets it."""
    if site_id is None or not site_id.startswith(SITE_PREFIX):
        return
    repo = ProjectRepository(session)
    if not await repo.site_in_use(site_id, other_than=mission_id):
        await repo.delete_site(site_id)


async def create(session: AsyncSession, who: Claims, data: dict[str, Any]) -> dict[str, Any]:
    """Save a new project. ``{mission, site_job}``."""
    if not who.named:
        raise audit_service.NotNamed("Changes are recorded against a name; this session has none.")
    _check_catalogue_ids(data.get("lifecycle"))
    repo = ProjectRepository(session)
    base = project_id_base(str(data["name"]))
    mission_id = free_id(base, await repo.ids_starting(base))
    intake_id = data.get("intake_id")
    sources = await _sources(session, who, intake_id)
    target, site_id, _site, moved = await _target(
        session, who, mission_id, str(data["name"]), data.get("target")
    )
    row, payloads = build_row(
        data,
        mission_id=mission_id,
        target=target,
        site_id=site_id,
        sources=sources,
        intake_id=intake_id,
    )
    await repo.insert(row, payloads, who.user_id)
    site_job = await _site_job(session, who, mission_id, site_id, moved)
    await audit_service.record(
        session,
        who,
        action="create",
        entity="project",
        entity_id=mission_id,
        before=None,
        after=_audit_view(row, payloads),
        note=f"Read from file reading {intake_id}." if intake_id else None,
        mission_id=mission_id,
    )
    return {"mission": await mission_service.get_mission(session, mission_id), "site_job": site_job}


async def _project(session: AsyncSession, mission_id: str) -> MissionRecord:
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    if m.origin != PROJECT:
        raise NotAProject(mission_id)
    return m


async def get(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    """One project as a mission (``MissionDetail``)."""
    await _project(session, mission_id)
    return await mission_service.get_mission(session, mission_id)


async def update(
    session: AsyncSession, who: Claims, mission_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Replace a project's facts with the form as given. ``{mission, site_job}``."""
    if not who.named:
        raise audit_service.NotNamed("Changes are recorded against a name; this session has none.")
    before = await _project(session, mission_id)
    _check_catalogue_ids(data.get("lifecycle"))
    intake_id = data.get("intake_id")
    if intake_id is None:
        intake_id = before.lifecycle.get("intake_id")
    sources = await _sources(session, who, intake_id)
    target, site_id, _site, moved = await _target(
        session, who, mission_id, str(data["name"]), data.get("target")
    )
    row, payloads = build_row(
        data,
        mission_id=mission_id,
        target=target,
        site_id=site_id,
        sources=sources,
        intake_id=intake_id,
    )
    if not await ProjectRepository(session).replace(mission_id, row, payloads):
        raise NotAProject(mission_id)
    if before.site_id != site_id:
        await _drop_own_site(session, mission_id, before.site_id)
    site_job = await _site_job(session, who, mission_id, site_id, moved)
    await audit_service.record(
        session,
        who,
        action="update",
        entity="project",
        entity_id=mission_id,
        before=_record_view(before),
        after=_audit_view(row, payloads),
        mission_id=mission_id,
    )
    return {"mission": await mission_service.get_mission(session, mission_id), "site_job": site_job}


async def rebuild_skyline(session: AsyncSession, who: Claims, mission_id: str) -> dict[str, Any]:
    """Queue the skyline of a project's target again, e.g. after a failed build.

    A running or waiting build is joined, not doubled; a failed one never blocks a new
    one (the queue only dedupes live jobs). ``{mission, site_job}``; ``site_job`` is
    None when the skyline is already built.
    """
    if not who.named:
        raise audit_service.NotNamed("Changes are recorded against a name; this session has none.")
    m = await _project(session, mission_id)
    if m.site_id is None:
        raise BadProject("this project has no target to map", "target")
    site_job = await _site_job(session, who, mission_id, m.site_id, False)
    return {"mission": await mission_service.get_mission(session, mission_id), "site_job": site_job}


async def delete(session: AsyncSession, who: Claims, mission_id: str) -> dict[str, Any]:
    """Remove a project (never a catalogue record). ``{id, deleted}``."""
    if not who.named:
        raise audit_service.NotNamed("Changes are recorded against a name; this session has none.")
    before = await _project(session, mission_id)
    if not await ProjectRepository(session).delete(mission_id):
        raise NotAProject(mission_id)
    await _drop_own_site(session, mission_id, before.site_id)
    await audit_service.record(
        session,
        who,
        action="delete",
        entity="project",
        entity_id=mission_id,
        before=_record_view(before),
        after=None,
        mission_id=mission_id,
    )
    return {"id": mission_id, "deleted": True}
