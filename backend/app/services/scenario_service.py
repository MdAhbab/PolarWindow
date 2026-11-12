"""Scenarios: what a mission would show if its missing facts were assumed (never saved).

A scenario never writes to the mission's record. It lays assumed values over an
in-memory copy of the record and runs the same launch, trip, contact and return
calculations on it, inside one job kind, ``scenario``, in the compute worker
(``workers/handlers/scenario.py``). This module is the API side: what is missing
(``gaps``), turning a reading of a prompt into assumptions (``interpret``),
starting or joining a scenario (``start``), and reading one back.

Every value carries its basis, tried in this order: ``you`` -> ``published`` ->
``live`` -> ``default``. Live values are fetched only by the compute worker (it
passes them to ``resolve_all``); nothing here touches the network. A field with
no basis is a gap, left out and said, never guessed.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import engine_closure
from app.core import scenario as core
from app.core.scenario import Candidate, FlightRow, Resolved
from app.data import catalogues
from app.db.repositories.jobs import AssessmentRepository, JobRepository
from app.db.repositories.missions import MissionRecord, MissionRepository
from app.db.repositories.pm import PmRepository
from app.db.repositories.scenarios import ScenarioRecord, ScenarioRepository
from app.db.repositories.sites import SiteRecord, SiteRepository
from app.services import (
    audit_service,
    job_service,
    mission_service,
    ready_service,
    sections_service,
)
from app.services.auth_service import Claims
from app.services.mission_service import MissionNotFound

KIND = "scenario"
#: Below every real job (those run at 0 to 3); presets below a scenario somebody asked for.
PRIORITY_ASKED = -1
PRIORITY_PRESET = -2
CLOSURE = engine_closure("lw", "traj", "vis", "net", "link", "ecl", "rad", "wx")
#: Direct flights to the Moon in the launch calendar take 3.5 to 6.5 days; a few more days are
#: spent in lunar orbit. Launches this long before an assumed landing are looked at.
LAUNCH_LEAD_DAYS = (10, 2)
POLL = {"queued": 3.0, "running": 2.0, "done": 0.0, "failed": 0.0}


class ScenarioNotFound(LookupError):
    pass


class BadScenario(ValueError):
    """The request cannot be used; the message says why in plain words."""


class Refused(ValueError):
    """The request is understood and not allowed; the message says why."""


# ---------------------------------------------------------------------------
# Names, options and precedents
# ---------------------------------------------------------------------------


async def names(session: AsyncSession) -> dict[str, dict[str, str]]:
    sites, _ = await SiteRepository(session).list_sites(limit=500)
    return {
        "vehicles": {r.id: r.name for r in catalogues.load("vehicles").records},
        "pads": {r.id: r.name for r in catalogues.load("launch_sites").records},
        "relays": {r.id: r.name for r in catalogues.load("relays").records if r.role == "relay"},
        "sites": {s.id: core.site_words(s.name) for s in sites},
    }


def _options(field_id: str, nm: dict[str, dict[str, str]]) -> list[dict[str, Any]] | None:
    if field_id == "vehicle_id":
        by = {r.id: r.provider for r in catalogues.load("vehicles").records}
        return [{"value": k, "label": v, "hint": by.get(k)} for k, v in nm["vehicles"].items()]
    if field_id == "pad_id":
        by = {r.id: r.operator for r in catalogues.load("launch_sites").records}
        return [{"value": k, "label": v, "hint": by.get(k)} for k, v in nm["pads"].items()]
    if field_id == "site_id":
        return [{"value": k, "label": v, "hint": None} for k, v in nm["sites"].items()]
    if field_id == "relays":
        return [{"value": k, "label": v, "hint": None} for k, v in nm["relays"].items()]
    if field_id == "transfer_type":
        return [{"value": k, "label": v, "hint": None} for k, v in core.TRANSFER_TYPES.items()]
    return None


async def flight_rows(session: AsyncSession, exclude: str) -> list[FlightRow]:
    """Missions that have launched, with the vehicle and pad they used: the precedents."""
    out = []
    for r in await MissionRepository(session).find(statuses=sorted(ready_service.FLOWN)):
        lc = r.lifecycle or {}
        if r.id == exclude or not (lc.get("vehicle_id") or lc.get("pad_id")):
            continue
        when = ((r.landing or r.launch or {}).get("date") or "")[:10]
        out.append(
            FlightRow(
                r.id, r.name, r.provider, r.lander, when, lc.get("vehicle_id"), lc.get("pad_id")
            )
        )
    return out


def _source_of(m: MissionRecord) -> tuple[str, str | None]:
    s = (m.sources or [{}])[0]
    url = s.get("url") or None
    return ("Mission record" if not s.get("title") else str(s["title"])[:120], url)


def published(m: MissionRecord) -> dict[str, Candidate]:
    """What the mission's record says, per field."""
    lc = m.lifecycle or {}
    src, url = _source_of(m)
    out: dict[str, Candidate] = {}

    def put(fid: str, value: Any, note: str | None = None) -> None:
        if value not in (None, "", []):
            out[fid] = Candidate(value, src, url, None, note)

    put("vehicle_id", lc.get("vehicle_id"))
    put("pad_id", lc.get("pad_id"))
    put("site_id", m.site_id)
    if m.landing and m.landing.get("precision") in ("second", "minute", "day"):
        put(
            "landing_date",
            str(m.landing["date"])[:10],
            f"Published as {m.landing['as_published']}.",
        )
    put("surface_days", m.planned_surface_days)
    if lc.get("transfer_type") in core.TRANSFER_TYPES:
        put("transfer_type", lc.get("transfer_type"))
    put("relays", list((lc.get("comms") or {}).get("relays") or []))
    return out


async def defaults(
    session: AsyncSession,
    m: MissionRecord,
    chosen: dict[str, Any],
    rows: list[FlightRow] | None = None,
) -> dict[str, Candidate]:
    """The named precedents and rules used when nothing else has a value.

    ``chosen`` holds the values already settled (so the default pad follows the vehicle)."""
    rows = await flight_rows(session, m.id) if rows is None else rows
    out: dict[str, Candidate] = {}
    veh = core.default_vehicle(m.provider, m.lander, rows)
    if veh:
        out["vehicle_id"] = veh
    vehicle_id = chosen.get("vehicle_id") or (veh.value if veh else None)
    pads: list[str] = []
    if vehicle_id:
        try:
            pads = list(catalogues.load("vehicles").get(str(vehicle_id)).pads)
        except KeyError:
            pads = []
    pad = core.default_pad(vehicle_id, m.provider, m.lander, rows, pads)
    if pad:
        out["pad_id"] = pad
    if m.landing and m.landing.get("precision") not in ("second", "minute", "day"):
        out["landing_date"] = Candidate(
            str(m.landing["date"])[:10],
            "Mission record",
            note=f"The record says '{m.landing['as_published']}'; its first day is used.",
        )
    out["surface_days"] = Candidate(
        mission_service.LUNAR_DAYLIGHT_S / 86400.0,
        "Surface window rule",
        note="One lunar daylight period (14.8 days), the span used when the duration is not "
        "published; rounded to the nearest half day.",
    )
    out["transfer_type"] = Candidate(
        "direct",
        "Launch calendar",
        note="The launch calendar designs direct transfers.",
    )
    stored = await PmRepository(session).parameters()
    for fid, pid in (
        ("sun_el_min_deg", "landing_sun_min_deg"),
        ("sun_el_max_deg", "landing_sun_max_deg"),
    ):
        row = stored.get(pid)
        if row is not None:
            out[fid] = Candidate(
                float(row["value"]),
                "Settings: project parameters",
                note=f"Entered by {row['changed_by']}.",
            )
    return out


def _launch_window(chosen: dict[str, Any], today: date) -> dict[str, Candidate]:
    if "launch_from" in chosen and "launch_to" in chosen:
        return {}
    landing = chosen.get("landing_date")
    if "launch_from" in chosen:
        a = date.fromisoformat(str(chosen["launch_from"])[:10])
        b = a + timedelta(days=90)
        note = "90 days from the first day, as the launch page does."
        src = "Launch calendar"
    elif "launch_to" in chosen:
        b = date.fromisoformat(str(chosen["launch_to"])[:10])
        a = b - timedelta(days=90)
        note = "90 days before the last day, as the launch page does."
        src = "Launch calendar"
    elif landing is not None:
        d = date.fromisoformat(str(landing)[:10])
        a, b = d - timedelta(days=LAUNCH_LEAD_DAYS[0]), d - timedelta(days=LAUNCH_LEAD_DAYS[1])
        note = (
            f"Direct flights take 3.5 to 6.5 days, so launches {LAUNCH_LEAD_DAYS[0]} to "
            f"{LAUNCH_LEAD_DAYS[1]} days before the landing are looked at."
        )
        src = "Launch calendar"
    else:
        a, b = today, today + timedelta(days=90)
        note = "The next 90 days, as the launch page does when no dates are chosen."
        src = "Launch calendar"
    out = {}
    if "launch_from" not in chosen:
        out["launch_from"] = Candidate(a.isoformat(), src, note=note)
    if "launch_to" not in chosen:
        out["launch_to"] = Candidate(b.isoformat(), src, note=note)
    return out


async def resolve_all(
    session: AsyncSession,
    m: MissionRecord,
    given: dict[str, Any],
    live: dict[str, Candidate] | None = None,
    today: date | None = None,
) -> list[Resolved]:
    """Every field that has a value, each with its basis. Fields with none are left out."""
    today = today or datetime.now(UTC).date()
    live = live or {}
    pub = published(m)
    rows = await flight_rows(session, m.id)
    chosen: dict[str, Any] = {}
    out: dict[str, Resolved] = {}

    def settle(fid: str, dflt: dict[str, Candidate]) -> None:
        r = core.resolve(
            fid, given=given, published=pub.get(fid), live=live.get(fid), default=dflt.get(fid)
        )
        if r is not None:
            out[fid] = r
            chosen[fid] = r.value

    # Order matters: the default pad follows the vehicle; the launch window follows the landing.
    base = await defaults(session, m, {}, rows)
    settle("vehicle_id", base)
    dflt = await defaults(session, m, chosen, rows)
    for fid in ("pad_id", "site_id", "landing_date", "surface_days", "transfer_type"):
        settle(fid, dflt)
    for fid in ("launch_from", "launch_to"):
        settle(fid, {})  # only what was said or fetched; the rest follows from these
    window = _launch_window(chosen, today)
    for fid in ("launch_from", "launch_to"):
        if fid not in out:
            settle(fid, window)
    for fid in ("sun_el_min_deg", "sun_el_max_deg", "relays"):
        settle(fid, dflt)
    return [out[f] for f in core.FIELD_IDS if f in out]


# ---------------------------------------------------------------------------
# The overlay (never saved)
# ---------------------------------------------------------------------------


def overlay(m: MissionRecord, res: list[Resolved], site: SiteRecord | None) -> MissionRecord:
    """The mission with the resolved values laid over it. A copy: the record is untouched."""
    v = {r.field: r.value for r in res}
    lc = dict(m.lifecycle or {})
    for key, fid in (
        ("vehicle_id", "vehicle_id"),
        ("pad_id", "pad_id"),
        ("transfer_type", "transfer_type"),
    ):
        if fid in v:
            lc[key] = v[fid]
    if "relays" in v:
        lc["comms"] = {**(lc.get("comms") or {}), "relays": list(v["relays"])}
    changes: dict[str, Any] = {"lifecycle": lc}
    if site is not None:
        changes.update(
            site_id=site.id,
            target_name=site.name,
            target={
                **(m.target or {}),
                "lat_deg": site.lat_deg,
                "lon_deg": site.lon_deg,
                "name": site.name,
            },
        )
    if "landing_date" in v:
        changes["landing"] = {
            "date": f"{v['landing_date']}T00:00:00Z",
            "precision": "day",
            "as_published": f"{v['landing_date']} (assumed)",
        }
    if "surface_days" in v:
        changes["planned_surface_days"] = float(v["surface_days"])
        changes["end_of_mission"] = None
    return dataclasses.replace(m, **changes)


def can_run(section: str, res: list[Resolved]) -> bool:
    return section != "trip" and not core.missing_for(section, [r.field for r in res])


# ---------------------------------------------------------------------------
# Wire shapes
# ---------------------------------------------------------------------------


def assumption_dict(r: Resolved, nm: dict[str, dict[str, str]]) -> dict[str, Any]:
    spec = core.SPEC_BY_ID[r.field]
    source = None
    if r.basis != "you" and r.source:
        source = {"name": r.source, "url": r.url, "fetched_at": r.fetched_at}
    return {
        "field": r.field,
        "label": spec.label,
        "value": r.value,
        "display": core.display(r.field, r.value, nm),
        "unit": spec.unit,
        "basis": r.basis,
        "source": source,
        "note": r.note,
    }


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def brief(r: ScenarioRecord) -> dict[str, Any]:
    return {
        "id": r.id,
        "mission_id": r.mission_id,
        "name": r.name,
        "prompt": r.prompt,
        "status": r.status,
        "progress": r.progress,
        "message": r.message,
        "preset": r.preset,
        "sections": list(r.sections),
        "created_at": _iso(r.created_at),
        "created_by_name": r.created_by_name,
    }


def full(r: ScenarioRecord) -> dict[str, Any]:
    return {
        **brief(r),
        "assumptions": r.assumptions,
        "phases": r.phases,
        "summaries": {k: str(v) for k, v in r.summaries.items()},
        "results": r.results if r.status == "done" else None,
        "poll_after_s": POLL.get(r.status, 3.0),
        "error": r.error,
    }


async def _mission(session: AsyncSession, mission_id: str) -> MissionRecord:
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    return m


# ---------------------------------------------------------------------------
# GET /missions/{id}/scenarios/gaps
# ---------------------------------------------------------------------------


def suggestions(m: MissionRecord, res: list[Resolved], nm: dict[str, dict[str, str]]) -> list[str]:
    v = {r.field: r.value for r in res}
    veh = nm["vehicles"].get(str(v.get("vehicle_id")), None)
    pad = nm["pads"].get(str(v.get("pad_id")), None)
    out = []
    if veh and pad:
        out.append(f"Launch on {veh} from {pad}")
    others = [n for k, n in nm["vehicles"].items() if k != v.get("vehicle_id")]
    if others:
        out.append(f"What if it launched on {others[0]} instead?")
    out.append("Land next month with 10 days on the surface")
    out.append("Use a direct transfer and 14 days on the surface")
    return out[:4]


async def gaps(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    m = await _mission(session, mission_id)
    nm = await names(session)
    states = {
        s["section"]: s["state"] for s in (await sections_service.sections_for(session, m))["data"]
    }
    res = await resolve_all(session, m, {})
    pub = published(m)
    gap_rows = []
    for s in core.SECTIONS:
        missing = [
            {
                "field": f,
                "label": core.SPEC_BY_ID[f].label,
                "why": core.WHY.get(f, f"{core.SPEC_BY_ID[f].label} is not published."),
            }
            for f in core.REQUIRED[s]
            if f not in pub
        ]
        if s == "trip":
            missing = [
                {
                    "field": "launch_from",
                    "label": "Launch time",
                    "why": "The trip is worked out from a launch time, and a designed trip is "
                    "not worked out yet.",
                }
            ]
        gap_rows.append(
            {
                "section": s,
                "state": states.get(s, "no_data"),
                "missing": missing,
                "can_explore": bool(missing) and can_run(s, res),
            }
        )
    by_field = {r.field: r for r in res}
    fields = []
    for spec in core.SPECS:
        d = by_field.get(spec.id)
        fields.append(
            {
                "field": spec.id,
                "label": spec.label,
                "help": spec.help,
                "kind": spec.kind,
                "unit": spec.unit,
                "options": _options(spec.id, nm),
                "min": spec.min,
                "max": spec.max,
                "default": assumption_dict(d, nm) if d is not None and d.basis != "you" else None,
                "sections": list(spec.sections),
            }
        )
    listed = await ScenarioRepository(session).for_mission(m.id)
    return {
        "mission_id": m.id,
        "gaps": gap_rows,
        "fields": fields,
        "presets": [brief(r) for r in listed if r.preset],
        "suggestions": suggestions(m, res, nm),
    }


# ---------------------------------------------------------------------------
# POST /missions/{id}/scenarios/interpret
# ---------------------------------------------------------------------------


async def reading_context(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    """What a reader needs to turn words into values: the choices and the mission's facts."""
    m = await _mission(session, mission_id)
    nm = await names(session)
    today = datetime.now(UTC).date()
    months = []
    for i in range(18):
        first = core.add_months(date(today.year, today.month, 1), i)
        a, b = core.month_span(first.year, first.month)
        months.append(
            {
                "name": f"{first.strftime('%B')} {first.year}",
                "first_day": a.isoformat(),
                "last_day": b.isoformat(),
            }
        )
    pub = published(m)
    return {
        "mission_id": m.id,
        "mission_name": m.name,
        "today": today.isoformat(),
        "vehicles": nm["vehicles"],
        "pads": nm["pads"],
        "relays": nm["relays"],
        "transfer_types": core.TRANSFER_TYPES,
        "months": months,
        "published": {k: c.value for k, c in pub.items()},
    }


async def _matching_preset(
    session: AsyncSession, m: MissionRecord, given: dict[str, Any], res: list[Resolved]
) -> str | None:
    """A preset this reading equals: the same assumptions, or the same values once resolved."""
    repo = ScenarioRepository(session)
    hit = await repo.by_key(core.scenario_key(m.id, core.SECTIONS, given))
    if hit is not None and hit.preset:
        return hit.id
    mine = {r.field: r.value for r in res}
    for p in await repo.for_mission(m.id):
        if p.preset and {r.field: r.value for r in await resolve_all(session, m, p.given)} == mine:
            return p.id
    return None


async def interpreted(
    session: AsyncSession, mission_id: str, reading: core.Reading, section: str | None = None
) -> dict[str, Any]:
    m = await _mission(session, mission_id)
    nm = await names(session)
    values = {k: v for k, v in reading.values.items() if k in core.SPEC_BY_ID}
    problems = core.validate(values)
    unresolved = list(reading.unresolved) + problems
    if problems:
        values = {
            k: v
            for k, v in values.items()
            if not any(core.SPEC_BY_ID[k].label in p for p in problems)
        }
    given = core.canonical(values)
    res = await resolve_all(session, m, given)
    preset = await _matching_preset(session, m, given, res)
    said = reading.interpreted_as or (
        "Read as: "
        + "; ".join(
            f"{core.SPEC_BY_ID[k].label} {core.display(k, v, nm)}" for k, v in given.items()
        )
        + "."
        if given
        else "Nothing in the prompt could be turned into a value."
    )
    if reading.notes:
        said = f"{said} {' '.join(reading.notes)}"
    return {
        "assumptions": [assumption_dict(r, nm) for r in res],
        "interpreted_as": said,
        "unresolved": unresolved,
        "method": reading.method,
        "matches_preset": preset,
    }


# ---------------------------------------------------------------------------
# POST /missions/{id}/scenarios
# ---------------------------------------------------------------------------


def job_params(m: MissionRecord, rec: ScenarioRecord) -> dict[str, Any]:
    return {
        "scenario_id": rec.id,
        "mission_id": m.id,
        "data_version": m.data_version,
        "given": rec.given,
        "sections": rec.sections,
        "catalogues": [
            catalogues.load(c).version
            for c in ("vehicles", "launch_sites", "relays", "ground_stations")
        ],
    }


async def enqueue(
    session: AsyncSession,
    m: MissionRecord,
    rec: ScenarioRecord,
    who: Claims | None,
    fresh: bool = False,
) -> ScenarioRecord:
    """Queue the work, or finish at once from an answer already stored for this key.

    A stored answer with a step that failed is not an answer: the work runs again.
    """
    repo = ScenarioRepository(session)

    async def ask(again: bool) -> job_service.Answer:
        return await job_service.answer_or_enqueue(
            session,
            kind=KIND,
            closure=CLOSURE,
            params=job_params(m, rec),
            mission_id=m.id,
            requested_by=who.user_id if who else None,
            priority=PRIORITY_PRESET if rec.preset else PRIORITY_ASKED,
            fresh=again,
        )

    ans = await ask(fresh)
    if ans.assessment is not None and core.failed_phases(ans.assessment.result.get("phases", [])):
        ans = await ask(True)
    if ans.assessment is not None:
        r = ans.assessment.result
        status, message = core.outcome(r["phases"], r.get("message", "Worked out."))
        await repo.finish(
            rec.id,
            results=r["results"],
            summaries=r["summaries"],
            assumptions=r["assumptions"],
            phases=r["phases"],
            message=message,
            status=status,
        )
    elif ans.job is not None:
        await repo.set_job(rec.id, int(ans.job["job_id"]))
        if ans.job["status"] == "failed":
            await repo.fail(rec.id, str(ans.job["message"]))
    found = await repo.get(rec.id)
    assert found is not None
    return found


async def create(
    session: AsyncSession,
    m: MissionRecord,
    *,
    given: dict[str, Any],
    sections: list[str],
    name: str | None,
    prompt: str | None,
    who: Claims | None,
    preset: bool = False,
) -> tuple[ScenarioRecord, bool]:
    """Start a scenario, or find the one with the same canonical assumptions. ``(row, created)``."""
    nm = await names(session)
    key = core.scenario_key(m.id, sections, given)
    repo = ScenarioRepository(session)
    rec, created = await repo.create(
        scenario_id=core.scenario_id(key),
        mission_id=m.id,
        key=key,
        name=(name or "").strip() or core.scenario_name(given, nm),
        prompt=prompt,
        given=given,
        sections=sorted(sections, key=core.SECTIONS.index),
        preset=preset,
        phases=core.phases(sections),
        created_by=who.user_id if who else None,
        created_by_name=who.actor if who else None,
    )
    if created:
        rec = await enqueue(session, m, rec, who)
    elif rec.status == "failed" or core.failed_phases(rec.phases):
        # Stored as failed, or "done" with a step that could not be worked out: neither
        # is an answer to join; the same scenario runs again.
        await repo.requeue(rec.id, core.phases(rec.sections))
        rec = await enqueue(session, m, rec, who, fresh=True)
    return rec, created


async def start(
    session: AsyncSession, who: Claims, mission_id: str, body: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    """``(created, scenario)``: 201 for a new scenario, 200 for one with the same assumptions."""
    m = await _mission(session, mission_id)
    raw = {a["field"]: a.get("value") for a in body.get("assumptions") or []}
    unknown = [f for f in raw if f not in core.SPEC_BY_ID]
    if unknown:
        raise BadScenario(f"'{unknown[0]}' is not something a scenario can assume.")
    problems = core.validate(raw)
    if problems:
        raise BadScenario(" ".join(problems))
    given = core.canonical(raw)
    sections = list(dict.fromkeys(body.get("sections") or core.SECTIONS))
    res = await resolve_all(session, m, given)
    if not any(can_run(s, res) for s in sections):
        needed = sorted({f for s in sections for f in core.missing_for(s, [r.field for r in res])})
        words = ", ".join(core.SPEC_BY_ID[f].label.lower() for f in needed) or "more values"
        raise BadScenario(
            f"Nothing can be worked out from these assumptions yet: {words} still have no "
            "value and no named precedent. Set them to continue."
        )
    rec, created = await create(
        session,
        m,
        given=given,
        sections=sections,
        name=body.get("name"),
        prompt=body.get("prompt"),
        who=who,
    )
    if created:
        await audit_service.record(
            session,
            who,
            action="create",
            entity="scenario",
            entity_id=rec.id,
            mission_id=m.id,
            before=None,
            after={"name": rec.name, "assumptions": given, "sections": rec.sections},
        )
    return created, full(rec)


# ---------------------------------------------------------------------------
# Reading back
# ---------------------------------------------------------------------------


async def _sync(session: AsyncSession, rec: ScenarioRecord) -> ScenarioRecord:
    """Bring up to date a scenario whose job ended without the row hearing of it."""
    if rec.status not in ("queued", "running") or rec.job_id is None:
        return rec
    job = await JobRepository(session).get(rec.job_id)
    repo = ScenarioRepository(session)
    if job is None:
        return rec
    if job.status == "failed":
        await repo.fail(rec.id, (job.error or "The job failed.").splitlines()[0])
    elif job.status == "done" and job.assessment_id is not None:
        a = await AssessmentRepository(session).get(job.assessment_id)
        if a is not None:
            r = a.result
            status, message = core.outcome(r["phases"], r.get("message", "Worked out."))
            await repo.finish(
                rec.id,
                results=r["results"],
                summaries=r["summaries"],
                assumptions=r["assumptions"],
                phases=r["phases"],
                message=message,
                status=status,
            )
    else:
        return rec
    return (await repo.get(rec.id)) or rec


async def get(session: AsyncSession, scenario_id: str) -> dict[str, Any]:
    rec = await ScenarioRepository(session).get(scenario_id)
    if rec is None:
        raise ScenarioNotFound(scenario_id)
    return full(await _sync(session, rec))


async def listing(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    m = await _mission(session, mission_id)
    rows = await ScenarioRepository(session).for_mission(m.id)
    return {"items": [brief(await _sync(session, r)) for r in rows]}


async def delete(session: AsyncSession, who: Claims, scenario_id: str) -> dict[str, Any]:
    repo = ScenarioRepository(session)
    rec = await repo.get(scenario_id)
    if rec is None:
        raise ScenarioNotFound(scenario_id)
    if rec.preset:
        raise Refused(
            "A preset is worked out ahead of time for everyone and cannot be deleted. "
            "Save your own scenario to change it."
        )
    await repo.delete(scenario_id)
    await audit_service.record(
        session,
        who,
        action="delete",
        entity="scenario",
        entity_id=scenario_id,
        mission_id=rec.mission_id,
        before={"name": rec.name, "assumptions": rec.given, "sections": rec.sections},
        after=None,
    )
    return {"id": scenario_id, "deleted": True}
