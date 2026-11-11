"""A published date reaches the AI at the precision it was published at."""

from __future__ import annotations

from app.agents.tools import published_when


def test_a_year_is_not_handed_over_as_the_first_of_january() -> None:
    block = {"date": "2026-01-01", "precision": "year", "as_published": "late 2026"}
    out = published_when("launch", block)
    assert out == {
        "launch": "2026",
        "launch_precision": "year",
        "launch_as_published": "late 2026",
    }
    assert "2026-01-01" not in str(out)


def test_a_month_and_a_quarter_keep_only_what_was_published() -> None:
    assert published_when("launch", {"date": "2027-03-01", "precision": "month"}) == {
        "launch": "2027-03",
        "launch_precision": "month",
    }
    assert (
        published_when("landing", {"date": "2027-10-01", "precision": "quarter"})["landing"]
        == "2027-Q4"
    )


def test_a_date_known_to_the_day_or_better_keeps_its_day() -> None:
    for precision in ("day", "minute", "second"):
        block = {"date": "2025-02-27", "precision": precision}
        assert published_when("launch", block) == {"launch": "2025-02-27"}


def test_no_date_is_no_date() -> None:
    assert published_when("landing", None) == {"landing": None}
    assert published_when("landing", {}) == {"landing": None}
