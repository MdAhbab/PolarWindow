"""Scores for forecast shares against what happened, and the hindcast's pieces (T4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.core import verification as vf
from app.feeds import hindcast


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
