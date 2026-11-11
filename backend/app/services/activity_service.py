"""What is being worked out now, app-wide: jobs and scenarios, in one list for the tray."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.scenarios import ActivityRepository, ActivityRow

RECENT = timedelta(minutes=15)
RECENT_MAX = 10
#: Job kinds the tray shows (a scenario's own job is shown as the scenario).
JOB_KINDS = ("launch", "trip", "contact", "rover", "site_build")
POLL_ACTIVE_S = 3.0
POLL_IDLE_S = 15.0

_LABEL = {
    "launch": "Launch opportunities for {m}",
    "trip": "Trip for {m}",
    "contact": "Contact for {m}",
    "rover": "Rover line of sight for {m}",
    "site_build": "Skyline for {m}",
}
_STEP_OF = {"launch": "launch", "trip": "trip", "contact": "contact", "rover": "contact"}


def _iso(dt: datetime) -> str:
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def item(r: ActivityRow) -> dict[str, Any]:
    name = r.mission_name or "a mission"
    if r.kind == "scenario":
        sections = r.extra.get("sections") or ["launch"]
        label = f"Scenario: {r.label or name}"
        href = f"/missions/{r.mission_id}/{sections[0]}?scenario={r.ref}" if r.mission_id else None
        key = f"scenario:{r.ref}"
    else:
        label = _LABEL.get(r.kind, "{m}").format(m=name if r.mission_name else "a new site")
        step = _STEP_OF.get(r.kind)
        href = f"/missions/{r.mission_id}/{step}" if r.mission_id and step else None
        key = f"job:{r.ref}"
    return {
        "key": key,
        "kind": r.kind,
        "label": label,
        "mission_id": r.mission_id,
        "mission_name": r.mission_name,
        "href": href,
        "status": r.status,
        "progress": r.progress,
        "message": r.message,
        "started_at": _iso(r.started_at),
        "finished_at": None if r.finished_at is None else _iso(r.finished_at),
    }


def assemble(rows: list[ActivityRow]) -> dict[str, Any]:
    """Queued and running oldest first; finished newest first, at most ten."""
    active = sorted(
        (r for r in rows if r.status in ("queued", "running")), key=lambda r: r.started_at
    )
    done = sorted(
        (r for r in rows if r.status in ("done", "failed") and r.finished_at is not None),
        key=lambda r: r.finished_at or r.started_at,
        reverse=True,
    )[:RECENT_MAX]
    return {
        "active": [item(r) for r in active],
        "recent": [item(r) for r in done],
        "poll_after_s": POLL_ACTIVE_S if active else POLL_IDLE_S,
    }


async def activity(session: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    since = (now or datetime.now(UTC)) - RECENT
    repo = ActivityRepository(session)
    rows = await repo.jobs(since, JOB_KINDS) + await repo.scenarios(since)
    return assemble(rows)
