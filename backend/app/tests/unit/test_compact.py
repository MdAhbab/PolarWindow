"""What an agent reads of a mission section (ADR-6, amended): at most 200 numbers."""

from __future__ import annotations

from app.agents.compact import MAX_NUMBERS, compact, count_numbers


def _q(value: float, unit: str = "km", pm: float | None = 1.0) -> dict:
    return {
        "value": value,
        "unit": unit,
        "provenance": "computed",
        "pm": pm,
        "lo": None,
        "hi": None,
        "factor": None,
        "open": False,
        "no_margin_reason": None,
        "missing_reason": None,
        "source": "https://example.org/x",
    }


def test_a_value_keeps_its_margin_and_loses_the_empty_fields() -> None:
    out = compact({"data": {"d": _q(3.0)}, "meta": {"sources": [{"name": "NASA", "url": "u"}]}})
    assert out["data"]["d"] == {"value": 3.0, "unit": "km", "provenance": "computed", "pm": 1.0}
    assert out["meta"] == {"sources": ["NASA"]}


def test_a_time_is_written_as_a_time() -> None:
    out = compact({"t0": _q(1_791_883_138.964, "s since epoch", pm=2640.0)})
    assert out["t0"]["value"] == "2026-10-13T09:18:58Z"
    assert out["t0"]["unit"] == "UTC" and out["t0"]["pm_s"] == 2640.0


def test_plot_series_are_left_out_and_said_so() -> None:
    out = compact({"data": {"samples": [{"earth_km": float(i)} for i in range(1821)]}})
    assert "samples" not in out["data"]
    assert out["left_out"] == {"data.samples": "1821 points of a plot series"}


def test_long_lists_and_big_answers_are_cut_to_the_cap() -> None:
    rows = [{"t0": _q(float(i)), "flight_days": _q(4.0), "wait": _q(0.5)} for i in range(38)]
    out = compact({"data": {"opportunities": rows, "pads": [{"lat": 28.6, "lon": -80.6}]}})
    assert len(out["data"]["opportunities"]) == 12
    assert out["left_out"]["data.opportunities"] == "first 12 of 38"
    many = {"data": {"a": [[float(j) for j in range(40)] for _ in range(10)]}}
    cut = compact(many)
    assert count_numbers(cut) <= MAX_NUMBERS
    assert cut["left_out"]
