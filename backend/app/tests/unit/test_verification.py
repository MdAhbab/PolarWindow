"""Scores for forecast shares against what happened, and the hindcast's pieces (T4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.core import verification as vf
from app.feeds import hindcast
from app.feeds import hindcast_reforecast as hr


def test_brier_and_skill() -> None:
    o = np.array([0.0, 0.0, 1.0, 0.0])
    assert vf.brier(np.array([0.0, 0.0, 1.0, 0.0]), o) == 0.0
    ref = np.full(4, 0.25)
    assert vf.brier(ref, o) == pytest.approx(0.1875)
    assert vf.brier_skill(np.array([0.1, 0.1, 0.7, 0.1]), o, ref) == pytest.approx(
        1 - (3 * 0.01 + 0.09) / 4 / 0.1875
    )
    # No event and a reference that says so: nothing to be skilful against.
    assert vf.brier_skill(np.zeros(3), np.zeros(3), np.zeros(3)) is None


def test_reliability_bins_and_the_gate() -> None:
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 20_000)
    o = (rng.uniform(0, 1, p.size) < p).astype(float)  # reliable by construction
    bins = vf.reliability(p, o)
    assert len(bins) == 10 and all(b.counted and b.ok for b in bins)
    assert vf.passes({24: 0.3, 48: 0.2}, bins)
    assert not vf.passes({24: 0.3, 48: 0.05}, bins)  # one lead short of the skill
    assert not vf.passes({24: None}, bins)
    # It happens every time the share is over 0.3: far from what the shares said.
    off = vf.reliability(p, (p > 0.3).astype(float))
    assert not vf.passes({24: 0.5}, off)
    few = vf.reliability(np.array([0.95] * 5), np.zeros(5))  # 5 cases: not counted
    assert few[-1].n == 5 and few[-1].ok and not few[-1].counted


def test_limit_brought_down_to_the_station() -> None:
    assert vf.neutral_ratio(49.3776, 10.0, 0.03) == pytest.approx(0.784, abs=0.001)
    assert hindcast.threshold_m_s() / 0.44704 == pytest.approx(23.5, abs=0.1)


def test_index_range_and_nearest_report() -> None:
    idx = (
        "66:12400000:d=2025011500:TMP:2 m above ground:24 hour fcst:ENS=+1\n"
        "67:12701456:d=2025011500:UGRD:10 m above ground:24 hour fcst:ENS=+1\n"
        "68:12964913:d=2025011500:VGRD:10 m above ground:24 hour fcst:ENS=+1\n"
        "69:13225763:d=2025011500:APCP:surface:18-24 hour acc fcst:ENS=+1\n"
    )
    assert hindcast._range_of(idx) == (12701456, 13225762)
    assert hindcast._range_of(idx.splitlines()[0]) is None
    t0 = datetime(2025, 1, 1, tzinfo=UTC)
    obs = {t0 - timedelta(minutes=5): 3.0, t0 + timedelta(minutes=55): 7.0}
    ts = sorted(obs)
    assert hindcast.nearest_obs(obs, ts, t0) == 3.0
    assert hindcast.nearest_obs(obs, ts, t0 + timedelta(hours=1)) == 7.0
    assert hindcast.nearest_obs(obs, ts, t0 + timedelta(hours=3)) is None


def test_crps_of_runs_and_of_a_climatology() -> None:
    # One run: CRPS is the absolute error.
    assert vf.crps_ensemble(np.array([[3.0]]), np.array([5.0]))[0] == pytest.approx(2.0)
    # Two runs at 0 and 2, measured 1: mean |x - y| = 1, spread term |0 - 2| * 2 / (2 * 4).
    assert vf.crps_ensemble(np.array([[0.0, 2.0]]), np.array([1.0]))[0] == pytest.approx(0.5)
    assert vf.crps_ensemble(np.array([[0.0, 2.0]]), np.array([1.0]), fair=True)[0] == (
        pytest.approx(0.0)
    )
    # A sample's CRPS is the same number as the ensemble formula over that sample.
    rng = np.random.default_rng(1)
    s = rng.normal(5, 2, 200)
    ens = vf.crps_ensemble(s[None, :], np.array([6.0]))[0]
    assert vf.crps_sample(s, 6.0) == pytest.approx(ens)
    # A large normal sample against its analytic CRPS at the mean: sigma (sqrt(2) - 1) / sqrt(pi)
    big = rng.normal(0, 1, 20_000)
    assert vf.crps_sample(big, 0.0) == pytest.approx((np.sqrt(2) - 1) / np.sqrt(np.pi), abs=0.01)


def test_skill_interval() -> None:
    rng = np.random.default_rng(2)
    ref = rng.uniform(1, 2, 500)
    lo, hi = vf.skill_interval(0.5 * ref, ref) or (0, 0)
    assert lo == pytest.approx(0.5) and hi == pytest.approx(0.5)
    noisy = vf.skill_interval(ref * rng.uniform(0.2, 1.0, 500), ref)
    assert noisy is not None and noisy[0] < 0.4 < noisy[1]


def test_reforecast_index_and_the_order_of_days() -> None:
    idx = (
        "15:11406350:d=2019010200:UGRD:10 m above ground:24 hour fcst:ENS=low-res ctl\n"
        "16:12228617:d=2019010200:UGRD:100 m above ground:24 hour fcst:ENS=low-res ctl\n"
        "31:24763445:d=2019010200:UGRD:10 m above ground:48 hour fcst:ENS=low-res ctl\n"
        "32:25593957:d=2019010200:UGRD:100 m above ground:48 hour fcst:ENS=low-res ctl\n"
    )
    assert hr.lead_ranges(idx, "ugrd") == {24: (11406350, 12228616), 48: (24763445, 25593956)}
    assert hr.lead_ranges(idx, "vgrd") == {}
    days = hr.plan(3, 2018, 2019)
    assert len(days) == len(set(days)) == 730
    # Every third day of the latest year first, then of the year before, then the days between.
    first = days[
        : len([d for d in days if d.year == 2019 and d.toordinal() % 3 == days[0].toordinal() % 3])
    ]
    assert {d.year for d in first} == {2019}
    assert days[len(first)].year == 2018
