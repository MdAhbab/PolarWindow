"""Capsule entry (plan track H): the standard atmosphere and the 3-DOF fall."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core import atmosphere, entry

#: The height of the entry interface the plan names (400,000 ft).
EI_HEIGHT_M = 121_920.0


@pytest.mark.parametrize(
    ("z_m", "t_k", "p_pa", "rho"),
    [
        (0.0, 288.15, 101_325.0, 1.2250),
        (11_019.1, 216.65, 22_632.0, 0.36392),
        (32_161.9, 228.65, 868.02, 0.013225),
        (86_000.0, 186.946, 0.37338, 6.958e-6),
    ],
)
def test_the_standard_atmosphere_below_86_km(z_m, t_k, p_pa, rho) -> None:
    t, p, r = atmosphere.lower(z_m)
    assert t == pytest.approx(t_k, abs=0.01)
    assert p == pytest.approx(p_pa, rel=2e-4)
    assert r == pytest.approx(rho, rel=2e-4)


@pytest.mark.parametrize(("z_km", "rho"), [(90.0, 3.416e-6), (100.0, 5.604e-7), (120.0, 2.222e-8)])
def test_the_standard_atmosphere_table_above_86_km(z_km, rho) -> None:
    assert atmosphere.density(z_km * 1000.0) == pytest.approx(rho, rel=1e-6)
    assert atmosphere.density(151_000.0) == 0.0


def test_density_falls_with_height_and_is_continuous_at_86_km() -> None:
    zs = np.arange(0.0, 150_000.0, 500.0)
    rho = np.array([atmosphere.density(float(z)) for z in zs])
    assert np.all(np.diff(rho) < 0)
    assert atmosphere.density(86_001.0) == pytest.approx(atmosphere.density(85_999.0), rel=1e-3)


def test_geodetic_height_on_the_ellipsoid() -> None:
    pole = np.array([0.0, 0.0, 1.0])
    h, lat = entry.geodetic_height(np.array([entry.R_EQ + 1000.0, 0.0, 0.0]), pole)
    assert h == pytest.approx(1000.0, abs=1e-6) and lat == pytest.approx(0.0)
    b = entry.R_EQ * (1 - entry.F_WGS84)
    h, lat = entry.geodetic_height(np.array([0.0, 0.0, b + 500.0]), pole)
    assert h == pytest.approx(500.0, abs=1e-3) and lat == pytest.approx(math.pi / 2)


def _state(speed: float, fpa_deg: float) -> tuple[np.ndarray, np.ndarray]:
    r0 = np.array([entry.R_EQ + EI_HEIGHT_M, 0.0, 0.0])
    g = math.radians(fpa_deg)
    v0 = speed * np.array([math.sin(g), math.cos(g), 0.0])
    return r0, v0


def test_a_blunt_capsule_lands_after_a_deceleration_pulse() -> None:
    pole = np.array([0.0, 0.0, 1.0])
    r0, v0 = _state(12_000.0, -8.2)
    cap = entry.Capsule(beta_kg_m2=63.0)
    fl = entry.fly(r0, v0, pole, cap, ground_m=0.0)
    assert fl.landed and 300 < fl.duration_s < 900
    assert 20 < fl.peak_deceleration_g(pole, cap) < 45
    assert abs(fl.height_m[-1]) < 1.0
    # A heavier capsule for its size lands further down range (the ground longitude, the
    # inertial one less the Earth's turn during the fall).
    far = entry.fly(r0, v0, pole, entry.Capsule(beta_kg_m2=80.0), ground_m=0.0)

    def ground_lon(f: entry.Flight) -> float:
        return math.atan2(f.r_m[-1][1], f.r_m[-1][0]) - entry.OMEGA_EARTH * f.duration_s

    assert ground_lon(far) > ground_lon(fl)


def test_a_wind_below_30_km_carries_the_capsule_with_it() -> None:
    pole = np.array([0.0, 0.0, 1.0])
    r0, v0 = _state(12_000.0, -8.2)
    calm = entry.fly(r0, v0, pole, entry.Capsule(beta_kg_m2=63.0))
    # At the equator with the pole along z, north is +z: a north wind moves it north.
    windy = entry.fly(r0, v0, pole, entry.Capsule(beta_kg_m2=63.0, wind_en_m_s=(0.0, 10.0)))
    drift_m = windy.r_m[-1][2] - calm.r_m[-1][2]
    assert 500.0 < drift_m < 10_000.0


def test_dispersions_rotate_the_velocity_as_asked() -> None:
    r0, v0 = _state(11_000.0, -6.0)
    _, v = entry.disperse(r0, v0, -1.0, 0.0, 0.0)
    assert entry.flight_path_angle_deg(r0, v) == pytest.approx(-7.0, abs=1e-9)
    _, v = entry.disperse(r0, v0, 0.0, 2.0, 0.01)
    assert np.linalg.norm(v) == pytest.approx(11_000.0 * 1.01)
    assert entry.flight_path_angle_deg(r0, v) == pytest.approx(-6.0, abs=1e-9)


def test_the_ellipse_of_scattered_points() -> None:
    rng = np.random.default_rng(1)
    e = rng.normal(2.0, 1.0, 20_000)
    n = rng.normal(-1.0, 3.0, 20_000)
    ell = entry.ellipse_km(e, n, p=0.99)
    k = math.sqrt(-2 * math.log(0.01))
    assert ell["east_km"] == pytest.approx(2.0, abs=0.05)
    assert ell["semi_major_km"] == pytest.approx(3.0 * k, rel=0.03)
    assert ell["semi_minor_km"] == pytest.approx(1.0 * k, rel=0.03)
    assert min(ell["azimuth_deg"], 180 - ell["azimuth_deg"]) < 3.0  # along north


def _thicker(k: float) -> entry.Air:
    """The standard atmosphere, ``k`` times as dense, as a density the caller gives."""
    return lambda _t, _r, h: k * atmosphere.density(h)


def test_a_density_the_caller_gives_replaces_the_standard_atmosphere() -> None:
    pole = np.array([0.0, 0.0, 1.0])
    r0, v0 = _state(12_000.0, -8.2)
    std = entry.fly(r0, v0, pole, entry.Capsule(beta_kg_m2=63.0))
    # The standard atmosphere handed in as a callable is the same flight.
    same = entry.fly(r0, v0, pole, entry.Capsule(beta_kg_m2=63.0, air=_thicker(1.0)))
    assert same.r_m[-1] == pytest.approx(std.r_m[-1], abs=1e-6)
    # Thicker air through the callable is thicker air through the scale, and slows the fall.
    thick = entry.fly(r0, v0, pole, entry.Capsule(beta_kg_m2=63.0, air=_thicker(1.1)))
    scaled = entry.fly(r0, v0, pole, entry.Capsule(beta_kg_m2=63.0, density_scale=1.1))
    assert thick.r_m[-1] == pytest.approx(scaled.r_m[-1], abs=1e-6)
    assert thick.duration_s > std.duration_s


def test_the_air_is_asked_at_seconds_from_entry_and_at_the_height_above_the_ellipsoid() -> None:
    pole = np.array([0.0, 0.0, 1.0])
    r0, v0 = _state(12_000.0, -8.2)
    calls: list[tuple[float, float, float]] = []

    def air(t: float, r: np.ndarray, h: float) -> float:
        calls.append((t, entry.geodetic_height(r, pole)[0], h))
        return atmosphere.density(h)

    fl = entry.fly(r0, v0, pole, entry.Capsule(beta_kg_m2=63.0, air=air))
    assert calls[0][0] == 0.0 and calls[0][2] == pytest.approx(EI_HEIGHT_M, abs=1e-6)
    # Steps of at most 2 s: the last stage of the last step may lie just past the ground.
    assert max(t for t, _, _ in calls) <= fl.duration_s + 2.0
    # The height it gets is the position's, floored at the ground.
    assert all(h == pytest.approx(max(g, 0.0), abs=1e-6) for _, g, h in calls)


def test_the_peak_deceleration_and_the_footprint_use_the_same_air() -> None:
    pole = np.array([0.0, 0.0, 1.0])
    r0, v0 = _state(12_000.0, -8.2)
    cap = entry.Capsule(beta_kg_m2=63.0)
    fl = entry.fly(r0, v0, pole, cap)
    double = entry.Capsule(beta_kg_m2=63.0, air=_thicker(2.0))
    assert fl.peak_deceleration_g(pole, double) == pytest.approx(
        2.0 * fl.peak_deceleration_g(pole, cap)
    )
    tiny = entry.Spread(fpa_deg=0.01, heading_deg=0.001, speed_frac=1e-6, beta_frac=0.0,
                        density_frac=0.0)  # fmt: skip
    plain = entry.footprint(r0, v0, pole, cap, tiny, runs=2)
    thick = entry.footprint(r0, v0, pole, entry.Capsule(63.0, air=_thicker(1.1)), tiny, runs=2)
    assert all(b.duration_s > a.duration_s for a, b in zip(plain, thick, strict=True))
