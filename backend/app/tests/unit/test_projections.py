"""The site frame: grid convergence and scale, measured against closed forms.

Both are *measured* in ``local_frame`` by stepping due north, precisely so the
projection's sign conventions cannot be got subtly wrong. These tests check
the measurement against the textbook values, which is the independent evidence
that the measurement is right.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core.projections import geographic_to_polar, local_frame


@pytest.mark.parametrize("lat", [-89.9, -89.44, -88.0, -85.99, -84.36])
def test_scale_factor_matches_polar_stereographic_true_at_the_pole(lat: float) -> None:
    """k = 1 / cos^2(c / 2) for a stereographic projection true at the pole.

    Ignoring k put every ray's samples at the wrong ground range: 0.24 % at
    Nobile, a 0.063 deg skyline bias at Malapert.
    """
    c = math.radians(90.0 + lat)
    want = 1.0 / math.cos(c / 2.0) ** 2
    assert local_frame(222.7, lat).scale_factor == pytest.approx(want, rel=5e-6)


@pytest.mark.parametrize("lon", [0.0, 45.0, 129.2, 222.7, 300.0])
def test_a_ground_step_lands_at_the_projected_point(lon: float) -> None:
    """A 1 km step due north in the site frame must land where pyproj puts the
    point 1 km further north. This is convergence and scale checked together."""
    lat = -86.0
    frame = local_frame(lon, lat)
    gx, gy = frame.local_to_grid(np.array([0.0]), np.array([1_000.0]))
    dlat = math.degrees(1_000.0 / 1_737_400.0)
    ex, ey = geographic_to_polar(np.array([lon]), np.array([lat + dlat]))
    assert math.hypot(float(gx[0] - ex[0]), float(gy[0] - ey[0])) < 0.05  # metres
