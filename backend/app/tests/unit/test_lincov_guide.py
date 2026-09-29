"""The errors at leaving Earth that a launch vehicle guide's table of injection accuracy gives
(``lincov.from_guide``), checked against orbit mechanics worked out here another way."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core import lincov

MU = 3.986004354360959e14
R_EARTH = 6_378_136.6
BASE = lincov.Errors(
    (1000.0, 1000.0, 1000.0),
    (0.5, 1.0, 0.5),
    1000.0,
    0.001,
    lincov.Gates(0.01, 0.01, 0.0175, 0.01),
)


def _orbit_state(rp_m: float, ra_m: float) -> np.ndarray:
    """Earth-centred state at the perigee of the orbit with these radii, in the x-y plane."""
    vp = math.sqrt(2.0 * MU * ra_m / (rp_m * (ra_m + rp_m)))
    return np.array([rp_m, 0.0, 0.0, 0.0, vp, 0.0])


def _apogee_after(rp_m: float, v_m_s: float) -> float:
    """Apogee radius of the orbit that leaves ``rp_m`` at ``v_m_s`` along the path (energy)."""
    a = -MU / (2.0 * (0.5 * v_m_s**2 - MU / rp_m))
    return 2.0 * a - rp_m


def test_a_speed_error_moves_the_apogee_by_the_two_body_derivative() -> None:
    rp, ra = R_EARTH + 185e3, R_EARTH + 35_786e3
    vp = math.sqrt(2.0 * MU * ra / (rp * (ra + rp)))
    per_speed = lincov.apogee_per_speed(MU, rp, ra)
    fd = (_apogee_after(rp, vp + 0.01) - _apogee_after(rp, vp - 0.01)) / 0.02
    assert per_speed == pytest.approx(fd, rel=1e-6)
    assert per_speed == pytest.approx(61_069.0, rel=1e-4)  # 61 km of apogee per m/s at GTO


def test_a_falcon_9_row_gives_the_radial_position_and_two_speeds_at_one_sigma() -> None:
    row = lincov.GuideRow(185.0, 35_786.0, 10.0, 500.0, 0.1, 3.0)  # Table 3-2, GTO row
    errors, found = lincov.from_guide(BASE, row, _orbit_state(7.0e6, 4.0e8), MU, R_EARTH)
    rp, ra = R_EARTH + 185e3, R_EARTH + 35_786e3
    vp = math.sqrt(2.0 * MU * ra / (rp * (ra + rp)))
    assert errors.tli_pos_m == pytest.approx((10_000.0 / 3.0, 1000.0, 1000.0))
    assert errors.tli_vel_m_s[0] == 0.5  # nothing in the table for the up-and-down speed
    assert errors.tli_vel_m_s[1] == pytest.approx(
        500_000.0 / 3.0 / lincov.apogee_per_speed(MU, rp, ra)
    )
    assert errors.tli_vel_m_s[1] == pytest.approx(2.729, abs=0.001)
    assert errors.tli_vel_m_s[2] == pytest.approx(vp * math.radians(0.1) / 3.0)
    assert errors.tli_vel_m_s[2] == pytest.approx(5.964, abs=0.001)
    # The rest of the assumed errors are as they were.
    assert (errors.od_pos_m, errors.od_vel_m_s, errors.gates) == (1000.0, 0.001, BASE.gates)
    assert [(d.axis, d.from_element) for d in found] == [
        ("pos_radial", "perigee"),
        ("vel_along", "apogee"),
        ("vel_cross", "inclination"),
    ]
    assert [d.value for d in found] == [
        errors.tli_pos_m[0],
        errors.tli_vel_m_s[1],
        errors.tli_vel_m_s[2],
    ]


def test_the_number_of_standard_deviations_scales_every_error() -> None:
    at3 = lincov.GuideRow(185.0, 35_786.0, 10.0, 500.0, 0.1, 3.0)
    at1 = lincov.GuideRow(185.0, 35_786.0, 10.0, 500.0, 0.1, 1.0)
    y = _orbit_state(7.0e6, 4.0e8)
    e3, _ = lincov.from_guide(BASE, at3, y, MU, R_EARTH)
    e1, _ = lincov.from_guide(BASE, at1, y, MU, R_EARTH)
    assert e1.tli_pos_m[0] == pytest.approx(3.0 * e3.tli_pos_m[0])
    assert e1.tli_vel_m_s[1] == pytest.approx(3.0 * e3.tli_vel_m_s[1])
    assert e1.tli_vel_m_s[2] == pytest.approx(3.0 * e3.tli_vel_m_s[2])


def test_a_row_with_no_reference_orbit_is_worked_out_in_the_orbit_of_the_plan() -> None:
    """Vulcan's lunar transfer row names no orbit: the perigee and apogee of the planned
    departure stand in, so the same apogee tolerance is a smaller speed error where the
    apogee moves farther for each m/s."""
    row = lincov.GuideRow(None, None, 1.9, 4630.0, 0.01, 3.0)
    rp, ra = R_EARTH + 300e3, 3.9e8
    y = _orbit_state(rp, ra)
    errors, found = lincov.from_guide(BASE, row, y, MU, R_EARTH)
    assert lincov.osculating_radii(y, MU) == pytest.approx((rp, ra), rel=1e-9)
    vp = math.sqrt(2.0 * MU * ra / (rp * (ra + rp)))
    assert errors.tli_pos_m[0] == pytest.approx(1900.0 / 3.0)
    assert errors.tli_vel_m_s[1] == pytest.approx(
        4_630_000.0 / 3.0 / lincov.apogee_per_speed(MU, rp, ra)
    )
    assert errors.tli_vel_m_s[2] == pytest.approx(vp * math.radians(0.01) / 3.0)
    assert len(found) == 3
    # At the Moon's distance a metre a second moves the apogee by thousands of kilometres.
    assert lincov.apogee_per_speed(MU, rp, ra) > 4.0e6
    assert errors.tli_vel_m_s[1] < 0.5


def test_only_what_the_row_prints_is_replaced() -> None:
    y = _orbit_state(7.0e6, 4.0e8)
    only_apogee = lincov.GuideRow(None, None, None, 4630.0, None, 3.0)
    errors, found = lincov.from_guide(BASE, only_apogee, y, MU, R_EARTH)
    assert errors.tli_pos_m == BASE.tli_pos_m
    assert errors.tli_vel_m_s[0] == BASE.tli_vel_m_s[0] and errors.tli_vel_m_s[2] == 0.5
    assert errors.tli_vel_m_s[1] != BASE.tli_vel_m_s[1]
    assert [d.axis for d in found] == ["vel_along"]
    nothing = lincov.GuideRow(None, None, None, None, None, 3.0)
    same, none_found = lincov.from_guide(BASE, nothing, y, MU, R_EARTH)
    assert same == BASE and none_found == []


def test_a_departure_that_does_not_close_gives_only_the_radial_position() -> None:
    """No apogee to move on an unbound path: the speed errors are not worked out from the
    table, and the assumed ones stay."""
    escape = np.array([7.0e6, 0.0, 0.0, 0.0, 11.5e3, 0.0])
    rp, ra = lincov.osculating_radii(escape, MU)
    assert math.isinf(ra) and rp == pytest.approx(7.0e6)
    row = lincov.GuideRow(None, None, 1.9, 4630.0, 0.01, 3.0)
    errors, found = lincov.from_guide(BASE, row, escape, MU, R_EARTH)
    assert errors.tli_pos_m[0] == pytest.approx(1900.0 / 3.0)
    assert errors.tli_vel_m_s == BASE.tli_vel_m_s
    assert [d.axis for d in found] == ["pos_radial"]


def test_the_errors_from_a_guide_are_a_covariance_the_budget_can_use() -> None:
    row = lincov.GuideRow(185.0, 35_786.0, 10.0, 500.0, 0.1, 3.0)
    y = _orbit_state(7.0e6, 4.0e8)
    errors, _ = lincov.from_guide(BASE, row, y, MU, R_EARTH)
    p = lincov.tli_covariance(y, errors)
    assert np.all(np.linalg.eigvalsh(p) > 0.0)
    rot = lincov.rtn(y)
    # In its own frame the covariance is the diagonal of the squared errors.
    diag = rot @ p[3:, 3:] @ rot.T
    assert np.diag(diag) == pytest.approx(np.square(errors.tli_vel_m_s))
