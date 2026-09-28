"""Small, pure pieces of the trip section (T2, C0): where the Moon's pull wins,
and thinning a trajectory to the points a chart can draw.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


def equal_pull_distance_m(earth_moon_m: float, mu_earth: float, mu_moon: float) -> float:
    """Distance from the Moon's centre, on the Earth-Moon line, where the two pulls are equal.

    From mu_e / (D - x)^2 = mu_m / x^2: x = D sqrt(mu_m) / (sqrt(mu_e) + sqrt(mu_m)).
    About 38,300 km at the mean Earth-Moon distance.
    """
    sm, se = math.sqrt(mu_moon), math.sqrt(mu_earth)
    return earth_moon_m * sm / (se + sm)


def sphere_of_influence_m(earth_moon_m: float, mu_earth: float, mu_moon: float) -> float:
    """Laplace's sphere of influence of the Moon: D (mu_m / mu_e)^(2/5), about 66,000 km."""
    return float(earth_moon_m * (mu_moon / mu_earth) ** 0.4)


def pull_margin(
    r_earth_m: FloatArray, r_moon_m: FloatArray, mu_earth: float, mu_moon: float
) -> FloatArray:
    """> 0 where the Moon pulls harder than Earth (point masses)."""
    return np.asarray(mu_moon / r_moon_m**2 - mu_earth / r_earth_m**2, dtype=np.float64)


def first_crossing(t: FloatArray, margin: FloatArray) -> float | None:
    """The first time ``margin`` goes from <= 0 to > 0, linearly interpolated."""
    up = margin > 0
    idx = np.flatnonzero(~up[:-1] & up[1:])
    if idx.size == 0:
        return None
    i = int(idx[0])
    m0, m1 = float(margin[i]), float(margin[i + 1])
    return float(t[i] + (t[i + 1] - t[i]) * (-m0) / (m1 - m0))


def thin(n: int, n_max: int) -> npt.NDArray[np.intp]:
    """Indices of at most ``n_max`` evenly spread samples, first and last kept."""
    if n <= n_max:
        return np.arange(n, dtype=np.intp)
    out: npt.NDArray[np.intp] = np.unique(np.round(np.linspace(0, n - 1, n_max)).astype(np.intp))
    return out
