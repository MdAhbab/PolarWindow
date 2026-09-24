"""The measurement-only summary never states a margin of zero hours (N1)."""

from __future__ import annotations

from app.agents.base import _metric_sentences

BASE = {"sunlit_s": 1_252_800.0, "sun_fraction_up": 0.99}


def _margin(uncertainty: dict[str, object]) -> str:
    return " ".join(_metric_sentences({**BASE, "uncertainty": uncertainty}, "Site"))


def test_a_smooth_moon_skyline_claims_no_margin() -> None:
    text = _margin({"edge_timing_s": 0.0, "grazing": False, "terrain_modelled": False})
    assert "0 hours" not in text
    assert "no stated margin" in text


def test_a_sub_hour_margin_is_less_than_an_hour_not_zero() -> None:
    text = _margin({"edge_timing_s": 521.7, "grazing": False, "terrain_modelled": True})
    assert "up to 0 hours" not in text
    assert "less than an hour" in text


def test_an_hour_or_more_is_stated_in_hours() -> None:
    text = _margin({"edge_timing_s": 61_527.5, "grazing": False, "terrain_modelled": True})
    assert "uncertain by up to 17 hours" in text
