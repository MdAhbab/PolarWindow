"""Weather rules against model numbers (B1): heights, units, counting runs."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from app.core import weather_rules as wr

M = {"u10_m_s": 6.0, "v10_m_s": 0.0, "u80_m_s": 10.0, "v80_m_s": 0.0}


def test_log_profile_hits_the_model_levels_and_interpolates_between() -> None:
    assert wr.speed_at(M, 10.0) == pytest.approx(6.0)
    assert wr.speed_at(M, 80.0) == pytest.approx(10.0)
    z = 162 * 0.3048
    assert wr.speed_at(M, z) == pytest.approx(6.0 + 4.0 * math.log(z / 10) / math.log(8))
    assert wr.speed_at({"u10_m_s": 1.0}, 50.0) is None


def test_units_and_comparisons() -> None:
    assert wr.to_m_s(30.0, "mph") == pytest.approx(13.4112)
    assert wr.from_m_s(wr.to_m_s(25.0, "kt"), "kt") == pytest.approx(25.0)
    with pytest.raises(ValueError):
        wr.to_m_s(1.0, "ft")
    assert wr.breaks(31.0, 30.0, "gt") and not wr.breaks(30.0, 30.0, "gt")
    assert wr.breaks(30.0, 30.0, "ge") and wr.breaks(2.0, 3.0, "lt")


def test_counting_runs_over_a_limit() -> None:
    members = {
        "0": M,
        "1": {**M, "u80_m_s": 20.0},
        "2": {**M, "u10_m_s": 15.0, "u80_m_s": 20.0},
        "3": {"t2m_k": 290.0},
    }
    k, n = wr.count_breaking(members, 49.4, wr.to_m_s(30.0, "mph"), "gt")
    assert (k, n) == (2, 3)  # the run without winds is not counted at all


def test_nearest_lead_within_tolerance() -> None:
    leads = {
        "24": {"valid": "2026-10-02T12:00:00Z"},
        "27": {"valid": "2026-10-02T15:00:00Z"},
    }
    t = datetime(2026, 10, 2, 14, 10, tzinfo=UTC)
    assert wr.nearest_lead(leads, t, 3 * 3600)[0] == "27"  # type: ignore[index]
    assert wr.nearest_lead(leads, datetime(2026, 10, 3, tzinfo=UTC), 3 * 3600) is None


def test_an_ensemble_leans_only_when_its_whole_interval_is_on_one_side() -> None:
    assert wr.lean(0.0, 0.09) == "under" and wr.lean(0.55, 0.9) == "over"
    assert wr.lean(0.18, 0.50) is None and wr.lean(0.3, 0.7) is None


def test_forecasts_that_disagree_are_named_in_plain_words() -> None:
    # 0 of 31 runs break the limit, yet NWS is over it: a disagreement; HRRR under: agrees.
    got = wr.disagreements(
        [("NWS", 34.0, True), ("HRRR", 20.0, False)], (0, 31, 0.0, 0.0787), "mph", 3.0
    )
    assert len(got) == 2  # NWS against the runs, and NWS against HRRR (14 mph apart, gap 3)
    assert got[0].startswith("NWS puts the wind at 34.0 mph, over the limit")
    assert "0 of 31 GEFS runs break it (95% range 0% to 7.9%)" in got[0]
    assert (
        got[1] == "NWS puts the wind at 34.0 mph, over the limit, and HRRR at 20.0 mph, under it."
    )
    # An ensemble that is unsure (interval across one half) contradicts nothing.
    assert wr.disagreements([("NWS", 34.0, True)], (10, 31, 0.18, 0.5), "mph", None) == []
    # Two forecasts a hair either side of the limit are not a disagreement...
    near = [("NWS", 30.4, True), ("HRRR", 29.8, False)]
    assert wr.disagreements(near, None, "mph", 3.0) == []
    # ...unless no typical error is known, and then opposite sides are enough.
    assert len(wr.disagreements(near, None, "mph", None)) == 1
    # One forecast alone, or agreement on one side, says nothing.
    assert wr.disagreements([("HRRR", 20.0, False)], None, "mph", 3.0) == []
    assert (
        wr.disagreements(
            [("NWS", 40.0, True), ("HRRR", 35.0, True)], (25, 31, 0.6, 0.93), "mph", 3.0
        )
        == []
    )
