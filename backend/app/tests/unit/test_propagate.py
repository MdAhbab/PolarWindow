"""The propagator against closed forms, itself run backwards, and the other origin.

Synthetic body tables (a Moon on a circular Kepler orbit, a distant Sun,
unrotated frames), so no kernels are needed. The real-ephemeris checks against
NASA's reconstructions live in tests/golden/test_propagate_vs_clps.py.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from app.core import forces, gravity, propagate

GM_E = 3.986004354360959e14
GM_M = 4.902800118457551e12
GM_S = 1.32712440041279419e20
A_MOON = 3.844e8
DAY = 86400.0


def _frame_z(theta: float) -> np.ndarray:
    """The matrix that takes coordinates to those of a frame turned by ``theta`` about z."""
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])


def _spin(t: np.ndarray, extra: float = 0.0) -> np.ndarray:
    """(n, 3, 3) J2000 -> body-fixed for an Earth turning about its axis at OMEGA_EARTH."""
    return np.array([_frame_z(forces.OMEGA_EARTH * float(x) + extra) for x in t])


def _tables(t0: float = 0.0, days: float = 6.0, dt: float = 300.0) -> forces.Tables:
    n = int(days * DAY / dt) + 1
    t = t0 + dt * np.arange(n)
    w = math.sqrt((GM_E + GM_M) / A_MOON**3)
    moon = np.column_stack(
        [
            A_MOON * np.cos(w * t),
            A_MOON * np.sin(w * t),
            np.zeros(n),
            -A_MOON * w * np.sin(w * t),
            A_MOON * w * np.cos(w * t),
            np.zeros(n),
        ]
    )
    ws = 2 * math.pi / (365.25 * DAY)
    sun = np.column_stack(
        [
            forces.AU_M * np.cos(ws * t),
            forces.AU_M * np.sin(ws * t),
            np.zeros(n),
            -forces.AU_M * ws * np.sin(ws * t),
            forces.AU_M * ws * np.cos(ws * t),
            np.zeros(n),
        ]
    )
    eye = np.broadcast_to(np.eye(3), (n, 3, 3)).copy()
    return forces.Tables(
        t0, dt, moon, sun, eye, _spin(t), GM_E, GM_M, GM_S, 6_378_136.6, 1_737_400.0, 6.957e8
    )


def _kepler(mu: float, r0: np.ndarray, v0: np.ndarray, dt: float) -> np.ndarray:
    """Two-body position after dt by Kepler's equation (elliptic)."""
    r = np.linalg.norm(r0)
    a = 1.0 / (2.0 / r - v0 @ v0 / mu)
    n = math.sqrt(mu / a**3)
    h = np.cross(r0, v0)
    e_vec = np.cross(v0, h) / mu - r0 / r
    e = np.linalg.norm(e_vec)
    p_hat = e_vec / e
    q_hat = np.cross(h / np.linalg.norm(h), p_hat)
    nu0 = math.atan2(r0 @ q_hat, r0 @ p_hat)
    ea0 = 2 * math.atan(math.sqrt((1 - e) / (1 + e)) * math.tan(nu0 / 2))
    m = ea0 - e * math.sin(ea0) + n * dt
    ea = m
    for _ in range(50):
        ea -= (ea - e * math.sin(ea) - m) / (1 - e * math.cos(ea))
    x = a * (math.cos(ea) - e)
    y = a * math.sqrt(1 - e * e) * math.sin(ea)
    return np.asarray(x * p_hat + y * q_hat)


def _random_moon_field(n: int = 8) -> gravity.Field:
    rng = np.random.default_rng(3)
    c = np.zeros((n + 1, n + 1))
    s = np.zeros((n + 1, n + 1))
    c[0, 0] = 1.0
    for i in range(2, n + 1):
        for j in range(i + 1):
            c[i, j] = rng.normal(0, 2e-5)
            s[i, j] = 0.0 if j == 0 else rng.normal(0, 2e-5)
    return gravity.Field(GM_M, 1_738_000.0, c, s, n)


def test_hermite_tables_reproduce_the_moon_between_knots() -> None:
    tab = _tables()
    t = np.array([150.0, 1e5 + 77.0, 3e5 + 211.0])
    got = forces.body_state(tab, forces.MOON, t)
    w = math.sqrt((GM_E + GM_M) / A_MOON**3)
    want = np.column_stack([A_MOON * np.cos(w * t), A_MOON * np.sin(w * t), np.zeros(3)])
    assert np.max(np.abs(got[:, :3] - want)) < 1e-5


def test_point_mass_matches_keplers_equation_to_a_millimetre() -> None:
    tab = _tables()
    model = forces.Model(earth_field=forces.earth_zonal(0), moon=False, sun=False)
    r0 = np.array([7.0e6, 0.0, 0.0])
    v0 = np.array([0.0, 7.9e3, 1.2e3])  # e ~ 0.1
    y0 = np.concatenate([r0, v0])
    dt = 5 * 2 * math.pi * math.sqrt(7.8e6**3 / GM_E)
    tr = propagate.propagate(tab, model, 0.0, y0, dt)
    want = _kepler(GM_E, r0, v0, dt)
    assert np.linalg.norm(tr.state[-1, :3] - want) < 1e-3


def test_j2_turns_the_node_at_the_textbook_rate() -> None:
    tab = _tables(days=3.5)
    model = forces.Model(earth_field=forces.earth_zonal(2), moon=False, sun=False)
    a, inc = 7.0e6, math.radians(50.0)
    v = math.sqrt(GM_E / a)
    y0 = np.array([a, 0, 0, 0, v * math.cos(inc), v * math.sin(inc)])
    period = 2 * math.pi * math.sqrt(a**3 / GM_E)
    t_end = 3 * DAY
    tr = propagate.propagate(tab, model, 0.0, y0, t_end)

    def mean_node(t0: float) -> float:
        ts = np.linspace(t0, t0 + period, 200, endpoint=False)
        st = tr.at(ts)
        h = np.cross(st[:, :3], st[:, 3:])
        return float(np.mean(np.unwrap(np.arctan2(h[:, 0], -h[:, 1]))))

    rate = (mean_node(t_end - period) - mean_node(0.0)) / (t_end - period)
    j2 = -forces.EGM2008_CN0[2] * math.sqrt(5)
    n = math.sqrt(GM_E / a**3)
    want = -1.5 * n * j2 * (forces.EGM2008_R_M / a) ** 2 * math.cos(inc)
    assert rate == pytest.approx(want, rel=0.02)


def test_forward_then_back_returns_within_a_metre_in_lunar_orbit() -> None:
    tab = _tables()
    model = forces.Model(origin=forces.MOON, moon_field=_random_moon_field(), cr_am=0.02)
    r = 1_838_000.0
    v = math.sqrt(GM_M / r)
    y0 = np.array([r, 0.0, 0.0, 0.0, 0.0, v])  # 100 km polar orbit
    t0 = 1000.0
    fwd = propagate.propagate(tab, model, t0, y0, t0 + DAY)
    back = propagate.propagate(tab, model, t0 + DAY, fwd.state[-1], t0)
    assert np.linalg.norm(back.state[-1, :3] - y0[:3]) < 1.0


def test_earth_and_moon_origins_give_the_same_trip() -> None:
    tab = _tables()
    m_e = forces.Model(origin=forces.EARTH, earth_field=forces.earth_zonal(0), sun=False)
    m_m = forces.Model(origin=forces.MOON, earth_field=forces.earth_zonal(0), sun=False)
    y0_e = np.array([3.0e8, 1.0e8, 0.0, -600.0, 400.0, 50.0])
    t0, t1 = 500.0, 500.0 + 2 * DAY
    a = propagate.propagate(tab, m_e, t0, y0_e, t1)
    y0_m = y0_e - forces.body_state(tab, forces.MOON, np.array([t0]))[0]
    b = propagate.propagate(tab, m_m, t0, y0_m, t1)
    b_e = b.state[-1] + forces.body_state(tab, forces.MOON, np.array([t1]))[0]
    assert np.linalg.norm(a.state[-1, :3] - b_e[:3]) < 1.0


def test_sunlight_pushes_and_the_earths_shadow_stops_it() -> None:
    tab = _tables()
    off = forces.derivatives(tab, forces.Model(sun=False, moon=False))
    on = forces.derivatives(tab, forces.Model(sun=False, moon=False, cr_am=0.02))
    t = 5 * DAY  # the Moon well away from the Sun's direction
    k = int(t / tab.dt)
    sun_dir = tab.sun[k, :3] / np.linalg.norm(tab.sun[k, :3])
    lit = np.concatenate([7e6 * sun_dir, [0, 0, 0]])
    dark = np.concatenate([-7e6 * sun_dir, [0, 0, 0]])
    push = on(t, lit)[3:] - off(t, lit)[3:]
    d = np.linalg.norm(tab.sun[k, :3] - lit[:3])
    want = forces.TSI_W_M2 / forces.C_M_S * 0.02 * (forces.AU_M / d) ** 2
    assert np.linalg.norm(push) == pytest.approx(want, rel=1e-9)
    assert push @ sun_dir < 0  # away from the Sun
    assert np.linalg.norm(on(t, dark)[3:] - off(t, dark)[3:]) == 0.0


def test_drag_opposes_motion_through_the_turning_air() -> None:
    drag = forces.Drag(cd_am=0.01, f107=150, f107a=150, ap=15, density=lambda *_: 3e-12)
    r = np.array([6_778_137.0, 0.0, 0.0])
    v = np.array([0.0, 7_670.0, 0.0])
    a = forces.drag_acceleration(0.0, r, v, np.eye(3), drag)
    v_rel = v - np.cross([0, 0, forces.OMEGA_EARTH], r)
    assert np.allclose(a, -0.5 * 0.01 * 3e-12 * np.linalg.norm(v_rel) * v_rel, rtol=1e-12)
    high = forces.drag_acceleration(0.0, 2.0 * r, v, np.eye(3), drag)
    assert not high.any()


def test_msis_density_at_400_km_is_of_the_published_order() -> None:
    drag = forces.Drag(cd_am=0.01, f107=150, f107a=150, ap=15)
    rho = forces.msis_density(8e8, 10.0, 20.0, 400e3, drag)
    assert 1e-12 < rho < 1e-11


def test_geodetic_height_on_the_ellipsoid() -> None:
    lat, lon, h = forces.geodetic(np.array([6_378_137.0, 0.0, 0.0]))
    assert abs(lat) < 1e-12 and abs(lon) < 1e-12 and abs(h) < 1e-6
    lat, _, h = forces.geodetic(np.array([0.0, 0.0, 6_356_752.314245 + 100.0]))
    assert lat == pytest.approx(90.0) and h == pytest.approx(100.0, abs=1e-6)


def test_residual_acceleration_finds_an_unmodelled_push() -> None:
    tab = _tables()
    model = forces.Model(origin=forces.MOON, earth_field=forces.earth_zonal(0), sun=False)
    base = forces.derivatives(tab, model)
    push = np.array([0.0, 2e-6, 0.0])

    def pushed(t: float, y: np.ndarray) -> np.ndarray:
        out = base(t, y)
        out[3:] += push
        return out

    from scipy.integrate import solve_ivp

    y0 = np.array([1.0e7, 0, 0, 0, math.sqrt(GM_M / 1.0e7), 0])
    sol = solve_ivp(
        pushed,
        (100.0, 100.0 + 6 * 3600),
        y0,
        method="DOP853",
        rtol=1e-12,
        atol=1e-9,
        dense_output=True,
    )
    ets = np.linspace(200.0, 100.0 + 5 * 3600, 20)
    res = propagate.residual_acceleration(
        tab, model, ets, sol.sol(ets).T, state_at=lambda t: sol.sol(t).T
    )
    assert np.allclose(res, 2e-6, rtol=1e-3)
    # The vectors say which way it pushes (observed - modelled, so along +y); the size is
    # their length.
    vec = propagate.residual_acceleration_vectors(
        tab, model, ets, sol.sol(ets).T, state_at=lambda t: sol.sol(t).T
    )
    assert np.allclose(vec, push, rtol=1e-3)
    assert np.allclose(np.linalg.norm(vec, axis=1), res, rtol=1e-12)


def test_earths_default_field_is_egm2008_to_degree_eight() -> None:
    assert forces.EGM2008_DEGREE == 8
    default = forces.Model().earth()
    assert default.degree == 8 and np.array_equal(default.s, forces.earth_egm(8).s)
    assert forces.earth_egm(20).degree == 8  # nothing is tabulated past it
    assert forces.earth_egm(1).degree == 0  # below degree 2, a point mass
    f4 = forces.earth_egm(4)
    assert f4.degree == 4 and f4.c.shape == (5, 5)
    assert (f4.c[4, 3], f4.s[4, 3]) == forces.EGM2008_CS[(4, 3)]
    assert not f4.c[1].any() and not f4.s[:, 0].any()  # no degree 1, no S_n0
    # The zonal column is J2..J6 as before, which is what the nodal-drift test above uses.
    assert [forces.earth_egm(6).c[n, 0] for n in range(2, 7)] == list(forces.EGM2008_CN0.values())


def test_earths_pull_turns_with_the_earth() -> None:
    """Zonal terms cannot tell which way the Earth has turned; the tesseral ones can. With
    the Earth turned by alpha and the spacecraft carried round with it, the pull is the
    still Earth's, turned by alpha."""
    tab = _tables(days=1.0)
    a = math.radians(37.0)
    rz = _frame_z(a)
    knots = tab.t0 + tab.dt * np.arange(tab.itrf.shape[0])
    turned = dataclasses.replace(tab, itrf=_spin(knots, extra=a))
    x_bf = np.array([2.2e7, 1.0e7, 8.0e6])  # 24,700 km out, well off every axis
    at_rest = np.zeros(3)
    egm = forces.Model(moon=False, sun=False)
    zonal = forces.Model(moon=False, sun=False, earth_field=forces.earth_zonal(6))
    still = forces.derivatives(tab, egm)(1000.0, np.concatenate([x_bf, at_rest]))[3:]
    moved = forces.derivatives(turned, egm)(1000.0, np.concatenate([rz.T @ x_bf, at_rest]))[3:]
    assert np.allclose(moved, rz.T @ still, rtol=1e-12, atol=0.0)
    flat = forces.derivatives(tab, zonal)(1000.0, np.concatenate([x_bf, at_rest]))[3:]
    assert np.linalg.norm(still - flat) > 1e-7  # the tesseral part is really there


GEO_R_M = 42_164_170.0


def _geo_east_pull(field: gravity.Field, step_deg: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """East-west acceleration (m/s^2) of the field's non-central part on the equator at
    geostationary radius, every ``step_deg`` of body-fixed longitude."""
    lons = np.arange(0.0, 360.0, step_deg)
    east = np.empty(lons.size)
    for k, lon in enumerate(np.radians(lons)):
        pos = GEO_R_M * np.array([math.cos(lon), math.sin(lon), 0.0])
        pull = gravity.acceleration(field, pos, include_central=False)
        east[k] = pull @ np.array([-math.sin(lon), math.cos(lon), 0.0])
    return lons, east


def _zeros(lons: np.ndarray, east: np.ndarray, *, rising: bool) -> list[float]:
    """Longitudes (deg) where ``east`` crosses zero rising or falling, by linear interpolation."""
    step = float(lons[1] - lons[0])
    out = []
    for k in range(lons.size):
        a, b = float(east[k]), float(east[(k + 1) % lons.size])
        if (a < 0.0 <= b) if rising else (a > 0.0 >= b):
            out.append((float(lons[k]) + a / (a - b) * step) % 360.0)
    return sorted(out)


def test_the_equatorial_bulge_sets_the_geostationary_drift_points() -> None:
    """Earth's equatorial ellipticity (C22, S22) pushes a geostationary satellite east or
    west by up to 5.6e-8 m/s^2. Along-track push moves the orbit's height, so the drift
    goes the other way (d2 lambda/dt2 = -3 a_east / a): the longitudes a satellite settles
    at are where the pull rises through zero, 90 degrees from the ones it is pulled to.
    Closed form for C22 and S22 alone; the whole field to degree 8 against the published
    drift points, about 75.3 E and 104.7 W (Soop, *Handbook of Geostationary Orbits*, 1994)
    and 0.0017 deg/day^2 for the ellipticity alone."""
    c22, s22 = forces.EGM2008_CS[(2, 2)]
    norm = math.sqrt(10.0 / 24.0)  # fully normalised -> conventional, n = m = 2
    amp = 6.0 * forces.EGM2008_GM * forces.EGM2008_R_M**2 / GEO_R_M**4
    amp *= norm * math.hypot(c22, s22)
    lam22 = 0.5 * math.degrees(math.atan2(s22, c22))  # the long axis of the equator: 14.9 W

    lons, east = _geo_east_pull(forces.earth_egm(2))
    # (a degree-2 field also has C21 and S21, 1e-9: they do not reach the equator's east pull)
    assert np.max(np.abs(east)) == pytest.approx(amp, rel=1e-3)
    settle = _zeros(lons, east, rising=True)
    assert settle == pytest.approx([(lam22 + 90.0) % 360.0, (lam22 + 270.0) % 360.0], abs=0.02)
    assert _zeros(lons, east, rising=False) == pytest.approx(
        [(lam22 + 180.0) % 360.0, (lam22 + 360.0) % 360.0], abs=0.02
    )
    drift = 3.0 * amp / GEO_R_M * math.degrees(1.0) * 86400.0**2
    assert drift == pytest.approx(0.0017, rel=0.03)

    lons, east = _geo_east_pull(forces.earth_egm(8))
    settle = _zeros(lons, east, rising=True)
    assert len(settle) == 2 and len(_zeros(lons, east, rising=False)) == 2
    assert settle[0] == pytest.approx(75.3, abs=1.0)
    assert settle[1] == pytest.approx(360.0 - 104.7, abs=1.0)
