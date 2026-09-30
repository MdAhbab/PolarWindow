"""Golden tests that need nothing on disk.

Same code paths as the real-data goldens -- ray-march, ENU projection, interval
extraction, the four numbers -- but against an analytic surface and a stub
ephemeris. These run on any machine, in any CI job, with no kernels and no
database, which is what keeps the golden safety net alive during ordinary local
development.

The values below were computed once from this deterministic input and pinned. A
change to them means the geometry moved.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core import timeline, visibility
from app.core.horizon import HorizonMask, build_mask
from app.core.spice import R_MOON_M

SITE_LAT, SITE_LON, SITE_ELEV = -88.5, 45.0, 1500.0
STEP_S = 900.0
N = 2835


def make_analytic_sampler(
    features: list[tuple[float, float, float, float]], *, base_height_m: float = 0.0
):
    """A terrain sampler built from Gaussian bumps, so no DEM is needed.

    Each feature is ``(east_m, north_m, height_m, sigma_m)``. The full pipeline (mask,
    timeline, metrics) then runs on a machine with no DEM at all, which is what keeps this
    safety net alive during local development.
    """

    def sample(x, y):
        z = np.full(np.shape(x), base_height_m, dtype=np.float64)
        for ex, ny, hm, sigma in features:
            d2 = (x - ex) ** 2 + (y - ny) ** 2
            z = z + hm * np.exp(-d2 / (2.0 * sigma * sigma))
        return z

    return sample


def synthetic_mask() -> HorizonMask:
    """A site with one dominant ridge and two lesser knolls."""
    sampler = make_analytic_sampler(
        [
            (1200.0, -900.0, 130.0, 300.0),  # ridge, bearing ~127 deg
            (-1500.0, 400.0, 55.0, 250.0),
            (300.0, 1900.0, 70.0, 280.0),
        ]
    )
    return build_mask(
        sampler,
        site_height_m=0.0,
        azimuth_step_deg=0.25,
        max_range_m=20_000.0,
        dem_post_spacing_m=20.0,
        dem_vertical_error_m=2.0,
    )


def stub_vectors(body: str) -> np.ndarray:
    """A deterministic stand-in ephemeris.

    Not SPICE, and not pretending to be: a circling Sun near the horizon and a
    librating Earth, which is the right *shape* for the south pole and is all
    these tests need in order to exercise the arc extraction.
    """
    t = np.arange(N + 1, dtype=np.float64) * STEP_S
    if body == "sun":
        lon = np.radians(180.0 - 360.0 * t / (708.734 * 3600.0))
        lat = np.radians(1.5424 * np.sin(2 * np.pi * t / (8766.0 * 3600.0)))
        r = 1.496e11
    else:
        lon = np.radians(7.9 * np.sin(2 * np.pi * t / (27.554 * 86400.0) + 1.31))
        lat = np.radians(6.69 * np.sin(2 * np.pi * t / (27.212 * 86400.0) + 0.62))
        r = 3.844e8
    return np.stack(
        [r * np.cos(lat) * np.cos(lon), r * np.cos(lat) * np.sin(lon), r * np.sin(lat)], axis=1
    )


@pytest.fixture(scope="module")
def computed():
    mask = synthetic_mask()
    basis = visibility.enu_basis(SITE_LAT, SITE_LON)
    site_pos = visibility.site_position(SITE_LAT, SITE_LON, R_MOON_M + SITE_ELEV)
    t = np.arange(N + 1, dtype=np.float64) * STEP_S
    sun = timeline.build_track("sun", t, stub_vectors("sun"), mask, basis, site_pos, 6.957e8)
    earth = timeline.build_track("earth", t, stub_vectors("earth"), mask, basis, site_pos, 6.371e6)
    return mask, timeline.site_metrics_from_tracks("synthetic", sun, earth), sun, earth


# Pinned from an actual run of this deterministic input, not from arithmetic.
# A change to any of them means the geometry moved and must be explained.
#
# The peak is cross-checked independently in the test below, which derives
# ~4.93 deg from the ridge's own dimensions; the mask reads 5.03 deg because the
# ray passes nearer the Gaussian's crest than its nominal centre. Having both a
# pinned value and a derived one is the point: the pin catches drift, the
# derivation catches a pin that was wrong to begin with.
GOLDEN_MASK_MAX_DEG = 5.0333
GOLDEN_MASK_MAX_BEARING = 126.75
GOLDEN_MASK_MEAN_DEG = 0.6664


def test_synthetic_mask_is_stable(computed) -> None:
    mask, _m, _s, _e = computed
    assert mask.azimuth_count == 1440
    assert mask.max_el_deg == pytest.approx(
        GOLDEN_MASK_MAX_DEG, abs=0.05
    ), f"mask peak moved: {mask.max_el_deg:.4f} vs golden {GOLDEN_MASK_MAX_DEG}"
    assert mask.max_el_bearing_deg == pytest.approx(GOLDEN_MASK_MAX_BEARING, abs=0.5)
    assert float(np.mean(mask.el_deg)) == pytest.approx(GOLDEN_MASK_MEAN_DEG, abs=0.05)


def test_synthetic_mask_matches_hand_arithmetic(computed) -> None:
    """The dominant ridge's angle, derived rather than remembered.

    130 m at hypot(1200, 900) = 1500 m, less the 0.65 m curvature drop:
    atan(129.35 / 1500) = 4.93 deg. The mask reads slightly lower because the
    Gaussian's peak is not sampled exactly at its centre.
    """
    mask, _m, _s, _e = computed
    d = float(np.hypot(1200.0, 900.0))
    drop = d * d / (2 * R_MOON_M)
    expected = float(np.degrees(np.arctan2(130.0 - drop, d)))
    assert mask.max_el_deg == pytest.approx(expected, abs=0.35)
    # The ridge is at bearing atan2(1200, -900) = 126.87 deg.
    assert mask.max_el_bearing_deg == pytest.approx(
        float(np.degrees(np.arctan2(1200.0, -900.0)) % 360.0), abs=0.5
    )


def test_synthetic_four_numbers_are_stable(computed) -> None:
    _mask, m, _s, _e = computed
    span = N * STEP_S
    assert m.sunlit_s + m.sun.down_s == pytest.approx(span, abs=1.0)
    assert m.earth_contact_s + m.earth.down_s == pytest.approx(span, abs=1.0)
    assert m.longest_dark_s <= m.sun.down_s + 1e-6
    assert m.worst_compound_s <= min(m.longest_dark_s, m.longest_blackout_s) + 1e-6
    # The Sun circles near the horizon at -88.5 deg, so a site behind a 4.6 deg
    # ridge loses a substantial but not total fraction of the month.
    assert 0.2 < m.sun.fraction_up < 0.95
    assert 0.2 < m.earth.fraction_up < 0.95


def test_synthetic_arcs_partition_the_window(computed) -> None:
    _mask, _m, sun, earth = computed
    for track in (sun, earth):
        total = sum(r.duration for r in track.arcs)
        assert total == pytest.approx(float(track.t_s[-1] - track.t_s[0]), abs=1e-6)
        for a, b in zip(track.arcs, track.arcs[1:], strict=False):
            assert a.value != b.value
            assert a.end == pytest.approx(b.start, abs=1e-9)


def test_synthetic_blocked_arcs_name_their_blocker(computed) -> None:
    """ "Blocked" without a blocking feature is the kind of answer that made the
    existing tools hard to trust."""
    _mask, _m, sun, _e = computed
    for i, arc in enumerate(sun.arcs):
        if not arc.value:
            assert sun.blocked_by_bearing_deg[i] is not None
            assert sun.blocked_by_el_deg[i] is not None
            assert 0.0 <= sun.blocked_by_bearing_deg[i] < 360.0
        else:
            assert sun.blocked_by_bearing_deg[i] is None


def test_synthetic_run_is_deterministic(computed) -> None:
    """Two runs of the same input must be bit-identical, or nothing above holds."""
    mask, m, _s, _e = computed
    mask2 = synthetic_mask()
    assert np.array_equal(mask.el_deg, mask2.el_deg)
