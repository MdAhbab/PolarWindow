"""Topocentric azimuth/elevation, and the visibility predicate.

Pure. Takes body position vectors in the Moon body-fixed frame and a site's
selenographic coordinates; returns look angles and a three-state visibility
series. No SPICE, no I/O, no clock.

Why unit vectors and not spherical trigonometry
-----------------------------------------------
The textbook azimuth formula

    az = atan2(sin(dlon) cos(lat_t),
               cos(lat_s) sin(lat_t) - sin(lat_s) cos(lat_t) cos(dlon))

carries a ``cos(lat_s)`` that goes to zero at the pole. Every site in this
product is within a few degrees of -90 deg, and the nearest is at -89.68 deg,
where that term is 0.0056. The formula does not merely lose precision there --
it loses it *anisotropically*, so the error shows up as an azimuth that drifts
in a direction, which is indistinguishable from terrain. Building the local
east/north/up basis as explicit unit vectors and projecting onto it has no such
term and is exact at the pole itself.

This mirrors ``frontend/src/lib/geometry/ephemeris.ts::lookAngles``, which made
the same choice for the same reason. The two implementations are cross-checked
in ``tests/unit/test_visibility.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int8]

#: Three-state visibility. Not a boolean, because the shadow edge is exactly
#: where the terrain model is weakest and a boolean there would be a lie.
DARK: Final[int] = 0
PENUMBRAL: Final[int] = 1
LIT: Final[int] = 2


@dataclass(frozen=True, slots=True)
class ENUBasis:
    """Local east/north/up unit vectors at a site, in the body-fixed frame."""

    east: FloatArray
    north: FloatArray
    up: FloatArray


def enu_basis(lat_deg: float, lon_deg: float) -> ENUBasis:
    """Local topocentric basis at a site on a sphere.

    ``up`` is the outward surface normal; ``east`` points along increasing
    longitude; ``north = up x east`` completes a right-handed set.

    At the exact pole ``east`` is degenerate (any equatorial direction will do)
    and this returns the one consistent with the site's nominal longitude, which
    keeps azimuth continuous as latitude passes through -90 deg rather than
    flipping by 180 deg.
    """
    phi = np.radians(lat_deg)
    lam = np.radians(lon_deg)
    cphi, sphi = np.cos(phi), np.sin(phi)
    clam, slam = np.cos(lam), np.sin(lam)

    up = np.array([cphi * clam, cphi * slam, sphi], dtype=np.float64)
    east = np.array([-slam, clam, 0.0], dtype=np.float64)
    north = np.array([-sphi * clam, -sphi * slam, cphi], dtype=np.float64)
    return ENUBasis(east=east, north=north, up=up)


def site_position(lat_deg: float, lon_deg: float, radius_m: float) -> FloatArray:
    """Cartesian position of a site in the body-fixed frame, metres."""
    b = enu_basis(lat_deg, lon_deg)
    return b.up * radius_m


def look_angles(
    basis: ENUBasis,
    vectors: FloatArray,
    *,
    site_pos: FloatArray | None = None,
) -> tuple[FloatArray, FloatArray]:
    """Azimuth (deg from north, clockwise) and elevation (deg) of each vector.

    Parameters
    ----------
    basis:
        From :func:`enu_basis`.
    vectors:
        ``(n, 3)`` positions of the target relative to the Moon's **centre**.
    site_pos:
        The site's own position vector. When given, the target vector is made
        topocentric by subtracting it -- which matters for Earth (384,400 km
        away, so the 1,737 km offset shifts the direction by up to ~0.26 deg)
        and is negligible but harmless for the Sun. Omitting it is the
        geocentric approximation and is wrong at the level this product claims
        to be right.
    """
    v = np.asarray(vectors, dtype=np.float64).reshape(-1, 3)
    if site_pos is not None:
        v = v - site_pos[None, :]

    norm = np.linalg.norm(v, axis=1)
    norm = np.where(norm == 0.0, 1.0, norm)
    u = v / norm[:, None]

    e = u @ basis.east
    n = u @ basis.north
    up = u @ basis.up

    az = np.degrees(np.arctan2(e, n))
    az = np.mod(az, 360.0)
    el = np.degrees(np.arcsin(np.clip(up, -1.0, 1.0)))
    return az, el


def interp_horizon(horizon_el_deg: FloatArray, az_deg: FloatArray) -> FloatArray:
    """Linearly interpolate a horizon mask at arbitrary azimuths, wrapping at 360.

    The mask is sampled on a uniform azimuth grid of ``len(horizon_el_deg)``
    bins starting at 0 deg. Wrapping is handled by appending the first bin, so
    the segment from the last bin back to 0 deg is interpolated rather than
    clamped -- a clamp there puts a discontinuity at due north, and due north is
    not special.
    """
    n = horizon_el_deg.shape[0]
    if n == 0:
        raise ValueError("empty horizon mask")
    step = 360.0 / n
    grid = np.arange(n + 1, dtype=np.float64) * step
    values = np.concatenate([horizon_el_deg, horizon_el_deg[:1]])
    return np.asarray(np.interp(np.mod(az_deg, 360.0), grid, values), dtype=np.float64)


def visibility_state(margin_deg: FloatArray, angular_radius_deg: FloatArray | float) -> IntArray:
    """Three-state visibility from a margin and the body's angular radius.

    ``margin >  +R`` -> LIT       (whole disc clear of the skyline)
    ``margin <  -R`` -> DARK      (whole disc occluded)
    otherwise        -> PENUMBRAL (partially illuminated / partially occulted)

    The penumbral band is reported as a state, never folded into a number. The
    brief is explicit about this and it is the right call: at the shadow edge the
    20 m DEM cannot resolve the boulder that actually decides the answer, so a
    precise-looking fraction there would be false precision at exactly the point
    of maximum ignorance.
    """
    r = np.asarray(angular_radius_deg, dtype=np.float64)
    out = np.full(margin_deg.shape, PENUMBRAL, dtype=np.int8)
    out[margin_deg > r] = LIT
    out[margin_deg < -r] = DARK
    return out


def sun_earth_angular_radius_deg(distance_m: FloatArray, body_radius_m: float) -> FloatArray:
    """Apparent angular radius of a sphere of ``body_radius_m`` at ``distance_m``."""
    radius = np.degrees(np.arcsin(np.clip(body_radius_m / distance_m, -1.0, 1.0)))
    return np.asarray(radius, dtype=np.float64)
