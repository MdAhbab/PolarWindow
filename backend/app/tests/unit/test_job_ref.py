"""What a waiting section says (ADR-12): the queue ahead, or that no worker is running."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.repositories.jobs import JobRecord
from app.services import job_service

T0 = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def _job(status: str = "queued", error: str | None = None) -> JobRecord:
    return JobRecord(
        id=7, kind="trip", mission_id="im-1", params={}, params_hash="h", closure="c",
        status=status, priority=0, attempts=0, max_attempts=3, run_after=T0,
        lease_owner=None, lease_until=None, progress=None, message="Queued.", error=error,
        assessment_id=None, created_at=T0, started_at=None, finished_at=None,
    )  # fmt: skip


def test_a_wait_says_how_many_answers_are_ahead() -> None:
    ref = job_service.job_ref(_job(), now=T0 + timedelta(seconds=5), ahead=2)
    assert "2 answers are being worked out first" in ref["message"]


def test_a_job_nobody_takes_says_the_worker_is_not_running() -> None:
    late = T0 + timedelta(seconds=job_service.STUCK_AFTER_S + 1)
    assert "make compute" in job_service.job_ref(_job(), now=late)["message"]


def test_a_failed_job_says_why() -> None:
    ref = job_service.job_ref(_job("failed", "ValueError: no reconstruction\nTraceback"), now=T0)
    assert ref["message"] == "Could not be worked out: ValueError: no reconstruction"
