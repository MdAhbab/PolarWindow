"""What span a mission's four numbers describe, and what that rests on."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.repositories.missions import MissionRecord
from app.services.mission_service import LUNAR_DAYLIGHT_S, surface_window


def rec(**kw: Any) -> MissionRecord:
    base: dict[str, Any] = {
        "id": "x",
        "name": "X",
        "vehicle_name": None,
        "task_order": None,
        "provider": None,
        "lander": None,
        "status": "completed",
        "outcome_note": "",
        "region": "south_polar",
        "target_name": None,
        "target": None,
        "ellipse": None,
        "launch": None,
        "landing": None,
        "end_of_mission": None,
        "planned_surface_days": None,
        "sort_at": None,
        "site_id": None,
        "sources": [],
        "unconfirmed_fields": [],
        "notes": [],
        "data_version": "v",
    }
    base.update(kw)
    return MissionRecord(**base)


def d(date: str, precision: str = "day", phrase: str = "p") -> dict[str, str]:
    return {"date": date, "precision": precision, "as_published": phrase}


def test_published_window_covers_whole_days() -> None:
    w = surface_window(rec(landing=d("2024-02-22"), end_of_mission=d("2024-02-29")))
    assert w.basis == "published"
    assert w.start == datetime(2024, 2, 22, tzinfo=UTC)
    assert w.end == datetime(2024, 3, 1, tzinfo=UTC)


def test_minute_precision_is_used_as_given() -> None:
    w = surface_window(
        rec(
            landing=d("2025-03-06T17:30:00Z", "minute"),
            end_of_mission=d("2025-03-07T06:15:00Z", "minute"),
        )
    )
    assert w.basis == "published"
    assert w.end - w.start == timedelta(hours=12, minutes=45)  # type: ignore[operator]


def test_planned_duration() -> None:
    w = surface_window(rec(status="planned", landing=d("2027-05-01"), planned_surface_days=10))
    assert w.basis == "planned" and w.end - w.start == timedelta(days=10)  # type: ignore[operator]


def test_unpublished_duration_is_named_as_an_assumption() -> None:
    w = surface_window(rec(status="planned", landing=d("2027-05-01")))
    assert w.basis == "assumed"
    assert (w.end - w.start).total_seconds() == LUNAR_DAYLIGHT_S  # type: ignore[operator]
    assert "assumption" in w.note


def test_a_year_is_not_a_window() -> None:
    w = surface_window(rec(status="planned", landing=d("2027-01-01", "year", "late 2027")))
    assert w.basis == "none" and w.start is None and "late 2027" in w.note


def test_no_surface_time_for_a_lost_mission() -> None:
    w = surface_window(rec(status="lost_before_landing", launch=d("2024-01-08")))
    assert w.basis == "none"
