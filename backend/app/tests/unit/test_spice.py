"""The ephemeris boundary: `core.spice` against the real kernels.

Skipped, loudly, where the kernels are absent (``requires_kernels``). These are
the checks test plan section 2.5 names -- frame, observer, units and the
interpolation the request path now relies on -- each of which would otherwise
fail as a plausible-looking number rather than an error.
"""

from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.requires_kernels

WINDOW_H = 708.5
STEP_S = 900.0


@pytest.fixture(scope="module")
def spice_loaded():
    from app.config import get_settings
    from app.core import spice

    spice.load(get_settings().kernel_dir)
    return spice


@pytest.fixture(scope="module")
def ets(spice_loaded) -> np.ndarray:
    a = spice_loaded.utc_to_et("2027-03-14T00:00:00Z")
    return spice_loaded.et_range(a, a + WINDOW_H * 3600.0, STEP_S)


def _angle_deg(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Angle between row vectors, stable at tiny angles (atan2, not arccos)."""
    cross = np.linalg.norm(np.cross(a, b), axis=1)
    dot = np.sum(a * b, axis=1)
    return np.degrees(np.arctan2(cross, dot))


def test_sun_distance_is_about_one_astronomical_unit(spice_loaded, ets) -> None:
    r = np.linalg.norm(spice_loaded.body_vectors("sun", ets), axis=1)
    assert np.all((r > 1.47e11) & (r < 1.53e11)), "observer, target or units are wrong"


def test_earth_distance_is_lunar(spice_loaded, ets) -> None:
    r = np.linalg.norm(spice_loaded.body_vectors("earth", ets), axis=1)
    assert np.all((r > 3.5e8) & (r < 4.1e8)), "observer, target or units are wrong"


@pytest.mark.parametrize("body", ["sun", "earth"])
def test_knot_interpolation_matches_direct_evaluation(spice_loaded, ets, body) -> None:
    """The request path interpolates between hourly knots; pin its error.

    The bound is 1e-6 deg -- two orders above what was measured and four below
    the 0.01 deg az/el tolerance of the golden fixtures -- so a change to the
    knot spacing or the spline that costs real accuracy fails here first.
    """
    fast = spice_loaded.body_vectors(body, ets)
    exact = spice_loaded.body_vectors(body, ets, knot_s=None)
    assert float(np.max(_angle_deg(fast, exact))) < 1e-6
    rel = np.abs(np.linalg.norm(fast, axis=1) / np.linalg.norm(exact, axis=1) - 1.0)
    assert float(np.max(rel)) < 1e-9


def test_moon_me_is_not_moon_pa(spice_loaded, ets) -> None:
    """Furnishing only the PA frame and calling it ME is a real, silent error.

    The two frames differ by roughly an arcminute; if they ever agree, the frame
    kernel is not doing what the site coordinates assume.
    """
    import spiceypy

    me, _ = spiceypy.spkpos("EARTH", ets[:50], "MOON_ME", "LT+S", "MOON")
    pa, _ = spiceypy.spkpos("EARTH", ets[:50], "MOON_PA", "LT+S", "MOON")
    sep = _angle_deg(np.asarray(me), np.asarray(pa))
    assert float(np.min(sep)) > 0.005, "MOON_ME and MOON_PA are identical"
    assert float(np.max(sep)) < 0.1, "MOON_ME and MOON_PA differ by far too much"


def test_utc_round_trip_across_a_leap_second_boundary(spice_loaded) -> None:
    """2016-12-31T23:59:60 is a real second; ET must count it."""
    import spiceypy

    before = spice_loaded.utc_to_et("2016-12-31T23:59:59Z")
    after = spice_loaded.utc_to_et("2017-01-01T00:00:00Z")
    assert after - before == pytest.approx(2.0, abs=1e-6)
    assert spiceypy.et2utc(after, "ISOC", 0) == "2017-01-01T00:00:00"


def test_one_hop_ephemeris_matches_the_parts(spice_loaded, ets) -> None:
    eph = spice_loaded.ephemeris("2027-03-14T00:00:00Z", "2027-04-12T12:30:00Z", STEP_S)
    assert eph.ets.shape == ets.shape
    np.testing.assert_allclose(eph.sun, spice_loaded.body_vectors("sun", eph.ets))
    np.testing.assert_allclose(eph.earth, spice_loaded.body_vectors("earth", eph.ets))
