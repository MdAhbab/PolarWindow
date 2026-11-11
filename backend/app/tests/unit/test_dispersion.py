"""The landing ellipse as a deterministic sample (ADR-22)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core import dispersion

#: Per-axis standard deviation of a bivariate normal cut at 3 sigma, in sigmas.
TRUNC_SD = math.sqrt((1 - math.exp(-4.5) * 5.5) / (1 - math.exp(-4.5)))


def test_sample_covariance_matches_a_b_psi() -> None:
    a, b, psi = 300.0, 100.0, 30.0
    p = dispersion.sample_ellipse(a, b, psi, 4000, seed=3)
    cov = np.cov(np.stack([p.east_m, p.north_m]))
    w, v = np.linalg.eigh(cov)
    assert math.sqrt(w[1]) == pytest.approx(a / 3 * TRUNC_SD, rel=0.05)
    assert math.sqrt(w[0]) == pytest.approx(b / 3 * TRUNC_SD, rel=0.05)
    bearing = math.degrees(math.atan2(v[0, 1], v[1, 1])) % 180.0
    assert abs(bearing - psi) < 3.0
    assert abs(p.east_m.mean()) < 5.0 and abs(p.north_m.mean()) < 5.0


def test_all_points_inside_the_3_sigma_ellipse() -> None:
    a, b, psi = 250.0, 60.0, 117.0
    p = dispersion.sample_ellipse(a, b, psi, 3000, seed=1)
    r = math.radians(psi)
    along = p.east_m * math.sin(r) + p.north_m * math.cos(r)
    across = p.east_m * math.cos(r) - p.north_m * math.sin(r)
    assert np.all((along / a) ** 2 + (across / b) ** 2 <= 1.0 + 1e-9)
    assert len(p.east_m) == 3000 and p.weights.sum() == pytest.approx(1.0)


def test_same_inputs_same_points_and_a_seed_changes_them() -> None:
    a = dispersion.sample_ellipse(100, 50, 10, 200, seed=7)
    b = dispersion.sample_ellipse(100, 50, 10, 200, seed=7)
    c = dispersion.sample_ellipse(100, 50, 10, 200, seed=8)
    assert np.array_equal(a.east_m, b.east_m) and np.array_equal(a.north_m, b.north_m)
    assert not np.array_equal(a.east_m, c.east_m)


def test_outline_is_the_contour() -> None:
    e, n = dispersion.outline(300, 100, 0, 72)
    assert n.max() == pytest.approx(300.0, rel=1e-6)  # azimuth 0: major axis is north
    assert e.max() == pytest.approx(100.0, rel=1e-3)
    assert (e[0], n[0]) == pytest.approx((e[-1], n[-1]))


def test_weighted_percentiles() -> None:
    v = np.array([1.0, 2.0, 3.0, 4.0, np.nan])
    assert dispersion.weighted_percentiles(v, qs=(50.0,)) == (2.0,)
    heavy = dispersion.weighted_percentiles(
        np.array([1.0, 10.0]), np.array([1.0, 9.0]), qs=(10.0, 50.0)
    )
    assert heavy == (1.0, 10.0)
    assert dispersion.weighted_percentiles(np.array([np.nan])) is None


def test_bad_inputs_are_refused() -> None:
    with pytest.raises(ValueError):
        dispersion.sample_ellipse(0, 10, 0, 10)
    with pytest.raises(ValueError):
        dispersion.sample_ellipse(10, 10, 0, 0)
