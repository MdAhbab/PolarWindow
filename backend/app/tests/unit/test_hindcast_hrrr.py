"""HRRR's one forecast against the station: the index, the plan, the reading, the scores (T4)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.core import verification as vf
from app.feeds import hindcast as hc
from app.feeds import hindcast_hrrr as hh
from app.feeds.parsers import grib_ranges as gr

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "feeds"


def test_the_wind_messages_are_found_in_the_index() -> None:
    idx = (FIX / "hrrr_f06_idx_excerpt.txt").read_text()
    # A message ends where the next begins; the 10 m U and V winds, not the 80 m or the maxima.
    assert hh.wind_ranges(idx, 6) == {"UGRD": (52154488, 54536102), "VGRD": (54536103, 56917717)}
    assert hh.wind_ranges(idx, 12) == {}  # another lead: none
    assert hh.file_url(date(2021, 6, 15), 12, 6).endswith(
        "hrrr.20210615/conus/hrrr.t12z.wrfsfcf06.grib2"
    )


def test_the_plan_takes_every_nth_day_at_both_runs_in_a_fixed_order() -> None:
    days = hh.plan(6, 2021, 2025)
    assert len(days) == len(set(days)) and {h for _, h in days} == set(hh.INITS)
    assert {d.year for d, _ in days} == set(range(2021, 2026))
    assert all(d.toordinal() % 6 == 0 for d, _ in days) and len(days) in (608, 610)
    assert days == hh.plan(6, 2021, 2025) and days != sorted(days)  # fixed, and not by date
    # A finer plan holds every run of a coarser one, so a run carried on adds only new ones.
    assert set(days) <= set(hh.plan(2, 2021, 2025))


def test_a_message_is_read_at_each_station_from_its_head_and_two_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = (FIX / "hrrr_f06_u10_head.bin").read_bytes()
    lay = gr.layout(head)
    asked: list[tuple[int, int]] = []
    offset = 52_154_488

    async def get(self: Any, url: str, a: int | None = None, b: int | None = None) -> bytes | None:
        assert a is not None and b is not None
        asked.append((a - offset, b - offset))
        return head if a - offset == 0 else bytes(range(1, b - a + 2))

    monkeypatch.setattr(hh.Reader, "get", get)
    reader = hh.Reader(None, 4)  # type: ignore[arg-type]
    got = asyncio.run(reader.message("u", (offset, offset + 2_000_000)))
    assert asked[0] == (0, gr.HEAD - 1)
    ks = [lay.grid.nearest(lat, lon) for _, _, lat, lon in hh.STATIONS.values()]
    assert asked[1:] == [lay.span(k) for k in ks]  # one short range for each station
    want = [
        lay.value(bytes(range(1, s1 - s0 + 2)), k)
        for k, (s0, s1) in zip(ks, asked[1:], strict=True)
    ]
    assert got == want


def _obs(t0: datetime, hours: int, speed: Any) -> dict[datetime, float]:
    return {t0 + timedelta(hours=h): float(speed(h)) for h in range(hours)}


def test_a_forecast_with_a_steady_bias_is_scored_and_its_calls_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hh, "out_path", lambda region: tmp_path / f"hrrr_{region}.json")
    thr = hc.threshold_m_s()
    rng = np.random.default_rng(3)
    # March 2019 hour by hour is the station's record; the same hours in 2021 are what happened.
    record = _obs(datetime(2019, 3, 1, tzinfo=UTC), 31 * 24, lambda _h: rng.uniform(1.0, 7.0))
    happened = _obs(datetime(2021, 3, 1, tzinfo=UTC), 31 * 24, lambda _h: rng.uniform(1.0, 7.0))
    # Three hours nothing else is forecast for (the 12 UTC hour of the 00 UTC run, the 00 UTC
    # hour of the 12 UTC run, and the 01 UTC one): the wind above the limit and called; called
    # and not there; there and missed.
    special = {
        ("2021-03-05T00", 12): (thr + 2.0, thr + 1.0),
        ("2021-03-06T12", 12): (4.0, thr + 1.0),
        ("2021-03-07T00", 1): (thr + 2.0, 5.0),
    }
    for (init_key, lead), (was, _said) in special.items():
        init = datetime.strptime(init_key, "%Y-%m-%dT%H").replace(tzinfo=UTC)
        happened[init + timedelta(hours=lead)] = was
    cache: dict[str, dict[str, Any]] = {}
    for day in range(1, 29):
        for hour in hh.INITS:
            init = datetime(2021, 3, day, hour, tzinfo=UTC)
            speeds: dict[str, Any] = {}
            for lead in hh.LEADS:
                valid = init + timedelta(hours=lead)
                said = special.get((hh.key(init.date(), hour), lead), (0.0, None))[1]
                speeds[str(lead)] = {
                    "vandenberg": happened[valid] + 0.5 if said is None else said,
                    "florida": None,
                }
            cache[hh.key(init.date(), hour)] = {"init": hh.key(init.date(), hour), "speeds": speeds}
    p = hh.score("vandenberg", cache, happened, record)
    d = json.loads(p.read_text())
    six = d["leads"]["6"]  # no special hour at this lead: every forecast is 0.5 m/s high
    assert six["cases"] == 56 and six["bias_m_s"] == pytest.approx(0.5)
    assert six["mae_m_s"] == pytest.approx(0.5) and six["rmse_m_s"] == pytest.approx(0.5)
    assert six["mae_skill"] > 0.5 and six["crps_skill"] > 0  # far closer than the record
    one, twelve = d["leads"]["1"], d["leads"]["12"]
    assert (one["hits"], one["misses"], one["false_alarms"]) == (0, 1, 0)
    assert (twelve["hits"], twelve["misses"], twelve["false_alarms"]) == (1, 0, 1)
    call = d["call_all_leads"]
    assert (call["events"], call["called_over"], call["hits"]) == (2, 2, 1)
    assert call["skill"] is None and f"fewer than the {vf.MIN_EVENTS}" in call["skill_note"]
    assert d["years"] == [2021] and d["runs_fetched"] == 56
    assert d["threshold_m_s"] == pytest.approx(thr)
    # A station with no forecasts at all is written too, with no numbers.
    none = json.loads(hh.score("florida", cache, happened, record).read_text())
    assert none["leads"]["1"]["cases"] == 0 and none["leads"]["1"]["bias_m_s"] is None
