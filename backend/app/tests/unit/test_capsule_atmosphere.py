"""The capsule's air: NRLMSIS 2.1 (NRLMSISE-00 when asked for) for the entry day along the
flight, and the standard atmosphere when the day's solar flux and geomagnetic activity are
missing."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from pymsis import msis

from app.core import entry, spice
from app.data import msis_indices
from app.data.msis_indices import Indices
from app.services import capsule

T0 = datetime(2023, 9, 24, 14, 41, 55, tzinfo=UTC)
AP = (20.875, 4.0, 6.0, 7.0, 5.0, 7.875, 9.125)


def _density(when: datetime, lon_deg: float, lat_deg: float, h_m: float, version: float) -> float:
    out = msis.calculate(
        np.datetime64(when.replace(tzinfo=None), "ms"),
        lon_deg,
        lat_deg,
        h_m / 1000.0,
        [174.1],
        [149.3],
        [list(AP)],
        version=version,
        geomagnetic_activity=-1,
    )
    return float(np.asarray(out).reshape(-1, 11)[0, 0])


def _over(lon_deg: float, h_m: float) -> np.ndarray:
    """The inertial position over the equator at ``lon_deg`` (J2000 = ITRF93 in these tests)."""
    lon = math.radians(lon_deg)
    return (entry.R_EQ + h_m) * np.array([math.cos(lon), math.sin(lon), 0.0])


@pytest.mark.parametrize("version", [0, 2.1])
def test_the_air_is_msis_at_the_point_and_time_of_the_flight(version: float) -> None:
    air = capsule.msis_air(T0, np.eye(3), 174.1, 149.3, AP, version)
    h = 80_000.0
    assert air(0.0, _over(30.0, h), h) == pytest.approx(_density(T0, 30.0, 0.0, h, version))
    # Six hours on, the same inertial point lies over the ground the Earth has turned away
    # from it: west by the Earth's turn, not east. Local time changes the density there.
    dt = 6 * 3600.0
    turn = math.degrees(entry.OMEGA_EARTH * dt)
    west = _density(T0 + timedelta(seconds=dt), 30.0 - turn, 0.0, h, version)
    east = _density(T0 + timedelta(seconds=dt), 30.0 + turn, 0.0, h, version)
    assert abs(west - east) > 1e-3 * west  # the check can tell the two apart
    assert air(dt, _over(30.0, h), h) == pytest.approx(west)


def test_the_air_uses_the_height_it_is_given() -> None:
    air = capsule.msis_air(T0, np.eye(3), 174.1, 149.3, AP)
    r = _over(-113.0, 50_000.0)
    assert air(0.0, r, 50_000.0) == pytest.approx(_density(T0, -113.0, 0.0, 50_000.0, 0))
    assert air(0.0, r, 60_000.0) < 0.75 * air(0.0, r, 50_000.0)


def test_the_days_atmosphere_is_msis_driven_by_that_days_indices(monkeypatch) -> None:
    ix = Indices(174.1, 149.3, AP, ("omni2_h0_mrg1hr_20230701_v01.cdf",))
    monkeypatch.setattr(capsule, "utc", lambda _et: T0)
    monkeypatch.setattr(msis_indices, "at", lambda _t: ix)
    monkeypatch.setattr(spice, "rotations", lambda *_a, **_k: np.eye(3)[None])
    atm = capsule.day_atmosphere(0.0)
    assert capsule.DEFAULT_MODEL == "NRLMSIS 2.1"
    assert atm.name == capsule.DEFAULT_MODEL and atm.fallback_reason is None
    assert (atm.f107_sfu, atm.f107_mean_sfu, atm.ap_3h) == (174.1, 149.3, 4.0)
    assert atm.files == ix.files and atm.air is not None
    h = 40_000.0
    assert atm.air(0.0, _over(0.0, h), h) == pytest.approx(_density(T0, 0.0, 0.0, h, 2.1))
    older = capsule.day_atmosphere(0.0, "NRLMSISE-00")
    assert older.name == "NRLMSISE-00" and older.air is not None
    assert older.air(0.0, _over(0.0, h), h) == pytest.approx(_density(T0, 0.0, 0.0, h, 0))
    # The two models differ where a capsule slows (the reason the default is not the older one).
    assert older.air(0.0, _over(0.0, 60_000.0), 60_000.0) > 1.03 * atm.air(
        0.0, _over(0.0, 60_000.0), 60_000.0
    )


def test_a_column_of_heights_is_the_density_and_temperature_at_each_of_them() -> None:
    heights = np.array([35_000.0, 50_000.0, 65_000.0])
    rho, temp = capsule.msis_column(T0, 39.0, -115.0, heights, 174.1, 149.3, AP, 2.1)
    assert rho.shape == temp.shape == (3,)
    for k, h in enumerate(heights):
        assert rho[k] == pytest.approx(_density(T0, -115.0, 39.0, float(h), 2.1))
        assert rho[k] == pytest.approx(
            capsule.msis_density(T0, 39.0, -115.0, float(h), 174.1, 149.3, AP, 2.1)
        )
    assert np.all(np.diff(rho) < 0) and np.all((temp > 180.0) & (temp < 300.0))


def test_the_standard_atmosphere_stands_in_when_the_day_has_no_indices(monkeypatch) -> None:
    monkeypatch.setattr(capsule, "utc", lambda _et: T0)
    monkeypatch.setattr(msis_indices, "at", lambda _t: None)
    atm = capsule.day_atmosphere(0.0)
    assert atm.air is None and atm.name == capsule.STANDARD_NAME
    assert atm.fallback_reason is not None and "24 September 2023" in atm.fallback_reason
    assert atm.f107_sfu is None and atm.ap_3h is None
    # A capsule with no air of its own falls through the standard atmosphere.
    assert entry.Capsule(63.0, air=atm.air).density(0.0, _over(0.0, 60_000.0), 60_000.0) > 0.0
