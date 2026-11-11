"""Slope from an elevation grid, and the static tip-over angle (ADR-22)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core import hazards


def plane(slope_deg: float, aspect_deg: float, spacing: float, n: int = 12) -> np.ndarray:
    x, y = np.meshgrid(np.arange(n) * spacing, np.arange(n) * spacing)
    t = math.tan(math.radians(slope_deg))
    a = math.radians(aspect_deg)
    return t * (x * math.cos(a) + y * math.sin(a))


@pytest.mark.parametrize("aspect", [0.0, 45.0, 137.0, 270.0])
@pytest.mark.parametrize("spacing", [5.0, 20.0])
def test_a_10_degree_ramp_is_10_degrees_everywhere(aspect: float, spacing: float) -> None:
    g = hazards.horn_slope(plane(10.0, aspect, spacing), spacing)
    assert np.allclose(g.slope_deg[1:-1, 1:-1], 10.0, atol=1e-9)
    assert np.isnan(g.slope_deg[0]).all() and np.isnan(g.slope_deg[:, -1]).all()
    assert g.baseline_m == 3 * spacing


def test_slope_uncertainty_scales_with_error_over_baseline() -> None:
    z = plane(10.0, 30.0, 5.0)
    s1 = hazards.horn_slope(z, 5.0, 0.5).sigma_deg[3, 3]
    s2 = hazards.horn_slope(z, 5.0, 1.0).sigma_deg[3, 3]
    s3 = hazards.horn_slope(plane(10.0, 30.0, 10.0), 10.0, 0.5).sigma_deg[3, 3]
    assert s2 == pytest.approx(2 * s1)
    assert s3 == pytest.approx(s1 / 2)
    flat = hazards.horn_slope(np.zeros((5, 5)), 5.0, 0.5).sigma_deg[2, 2]
    assert flat == pytest.approx(math.degrees(0.5 * math.sqrt(12) / 40.0))


def test_tip_over_against_a_hand_value() -> None:
    # atan(4.6 / 3.0) = atan(1.5333...) = 56.8887 deg
    assert hazards.tip_over_deg(4.6, 1.5) == pytest.approx(56.8887, abs=1e-3)
    with pytest.raises(ValueError):
        hazards.tip_over_deg(4.6, 0.0)


def test_nan_neighbours_give_nan_and_exceedance_counts_only_known_cells() -> None:
    z = plane(10.0, 0.0, 5.0)
    z[5, 5] = np.nan
    g = hazards.horn_slope(z, 5.0)
    assert np.isnan(g.slope_deg[4:7, 4:7]).all()
    assert hazards.exceedance(np.array([5.0, 12.0, np.nan]), 10.0) == (1, 2)


def test_lookup_nearest() -> None:
    grid = np.arange(12.0).reshape(3, 4)
    x = np.array([101.0, 139.0, 99.0])
    y = np.array([49.0, 21.0, 49.0])
    v = hazards.lookup_nearest(grid, 100.0, 50.0, 10.0, x, y)
    assert v[0] == 0.0 and v[1] == 11.0 and np.isnan(v[2])
