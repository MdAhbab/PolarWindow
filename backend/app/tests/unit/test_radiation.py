"""Radiation screening (plan track E): belts, cosmic rays, past events."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from app.core import belts, gcr
from app.data import space_climate
from app.services import radiation


def test_time_inside_and_passes_count_by_step_midpoints() -> None:
    t = np.arange(0.0, 600.0, 60.0)
    inside = np.array([0, 1, 1, 1, 0, 0, 1, 1, 0, 0], dtype=bool)
    assert belts.time_inside(t, inside) == pytest.approx(60 * 2 + 30 * 2 + 60 + 30 * 2)
    assert belts.passes(t, inside).stretches == [(60.0, 180.0), (360.0, 420.0)]
    assert belts.fluence(np.array([0.0, 10.0]), np.array([1.0, 3.0])) == pytest.approx(20.0)


@pytest.mark.skipif(not belts.available(), reason="IRBEM (spacepy) not installed")
def test_the_belts_are_where_the_maps_put_them() -> None:
    x = np.array([1.5, 2.0, 4.5, 20.0]) * belts.RE_KM
    xyz = np.c_[x, np.zeros(4), np.zeros(4)]
    when = [datetime(2024, 2, 15, 6, tzinfo=UTC)] * 4
    e = belts.integral_flux("e", "max", [1.0], when, xyz)[0]
    p = belts.integral_flux("p", "max", [10.0], when, xyz)[0]
    assert e[2] > e[1] > 0 and e[3] == 0  # the outer belt holds the electrons
    assert p[0] > 0 and p[2] == 0 and p[3] == 0  # the protons stay inside


def test_the_cosmic_ray_model_and_its_modulation() -> None:
    assert gcr.w_from_oulu(6814.3) == pytest.approx(5.0, abs=0.1)
    e = np.array([100.0, 1000.0])
    quiet, active = gcr.flux(5.0, 1, e), gcr.flux(100.0, 1, e)
    assert np.all(active < quiet)  # a busier Sun lets fewer in
    assert gcr.dose_ratio(100.0, 5.0) < 1.0 < gcr.dose_ratio(0.0, 100.0)
    with pytest.raises(ValueError):
        gcr.flux(250.0, 1, e)


def test_open_sky_is_one_for_a_flat_horizon() -> None:
    assert gcr.open_sky_fraction(np.zeros(360)) == pytest.approx(1.0)
    walls = np.full(360, 30.0)
    assert gcr.open_sky_fraction(walls) == pytest.approx(0.5)
    assert gcr.open_sky_fraction(np.full(360, -2.0)) > 1.0


def test_the_model_meets_crater_within_the_margin() -> None:
    got = space_climate.oulu_at(datetime(2009, 6, 20, tzinfo=UTC))
    assert got is not None, "data/radiation/oulu_nm_monthly.json is committed"
    w = max(0.0, gcr.w_from_oulu(got[0]))
    cgy_yr = gcr.thin_si_dose_gy_s(w) * 365.25 * 86400 * 100
    assert abs(cgy_yr / 18.9 - 1) <= radiation.GCR_PM  # CRaTER microdosimeter
    assert abs(cgy_yr / 16.5 - 1) <= radiation.GCR_PM  # CRaTER D1-D2


def test_past_event_peaks_match_noaas_list_within_ten_percent() -> None:
    events = [e for e in space_climate.sep_scenarios() if e.get("peak_gt10_pfu")]
    assert len(events) == 2
    for e in events:
        assert abs(float(e["peak_gt10_pfu"]) / float(e["swpc_list_peak_pfu"]) - 1) <= 0.10  # type: ignore[arg-type]
    king = next(e for e in space_climate.sep_scenarios() if e["id"] == "aug-1972")
    assert float(king["fluence_gt30_cm2"]) == pytest.approx(7.9e9)  # type: ignore[arg-type]


def test_goes_csv_integrates_to_a_fluence() -> None:
    head = "p3_flux_ic:description = x\ndata: \n"
    cols = "time_tag,p3_flux_ic,p4_flux_ic,p6_flux_ic\n"
    rows = "".join(
        f"2003-10-28 12:{m:02d}:00.000,{v},1,-99999\n" for m, v in ((0, 10), (5, 20), (10, 30))
    )
    got = space_climate.goes_fluence(head + cols + rows, "2003-10-28 12:00", "2003-10-28 12:05")
    assert got["samples"] == 2 and got["peak_gt10_pfu"] == 20.0
    assert got["fluence_gt10_cm2"] == pytest.approx(30 * 300 * 4 * np.pi)
    assert got["missing_gt60"] == 2


def test_donki_keeps_only_goes_threshold_crossings() -> None:
    def row(i: str, name: str) -> dict[str, object]:
        return {"sepID": i, "eventTime": "t", "link": "l", "instruments": [{"displayName": name}]}

    rows = [row("a", "GOES-P: SEISS >10 MeV"), row("b", "SOHO: COSTEP 15.8-39.8 MeV")]
    assert [e["id"] for e in space_climate.goes_events(rows)] == ["a"]
