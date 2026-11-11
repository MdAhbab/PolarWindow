"""The landing ellipse as a distribution of touchdown points (ADR-22).

A published landing ellipse is a 3-sigma contour of a bivariate normal. This
module turns ``(a, b, psi)`` into a fixed set of points that follow that
distribution, so that anything evaluated at the points (slope, illumination)
has a distribution over the ellipse and not just a value at its centre.

The points come from a Halton sequence (bases 2 and 3) pushed through the
inverse normal CDF, then cut at 3 sigma. A seed gives the sequence a fixed
Cranley-Patterson shift, so the same inputs always give the same points and
nothing depends on a global random state. Pure: no I/O, no clock.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
from scipy.special import ndtri

FloatArray = npt.NDArray[np.float64]

#: The ellipse is the 3-sigma contour.
SIGMA_LIMIT: Final[float] = 3.0
_BASES: Final[tuple[int, int]] = (2, 3)


def _halton(n: int, base: int, start: int = 1) -> FloatArray:
    """``n`` terms of the van der Corput sequence in ``base``, from index ``start``."""
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        k = start + i
        f = 1.0
        r = 0.0
        while k > 0:
            f /= base
            r += f * (k % base)
            k //= base
        out[i] = r
    return out


@dataclass(frozen=True, slots=True)
class Points:
    """Offsets from the ellipse centre in metres, east and north, with equal weights."""

    east_m: FloatArray
    north_m: FloatArray
    weights: FloatArray


def sample_ellipse(
    semi_major_m: float, semi_minor_m: float, azimuth_deg: float, n: int, seed: int = 0
) -> Points:
    """``n`` points of the 3-sigma-truncated bivariate normal.

    ``semi_major_m`` and ``semi_minor_m`` are the 3-sigma half-axes (so sigma is
    a third of each). ``azimuth_deg`` is the bearing of the major axis from true
    north, clockwise. Every point lies inside the ellipse.
    """
    if n < 1:
        raise ValueError("need at least one point")
    if semi_major_m <= 0 or semi_minor_m <= 0:
        raise ValueError("the half-axes must be positive")
    shift = np.random.default_rng(seed).random(2)
    cap = 1.0 - math.exp(-0.5 * SIGMA_LIMIT**2)  # share of the normal inside 3 sigma
    take = int(math.ceil(n / cap)) + 8
    start = 1
    zs: list[FloatArray] = []
    have = 0
    while have < n:
        u = np.stack(
            [(_halton(take, b, start) + s) % 1.0 for b, s in zip(_BASES, shift, strict=False)],
            axis=1,
        )
        u = np.clip(u, 1e-12, 1.0 - 1e-12)
        z = ndtri(u)
        z = z[np.hypot(z[:, 0], z[:, 1]) <= SIGMA_LIMIT]
        zs.append(z)
        have += len(z)
        start += take
    z = np.concatenate(zs)[:n]
    sa = semi_major_m / SIGMA_LIMIT
    sb = semi_minor_m / SIGMA_LIMIT
    psi = math.radians(azimuth_deg)
    major = (math.sin(psi), math.cos(psi))  # east, north
    minor = (math.cos(psi), -math.sin(psi))
    east = z[:, 0] * sa * major[0] + z[:, 1] * sb * minor[0]
    north = z[:, 0] * sa * major[1] + z[:, 1] * sb * minor[1]
    return Points(east, north, np.full(n, 1.0 / n))


def outline(
    semi_major_m: float, semi_minor_m: float, azimuth_deg: float, vertices: int = 72
) -> tuple[FloatArray, FloatArray]:
    """The 3-sigma contour as a closed ring of east/north offsets, metres."""
    t = np.linspace(0.0, 2.0 * math.pi, vertices + 1)
    psi = math.radians(azimuth_deg)
    p, q = semi_major_m * np.cos(t), semi_minor_m * np.sin(t)
    east = p * math.sin(psi) + q * math.cos(psi)
    north = p * math.cos(psi) - q * math.sin(psi)
    return east, north


def weighted_percentiles(
    values: FloatArray,
    weights: FloatArray | None = None,
    qs: tuple[float, ...] = (10.0, 50.0, 90.0),
) -> tuple[float, ...] | None:
    """Weighted percentiles of the finite ``values``; None when none are finite.

    A percentile is the smallest value whose cumulative weight reaches ``q`` per
    cent (the weighted empirical distribution; no interpolation, so a reported
    percentile is always a value that occurred).
    """
    v = np.asarray(values, dtype=np.float64)
    w = np.ones_like(v) if weights is None else np.asarray(weights, dtype=np.float64)
    ok = np.isfinite(v) & (w > 0)
    if not ok.any():
        return None
    v, w = v[ok], w[ok]
    order = np.argsort(v, kind="stable")
    v, w = v[order], w[order]
    cum = np.cumsum(w) / w.sum()
    idx = [min(int(np.searchsorted(cum, q / 100.0 - 1e-12)), len(v) - 1) for q in qs]
    return tuple(float(v[i]) for i in idx)
