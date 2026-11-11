"""The lumped bus node and its coupling to the battery (ADR-21)."""

from __future__ import annotations

import numpy as np
import pytest

from app.core import thermal

BUS = thermal.BusParams(
    absorptivity=0.3,
    side_area_m2=2.0,
    top_area_m2=0.0,
    bus_emissivity=0.8,
    regolith_emissivity=0.95,
    view_factor=0.5,
    base_area_m2=2.0,
    radiator_emissivity=0.85,
    radiator_area_m2=0.5,
    heat_capacity_j_per_k=2.0e5,
)


def drive(n: int, h: float, p_gen: float, q_sol: float, t_surf: float) -> thermal.Drive:
    m = 2 * n + 1
    return thermal.Drive(h, np.full(m, p_gen), np.full(m, q_sol), np.full(m, t_surf))


def power(
    heater_w: float = 0.0, setpoint_c: float = -1000.0, cap: float = 100.0
) -> thermal.PowerParams:
    return thermal.PowerParams(cap, 20.0, 10.0, 1.0, heater_w, setpoint_c + thermal.ZERO_C_K)


def test_integrator_reaches_the_analytic_steady_state() -> None:
    n, h = 20000, 300.0  # about 70 days
    pw = power(cap=1e9)
    # Loads of 30 W are carried by a huge battery; they dissipate fully.
    res = thermal.integrate_coupled(BUS, pw, drive(n, h, 0.0, 40.0, 150.0), 300.0, 5e8)
    want = thermal.steady_state_temperature(BUS, q_in_w=40.0, t_surf_k=150.0, dissipated_w=30.0)
    assert res.t_bus_k[-1] == pytest.approx(want, rel=1e-6)


def test_pure_radiation_cooling_matches_the_closed_form() -> None:
    bus = thermal.BusParams(0.0, 0.0, 0.0, 0.8, 0.95, 0.0, 0.0, 0.85, 0.5, 2.0e5, t_space_k=0.0)
    pw = thermal.PowerParams(100.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    n, h, t0 = 2000, 60.0, 300.0
    res = thermal.integrate_coupled(bus, pw, drive(n, h, 0.0, 0.0, 0.0), t0, 50.0)
    k = thermal.SIGMA * 0.85 * 0.5
    t = n * h
    closed = (1.0 / t0**3 + 3.0 * k * t / bus.heat_capacity_j_per_k) ** (-1.0 / 3.0)
    assert res.t_bus_k[-1] == pytest.approx(closed, rel=1e-6)


def test_heater_draws_from_the_battery_and_warms_the_bus() -> None:
    n, h = 600, 60.0
    big = 1e6  # a battery that does not run out in ten hours
    cold = thermal.integrate_coupled(
        BUS, power(0.0, cap=big), drive(n, h, 0.0, 0.0, 3.0), 250.0, big
    )
    heated = thermal.integrate_coupled(
        BUS, power(80.0, setpoint_c=0.0, cap=big), drive(n, h, 0.0, 0.0, 3.0), 250.0, big
    )
    assert heated.t_bus_k[-1] > cold.t_bus_k[-1]
    assert heated.soc_wh[-1] < cold.soc_wh[-1]
    # Energy conservation: what left the battery is the loads plus the heater.
    spent = cold.soc_wh[0] - heated.soc_wh[-1]
    assert spent == pytest.approx(
        (30.0 * n * h + float(heated.heater_w[1:].sum()) * h) / 3600.0, rel=1e-6
    )


def test_empty_battery_dissipates_nothing_and_the_heater_stops() -> None:
    n, h = 600, 60.0
    res = thermal.integrate_coupled(
        BUS, power(80.0, setpoint_c=100.0, cap=1.0), drive(n, h, 0.0, 0.0, 3.0), 250.0, 1.0
    )
    assert res.soc_wh[-1] == 0.0
    assert res.heater_w[-1] == 0.0
    assert res.t_bus_k[-1] < res.t_bus_k[0]
    assert res.unserved_wh > 0.0


def test_empty_battery_spends_only_what_the_arrays_generate() -> None:
    res = thermal.integrate_coupled(
        BUS, power(80.0, setpoint_c=100.0, cap=1.0), drive(50, 60.0, 45.0, 0.0, 3.0), 250.0, 0.0
    )
    # 45 W generated: 30 W to the loads first, 15 W left for the heater.
    assert res.heater_w[-1] == pytest.approx(15.0)


def test_ground_temperature_equilibrium_and_cap() -> None:
    el, s, lit = np.array([30.0, 30.0, 30.0]), np.full(3, 1361.0), np.array([1.0, 1.0, 0.0])
    t = thermal.ground_temperature(
        el, s, lit, regolith_absorptivity=0.88, regolith_emissivity=0.95, cap_k=1e9, dark_k=50.0
    )
    want = (0.88 * 1361.0 * 0.5 / (0.95 * thermal.SIGMA)) ** 0.25
    assert t[0] == pytest.approx(want)
    assert t[2] == 50.0
    capped = thermal.ground_temperature(
        el, s, lit, regolith_absorptivity=0.88, regolith_emissivity=0.95, cap_k=200.0, dark_k=50.0
    )
    assert capped[0] == 200.0


def test_hours_below_and_first_below() -> None:
    t = np.array([0.0, 3600.0, 7200.0])
    k = np.array([300.0, 250.0, 250.0])
    assert thermal.hours_below(t, k, 275.0) == pytest.approx(0.5 + 1.0)
    assert thermal.first_below(t, k, 275.0) == pytest.approx(1800.0)
    assert thermal.first_below(t, k, 100.0) is None
