"""Array geometry and battery arithmetic (ADR-21), against hand values."""

from __future__ import annotations

import numpy as np
import pytest

from app.core import power

A = np.array


def test_flat_deck_at_30_degrees_gives_half_the_area() -> None:
    a = power.effective_area("top_deck_flat", A([0.0]), A([30.0]), area_m2=2.0)
    assert a[0] == pytest.approx(1.0)


def test_sun_tracking_is_full_area_while_up_and_zero_below() -> None:
    a = power.effective_area("sun_tracking", A([0.0, 0.0]), A([5.0, -1.0]), area_m2=2.0)
    assert list(a) == [2.0, 0.0]


def test_vertical_faces_hand_value() -> None:
    # Four faces, Sun due north at el 0: one face square-on, two edge-on, one away.
    a = power.effective_area(
        "vertical_faces", A([0.0]), A([0.0]), area_m2=1.0, face_count=4, face_offset_deg=0.0
    )
    assert a[0] == pytest.approx(1.0)
    # Sun at 45 deg azimuth lights two faces at cos 45 each.
    b = power.effective_area(
        "vertical_faces", A([45.0]), A([0.0]), area_m2=1.0, face_count=4, face_offset_deg=0.0
    )
    assert b[0] == pytest.approx(2 * np.cos(np.radians(45.0)))
    # Overhead Sun: vertical faces see nothing.
    c = power.effective_area(
        "vertical_faces", A([0.0]), A([90.0]), area_m2=1.0, face_count=4, face_offset_deg=0.0
    )
    assert c[0] == pytest.approx(0.0, abs=1e-12)


def test_irradiance_is_inverse_square_in_distance() -> None:
    s = power.irradiance(A([power.AU_M, 2 * power.AU_M]), 2)
    assert s[0] == pytest.approx(1361.0)
    assert s[1] == pytest.approx(1361.0 / 4)
    assert list(power.irradiance(None, 3)) == [1361.0] * 3


def test_generated_power_formula() -> None:
    p = power.generated_power(A([2.0]), A([1361.0]), A([1.0]), efficiency=0.3, dust_loss=0.1)
    assert p[0] == pytest.approx(0.3 * 2.0 * 1361.0 * 0.9)


def test_lit_share_is_exact_for_an_edge_inside_a_step() -> None:
    share = power.lit_share(A([0.0, 100.0, 200.0]), [(50.0, 150.0)])
    assert list(share) == [0.5, 0.5]


def test_soc_conserves_energy_and_clamps() -> None:
    # 100 W net for 1 h into a 1000 Wh battery from 500 Wh: +100 Wh, exactly.
    soc = power.integrate_soc(A([100.0] * 6), 600.0, 1000.0, 500.0)
    assert soc[-1] == pytest.approx(600.0)
    # Overcharge clamps at capacity; deep discharge clamps at 0.
    assert power.integrate_soc(A([1e6]), 3600.0, 1000.0, 500.0)[-1] == 1000.0
    assert power.integrate_soc(A([-1e6]), 3600.0, 1000.0, 500.0)[-1] == 0.0


def test_first_empty_time_interpolates() -> None:
    t = A([0.0, 100.0, 200.0])
    assert power.first_empty_time(t, A([10.0, 5.0, 0.0])) == pytest.approx(200.0)
    assert power.first_empty_time(t, A([10.0, 5.0, 0.0, 0.0])[:3]) == pytest.approx(200.0)
    assert power.first_empty_time(t, A([10.0, 9.0, 8.0])) is None
