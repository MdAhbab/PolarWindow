"""The activity tray: jobs and scenarios in progress and just finished. No database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.db.repositories.scenarios import ActivityRow
from app.services import activity_service

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def row(kind: str, ref: str, status: str, minutes_ago: int, **kw: Any) -> ActivityRow:
    done = status in ("done", "failed")
    start = NOW - timedelta(minutes=minutes_ago)
    base: dict[str, Any] = {
        "kind": kind,
        "ref": ref,
        "mission_id": "m1",
        "mission_name": "Athena",
        "status": status,
        "progress": 1.0 if done else 0.4,
        "message": "",
        "label": None,
        "started_at": start,
        "finished_at": start + timedelta(minutes=1) if done else None,
    }
    base.update(kw)
    return ActivityRow(**base)


def test_in_progress_oldest_first_and_finished_newest_first() -> None:
    out = activity_service.assemble(
        [
            row("trip", "3", "running", 2),
            row("launch", "1", "queued", 5),
            row("contact", "2", "done", 9),
            row("scenario", "sc-1", "done", 4, label="Falcon Heavy", extra={"sections": ["trip"]}),
        ]
    )
    assert [i["key"] for i in out["active"]] == ["job:1", "job:3"]
    assert [i["key"] for i in out["recent"]] == ["scenario:sc-1", "job:2"]
    assert out["poll_after_s"] == activity_service.POLL_ACTIVE_S


def test_idle_polls_slowly_and_a_failure_counts_as_finished() -> None:
    out = activity_service.assemble([row("launch", "1", "failed", 3, message="boom")])
    assert out["active"] == [] and out["recent"][0]["status"] == "failed"
    assert out["poll_after_s"] == activity_service.POLL_IDLE_S


def test_at_most_ten_finished_items_are_shown() -> None:
    rows = [row("launch", str(i), "done", i + 1) for i in range(15)]
    assert len(activity_service.assemble(rows)["recent"]) == activity_service.RECENT_MAX


def test_a_scenario_links_to_its_first_step_and_a_job_to_its_page() -> None:
    sc = activity_service.item(
        row(
            "scenario",
            "sc-9",
            "running",
            1,
            label="Landing in March",
            extra={"sections": ["contact", "return"]},
        )
    )
    assert sc["label"] == "Scenario: Landing in March"
    assert sc["href"] == "/missions/m1/contact?scenario=sc-9"
    job = activity_service.item(row("rover", "7", "running", 1))
    assert job["href"] == "/missions/m1/contact" and "Rover" in job["label"]
    build = activity_service.item(
        row("site_build", "8", "queued", 1, mission_id=None, mission_name=None)
    )
    assert build["href"] is None and "a new site" in build["label"]
    assert sc["started_at"].endswith("+00:00") and sc["finished_at"] is None


async def test_the_query_looks_back_fifteen_minutes_over_jobs_and_scenarios(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class Repo:
        def __init__(self, _s: Any) -> None: ...

        async def jobs(self, since: datetime, kinds: tuple[str, ...]) -> list[ActivityRow]:
            seen["jobs"] = (since, kinds)
            return [row("launch", "1", "running", 1)]

        async def scenarios(self, since: datetime) -> list[ActivityRow]:
            seen["scenarios"] = since
            return [row("scenario", "sc-1", "done", 2)]

    monkeypatch.setattr(activity_service, "ActivityRepository", Repo)
    out = await activity_service.activity(None, NOW)  # type: ignore[arg-type]
    assert seen["jobs"] == (NOW - activity_service.RECENT, activity_service.JOB_KINDS)
    assert seen["scenarios"] == NOW - activity_service.RECENT
    assert "scenario" not in activity_service.JOB_KINDS  # a scenario's own job is shown once
    assert len(out["active"]) == 1 and len(out["recent"]) == 1
