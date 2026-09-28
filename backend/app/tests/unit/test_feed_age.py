"""A snapshot's age: its issue time, else the last fetch that found it current."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.repositories.feeds import HealthRecord, SnapshotRecord
from app.services import feed_service

T = datetime(2026, 9, 28, 12, tzinfo=UTC)


def _snap(issued: datetime | None, sid: int = 7) -> SnapshotRecord:
    return SnapshotRecord(
        sid, "donki", "flr", "", issued, None, None, T - timedelta(days=2), "https://x.test",
        200, None, None, None, {"count": 0, "events": []}, "t", "t", "ok", [],
    )  # fmt: skip


def _health(last_ok: datetime, sid: int = 7) -> HealthRecord:
    return HealthRecord(
        "donki", "flr", "", "t", 86_400, 1800, last_ok, last_ok, sid, None, 0, None
    )  # fmt: skip


def test_an_unchanged_list_is_as_new_as_the_last_fetch_that_found_it() -> None:
    # Fetched two days ago, the same body found an hour ago: an hour old, not two days.
    assert feed_service.data_time(_snap(None), _health(T - timedelta(hours=1))) == T - timedelta(
        hours=1
    )
    # Another snapshot is current: this one's own fetch time.
    other = _health(T - timedelta(hours=1), sid=8)
    assert feed_service.data_time(_snap(None), other) == T - timedelta(days=2)
    # An issue time is the data's own time, whatever the fetches.
    issued = T - timedelta(days=3)
    assert feed_service.data_time(_snap(issued), _health(T)) == issued
