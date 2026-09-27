"""Spherical-harmonic gravity: the Moon's lumpy field and Earth's zonal terms. Pure.

The potential is summed with the fully normalised Cunningham recursion for
``V_nm``, ``W_nm`` (Montenbruck and Gill, *Satellite Orbits*, 2000, section
3.2.4, with the normalisation carried through the recursion), which has no
singularity at the poles: lunar polar orbits and south-polar landing sites
are exactly where a latitude-longitude formulation breaks down.

    U = GM/R * sum_{n=0}^{N} sum_{m=0}^{n} (C_nm V_nm + S_nm W_nm)

with V_00 = R/r. The acceleration is the gradient of the non-spherical part
by central differences (step ``H_M``), evaluated in the body-fixed frame; the
point-mass part is added analytically. The step is chosen so that truncation
(h^2 terms) and rounding (eps * U_pert / h) are both below 1e-12 m/s^2 for
the Moon at orbital heights; ``test_gravity.py`` pins the gradient against an
independent spherical-coordinate evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
from numba import njit

FloatArray = npt.NDArray[np.float64]

#: Central-difference step for the gradient, metres.
H_M: Final[float] = 1.0


@dataclass(frozen=True, slots=True)
class Field:
    """A fully normalised spherical-harmonic field in its body-fixed frame."""

    gm: float  # m^3/s^2
    radius_m: float
    c: FloatArray  # (N+1, N+1), C[n, m]
    s: FloatArray
    degree: int

    def truncated(self, n: int) -> Field:
        n = min(n, self.degree)
        return Field(
            self.gm,
            self.radius_m,
            self.c[: n + 1, : n + 1].copy(),
            self.s[: n + 1, : n + 1].copy(),
            n,
        )


@njit(cache=True)  # type: ignore[misc]
def _potential(
    x: float,
    y: float,
    z: float,
    c: FloatArray,
    s: FloatArray,
    radius: float,
    nmax: int,
    skip_central: bool,
) -> float:
    r2 = x * x + y * y + z * z
    rho = radius * radius / r2
    x0 = radius * x / r2
    y0 = radius * y / r2
    z0 = radius * z / r2
    v = np.zeros((nmax + 1, nmax + 1))
    w = np.zeros((nmax + 1, nmax + 1))
    v[0, 0] = radius / np.sqrt(r2)
    w[0, 0] = 0.0
    for m in range(0, nmax + 1):
        if m > 0:
            f = np.sqrt(3.0) if m == 1 else np.sqrt((2.0 * m + 1.0) / (2.0 * m))
            v[m, m] = f * (x0 * v[m - 1, m - 1] - y0 * w[m - 1, m - 1])
            w[m, m] = f * (x0 * w[m - 1, m - 1] + y0 * v[m - 1, m - 1])
        if m + 1 <= nmax:
            n = m + 1
            a = np.sqrt((2.0 * n - 1.0) * (2.0 * n + 1.0) / ((n - m) * (n + m)))
            v[n, m] = a * z0 * v[n - 1, m]
            w[n, m] = a * z0 * w[n - 1, m]
        for n in range(m + 2, nmax + 1):
            a = np.sqrt((2.0 * n - 1.0) * (2.0 * n + 1.0) / ((n - m) * (n + m)))
            b = np.sqrt(
                (2.0 * n + 1.0)
                * (n + m - 1.0)
                * (n - m - 1.0)
                / ((2.0 * n - 3.0) * (n + m) * (n - m))
            )
            v[n, m] = a * z0 * v[n - 1, m] - b * rho * v[n - 2, m]
            w[n, m] = a * z0 * w[n - 1, m] - b * rho * w[n - 2, m]
    total = 0.0
    for n in range(0, nmax + 1):
        if skip_central and n == 0:
            continue
        for m in range(0, n + 1):
            total += c[n, m] * v[n, m] + s[n, m] * w[n, m]
    return total


def potential(field: Field, r_bf: FloatArray, *, include_central: bool = True) -> float:
    """Gravitational potential (m^2/s^2, positive) at a body-fixed position (m)."""
    x, y, z = (float(v) for v in r_bf)
    sigma = _potential(x, y, z, field.c, field.s, field.radius_m, field.degree, not include_central)
    return float(field.gm / field.radius_m * sigma)


@njit(cache=True)  # type: ignore[misc]
def _grad(
    x: float, y: float, z: float, c: FloatArray, s: FloatArray, radius: float, nmax: int, h: float
) -> tuple[float, float, float]:
    gx = (
        _potential(x + h, y, z, c, s, radius, nmax, True)
        - _potential(x - h, y, z, c, s, radius, nmax, True)
    ) / (2.0 * h)
    gy = (
        _potential(x, y + h, z, c, s, radius, nmax, True)
        - _potential(x, y - h, z, c, s, radius, nmax, True)
    ) / (2.0 * h)
    gz = (
        _potential(x, y, z + h, c, s, radius, nmax, True)
        - _potential(x, y, z - h, c, s, radius, nmax, True)
    ) / (2.0 * h)
    return gx, gy, gz


def acceleration(field: Field, r_bf: FloatArray, *, include_central: bool = True) -> FloatArray:
    """Gravitational acceleration (m/s^2) at a body-fixed position (m)."""
    x, y, z = (float(v) for v in r_bf)
    out = np.zeros(3)
    if field.degree >= 2:
        gx, gy, gz = _grad(x, y, z, field.c, field.s, field.radius_m, field.degree, H_M)
        out[:] = (gx, gy, gz)
        out *= field.gm / field.radius_m
    if include_central:
        r = np.sqrt(x * x + y * y + z * z)
        out += -field.gm * np.array([x, y, z]) / r**3
    return out


def zonal_field(gm: float, radius_m: float, c_n0: dict[int, float]) -> Field:
    """A field with only zonal terms (Earth's J2..J6), from normalised C_n0."""
    n = max(c_n0)
    c = np.zeros((n + 1, n + 1))
    c[0, 0] = 1.0
    for k, v in c_n0.items():
        c[k, 0] = v
    return Field(gm, radius_m, c, np.zeros_like(c), n)
