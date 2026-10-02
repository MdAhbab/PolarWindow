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


def _wind_check(passes: bool, leads: tuple[str, ...] = ("24", "48"), **more: object) -> dict:
    lead = {"cases": 500, "events": 12, "skill": 0.3, "skill_95": [0.1, 0.5], "crps_skill": 0.2}
    return {
        "rule_id": "f9-wind-162ft",
        "station": "KVBG",
        "event": "sustained wind at 10 m above 10.52 m/s (23.5 mph)",
        "period": "2007-01-08..2019-12-31",
        "gate": "the plan's gate",
        "passes": passes,
        "leads": {k: dict(lead) for k in leads},
        **more,
    }


def _on_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **files: dict) -> None:
    from types import SimpleNamespace

    from app.data import verification as ver

    folder = tmp_path / "hindcast"
    folder.mkdir()
    for name, body in files.items():
        (folder / name).write_text(json.dumps(body))
    monkeypatch.setattr(ver, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path))
    ver.load.cache_clear()


def test_the_multi_year_check_is_used_first_and_covers_only_the_leads_it_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.data import verification as ver

    _on_disk(
        tmp_path,
        monkeypatch,
        **{
            "gefs_reforecast_wind_vandenberg.json": _wind_check(
                True, days_fetched=845, system="GEFSv12 reforecast"
            ),
            "gefs_wind_vandenberg.json": _wind_check(False),
        },
    )
    try:
        assert ver.checked("vandenberg", "f9-wind-162ft")
        assert ver.checked("vandenberg", "f9-wind-162ft", 47.9)
        assert not ver.checked("vandenberg", "f9-wind-162ft", 1.0)
        assert not ver.checked("vandenberg", "f9-wind-162ft", 36.0)
        assert not ver.checked("vandenberg", "f9-wind-162ft", -1.0)
        assert not ver.checked("vandenberg", "f9-wind-162ft", 120.0)  # further out than 48 h
        assert not ver.checked("vandenberg", "another-rule")
        assert ver.reach_h("vandenberg") == 48 and ver.reach_h("florida") == 0
        text = ver.summary("vandenberg", "f9-wind-162ft") or ""
        assert "845 forecast days" in text and f"{ver.CRPS_WORDS}, 0.20" in text
        assert (
            "using forecasts from NOAA’s forecast model re-run for past years (GEFS version 12), "
            "for 2007-01-08 to 2019-12-31"
        ) in text
        assert "It passed the gate" in text and "near 24, 48 h ahead" in text
    finally:
        ver.load.cache_clear()


def test_the_single_year_check_stands_in_and_a_failed_one_is_never_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.data import verification as ver

    _on_disk(
        tmp_path,
        monkeypatch,
        **{"gefs_wind_florida.json": _wind_check(False, leads=("24",))},
    )
    try:
        assert ver.load("florida") is not None and not ver.checked("florida", "f9-wind-162ft")
        text = ver.summary("florida", "f9-wind-162ft") or ""
        assert "did not pass" in text and "up to" not in text
        assert ver.load("vandenberg") is None and ver.summary("vandenberg", "x") is None
    finally:
        ver.load.cache_clear()


def test_a_score_the_files_cannot_work_out_is_said_so() -> None:
    from app.data import verification as ver

    x = {"cases": 786, "events": 0, "skill": None, "skill_note": "no", "crps_skill": -0.95}
    words = ver._lead_words("24", x)
    assert f"{ver.BRIER_WORDS}, not worked out (too few cases above the limit)" in words
    assert "no case of the wind above the limit" in words and f"{ver.CRPS_WORDS}, -0.95" in words


def test_the_note_on_the_check_uses_no_term_a_forecaster_would_have_to_explain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The committed checks, said as a person on the launch team reads them."""
    from types import SimpleNamespace

    from app.data import verification as ver

    root = Path(__file__).resolve().parents[4] / "data"
    monkeypatch.setattr(ver, "get_settings", lambda: SimpleNamespace(data_dir=root))
    ver.load.cache_clear()
    try:
        for region in ("florida", "vandenberg"):
            text = ver.summary(region, "f9-wind-162ft") or ""
            assert "re-run for past years" in text and "did not pass the gate" in text, region
            assert ver.BRIER_WORDS in text and ver.CRPS_WORDS in text
            for term in ("reforecast", "Brier", "CRPS", "hindcast", "perturbed", "UTC", "bins"):
                assert term not in text, (region, term)
            assert ">=" not in text and "skill" not in text
    finally:
        ver.load.cache_clear()


def test_a_gate_is_said_with_the_numbers_the_file_states() -> None:
    from app.data import verification as ver

    said = ver._gate_words(
        "Brier skill >= 0.1 at each lead (from at least 10 cases above the limit) and "
        "reliability within 0.1 in bins with >= 30 cases"
    )
    assert "at least 0.1 better than the past-years rate at each lead ahead" in said
    assert "10 or more cases with the wind above the limit" in said
    assert "30 or more cases gave a like share of runs" in said
    assert "within 0.1 of that share" in said
    # The one-year file has no event count; a gate in another form is quoted, not guessed at.
    older = ver._gate_words(
        "Brier skill >= 0.1 at each lead and reliability within 0.1 in bins with >= 30 cases"
    )
    assert "worked out only from" not in older
    assert ver._gate_words("the plan's gate") == "the plan's gate"


def test_the_scored_files_say_what_the_plans_gate_says() -> None:
    """``passes`` in each committed output is the gate applied to that file's own numbers."""
    root = Path(__file__).resolve().parents[4] / "data" / "hindcast"
    for region in ("florida", "vandenberg"):
        d = json.loads((root / f"gefs_reforecast_wind_{region}.json").read_text())
        skills = {int(k): v["skill"] for k, v in d["leads"].items()}
        expected = bool(skills) and all(s is not None and s >= vf.BSS_MIN for s in skills.values())
        expected = expected and all(b["ok"] for b in d["reliability"])
        assert d["passes"] is expected, region


def _hrrr_check(**call: object) -> dict:
    lead = {
        "cases": 700,
        "bias_m_s": 0.3,
        "rmse_m_s": 1.7,
        "mae_m_s": 1.2,
        "mae_skill": 0.25,
        "mae_skill_95": [0.2, 0.3],
        "events": 10,
        "called_over": 8,
        "hits": 6,
        "false_alarms": 2,
        **call,
    }
    return {
        "station": "KVBG",
        "years": [2021, 2022, 2025],
        "leads": {"1": dict(lead), "6": {**lead, "rmse_m_s": 1.9}, "18": {**lead, "cases": 0}},
        "call_all_leads": {
            "cases": 2800,
            "events": 40,
            "called_over": 30,
            "hits": 24,
            "false_alarms": 6,
            **call,
        },
    }


def test_hrrr_check_is_read_at_the_nearest_lead_and_put_in_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.data import verification as ver

    _on_disk(tmp_path, monkeypatch, **{"hrrr_wind_vandenberg.json": _hrrr_check()})
    ver.hrrr_load.cache_clear()
    try:
        assert ver.hrrr_error_m_s("vandenberg", 5.0) == 1.9  # the 6 h lead is nearest
        assert ver.hrrr_error_m_s("vandenberg", 1.0) == 1.7
        assert ver.hrrr_error_m_s("florida", 6.0) is None  # nothing scored there
        assert ver.hrrr_error_m_s("vandenberg", 18.0) is None  # a lead with no cases
        words = ver.hrrr_words("vandenberg", 6.0) or ""
        assert "KVBG for 2021 to 2025 (700 runs at this lead)" in words
        assert "off by 1.2 m/s on average, 0.3 m/s above the station's" in words
        assert "25% closer to what was measured" in words
        assert "usual wind for that month and hour (95 % 20 to 30%)." in words
        assert "10 times in 700 runs, HRRR called 6 of them, and 2 of its 8 calls" in words
        assert "at this lead" in words and "over all leads" not in words
        assert "height was not observed" in words
        assert ver.hrrr_words("vandenberg", 24.0) is None
        assert ver.hrrr_words("vandenberg", -1.0) is None
        assert ver.hrrr_words("florida", 6.0) is None
    finally:
        ver.hrrr_load.cache_clear()


def test_an_entered_limit_does_not_borrow_the_published_limits_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.data import verification as ver

    check = _hrrr_check()
    check["threshold_m_s"] = 10.52
    _on_disk(
        tmp_path,
        monkeypatch,
        **{
            "hrrr_wind_vandenberg.json": check,
            "gefs_reforecast_wind_vandenberg.json": _wind_check(True, threshold_m_s=10.52),
        },
    )
    ver.hrrr_load.cache_clear()
    try:
        words = ver.hrrr_words("vandenberg", 6.0, 8.0) or ""
        assert "entered limit differs" in words and "HRRR called" not in words
        assert ver.checked("vandenberg", "f9-wind-162ft", 24, threshold_m_s=10.52)
        assert not ver.checked("vandenberg", "f9-wind-162ft", 24, threshold_m_s=8.0)
    finally:
        ver.hrrr_load.cache_clear()
        ver.load.cache_clear()


def test_hrrr_words_say_no_lean_and_give_a_worse_skill_in_its_own_direction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.data import verification as ver

    check = _hrrr_check()
    check["leads"]["1"].update(bias_m_s=0.004, mae_skill=-0.1, mae_skill_95=[-0.3, 0.02])
    check["leads"]["6"].pop("mae_skill_95")
    _on_disk(tmp_path, monkeypatch, **{"hrrr_wind_vandenberg.json": check})
    ver.hrrr_load.cache_clear()
    try:
        words = ver.hrrr_words("vandenberg", 1.0) or ""
        assert "0.0 m/s above" not in words and "no higher or lower than the station's" in words
        # a skill below zero is "further from", its interval turned the same way round
        assert "10% further from what was measured" in words and "(95 % -2 to 30%)" in words
        # no interval on file, none said
        assert "usual wind for that month and hour." in (ver.hrrr_words("vandenberg", 6.0) or "")
    finally:
        ver.hrrr_load.cache_clear()


def test_a_call_that_was_never_tested_is_said_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.data import verification as ver

    _on_disk(
        tmp_path,
        monkeypatch,
        **{"hrrr_wind_vandenberg.json": _hrrr_check(events=0, hits=0, called_over=1)},
    )
    ver.hrrr_load.cache_clear()
    try:
        words = ver.hrrr_words("vandenberg", 6.0) or ""
        assert "never reported wind above the limit" in words and "not tested" in words
    finally:
        ver.hrrr_load.cache_clear()
