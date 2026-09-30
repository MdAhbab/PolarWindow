"""Which model has the air right between 30 and 70 km (``golden.capsule_air``): how the
measured profiles are binned, how a model is scored against them, the rule that picks the
default, and, with the extracts and OMNI files on disk, what the two instruments say."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.config import get_settings
from app.data.space_climate import omni_dir
from app.services import capsule
from app.validation import capsule_air as air
from app.validation import capsule_air_data as data

T0 = datetime(2023, 9, 24, 14, 41, tzinfo=UTC)


def _needs_omni() -> None:
    if not list(omni_dir().glob("omni2_h0_mrg1hr_20230701_v01.cdf")):
        pytest.skip("OMNI hourly file for July to December 2023 not on disk (make space-climate)")


def test_a_bin_is_the_mean_temperature_and_the_geometric_mean_density() -> None:
    z = np.array([30.2, 30.8, 33.5, 34.9, -999.0, 40.0])
    t = np.array([220.0, 224.0, 230.0, 231.0, 240.0, 250.0])
    n = np.array([4.0e17, 1.0e17, 2.0e16, -999.0, 5.0e15, 1.0e15])
    got_t = data.bin_km(z, t)
    got_n = data.bin_km(z, n, geometric=True)
    assert len(got_t) == len(got_n) == data.BIN_HI_KM - data.BIN_LO_KM == 40
    assert got_t[0] == 222.0 and got_t[3] == 230.0 and got_t[4] == 231.0
    assert got_n[0] == pytest.approx(2.0e17, rel=1e-3)  # sqrt(4e17 * 1e17)
    assert got_n[3] == pytest.approx(2.0e16, rel=1e-3) and got_n[4] is None  # -999 is missing
    assert got_t[1] is None and got_t[2] is None  # no point in 31 to 33 km
    assert got_t[10] == 250.0  # 40 km


def _profiles(density_scale: float = 1.0, temperature_shift: float = 0.0) -> air.Profiles:
    """Profiles that are NRLMSIS 2.1 itself, at a few places and times, scaled and shifted."""
    z = np.arange(30.5, 70.0, 1.0)
    when = [T0 + timedelta(hours=6 * i) for i in range(3)]
    shape = (len(when), len(z))
    blank = air.Profiles(
        "synthetic",
        when,
        np.array([35.0, 39.0, 44.0]),
        np.array([-125.0, -115.0, -105.0]),
        z,
        np.zeros(shape),
        np.ones(shape),
    )
    rho, temp = air.model_grid(blank, "NRLMSIS 2.1")
    return air.Profiles(
        "synthetic",
        when,
        blank.lat_deg,
        blank.lon_deg,
        z,
        temp + temperature_shift,
        rho * density_scale,
    )


def test_a_model_is_scored_by_its_mean_log_difference_from_the_measurement_in_each_band() -> None:
    _needs_omni()
    exact = air.score(_profiles(), "NRLMSIS 2.1")
    assert exact.density_bias_pct == pytest.approx((0.0,) * 8, abs=1e-9)
    assert exact.temperature_bias_k == pytest.approx((0.0,) * 8, abs=1e-9)
    assert exact.rms_pct == pytest.approx(0.0, abs=1e-9)
    # Air measured 5 % thinner than the model, and 3 K colder: the model is 5.26 % dense, 3 K warm.
    off = air.score(_profiles(density_scale=0.95, temperature_shift=-3.0), "NRLMSIS 2.1")
    assert off.density_bias_pct == pytest.approx((100 * (1 / 0.95 - 1),) * 8, abs=1e-6)
    assert off.temperature_bias_k == pytest.approx((3.0,) * 8, abs=1e-9)
    assert off.rms_pct == pytest.approx(100 * np.log(1 / 0.95), abs=1e-6)
    # The other model is off where the two differ (about 5 % at 50 to 70 km).
    older = air.score(_profiles(), "NRLMSISE-00")
    assert older.rms_pct > 2.0 and max(older.density_bias_pct[4:]) > 3.0


def _score(model: str, pct: float) -> air.Score:
    return air.Score(model, (pct,) * 8, (0.0,) * 8)


def _instrument(newer_pct: float, older_pct: float) -> dict[str, air.Score]:
    return {
        "NRLMSISE-00": _score("NRLMSISE-00", older_pct),
        "NRLMSIS 2.1": _score("NRLMSIS 2.1", newer_pct),
        capsule.STANDARD_NAME: _score(capsule.STANDARD_NAME, 4.0),
    }


def test_the_lower_score_wins_when_both_instruments_are_clear_about_it() -> None:
    both = {"SABER": _instrument(0.6, 3.7), "lidar": _instrument(1.6, 5.0)}
    assert air.choose(both) == ("NRLMSIS 2.1", "measurements")
    # The rule is symmetric: were the older model nearer in both, it would be the default.
    flipped = {"SABER": _instrument(3.7, 0.6), "lidar": _instrument(5.0, 1.6)}
    assert air.choose(flipped) == ("NRLMSISE-00", "measurements")


def test_a_gap_under_a_point_in_either_instrument_is_a_tie_the_published_evaluations_decide() -> (
    None
):
    tie = {"SABER": _instrument(0.6, 3.7), "lidar": _instrument(2.0, 2.9)}  # 0.9 points
    assert air.choose(tie) == ("NRLMSIS 2.1", "published evaluations")
    # A tie goes to the published evaluations' model even where the older one scores lower.
    older_ahead = {"SABER": _instrument(3.2, 3.0), "lidar": _instrument(3.6, 3.0)}
    assert air.choose(older_ahead) == ("NRLMSIS 2.1", "published evaluations")


def test_the_shape_only_score_leaves_out_the_level_of_the_measured_density() -> None:
    level = air.Score("m", (5.0,) * 8, (0.0,) * 8)  # 5 % too dense at every height
    assert level.rms_pct == pytest.approx(100 * np.log(1.05)) and level.shape_rms_pct == 0.0
    # 0 % at 30 to 35 km rising 1 point a band: the seven bands above are 1 to 7 points up.
    ramp = air.Score("m", tuple(float(k) for k in range(8)), (0.0,) * 8)
    expected = np.sqrt(np.mean(np.square(np.log1p(np.arange(1, 8) / 100.0) * 100.0)))
    assert ramp.shape_rms_pct == pytest.approx(expected, rel=1e-9)


def test_cuts_drop_some_profiles_and_never_all_of_them() -> None:
    _needs_omni()
    p = _profiles()
    n = len(p.when)
    night = air.cuts(p)  # no local time given: each profile left out in turn
    assert len(night) == n and all(k.sum() == n - 1 for k in night.values())
    assert all("without the night of" in name for name in night)
    lst = np.array([3.6, 3.6, 18.0])
    with_lt = air.Profiles(
        p.name, p.when, p.lat_deg, p.lon_deg, p.z_km, p.temperature_k, p.density, lst
    )
    by = air.cuts(with_lt)
    assert by["28 to 38 N"].tolist() == [True, False, False]  # 35, 39, 44 N
    assert by["38 to 49 N"].tolist() == [False, True, True]
    assert by["35 to 42 N (round the entry track)"].tolist() == [True, True, False]
    assert by["before noon, local solar time"].tolist() == [True, True, False]
    assert by["after noon, local solar time"].tolist() == [False, False, True]
    left = air.cut_scores(with_lt)
    assert set(left) == set(by)
    for name, (kept, sc) in left.items():
        assert kept == int(by[name].sum()) and set(sc) == set(air.CANDIDATES)
        assert sc["NRLMSIS 2.1"].rms_pct == pytest.approx(0.0, abs=1e-9)  # the profiles are it


def test_the_extracts_are_the_profiles_the_docs_describe() -> None:
    s, li = air.saber(), air.lidar()
    assert len(s.when) == 136 and len(li.when) == 9
    assert s.z_km[0] == 30.5 and s.z_km[-1] == 69.5 and len(s.z_km) == 40
    assert np.all((s.lat_deg >= 28.0) & (s.lat_deg <= 49.0))
    assert all(
        datetime(2023, 9, 24, tzinfo=UTC) <= t < datetime(2023, 9, 25, tzinfo=UTC) for t in s.when
    )
    assert {t.day for t in li.when} == {19, 20, 21, 22, 26, 27, 28, 29, 30}
    for p in (s, li):
        ok = ~np.isnan(p.density)
        assert ok.mean() > 0.9  # nearly every bin has a value
        # Air density in kg/m^3 at 30 km is about 0.018 and at 70 km about 8e-5.
        assert 0.014 < np.nanmedian(p.density[:, 0]) < 0.024
        assert 4e-5 < np.nanmedian(p.density[:, -1]) < 1.5e-4
        assert 180.0 < np.nanmedian(p.temperature_k) < 290.0


def test_the_measured_air_picks_the_model_the_capsule_flies_through() -> None:
    """The default model is the one the measurements choose, by more than the tie band in both
    instruments, and the standard atmosphere, which knows nothing of the day, is worse than it."""
    _needs_omni()
    ev = air.evidence()
    assert ev["chosen"] == capsule.DEFAULT_MODEL and ev["decided_by"] == "measurements"
    for inst in ev["instruments"]:
        by = {m["name"]: m["rms_density_bias_pct"] for m in inst["models"]}
        assert by[capsule.DEFAULT_MODEL] < 2.0  # within 2 % of the measured density
        assert by["NRLMSISE-00"] - by[capsule.DEFAULT_MODEL] >= air.TIE_POINTS
        assert by[capsule.STANDARD_NAME] > by[capsule.DEFAULT_MODEL]
    assert "'" not in ev["basis"] and "NRLMSIS 2.1" in ev["basis"]
    assert get_settings().data_dir.joinpath(air.SABER).exists()


def test_the_choice_holds_with_some_of_the_profiles_left_out() -> None:
    """By latitude and local solar time for SABER, and with each night of the lidar left out:
    the default is nearer every time, by two points or more in the score and, with the level
    of the measured density left out, by less but never the other way."""
    _needs_omni()
    ev = air.evidence()
    seen = 0
    for inst in ev["instruments"]:
        assert len(inst["cuts"]) == (5 if inst["profiles"] > 50 else inst["profiles"])
        for cut in inst["cuts"]:
            by = {m["name"]: m for m in cut["models"]}
            new, old = by[capsule.DEFAULT_MODEL], by["NRLMSISE-00"]
            assert old["rms_density_bias_pct"] - new["rms_density_bias_pct"] >= 2.0, cut["name"]
            assert new["shape_rms_density_bias_pct"] < old["shape_rms_density_bias_pct"]
            seen += 1
    assert seen == 14
