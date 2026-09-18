"""Ray-march tests against surfaces whose horizon is known analytically.

Testing a ray-marcher against its own output proves nothing. Every case here
uses a surface whose skyline can be derived by hand -- a plane, a cone, a wall,
a ramp -- so the assertion is against arithmetic rather than against a previous
run.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core.horizon import R_MOON_M, build_mask, curvature_drop_m, downsample, ray_distances


def flat(height: float = 0.0):
    def sample(x, y):
        return np.full(np.shape(x), height, dtype=np.float64)

    return sample


def cone(bearing_deg: float, range_m: float, height_m: float, sigma_m: float = 60.0):
    """A narrow Gaussian peak at a known bearing and range."""
    a = np.radians(bearing_deg)
    cx, cy = np.sin(a) * range_m, np.cos(a) * range_m

    def sample(x, y):
        d2 = (np.asarray(x) - cx) ** 2 + (np.asarray(y) - cy) ** 2
        return height_m * np.exp(-d2 / (2 * sigma_m**2))

    return sample


def test_flat_plane_horizon_is_slightly_below_level() -> None:
    """The ground curves away, so a flat plane's skyline is negative.

    This is the assertion that a clamp at zero would break, and at the south
    pole -- where the Sun spends the whole month within a degree of level -- a
    tenth of a degree of horizon is hours of sunlight. The sign is load-bearing.
    """
    m = build_mask(flat(), azimuth_step_deg=2.0, max_range_m=20_000.0, site_height_m=0.0)
    assert m.max_el_deg < 0.0
    assert np.all(m.el_deg < 0.0)
    # Every bearing is identical on a plane.
    assert float(m.el_deg.max() - m.el_deg.min()) == pytest.approx(0.0, abs=1e-5)
    # At the far-field range the value is -atan(drop/r).
    r = float(m.range_m[0])
    expected = -np.degrees(np.arctan2(r * r / (2 * R_MOON_M), r))
    assert float(m.el_deg[0]) == pytest.approx(expected, abs=0.01)


def test_single_blocker_bearing_and_elevation() -> None:
    """A cone of known height at known range sets a known skyline angle."""
    brg, rng, hgt = 120.0, 3000.0, 400.0
    m = build_mask(
        cone(brg, rng, hgt, sigma_m=120.0),
        azimuth_step_deg=0.25,
        max_range_m=20_000.0,
        site_height_m=0.0,
    )
    expected = np.degrees(np.arctan2(hgt - rng * rng / (2 * R_MOON_M), rng))
    assert m.max_el_deg == pytest.approx(expected, abs=0.05)
    assert m.max_el_bearing_deg == pytest.approx(brg, abs=0.5)


def test_blocker_is_local_not_global() -> None:
    """Bearings away from the blocker must stay at the flat-plane horizon."""
    m = build_mask(
        cone(90.0, 2000.0, 300.0, sigma_m=80.0),
        azimuth_step_deg=1.0,
        max_range_m=20_000.0,
        site_height_m=0.0,
    )
    opposite = int(270 / 1.0)
    assert float(m.el_deg[opposite]) < 0.0


def test_curvature_drop_is_applied() -> None:
    """d^2/2R at 20 km is 115.1 m. Omitting it is invisible near and wrong far."""
    assert float(curvature_drop_m(np.array([20_000.0]))[0]) == pytest.approx(115.1, abs=0.2)
    assert float(curvature_drop_m(np.array([50_000.0]))[0]) == pytest.approx(719.5, abs=1.0)

    far = 30_000.0
    tall = 500.0
    with_curve = build_mask(
        cone(0.0, far, tall, sigma_m=800.0),
        azimuth_step_deg=5.0,
        max_range_m=40_000.0,
        site_height_m=0.0,
    )
    without = build_mask(
        cone(0.0, far, tall, sigma_m=800.0),
        azimuth_step_deg=5.0,
        max_range_m=40_000.0,
        site_height_m=0.0,
        r_body_m=1e15,  # effectively flat
    )
    assert without.max_el_deg > with_curve.max_el_deg


def test_step_schedule_does_not_skip_a_near_ridge() -> None:
    """A thin, tall feature at short range must still be found."""
    m = build_mask(
        cone(45.0, 300.0, 60.0, sigma_m=25.0),
        azimuth_step_deg=0.25,
        max_range_m=20_000.0,
        site_height_m=0.0,
        dem_post_spacing_m=20.0,
    )
    assert m.max_el_deg > 5.0, "a 60 m feature at 300 m should show ~11 degrees"
    assert m.max_el_bearing_deg == pytest.approx(45.0, abs=1.5)


def test_noise_floor_rejects_a_near_field_artefact() -> None:
    """A rise indistinguishable from DEM error must not become a blocker.

    At 40 m a 2 m vertical error is 2.9 degrees of apparent skyline, which is
    larger than almost any real horizon at these sites. Before this rule the
    mask reported an open ridge as having a 2.46 degree skyline whose blocker
    was 40 m away and 1.7 m high.
    """
    m = build_mask(
        cone(10.0, 45.0, 1.5, sigma_m=15.0),
        azimuth_step_deg=2.0,
        max_range_m=20_000.0,
        site_height_m=0.0,
        dem_post_spacing_m=20.0,
        dem_vertical_error_m=2.0,
    )
    assert m.max_el_deg < 0.5, f"near-field noise became a {m.max_el_deg:.2f} deg blocker"
    assert float(m.range_m.min()) >= 400.0


def test_ray_distances_start_beyond_the_resolvable_scale() -> None:
    d = ray_distances(max_range_m=1000.0, min_step_m=5.0, min_range_m=40.0)
    assert d[0] == pytest.approx(40.0)
    assert np.all(np.diff(d) > 0)
    assert d[-1] <= 1000.0


def test_coverage_reports_missing_dem() -> None:
    """NaN outside the model propagates into coverage rather than being clamped.

    An edge clamp would extend the last row of pixels outward forever, which
    near a crater rim invents a plateau that blocks the Sun.
    """

    def half(x, y):
        z = np.zeros(np.shape(x), dtype=np.float64)
        return np.where(np.asarray(y) > 0, z, np.nan)

    m = build_mask(half, azimuth_step_deg=5.0, max_range_m=10_000.0, site_height_m=0.0)
    assert 0.2 < m.coverage < 0.8


def test_downsample_takes_the_maximum_never_the_mean() -> None:
    """Averaging a skyline invents sky where a ridge is."""
    el = np.zeros(1440, dtype=np.float32)
    el[7] = 12.0  # one narrow ridge inside the first 1-degree group
    out = downsample(el, 360)
    assert out.shape == (360,)
    assert float(out[1]) == pytest.approx(12.0), "the ridge was averaged away"
    assert float(np.mean(el[4:8])) < 12.0, "sanity: a mean would have lost it"


def test_downsample_rejects_a_non_divisor() -> None:
    with pytest.raises(ValueError, match="cannot downsample"):
        downsample(np.zeros(1440, dtype=np.float32), 500)


def test_azimuth_step_must_divide_360() -> None:
    with pytest.raises(ValueError, match="divide 360"):
        build_mask(flat(), azimuth_step_deg=7.0, site_height_m=0.0)


def test_site_outside_the_dem_is_an_error_not_a_guess() -> None:
    def nowhere(x, y):
        return np.full(np.shape(x), np.nan, dtype=np.float64)

    with pytest.raises(ValueError, match="outside the elevation model"):
        build_mask(nowhere, azimuth_step_deg=10.0)


def test_mask_is_reproducible() -> None:
    a = build_mask(cone(200.0, 1500.0, 120.0), azimuth_step_deg=1.0, site_height_m=0.0)
    b = build_mask(cone(200.0, 1500.0, 120.0), azimuth_step_deg=1.0, site_height_m=0.0)
    assert np.array_equal(a.el_deg, b.el_deg)
