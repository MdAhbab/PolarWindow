"""Slope and tip-over from an elevation grid (ADR-22).

A slope is only meaningful with its baseline: the same ground is gentler at
80 m than at 5 m. Every slope here is returned with the baseline it was taken
over, and slopes from different baselines are never put in one statistic.

Pure: no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

#: Horn's 3x3 stencil spans three posts.
HORN_BASELINE_POSTS = 3.0
#: Variance of the Horn gradient for independent post errors, in units of
#: sigma_z^2 / spacing^2: the squared weights (1,2,1 on each side) sum to 12, over 8^2.
_HORN_VAR = 12.0 / 64.0


@dataclass(frozen=True, slots=True)
class SlopeGrid:
    slope_deg: FloatArray
    sigma_deg: FloatArray
    spacing_m: float
    #: Ground the slope averages over: three posts.
    baseline_m: float


def horn_slope(z: FloatArray, spacing_m: float, sigma_z_m: float | FloatArray = 0.0) -> SlopeGrid:
    """Horn's 3x3 weighted gradient, in degrees, with its 1-sigma uncertainty.

    Only the gradient's magnitude is used, so the grid's row direction does not
    matter. The edge ring and any cell with a missing neighbour are NaN. The
    uncertainty propagates ``sigma_z_m`` through the stencil as independent post
    errors (``sigma_g = sigma_z * sqrt(12) / (8 * spacing)``) and then through the
    arctangent, so it scales with the elevation error over the spacing. Errors in
    a gridded DEM are correlated, which would lower it: this is the larger figure.
    """
    z = np.asarray(z, dtype=np.float64)
    if spacing_m <= 0:
        raise ValueError("spacing must be positive")
    if z.ndim != 2 or min(z.shape) < 3:
        raise ValueError("need a grid of at least 3 x 3")
    a, b, c = z[:-2, :-2], z[:-2, 1:-1], z[:-2, 2:]
    d, f = z[1:-1, :-2], z[1:-1, 2:]
    g, h, i = z[2:, :-2], z[2:, 1:-1], z[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8.0 * spacing_m)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8.0 * spacing_m)
    grad = np.hypot(dzdx, dzdy)
    slope = np.full(z.shape, np.nan)
    slope[1:-1, 1:-1] = np.degrees(np.arctan(grad))
    sz = np.asarray(sigma_z_m, dtype=np.float64)
    sz_in = sz if sz.ndim == 0 else sz[1:-1, 1:-1]
    sg = sz_in * math.sqrt(_HORN_VAR) / spacing_m
    sigma = np.full(z.shape, np.nan)
    sigma[1:-1, 1:-1] = np.degrees(sg / (1.0 + grad**2))
    slope[~np.isfinite(z)] = np.nan
    sigma[~np.isfinite(slope)] = np.nan
    return SlopeGrid(slope, sigma, spacing_m, HORN_BASELINE_POSTS * spacing_m)


def tip_over_deg(footprint_diameter_m: float, cg_height_m: float) -> float:
    """Static tip-over angle ``atan(D / (2 h_CG))`` in degrees."""
    if footprint_diameter_m <= 0 or cg_height_m <= 0:
        raise ValueError("footprint diameter and CG height must be positive")
    return math.degrees(math.atan(footprint_diameter_m / (2.0 * cg_height_m)))


def lookup_nearest(
    grid: FloatArray,
    origin_x_m: float,
    origin_y_m: float,
    spacing_m: float,
    x: FloatArray,
    y: FloatArray,
) -> FloatArray:
    """Value of the cell containing each point; NaN outside the grid.

    ``origin`` is the outer corner of the top-left cell; rows run to -y.
    """
    col = np.floor((np.asarray(x) - origin_x_m) / spacing_m).astype(np.int64)
    row = np.floor((origin_y_m - np.asarray(y)) / spacing_m).astype(np.int64)
    h, w = grid.shape
    ok = (col >= 0) & (col < w) & (row >= 0) & (row < h)
    out = np.full(np.shape(x), np.nan)
    out[ok] = grid[row[ok], col[ok]]
    return out


def exceedance(slope_deg: FloatArray, limit_deg: float) -> tuple[int, int]:
    """``(k, n)``: points above ``limit_deg`` among the ``n`` that have a slope."""
    ok = np.isfinite(slope_deg)
    return int(np.count_nonzero(slope_deg[ok] > limit_deg)), int(np.count_nonzero(ok))
