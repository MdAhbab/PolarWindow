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


# ---------------------------------------------------------------------------
# The general interface the lifecycle engines use (ADR-11)
# ---------------------------------------------------------------------------


def _lifecycle_or_skip(spice_mod, *names: str) -> None:
    gone = [n for n in names if n in spice_mod.state().lifecycle_missing]
    if gone:
        pytest.skip(f"lifecycle kernels not on disk: {gone} (make kernels)")


@pytest.mark.parametrize(("body", "target"), [("sun", "SUN"), ("earth", "EARTH")])
def test_general_positions_reproduce_the_surface_helper_exactly(
    spice_loaded, ets, body, target
) -> None:
    """The surface numbers are pinned by goldens; the general path must not move them."""
    old = spice_loaded.body_vectors(body, ets)
    new = spice_loaded.positions(
        target, "MOON", spice_loaded.MOON_ME, "LT+S", ets, knot_s=spice_loaded.EPHEMERIS_KNOT_S
    )
    assert np.array_equal(old, new)


def test_states_carry_velocity_consistent_with_positions(spice_loaded) -> None:
    et0 = spice_loaded.utc_to_et("2027-03-14T00:00:00Z")
    ets = np.array([et0 - 1.0, et0, et0 + 1.0])
    st = spice_loaded.states("MOON", "EARTH", spice_loaded.J2000, "NONE", ets)
    finite_diff = (st[2, :3] - st[0, :3]) / 2.0
    assert np.allclose(st[1, 3:], finite_diff, rtol=1e-6)
    speed = np.linalg.norm(st[1, 3:])
    assert 900.0 < speed < 1_100.0, "the Moon moves about 1 km/s around Earth"


def test_rotations_are_proper_rotations(spice_loaded, ets) -> None:
    m = spice_loaded.rotations(spice_loaded.J2000, spice_loaded.MOON_ME, ets[:10])
    eye = np.einsum("nij,nkj->nik", m, m)
    assert np.allclose(eye, np.eye(3), atol=1e-12)
    assert np.allclose(np.linalg.det(m), 1.0, atol=1e-12)


def test_gm_matches_de440(spice_loaded) -> None:
    _lifecycle_or_skip(spice_loaded, "gm_de440.tpc")
    # Park et al. (2021), the DE440 paper: GM(Earth) = 398600.435507 km^3/s^2 in
    # TDB units. The IERS figure 398600.4418 is in TT units and differs by the
    # TT/TDB scale (1.6e-8): a propagator mixing the two drifts by metres a day.
    assert spice_loaded.gm_m3_s2("EARTH") == pytest.approx(3.98600435507e14, rel=1e-11)
    assert spice_loaded.gm_m3_s2("MOON") == pytest.approx(4.902800118e12, rel=1e-9)


def test_goldstone_70m_is_where_the_dsn_says(spice_loaded) -> None:
    """DSS-14 at Goldstone: 35.426 N, 243.111 E (DSN 810-005 module 301)."""
    _lifecycle_or_skip(
        spice_loaded, "earthstns_itrf93_260814.bsp", "earth_1962_260806_2126_combined.bpc"
    )
    et = spice_loaded.utc_to_et("2027-03-14T00:00:00Z")
    x, y, z = spice_loaded.positions(
        "DSS-14", "EARTH", spice_loaded.ITRF93, "NONE", np.array([et]), knot_s=None
    )[0]
    # Geodetic latitude on WGS-84 by fixed-point iteration (converges in a few steps).
    a, f = 6_378_137.0, 1.0 / 298.257223563
    e2 = f * (2.0 - f)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1.0 - e2))
    for _ in range(10):
        n = a / np.sqrt(1.0 - e2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1.0 - e2 * n / (n + h)))
    assert np.degrees(lat) == pytest.approx(35.426, abs=0.01)
    assert np.degrees(np.arctan2(y, x)) % 360.0 == pytest.approx(243.111, abs=0.01)


def test_et_to_utc_round_trip(spice_loaded) -> None:
    et = spice_loaded.utc_to_et("2026-11-15T12:34:56.789Z")
    assert spice_loaded.et_to_utc(et) == "2026-11-15T12:34:56.789Z"
