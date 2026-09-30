"""A product fetched only near a launch is idle, not stale, when nothing is near."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.repositories.feeds import HealthRecord
from app.feeds.adapters import glm, nomads
from app.services import feed_service
from app.workers import feeds as feeds_worker

NOW = datetime(2026, 9, 29, 8, 50, tzinfo=UTC)


def _glm(last_ok: datetime | None, errors: int = 0) -> HealthRecord:
    return HealthRecord(
        "goes", "glm", "florida", "t", 1200, 600, last_ok, last_ok, None, None, errors, None
    )


def test_an_empty_on_demand_product_says_why_instead_of_stale() -> None:
    row = feed_service._row(_glm(NOW - timedelta(minutes=9)), None, "closed", NOW)
    assert row["age_s"] is None and row["stale"] is False  # asked 9 minutes ago: nothing near
    assert "only in the 6 hours before" in row["note"] and "not a fault" in row["note"]
    # The six hours in the words are the ones the adapter uses.
    assert glm.LOOKAHEAD.total_seconds() == 6 * 3600


def test_the_launch_forecast_with_no_launch_within_reach_says_why_instead_of_stale() -> None:
    """Vandenberg with no designed launch opportunity in the next 16 days: the worker asked, and
    there was nothing to fetch, so the row holds no snapshot and is idle."""
    h = HealthRecord(
        "nomads", "gefs_launch", "vandenberg", "t", 64800, 21600, NOW, NOW, None, None, 0, None
    )
    row = feed_service._row(h, None, "closed", NOW)
    assert row["age_s"] is None and row["stale"] is False
    assert "within 16 days" in row["note"] and "not a fault" in row["note"]
    # The 16 days in the words are the reach the worker looks ahead and the forecast has.
    assert feeds_worker.FORECAST_REACH.days == 16
    assert nomads.GEFS_MAX_LEAD_H == 16 * 24


def test_an_on_demand_product_nobody_has_asked_for_is_still_stale() -> None:
    assert feed_service._row(_glm(None), None, "closed", NOW)["stale"] is True
    lapsed = _glm(NOW - timedelta(hours=2))  # the worker stopped asking
    assert feed_service._row(lapsed, None, "closed", NOW)["stale"] is True


def test_the_rest_keep_their_rule_and_carry_no_note() -> None:
    h = HealthRecord("nws", "grid", "pad", "t", 3600, 600, NOW, NOW, 3, None, 0, None)
    fresh = feed_service._row(h, NOW - timedelta(minutes=5), "closed", NOW)
    assert fresh["stale"] is False and fresh["note"] is None
    old = feed_service._row(h, NOW - timedelta(hours=3), "closed", NOW)
    assert old["stale"] is True and old["age_s"] == 3 * 3600
