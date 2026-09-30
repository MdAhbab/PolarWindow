"""The propagator against NASA's reconstructed trajectories (plan C1 acceptance).

The arcs start where ``validate_trip.scan`` finds no firing (quiet stretches;
see that module for the method); ``make validate-trip`` prints the full table
for docs/validation.md. Tolerances are the plan's: 1 km after 24 h and 5 km
after 72 h against a reconstruction, 1 km after 24 h against LRO, 1 m for a
forward-and-back round trip.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.config import get_settings

pytestmark = [pytest.mark.requires_kernels, pytest.mark.requires_clps_spice, pytest.mark.slow]


@pytest.fixture(scope="module")
def vt():
    from app.data import gravity
    from app.validation import validate_trip

    s = get_settings()
    for path, _, _ in validate_trip.FLOWN.values():
        if not (s.data_dir / path).exists():
            pytest.skip(f"{path} not on disk (polar-data sync)")
    if not (s.data_dir / gravity.FILE).exists():
        pytest.skip("GRGM1200A not on disk (polar-data sync)")
    from app.core import spice

    spice.load(s.kernel_dir)
    return validate_trip


def _et(utc: str) -> float:
    from app.core import spice

    return spice.utc_to_et(utc)


@pytest.mark.parametrize(
    ("start", "hours", "tol_km"),
    [("2025-01-16T07:32:36", 24.0, 1.0), ("2025-02-03T13:12:36", 72.0, 5.0)],
)
def test_blue_ghost_cruise_within_tolerance(vt, start, hours, tol_km) -> None:
    err_m, where, _ = vt.arc("blue-ghost-m1", _et(start), hours)
    assert where == "cruise"
    assert err_m / 1000.0 <= tol_km


def test_im2_low_lunar_orbit_day_within_a_kilometre(vt) -> None:
    err_m, where, _ = vt.arc("im-2", _et("2025-03-04T13:01:09"), 24.0, degree=100)
    assert where == "lunar orbit"
    assert err_m <= 1000.0


def test_lro_day_within_a_kilometre(vt) -> None:
    err_m, where, _ = vt.arc("lro", _et("2025-03-21T01:41:00"), 24.0, degree=100)
    assert where == "lunar orbit"
    assert err_m <= 1000.0


def test_forward_and_back_on_a_real_trip_within_a_metre(vt) -> None:
    assert vt.round_trip("blue-ghost-m1", _et("2025-01-16T07:32:36"), 24.0) <= 1.0


def test_peregrines_leak_shows_as_unexplained_acceleration(vt) -> None:
    """Not acceptance: the leak-detection check. Peregrine's reconstruction needs a
    push the force model does not have for its whole cruise; Blue Ghost's does not."""
    pere, quiet = vt.scan("peregrine-m1", degree=50)
    bg, _ = vt.scan("blue-ghost-m1", degree=50)
    assert quiet == []
    assert pere.residual_median_m_s2 > 1e-5
    assert pere.residual_median_m_s2 > 50 * bg.residual_median_m_s2
    assert np.isfinite(pere.residual_p90_m_s2)
