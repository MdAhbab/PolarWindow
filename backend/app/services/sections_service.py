"""The mission hub's six steps and one plain sentence for each (never a verdict).

``GET /missions/{id}/sections`` answers quickly and computes nothing heavy:
each step's state comes from the records, the catalogues and any stored
answer, and a step whose answer is still being worked out says so.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ENGINE_VERSION
from app.db.repositories.missions import MissionRecord, MissionRepository
from app.db.repositories.scenarios import ScenarioRepository
from app.db.repositories.sites import MaskRepository
from app.services import lifecycle, mission_service, ready_service
from app.services.mission_service import MissionNotFound


def _status(
    section: str, state: str, summary: str, as_of: datetime | None = None
) -> dict[str, Any]:
    return {"section": section, "state": state, "summary": summary, "as_of": as_of}


def _when(text: str) -> str:
    t = lifecycle.parse_time(text)
    date = f"{t.day} {t.strftime('%b %Y')}"
    return f"{date} {t.strftime('%H:%M')} UTC" if "T" in text else date


async def skyline_gate(
    session: AsyncSession, section: str, m: MissionRecord
) -> dict[str, Any] | None:
    """An honest status for a step that needs the landing spot's skyline, when it has none.

    None when the skyline is built (or the mission has no landing spot). Otherwise the
    state says what is happening: ``computing`` with the job's number while it is built,
    ``no_data`` with the reason when the build failed or was never started.
    """
    if m.site_id is None:
        return None
    if m.site_id in await MaskRepository(session).existing_site_ids(ENGINE_VERSION):
        return None
    from sqlalchemy import text

    row = (
        await session.execute(
            text(
                "SELECT id, status, error, coalesce(finished_at, created_at) AS last_at "
                "FROM jobs WHERE kind = 'site_build' AND mission_id = :m "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"m": m.id},
        )
    ).one_or_none()
    if row is not None and row.status in ("queued", "running"):
        return _status(
            section,
            "computing",
            f"The skyline at this spot is still being mapped (job {row.id}).",
            row.last_at,
        )
    if row is not None and row.status == "failed":
        # First line only, and without the exception class the worker prefixes.
        why = str(row.error or "").splitlines()[0] if row.error else ""
        why = re.sub(r"^[A-Za-z_][\w.]*: ", "", why)
        return _status(
            section,
            "no_data",
            f"The skyline at this spot could not be mapped: {why or 'the build failed'}"
            f" (job {row.id}).",
            row.last_at,
        )
    return _status(section, "no_data", "The skyline at this spot has not been mapped yet.")


async def _ready(session: AsyncSession, m: MissionRecord) -> dict[str, Any]:
    if m.status in ready_service.CANCELLED:
        return _status("ready", "not_applicable", "This delivery was cancelled.")
    rows = await ready_service.items(session, m)
    n = len(rows)
    known = [r for r, k in rows if k]
    blocked = sum(r.state == "blocked" for r in known)
    ready = sum(r.state == "ready" for r in known)
    if m.status in ready_service.FLOWN and all(r.source == "public" for r, _ in rows):
        return _status("ready", "available", f"All {n} items flew; nothing was entered after.")
    if not any(r.source == "entered" or r.changed_by for r in known):
        return _status("ready", "needs_input", f"{n} items; no states entered yet.")
    parts = [f"{len(known)} of {n} items have a state", f"{ready} ready"]
    if blocked:
        parts.append(f"{blocked} blocked")
    return _status("ready", "available", "; ".join(parts) + ".")


async def _launch(session: AsyncSession, m: MissionRecord) -> dict[str, Any]:
    if m.status in ready_service.CANCELLED:
        return _status("launch", "not_applicable", "This delivery was cancelled.")
    lc = m.lifecycle or {}
    job = await _stored(session, "launch", m.id)
    if job and job[0] in ("queued", "running"):
        return _status("launch", "computing", "Launch opportunities are being worked out.", job[1])
    if not lc.get("t0") and lc.get("pad_id") and lc.get("vehicle_id") and m.site_id:
        if (gate := await skyline_gate(session, "launch", m)) is not None:
            return gate
        pad = mission_service.catalogue_name("launch_sites", lc.get("pad_id"))
        return _status(
            "launch",
            "available",
            f"Launch opportunities from {pad}, backed out from sunlight at the landing spot.",
            job[1] if job and job[0] == "done" else None,
        )
    t0 = lc.get("t0")
    veh = mission_service.catalogue_name("vehicles", lc.get("vehicle_id"))
    pad = mission_service.catalogue_name("launch_sites", lc.get("pad_id"))
    if t0:
        where = " ".join(x for x in (f"on {veh}" if veh else "", f"from {pad}" if pad else "") if x)
        return _status(
            "launch", "available", f"Launched {_when(t0['date'])} {where}.".replace("  ", " ")
        )
    if m.launch:
        return _status(
            "launch",
            "no_data",
            f"Launch {m.launch['as_published']}; launch dates are not worked out yet.",
        )
    return _status("launch", "no_data", "The launch date is not published.")


async def _landing(session: AsyncSession, m: MissionRecord) -> dict[str, Any]:
    window = mission_service.surface_window(m)
    if m.status in ready_service.CANCELLED or window.basis == "none":
        state = "not_applicable" if m.status in mission_service.NO_SURFACE else "no_data"
        return _status("landing", state, window.note)
    if (gate := await skyline_gate(session, "landing", m)) is not None:
        return gate
    target = m.target_name or "the target"
    return _status("landing", "available", f"Sunlight and contact with Earth at {target}.")


async def _stored(
    session: AsyncSession, kind: str, mission_id: str
) -> tuple[str, datetime | None] | None:
    """The state of the newest answer or job of ``kind`` for this mission, if any."""
    from sqlalchemy import text

    row = (
        await session.execute(
            text(
                "SELECT status, coalesce(finished_at, created_at) AS last_at FROM jobs "
                "WHERE kind = :k AND mission_id = :m ORDER BY id DESC LIMIT 1"
            ),
            {"k": kind, "m": mission_id},
        )
    ).one_or_none()
    return None if row is None else (str(row.status), row.last_at)


async def sections(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    m = await MissionRepository(session).get(mission_id)
    if m is None:
        raise MissionNotFound(mission_id)
    return await sections_for(session, m)


async def sections_for(session: AsyncSession, m: MissionRecord) -> dict[str, Any]:
    """The six steps for a mission record (a scenario passes one with assumed values over it)."""
    out = [
        await _ready(session, m),
        await _launch(session, m),
        await _trip(session, m),
        await _landing(session, m),
        await _contact(session, m),
        _return(m),
    ]
    return {
        "data": out,
        "meta": lifecycle.meta(
            engines=("ready", "vis"),
            sources=[
                lifecycle.source_ref(
                    "CLPS mission record (data/missions.json)",
                    m.sources[0]["url"] if m.sources else None,
                )
            ],
            parts=[
                (
                    "Summaries",
                    "Each line counts or names what the section shows; "
                    "it is never a verdict on the mission.",
                )
            ],
            computed_at=datetime.now(UTC),
        ),
    }


async def step_marks(session: AsyncSession, m: MissionRecord) -> list[dict[str, Any]]:
    """What each of the six steps has, for the mission list: one mark per step.

    ``record``: the mission's own record answers it (published, flown or entered).
    ``example``: only a worked example (a preset scenario) answers it, from assumed
    values; ``scenario_id`` names the first one that does. ``input``: nothing does yet.
    ``none``: the step does not apply (a cancelled delivery).
    """
    states = {s["section"]: s["state"] for s in (await sections_for(session, m))["data"]}
    presets = sorted(
        (
            r
            for r in await ScenarioRepository(session).for_mission(m.id)
            if r.preset and r.status == "done"
        ),
        key=lambda r: r.created_at,
    )
    out = []
    for section in ("ready", "launch", "trip", "landing", "contact", "return"):
        state = states.get(section, "no_data")
        example = None
        if state in ("available", "computing"):
            mark = "record"
        elif state == "not_applicable":
            mark = "none"
        else:
            example = next(
                (
                    r.id
                    for r in presets
                    if any(p.get("id") == section and p.get("state") == "done" for p in r.phases)
                ),
                None,
            )
            mark = "input" if example is None else "example"
        out.append({"section": section, "mark": mark, "scenario_id": example})
    return out


async def _trip(session: AsyncSession, m: MissionRecord) -> dict[str, Any]:
    if m.status in ready_service.CANCELLED:
        return _status("trip", "not_applicable", "This delivery was cancelled.")
    job = await _stored(session, "trip", m.id)
    if job and job[0] in ("queued", "running"):
        return _status("trip", "computing", "The trip is being worked out.", job[1])
    if job and job[0] == "done":
        return _status("trip", "available", "The trip from launch to the Moon.", job[1])
    if m.status in ready_service.FLOWN:
        return _status("trip", "available", "The flown trip, from NASA's reconstruction.")
    return _status("trip", "no_data", "The trip is not worked out until a launch time is set.")


async def _contact(session: AsyncSession, m: MissionRecord) -> dict[str, Any]:
    if m.status in ready_service.CANCELLED:
        return _status("contact", "not_applicable", "This delivery was cancelled.")
    if m.site_id is None:
        return _status(
            "contact",
            "no_data",
            "No landing spot is published, so contact " "cannot be worked out.",
        )
    if (gate := await skyline_gate(session, "contact", m)) is not None:
        return gate
    job = await _stored(session, "contact", m.id)
    if job and job[0] in ("queued", "running"):
        return _status("contact", "computing", "Contact is being worked out.", job[1])
    return _status(
        "contact",
        "available",
        "When NASA's deep-space dishes (Deep Space Network) can hear the lander.",
        job[1] if job else None,
    )


def _return(m: MissionRecord) -> dict[str, Any]:
    if m.status in ready_service.CANCELLED:
        return _status("return", "not_applicable", "This delivery was cancelled.")
    lc = m.lifecycle or {}
    veh = mission_service.catalogue_name("vehicles", lc.get("vehicle_id"))
    if veh:
        return _status(
            "return",
            "available",
            f"Where the {veh} booster comes down; " "nothing returns from the Moon.",
        )
    return _status(
        "return",
        "no_data",
        "The launch vehicle is not published; nothing returns " "from the Moon.",
    )
