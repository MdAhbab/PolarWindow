"""The spherical-harmonic gravity against an independent evaluation.

The reference sums the same series in latitude and longitude with SciPy's
associated Legendre functions and an explicit normalisation, a different
formulation from the Cunningham recursion under test; its gradient is taken
analytically in spherical coordinates away from the poles.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.special import lpmv

from app.core import gravity


def _norm(n: int, m: int) -> float:
    return math.sqrt((2 - (m == 0)) * (2 * n + 1) * math.factorial(n - m) / math.factorial(n + m))


def _reference_u(field: gravity.Field, r: float, lat: float, lon: float, nmin: int = 0) -> float:
    sphi = math.sin(lat)
    total = 0.0
    for n in range(nmin, field.degree + 1):
        for m in range(0, n + 1):
            # SciPy includes the Condon-Shortley phase; geodesy does not.
            p = (-1) ** m * lpmv(m, n, sphi) * _norm(n, m)
            total += (
                (field.radius_m / r) ** (n + 1)
                * p
                * (field.c[n, m] * math.cos(m * lon) + field.s[n, m] * math.sin(m * lon))
            )
    return field.gm / field.radius_m * total


@pytest.fixture(scope="module")
def field() -> gravity.Field:
    rng = np.random.default_rng(7)
    n = 12
    c = np.zeros((n + 1, n + 1))
    s = np.zeros((n + 1, n + 1))
    c[0, 0] = 1.0
    for i in range(2, n + 1):
        for j in range(0, i + 1):
            c[i, j] = rng.normal(0, 1e-5)
            s[i, j] = 0.0 if j == 0 else rng.normal(0, 1e-5)
    return gravity.Field(4.9028e12, 1.738e6, c, s, n)


@pytest.mark.parametrize(("lat", "lon"), [(0.3, 1.0), (-1.2, 4.0), (1.5, -2.0), (-1.5690, 0.3)])
def test_potential_matches_the_latitude_longitude_sum(field, lat, lon) -> None:
    r = 1.85e6
    xyz = r * np.array(
        [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
    )
    got = gravity.potential(field, xyz)
    ref = _reference_u(field, r, lat, lon)
    assert got == pytest.approx(ref, rel=1e-12)


def test_gradient_matches_a_fine_difference_of_the_reference(field) -> None:
    lat, lon, r = 0.4, 2.2, 1.9e6
    xyz = r * np.array(
        [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
    )
    a = gravity.acceleration(field, xyz, include_central=False)
    h = 5.0
    ref = np.zeros(3)
    for k in range(3):
        e = np.zeros(3)
        e[k] = h

        def u(p: np.ndarray) -> float:
            rr = float(np.linalg.norm(p))
            # Perturbation only: summing it onto GM/r would lose ~1e-10 m/s^2 to rounding.
            return _reference_u(field, rr, math.asin(p[2] / rr), math.atan2(p[1], p[0]), nmin=1)

        ref[k] = (u(xyz + e) - u(xyz - e)) / (2 * h)
    assert np.allclose(a, ref, rtol=1e-6, atol=1e-12)


def test_the_pole_is_not_special(field) -> None:
    # Directly over the south pole, where a latitude formulation divides by zero.
    a = gravity.acceleration(field, np.array([0.0, 0.0, -1.85e6]))
    assert np.all(np.isfinite(a))


def test_point_mass_and_j2_limit() -> None:
    gm, re = 3.986004415e14, 6378136.3
    c20 = -0.484165143790815e-03
    f = gravity.zonal_field(gm, re, {2: c20})
    r = np.array([7.0e6, 0.0, 0.0])  # on the equator
    a = gravity.acceleration(f, r)
    j2 = -c20 * math.sqrt(5)
    # Equatorial J2 acceleration: -GM/r^2 (1 + 1.5 J2 (Re/r)^2).
    expect = -gm / 7.0e6**2 * (1 + 1.5 * j2 * (re / 7.0e6) ** 2)
    assert a[0] == pytest.approx(expect, rel=1e-9)
    assert abs(a[1]) < 1e-12 and abs(a[2]) < 1e-12


def test_the_grail_reader_stops_at_the_requested_degree() -> None:
    from app.data.gravity import parse

    head = " 1.738e+03, 4.9028001224453001e+03, 6.4e-15, 1200, 1200,    1, 0.0, 0.0"
    rows = [
        "    2,    0, -9.09e-05, 0.0, 1e-12, 0.0",
        "    2,    1, 1.0e-09, 2.0e-09, 1e-12, 1e-12",
        "    2,    2, 3.47e-05, 1.0e-09, 1e-12, 1e-12",
        "    3,    0, -3.2e-06, 0.0, 1e-12, 0.0",
    ]
    f = parse([head, *rows], degree=2)
    assert f.degree == 2 and f.c.shape == (3, 3)
    assert f.gm == pytest.approx(4.9028001224453001e12) and f.radius_m == 1.738e6
    assert f.c[2, 0] == -9.09e-05 and f.s[2, 1] == 2.0e-09 and f.c[0, 0] == 1.0
    with pytest.raises(ValueError):
        parse([head.replace("    1, 0.0", "    0, 0.0"), *rows], degree=2)
