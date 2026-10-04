"""Unit tests for the SLDEM2015 reader, projection geometry, and terrain sampler."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core.horizon import build_mask
from app.core.projections import R_MOON_M
from app.data.sldem import (
    SLDEM_PRODUCT_NAME,
    SldemTile,
    destination_spherical,
    is_terrain_covered,
    make_sldem_samplers,
)


def test_destination_spherical_steps() -> None:
    """Test spherical destination from the equator and north."""
    # From (0, 0), step 10 km north
    lat_n, lon_n = destination_spherical(0.0, 0.0, np.array([0.0]), np.array([10_000.0]))
    expected_dlat = math.degrees(10_000.0 / R_MOON_M)
    assert float(lat_n[0]) == pytest.approx(expected_dlat, rel=1e-6)
    assert float(lon_n[0]) == pytest.approx(0.0, abs=1e-6)

    # From (0, 0), step 10 km east
    lat_e, lon_e = destination_spherical(0.0, 0.0, np.array([10_000.0]), np.array([0.0]))
    assert float(lat_e[0]) == pytest.approx(0.0, abs=1e-6)
    assert float(lon_e[0]) == pytest.approx(expected_dlat, rel=1e-6)


def test_sldem_longitude_wrap() -> None:
    """Check that longitude wrapping across 0/360 deg does not break sampling."""
    # Synthetic tile covering lon 355 to 5 (crossing 0)
    # Origin at lat 10.0, lon 355.0
    size = 200
    res_deg = 0.05
    heights = np.zeros((size, size), dtype=np.float32)

    tile = SldemTile(
        heights=heights,
        origin_lat_deg=10.0,
        origin_lon_deg=355.0,
        dlat_deg=-res_deg,
        dlon_deg=res_deg,
        product=SLDEM_PRODUCT_NAME,
        scale_m=1500.0,
        vertical_error_m=3.5,
    )

    # Site at lon 359.5, sample 50 km east (which crosses into ~1.1 deg lon)
    sample, _ = make_sldem_samplers(5.0, 359.5, tile)
    z = sample(np.array([50_000.0]), np.array([0.0]))
    assert np.isfinite(z[0])


def test_edge_returns_nan_not_index_error() -> None:
    """Sampling outside the window returns NaN rather than raising IndexError."""
    heights = np.zeros((50, 50), dtype=np.float32)
    tile = SldemTile(
        heights=heights,
        origin_lat_deg=10.0,
        origin_lon_deg=50.0,
        dlat_deg=-0.01,
        dlon_deg=0.01,
        product=SLDEM_PRODUCT_NAME,
        scale_m=300.0,
        vertical_error_m=3.5,
    )
    sample, sigma = make_sldem_samplers(10.0, 50.0, tile)
    # Query 100 km away: well outside 0.5 deg window
    z = sample(np.array([100_000.0]), np.array([100_000.0]))
    s = sigma(np.array([100_000.0]), np.array([100_000.0]))
    assert np.isnan(z[0])
    assert np.isnan(s[0])


def test_synthetic_cone_horizon_matches_analytic_angle() -> None:
    """A synthetic cone around a site: ray-marched horizon matches analytic angle.

    Build a conical depression or wall around site (10 deg N, 60 deg E):
    At distance r from site, height is h(r) = max(0, 1000 - 0.1 * r).
    At r = 2000 m, h = 800 m.
    At site (r = 0), h_site = 1000 m.
    Instead, build an obstacle ring at radius r_ring = 10,000 m with height h_ring = 1,000 m
    on flat ground (h = 0).
    Then theta = atan2(1000 - r_ring^2 / (2 * R_MOON), 10000).
    """
    site_lat, site_lon = 10.0, 60.0
    r_ring = 10_000.0
    h_ring = 1_000.0

    # Grid covering +- 20 km around site: ~0.7 deg
    res_deg = 0.002  # ~60 m
    n_pts = 800
    lat_top = site_lat + (n_pts // 2) * res_deg
    lon_left = site_lon - (n_pts // 2) * res_deg

    # Create grid of heights with a circular ridge at r_ring
    # Use destination_spherical to populate grid distances
    lats = lat_top - np.arange(n_pts) * res_deg
    lons = lon_left + np.arange(n_pts) * res_deg
    grid_lon, grid_lat = np.meshgrid(lons, lats)

    # Approximate ground distance to site
    dlat_m = (grid_lat - site_lat) * math.radians(1.0) * R_MOON_M
    dlon_m = (grid_lon - site_lon) * math.radians(1.0) * R_MOON_M * math.cos(math.radians(site_lat))
    dist_grid = np.hypot(dlon_m, dlat_m)

    # Ridge Gaussian or ring around r_ring
    heights = np.zeros((n_pts, n_pts), dtype=np.float32)
    ring_mask = np.abs(dist_grid - r_ring) < 100.0
    heights[ring_mask] = h_ring

    tile = SldemTile(
        heights=heights,
        origin_lat_deg=float(lat_top),
        origin_lon_deg=float(lon_left),
        dlat_deg=-res_deg,
        dlon_deg=res_deg,
        product=SLDEM_PRODUCT_NAME,
        scale_m=60.0,
        vertical_error_m=3.5,
    )

    sampler, sig_sampler = make_sldem_samplers(site_lat, site_lon, tile)

    mask = build_mask(
        sampler,
        azimuth_step_deg=1.0,
        max_range_m=20_000.0,
        dem_post_spacing_m=60.0,
        dem_vertical_error_m=3.5,
        sample_sigma=sig_sampler,
    )

    # Analytic angle:
    drop = (r_ring**2) / (2.0 * R_MOON_M)
    analytic_theta_deg = math.degrees(math.atan2(h_ring - drop, r_ring))

    # All azimuths should see the ring at ~analytic_theta_deg
    assert np.all(mask.coverage > 0.99)
    assert np.mean(mask.el_deg) == pytest.approx(analytic_theta_deg, abs=0.1)


def test_coverage_detection() -> None:
    """Verify is_terrain_covered for polar and equatorial mission coordinates."""
    # APEX-1 (Schrödinger, 74.73S)
    assert is_terrain_covered(-74.73, 132.93)
    # Blue Ghost 1 (18.56N, 61.81E)
    assert is_terrain_covered(18.5623, 61.8103)
    # Peregrine M1 (35.25N, 319.01E)
    assert is_terrain_covered(35.25, 319.01)
    # IM-3 (7.39N, 301.04E)
    assert is_terrain_covered(7.39, 301.04)
    # Uncovered coordinate outside our tiles (e.g. 70°N)
    assert not is_terrain_covered(70.0, 100.0)
