"""Scores for forecast shares against what happened, and the hindcast's pieces (T4)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

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
    every_third = {
        date.fromordinal(o)
        for o in range(date(2018, 1, 1).toordinal(), date(2020, 1, 1).toordinal())
        if o % 3 == 0
    }
    assert len(days) == len(set(days)) == len(every_third) and set(days) == every_third
    # A fixed random order: the same each time, another for another seed, and a run
    # stopped early holds days from both years, not the latest year's first.
    assert days == hr.plan(3, 2018, 2019) and days != hr.plan(3, 2018, 2019, seed=1)
    assert {d.year for d in days[:30]} == {2018, 2019}
    assert len({d.month for d in days[:60]}) >= 8


def test_wilson_interval_and_blocks_of_cases() -> None:
    lo, hi = vf.wilson(0, 20)
    assert lo == 0.0 and hi == pytest.approx(0.161, abs=0.002)  # nothing seen in 20
    lo, hi = vf.wilson(50, 100)
    assert (lo, hi) == pytest.approx((0.404, 0.596), abs=0.002)
    bin_ = vf.reliability(np.array([0.5] * 100), np.array([1.0] * 50 + [0.0] * 50))[5]
    assert bin_.freq_95 == pytest.approx((0.404, 0.596), abs=0.002)
    assert vf.reliability(np.array([0.5]), np.array([1.0]))[0].freq_95 is None  # empty bin
    # Cases in blocks that share a fate: drawing whole blocks gives the wider interval.
    rng = np.random.default_rng(3)
    blocks = np.repeat(np.arange(40), 25)
    ref = np.ones(blocks.size)
    score = np.repeat(rng.uniform(0.2, 1.4, 40), 25)  # a block's cases are all alike
    one = vf.skill_interval(score, ref) or (0.0, 0.0)
    many = vf.skill_interval(score, ref, blocks=blocks) or (0.0, 0.0)
    assert many[1] - many[0] > 3 * (one[1] - one[0])
    assert vf.skill_interval(score, ref, blocks=np.zeros(blocks.size)) is None  # one block


def _fake_record(events: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """A cache of 60 days at the Cape and the station record that goes with it: the runs
    all say 12 m/s on the days the station then reported it, and 3 m/s otherwise."""
    monkeypatch.setattr(hr, "out_path", lambda region: tmp_path / f"{region}.json")
    cache: dict[str, dict] = {}
    obs: dict[datetime, float] = {}
    for i in range(60):
        day = date(2019, 1, 2) + timedelta(days=i)
        windy = i < events
        for lead in (24, 48):
            valid = datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(hours=lead)
            obs[valid - timedelta(minutes=4)] = 12.0 if windy else 3.0
        speeds = [12.0 if windy else 3.0] * len(hr.MEMBERS)
        cache[day.isoformat()] = {
            "init": day.isoformat(),
            "speeds": {
                "florida": {"24": speeds, "48": speeds},
                "vandenberg": {"24": speeds, "48": speeds},
            },
        }
    out = hr.score("florida", cache, obs)
    return json.loads(out.read_text())


def test_reforecast_skill_needs_enough_cases_above_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    few = _fake_record(4, tmp_path, monkeypatch)
    assert few["leads"]["24"]["events"] == 4 and few["leads"]["24"]["skill"] is None
    assert "fewer than the 10" in few["leads"]["24"]["skill_note"] and not few["passes"]
    # Runs that always got it right have a CRPS of zero: a skill of 1 against climatology.
    assert few["leads"]["24"]["crps_skill"] == pytest.approx(1.0, abs=0.02)
    many = _fake_record(15, tmp_path, monkeypatch)
    lead = many["leads"]["24"]
    assert lead["events"] == 15 and lead["skill"] == pytest.approx(1.0)
    assert lead["skill_note"] is None and lead["skill_95"][0] > 0.9
    top = lead["reliability"][-1]  # the bin of shares above 0.9: 15 cases, all above the limit
    assert top["n"] == 15 and top["observed"] == 1.0 and not top["counted"]
    assert top["observed_95"][0] > 0.7
    assert many["passes"]  # skill 1 at both leads; no bin holds enough cases to be off


@pytest.mark.asyncio
async def test_a_failed_day_goes_to_the_back_of_the_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    import httpx

    monkeypatch.setattr(hr, "cache_path", lambda: tmp_path / "cache.jsonl")
    asked: list[date] = []
    slept: list[float] = []

    async def fast_sleep(seconds: float) -> None:
        slept.append(seconds)

    async def day(self: hr.Fetcher, d: date) -> dict:
        asked.append(d)
        if d == date(2019, 1, 3) and asked.count(d) == 1:
            raise httpx.ConnectTimeout("the link is down")
        return {"init": d.isoformat(), "speeds": {}}

    monkeypatch.setattr(hr.Fetcher, "day", day)
    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    await hr.fetch(1, 2019, 2019, hours=1.0, parallel=2, workers=2, seed=0)
    # Every day of the year (stride 1 keeps them all) is cached once, the failed one
    # after a wait; nothing is written for a day that failed.
    got = [json.loads(x)["init"] for x in (tmp_path / "cache.jsonl").read_text().splitlines()]
    assert len(got) == len(set(got)) == 365 and "2019-01-03" in got
    assert asked.count(date(2019, 1, 3)) == 2 and slept == [20.0]
