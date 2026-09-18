"""ENU basis and look angles, tested where they actually break: the pole.

Every site in this product is within a few degrees of -90, and the textbook
azimuth formula carries a cos(lat) that goes to zero there. It does not merely
lose precision -- it loses it directionally, so the error reads as terrain
rather than as noise. These tests exist to prove the unit-vector form does not.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core import visibility as vis


def _unit(lat_deg: float, lon_deg: float) -> np.ndarray:
    phi, lam = np.radians(lat_deg), np.radians(lon_deg)
    return np.array([np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)])


@pytest.mark.parametrize("lat", [-89.9999, -89.68, -85.0, -45.0, 0.0, 60.0])
@pytest.mark.parametrize("lon", [0.0, 90.0, 166.4, 272.9, 359.9])
def test_enu_basis_is_orthonormal(lat: float, lon: float) -> None:
    b = vis.enu_basis(lat, lon)
    for v in (b.east, b.north, b.up):
        assert np.linalg.norm(v) == pytest.approx(1.0, abs=1e-12)
    assert b.east @ b.north == pytest.approx(0.0, abs=1e-12)
    assert b.north @ b.up == pytest.approx(0.0, abs=1e-12)
    assert b.up @ b.east == pytest.approx(0.0, abs=1e-12)
    # Right-handed: east x north = up. A sign flip here shows up downstream as
    # a 180-degree azimuth error, which looks exactly like different terrain.
    assert np.cross(b.east, b.north) == pytest.approx(b.up, abs=1e-12)


def test_zenith_is_ninety_degrees() -> None:
    b = vis.enu_basis(-88.0, 40.0)
    az, el = vis.look_angles(b, (b.up * 1e9)[None, :])
    assert el[0] == pytest.approx(90.0, abs=1e-9)
    assert np.isfinite(az[0])


def test_horizon_is_zero_elevation() -> None:
    b = vis.enu_basis(-88.0, 40.0)
    for direction in (b.east, b.north, -b.east, -b.north):
        _az, el = vis.look_angles(b, (direction * 1e9)[None, :])
        assert el[0] == pytest.approx(0.0, abs=1e-9)


def test_azimuth_cardinals() -> None:
    """North-clockwise, matching the frontend's lookAngles."""
    b = vis.enu_basis(-85.0, 30.0)
    cases = [(b.north, 0.0), (b.east, 90.0), (-b.north, 180.0), (-b.east, 270.0)]
    for direction, expected in cases:
        az, _el = vis.look_angles(b, (direction * 1e9)[None, :])
        assert az[0] % 360 == pytest.approx(expected, abs=1e-9)


def test_azimuth_is_stable_at_the_pole() -> None:
    """Sweep a target right round a near-pole site; azimuth must not jump.

    The spherical-trig formula fails this; the unit-vector form passes. Without
    a test the difference is invisible until it shows up as a phantom blocker.
    """
    b = vis.enu_basis(-89.9999, 12.0)
    angles = np.linspace(0, 2 * np.pi, 721)
    vecs = np.stack([np.sin(a) * b.east + np.cos(a) * b.north + 0.02 * b.up for a in angles]) * 1e9
    az, _el = vis.look_angles(b, vecs)
    unwrapped = np.degrees(np.unwrap(np.radians(az)))
    steps = np.abs(np.diff(unwrapped))
    assert steps.max() < 1.0, f"azimuth jumped by {steps.max():.3f} deg"


def test_topocentric_offset_matters_for_earth() -> None:
    """Subtracting the site vector is not optional at Earth's distance.

    The Moon's 1,737 km radius against Earth's 384,400 km shifts the apparent
    direction by up to ~0.26 degrees -- larger than the Sun's whole disc, and
    far larger than the differences this product reports.
    """
    b = vis.enu_basis(-88.0, 0.0)
    site = vis.site_position(-88.0, 0.0, 1_737_400.0)
    earth = np.array([[3.844e8, 0.0, 0.0]])
    _az_geo, el_geo = vis.look_angles(b, earth)
    _az_topo, el_topo = vis.look_angles(b, earth, site_pos=site)
    assert abs(el_geo[0] - el_topo[0]) > 0.1


def test_interp_horizon_wraps_at_360() -> None:
    """The segment from the last bin back to 0 is interpolated, not clamped.

    Clamping puts a discontinuity at due north, and due north is not special --
    but it is where the Sun's azimuth passes every lunar day at every site.
    """
    mask = np.array([0.0, 10.0, 20.0, 30.0])  # bins at 0, 90, 180, 270
    got = vis.interp_horizon(mask, np.array([315.0]))
    assert got[0] == pytest.approx(15.0, abs=1e-9)
    assert vis.interp_horizon(mask, np.array([360.0]))[0] == pytest.approx(0.0, abs=1e-9)


def test_visibility_three_states() -> None:
    margin = np.array([1.0, 0.1, -0.1, -1.0])
    state = vis.visibility_state(margin, 0.5)
    assert state.tolist() == [vis.LIT, vis.PENUMBRAL, vis.PENUMBRAL, vis.DARK]


def test_disc_fraction_is_monotonic_and_bounded() -> None:
    m = np.linspace(-1.0, 1.0, 101)
    frac = vis.disc_fraction_clear(m, 0.5)
    assert frac.min() >= 0.0 and frac.max() <= 1.0
    assert np.all(np.diff(frac) >= -1e-12)
    assert vis.disc_fraction_clear(np.array([0.0]), 0.5)[0] == pytest.approx(0.5, abs=1e-9)


def test_matches_frontend_reference_implementation() -> None:
    """Agree with the TypeScript engine's lookAngles to 1e-9.

    Two independently written implementations of the same maths. Cheap to run,
    and it is what makes the Python port auditable rather than merely plausible.
    """

    def reference(
        site_lat: float, site_lon: float, t_lat: float, t_lon: float
    ) -> tuple[float, float]:
        # Transcribed from frontend/src/lib/geometry/ephemeris.ts::lookAngles
        phi, lam = np.radians(site_lat), np.radians(site_lon)
        cphi, sphi, clam, slam = np.cos(phi), np.sin(phi), np.cos(lam), np.sin(lam)
        upx, upy, upz = cphi * clam, cphi * slam, sphi
        ex, ey = -slam, clam
        nx, ny, nz = -sphi * clam, -sphi * slam, cphi
        tphi, tlam = np.radians(t_lat), np.radians(t_lon)
        ct = np.cos(tphi)
        sx, sy, sz = ct * np.cos(tlam), ct * np.sin(tlam), np.sin(tphi)
        e = sx * ex + sy * ey
        n = sx * nx + sy * ny + sz * nz
        u = sx * upx + sy * upy + sz * upz
        return float(np.degrees(np.arctan2(e, n)) % 360), float(
            np.degrees(np.arcsin(np.clip(u, -1, 1)))
        )

    rng = np.random.default_rng(20260918)
    for _ in range(400):
        slat = float(rng.uniform(-90, -80))
        slon = float(rng.uniform(0, 360))
        tlat = float(rng.uniform(-90, 90))
        tlon = float(rng.uniform(0, 360))
        exp_az, exp_el = reference(slat, slon, tlat, tlon)
        b = vis.enu_basis(slat, slon)
        vec = _unit(tlat, tlon)[None, :] * 1e9
        az, el = vis.look_angles(b, vec)
        assert az[0] == pytest.approx(exp_az, abs=1e-9)
        assert el[0] == pytest.approx(exp_el, abs=1e-9)
