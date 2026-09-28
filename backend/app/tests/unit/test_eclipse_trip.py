"""Conical shadows and the Moon's pull (T2). Pure; no kernels."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core import eclipse, trip

AU = 1.495978707e11
R_SUN = 6.957e8
R_EARTH = 6.371e6


def _occ(sep_rad: float, a: float, b: float) -> eclipse.Occultation:
    return eclipse.Occultation(
        sun_radius=np.array([a]), body_radius=np.array([b]), separation=np.array([sep_rad])
    )


def test_no_overlap_full_cover_and_annular() -> None:
    assert _occ(1.0, 0.1, 0.2).visible_fraction()[0] == 1.0
    assert _occ(0.05, 0.1, 0.2).visible_fraction()[0] == 0.0
    # Annular: the body (radius 0.05) sits inside the Sun's disc (radius 0.1).
    assert _occ(0.01, 0.1, 0.05).visible_fraction()[0] == pytest.approx(1 - 0.25)


def test_half_covered_equal_discs_by_symmetry() -> None:
    # Equal discs with centres one radius apart overlap in 2(pi/3 - sqrt(3)/4) r^2.
    r = 0.01
    f = _occ(r, r, r).visible_fraction()[0]
    lens = 2 * (math.pi / 3 - math.sqrt(3) / 4)
    assert f == pytest.approx(1 - lens / math.pi, rel=1e-9)


def test_states_and_runs_behind_earth() -> None:
    # A spacecraft passing straight behind Earth, 7,000 km from its centre.
    t = np.arange(0.0, 7200.0, 60.0)
    x = 7.0e6 * np.cos(2 * np.pi * t / 7200.0)
    y = 7.0e6 * np.sin(2 * np.pi * t / 7200.0)
    sc = np.stack([x, y, np.zeros_like(x)], axis=1)
    sun = np.array([AU, 0.0, 0.0])
    occ = eclipse.occultation(sun - sc, -sc, R_SUN, R_EARTH)
    st = eclipse.state([occ])
    assert st[0] == eclipse.LIT and st[t.size // 2] == eclipse.DARK
    runs = [r for r in eclipse.shadow_runs(t, [occ]) if r.value]
    assert len(runs) == 1 and 0.3 < runs[0].duration / 7200 < 0.45


def test_where_the_moons_pull_wins() -> None:
    mu_e, mu_m = 3.986004e14, 4.9028e12
    d = 3.844e8
    x = trip.equal_pull_distance_m(d, mu_e, mu_m)
    assert 37_000e3 < x < 39_000e3
    # At that distance the two pulls are equal.
    assert mu_m / x**2 == pytest.approx(mu_e / (d - x) ** 2, rel=1e-9)
    assert 60_000e3 < trip.sphere_of_influence_m(d, mu_e, mu_m) < 70_000e3
    t = np.array([0.0, 10.0])
    m = trip.pull_margin(np.array([d - 5e7, d - 3e7]), np.array([5e7, 3e7]), mu_e, mu_m)
    assert trip.first_crossing(t, m) is not None


def test_thin_keeps_ends_and_bounds_the_count() -> None:
    idx = trip.thin(100_000, 2000)
    assert idx[0] == 0 and idx[-1] == 99_999 and len(idx) <= 2000
    assert list(trip.thin(5, 2000)) == [0, 1, 2, 3, 4]
