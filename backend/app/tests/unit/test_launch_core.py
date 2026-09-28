"""Launch instants, direct transfers and landing windows: the pure pieces (T2 C2, D1, D2)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core import intervals, landing_windows, launchwin, transfer
from app.core.intervals import Run
from app.core.vec import east_north, rotate, unit

GM_EARTH = 3.986004418e14
GM_MOON = 4.9028e12


def test_pad_itrf_matches_wgs84_radius_and_latitude() -> None:
    p = launchwin.pad_itrf(28.608, -80.604)
    r = float(np.linalg.norm(p))
    assert 6_372_000 < r < 6_374_000  # WGS84 radius at 28.6 degrees
    geocentric = math.degrees(math.asin(p[2] / r))
    e2 = launchwin.WGS84_F * (2 - launchwin.WGS84_F)
    expected = math.degrees(math.atan((1 - e2) * math.tan(math.radians(28.608))))
    assert geocentric == pytest.approx(expected, abs=1e-9)


def test_angle_along_and_wrap() -> None:
    p = np.array([1.0, 0.0, 0.0])
    h = np.array([0.0, 0.0, 1.0])
    r = rotate(p, h, math.radians(250.0))
    assert math.degrees(launchwin.angle_along(p, r, h)) == pytest.approx(250.0)
    assert launchwin.wrap(math.radians(190.0)) == pytest.approx(math.radians(-170.0))
    assert launchwin.wrap(math.pi) == pytest.approx(-math.pi) or launchwin.wrap(
        math.pi
    ) == pytest.approx(math.pi)


def test_roots_skip_the_wrap_of_a_wrapped_residual() -> None:
    # A sawtooth wrapped into (-pi, pi]: crosses zero at 50 and 150, wraps at 100 and 200.
    def f(t: float) -> float:
        return launchwin.wrap(2.0 * math.pi * (t - 50.0) / 100.0)

    found = launchwin.roots(f, 0.0, 230.0, step_s=7.0)
    assert found == pytest.approx([50.0, 150.0], abs=1e-3)


def test_a_due_east_climb_gives_an_orbit_inclined_at_the_pad_latitude() -> None:
    lat = math.radians(28.6)
    p = np.array([math.cos(lat), 0.0, math.sin(lat)])
    h = launchwin.climb_plane(p, 90.0)
    assert math.degrees(math.acos(h[2])) == pytest.approx(28.6, abs=1e-9)
    # Steering off due east only raises the inclination.
    for az in (70.0, 110.0):
        assert math.degrees(math.acos(launchwin.climb_plane(p, az)[2])) > 28.6
    # A direction in that plane has no northward part at the pad: the due-east gap is zero.
    ahead = rotate(p, h, 1.0)
    assert launchwin.due_east_gap(p, ahead) == pytest.approx(0.0, abs=1e-12)
    east, north = east_north(p)
    assert float(east @ north) == pytest.approx(0.0) and north[2] > 0


def test_azimuth_of_a_due_east_plane() -> None:
    lat = math.radians(28.6)
    up = np.array([math.cos(lat), 0.0, math.sin(lat)])
    h = launchwin.climb_plane(up, 90.0)
    az_i, az_r = launchwin.azimuth_deg(up, h, 7800.0, 6_373_000.0)
    assert az_i == pytest.approx(90.0, abs=1e-9)
    assert az_r == pytest.approx(90.0, abs=1e-6)  # Earth's spin is along east too


def test_climb_azimuth_inverts_the_climb_plane_and_the_inclination_formula() -> None:
    lat = 28.6
    p = np.array([math.cos(math.radians(lat)), 0.0, math.sin(math.radians(lat))])
    for az in (60.0, 87.5, 90.0, 110.0):
        h = launchwin.climb_plane(p, az)
        assert launchwin.climb_azimuth(p, h) == pytest.approx(az, abs=1e-9)
        inc = math.degrees(math.acos(h[2]))
        assert launchwin.inclination_for_azimuth(lat, az) == pytest.approx(inc, abs=1e-9)
        pair = launchwin.azimuth_for_inclination(lat, inc)
        assert pair is not None and min(abs(pair[0] - az), abs(pair[1] - az)) < 1e-6
        # A climb at this azimuth holds the direction it moves in at the pad.
        ahead = rotate(p, h, 0.3)
        assert launchwin.climb_gap(p, ahead, az) == pytest.approx(0.0, abs=1e-12)
    assert launchwin.azimuth_for_inclination(lat, 20.0) is None  # below the latitude


def test_ground_azimuth_turns_away_from_east() -> None:
    # Due east is due east over the ground too; off east the ground's speed turns it further.
    assert launchwin.ground_azimuth(28.6, 90.0, 7800.0) == pytest.approx(90.0, abs=1e-9)
    assert launchwin.ground_azimuth(28.6, 110.0, 7800.0) > 110.0
    assert launchwin.ground_azimuth(28.6, 70.0, 7800.0) < 70.0
    lat = math.radians(28.6)
    up = np.array([math.cos(lat), 0.0, math.sin(lat)])
    h = launchwin.climb_plane(up, 110.0)
    _, az_r = launchwin.azimuth_deg(up, h, 7800.0, launchwin.WGS84_A)
    assert launchwin.ground_azimuth(28.6, 110.0, 7800.0) == pytest.approx(az_r, abs=1e-6)


def test_patched_conic_limits() -> None:
    r_park, r_moon = 6_578_000.0, 384_400_000.0
    a_h = 0.5 * (r_park + r_moon)
    t_hohmann = math.pi * math.sqrt(a_h**3 / GM_EARTH)
    nu, v_p = transfer.patched_conic(r_park, r_moon, t_hohmann * 1.2, GM_EARTH)
    # Slower than a Hohmann transfer: aimed at apogee, 180 degrees, Hohmann speed.
    assert math.degrees(nu) == pytest.approx(180.0, abs=0.05)
    assert v_p == pytest.approx(math.sqrt(GM_EARTH * (2 / r_park - 1 / a_h)), rel=1e-5)
    nu3, v3 = transfer.patched_conic(r_park, r_moon, 3.0 * 86_400.0, GM_EARTH)
    assert math.degrees(nu3) < 180.0 and v3 > v_p  # faster means more speed, less angle


def test_parking_orbit_is_circular_and_times_a_direction() -> None:
    park = transfer.Parking(
        100.0, np.array([6_578_000.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]), GM_EARTH
    )
    y = park.state(100.0 + park.period / 4)
    assert y[:3] == pytest.approx([0.0, 6_578_000.0, 0.0], abs=1e-3)
    assert float(np.linalg.norm(y[3:])) == pytest.approx(math.sqrt(GM_EARTH / 6_578_000.0))
    t = park.time_at(np.array([-1.0, 0.0, 0.3]), after=100.0)
    assert t == pytest.approx(100.0 + park.period / 2)


def test_bplane_of_a_hyperbola_gives_its_closest_approach() -> None:
    rp, v_inf = 1_837_400.0, 800.0
    v_p = math.sqrt(v_inf**2 + 2 * GM_MOON / rp)
    # At periapsis, over the Moon's pole (a polar pass): r along x, v along z.
    bp = transfer.bplane(
        np.array([rp, 0.0, 0.0]), np.array([0.0, 0.0, v_p]), GM_MOON, np.array([0.0, 0.0, 1.0])
    )
    assert float(bp["rp"]) == pytest.approx(rp, rel=1e-9)
    assert float(bp["v_inf"]) == pytest.approx(v_inf, rel=1e-9)
    assert float(bp["inc_deg"]) == pytest.approx(90.0, abs=1e-9)
    b = math.hypot(float(bp["bt"]), float(bp["br"]))
    assert b == pytest.approx(rp * math.sqrt(1 + 2 * GM_MOON / (rp * v_inf**2)), rel=1e-9)
    target = transfer.Target(0.0, rp, 90.0)
    bt, br = transfer.b_target(bp, np.array([0.0, 0.0, 1.0]), target, GM_MOON)
    assert bt == pytest.approx(float(bp["bt"]), abs=1.0)
    assert br == pytest.approx(float(bp["br"]), abs=1.0)
    with pytest.raises(ValueError):
        transfer.bplane(
            np.array([rp, 0, 0]), np.array([0, 0, 100.0]), GM_MOON, np.array([0, 0, 1.0])
        )


def test_tli_adds_speed_along_the_orbit() -> None:
    park = transfer.Parking(
        0.0, np.array([6_578_000.0, 0.0, 0.0]), unit(np.array([0, 0, 1.0])), GM_EARTH
    )
    y = transfer.tli_state(park, 0.0, 3100.0)
    v_c = math.sqrt(GM_EARTH / 6_578_000.0)
    assert y[3:] == pytest.approx([0.0, v_c + 3100.0, 0.0])


# --- landing windows ---------------------------------------------------------

DAY = 86_400.0


def _track() -> tuple[np.ndarray, np.ndarray, list[Run]]:
    """A 30-day lunar day: the Sun up (elevation > 0) for the first 15 days, peaking at 8."""
    t = np.arange(0.0, 30 * DAY + 1, 1800.0)
    el = 8.0 * np.sin(2 * math.pi * t / (30 * DAY))
    return t, el, intervals.runs_from_margin(t, el)


def test_windows_need_the_sun_up_rising_and_in_band() -> None:
    t, el, sun_up = _track()
    earth = [Run(True, 0.0, float(t[-1]))]
    rule = landing_windows.Rule(sun_min_deg=2.0, sun_max_deg=6.0, surface_days=None)
    w = [r for r in landing_windows.windows(t, el, el, sun_up, earth, rule) if r.value]
    assert len(w) == 1  # only on the way up
    lo = 30 * DAY / (2 * math.pi) * math.asin(2 / 8)
    hi = 30 * DAY / (2 * math.pi) * math.asin(6 / 8)
    assert w[0].start == pytest.approx(lo, abs=900) and w[0].end == pytest.approx(hi, abs=900)
    # Earth down for the first part of it cuts the window.
    earth = [Run(False, 0.0, 2 * DAY), Run(True, 2 * DAY, float(t[-1]))]
    w2 = [r for r in landing_windows.windows(t, el, el, sun_up, earth, rule) if r.value]
    assert w2[0].start == pytest.approx(2 * DAY)


def test_surface_days_move_the_window_end() -> None:
    t, el, sun_up = _track()
    earth = [Run(True, 0.0, float(t[-1]))]
    rule = landing_windows.Rule(sun_min_deg=None, sun_max_deg=None, surface_days=12.0)
    w = [r for r in landing_windows.windows(t, el, el, sun_up, earth, rule) if r.value]
    # Rising lasts 7.5 days, sunset is at 15 days: landing no later than day 3.
    assert w[0].end == pytest.approx(3 * DAY, abs=1800)
    left, cut = landing_windows.sunlight_after(DAY, sun_up, float(t[-1]))
    assert left == pytest.approx(14 * DAY, abs=1800) and cut is False
    assert landing_windows.inside(w, DAY) and not landing_windows.inside(w, 4 * DAY)


def test_a_short_allowed_stretch_is_dropped() -> None:
    t = np.arange(0.0, DAY, 600.0)
    el = np.full(t.size, -1.0)
    el[(t > 10_000) & (t < 11_000)] = 1.0  # a glint through a notch, under an hour
    runs = intervals.runs_from_margin(t, el)
    rule = landing_windows.Rule(None, None, None, rising=False)
    w = landing_windows.windows(t, el, el, runs, [Run(True, 0.0, float(t[-1]))], rule)
    assert not any(r.value for r in w)
