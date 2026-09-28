"""Phasing loops (C3) and correction burns (C4) on synthetic body tables.

The checks against Blue Ghost's and the Nova-C landers' reconstructions live
in tests/golden/test_loops_vs_clps.py.
"""

from __future__ import annotations

import math

import numpy as np

from app.core import forces, lincov, phasing, propagate, transfer
from app.tests.unit.test_propagate import GM_E, _tables

KEPLER = forces.Model(earth_field=forces.earth_zonal(0), moon=False, sun=False)


def _ellipse(r_p: float, r_a: float) -> np.ndarray:
    a = 0.5 * (r_p + r_a)
    v_p = math.sqrt(GM_E * (2.0 / r_p - 1.0 / a))
    return np.array([r_p, 0.0, 0.0, 0.0, v_p, 0.0])


def _burned(tab: forces.Tables, y0: np.ndarray, t_burn: float, dv: np.ndarray, t1: float):
    a = propagate.propagate(tab, KEPLER, 0.0, y0, t_burn)
    y = a.state[-1].copy()
    y[3:] += dv
    b = propagate.propagate(tab, KEPLER, t_burn, y, t1)

    def at(ets: np.ndarray) -> np.ndarray:
        ets = np.atleast_1d(ets)
        return np.where(
            (ets <= t_burn)[:, None], a.at(np.minimum(ets, t_burn)), b.at(np.maximum(ets, t_burn))
        )

    return at


def test_a_burn_is_found_where_and_as_large_as_it_was() -> None:
    tab = _tables(days=2.0)
    y0 = _ellipse(7.0e6, 30.0e6)
    dv = np.array([0.4, -0.3, 0.2])
    at = _burned(tab, y0, 20_000.0, dv, 60_000.0)
    burns = phasing.find_burns(tab, KEPLER, at, 0.0, 57_600.0)
    assert len(burns) == 1
    b = burns[0]
    assert abs(b.t - 20_000.0) < 2.0
    assert np.max(np.abs(b.dv - dv)) < 2e-3
    assert b.start <= 20_000.0 <= b.end


def test_no_burn_is_found_in_a_clean_orbit() -> None:
    tab = _tables(days=2.0)
    tr = propagate.propagate(tab, KEPLER, 0.0, _ellipse(7.0e6, 30.0e6), 60_000.0)
    assert phasing.find_burns(tab, KEPLER, tr.at, 0.0, 57_600.0) == []


def test_apsides_and_replay_of_a_kepler_ellipse() -> None:
    tab = _tables(days=3.0)
    r_p, r_a = 7.0e6, 40.0e6
    period = 2 * math.pi * math.sqrt((0.5 * (r_p + r_a)) ** 3 / GM_E)
    y0 = _ellipse(r_p, r_a)
    tr = propagate.propagate(tab, KEPLER, 0.0, y0, 2.2 * period)
    found = phasing.apsides(tr.at, 60.0, 2.2 * period)
    kinds = [a.kind for a in found]
    assert kinds == ["apogee", "perigee", "apogee", "perigee"]
    assert abs(found[0].t - period / 2) < 0.05 and abs(found[0].r_m - r_a) < 1.0
    assert abs(found[1].t - period) < 0.05 and abs(found[1].r_m - r_p) < 1.0
    # Replaying with no burns gives the same apsides from events.
    rp = phasing.replay(tab, KEPLER, 0.0, y0, [], 2.2 * period)
    for flown, again in phasing.match(found, rp.apsides):
        assert again is not None
        assert abs(again.t - flown.t) < 0.05 and abs(again.r_m - flown.r_m) < 1.0


def test_replay_adds_the_burns() -> None:
    tab = _tables(days=2.0)
    y0 = _ellipse(7.0e6, 30.0e6)
    dv = np.array([0.0, 5.0, 0.0])
    at = _burned(tab, y0, 20_000.0, dv, 60_000.0)
    burn = phasing.Burn(20_000.0, dv, 19_800.0, 21_600.0, 0.0, 0.0)
    rp = phasing.replay(tab, KEPLER, 0.0, y0, [burn], 60_000.0)
    assert np.max(np.abs(rp.end_state[:3] - at(np.array([60_000.0]))[0, :3])) < 1e-3


def test_two_body_plan_puts_the_last_perigee_on_time() -> None:
    r_p, v_p = 6.6e6, 10_880.0
    a1 = 1.0 / (2.0 / r_p - v_p**2 / GM_E)
    p1 = 2 * math.pi * math.sqrt(a1**3 / GM_E)
    t_final = 3.1 * p1
    raise_dv, dv1, dv2 = phasing.two_body_plan(GM_E, r_p, v_p, 0.0, t_final, 3, 3.84e8, 4.5 * 86400)
    assert raise_dv == 0.0
    a2 = 1.0 / (2.0 / r_p - (v_p + dv1) ** 2 / GM_E)
    p2 = 2 * math.pi * math.sqrt(a2**3 / GM_E)
    assert abs(p1 + 2 * p2 - t_final) < 1e-3
    _, v_need = transfer.patched_conic(r_p, 3.84e8, 4.5 * 86400, GM_E)
    assert abs(v_p + dv1 + dv2 - v_need) < 1e-9
    assert phasing.loops_for(GM_E, r_p, v_p, 0.0, t_final) == 3
    # Raising the perigee at the first apogee costs speed there and lengthens loop 1.
    raise_dv, _, _ = phasing.two_body_plan(
        GM_E, r_p, v_p, 0.0, t_final, 3, 3.84e8, 4.5 * 86400, 13.0e6
    )
    assert raise_dv > 0.0


def _day(t: float, dv: float, refused: str | None = None, n: int = 3) -> phasing.Day:
    d = phasing.LoopDesign(
        t, 0, t, 3000, n, None, 0.0, 0.0, dv, [], [], [], 0, 0, t, 0, 0, 0, 0, 1, True, refused
    )
    return phasing.pick(t, [d], 50.0)


def test_launch_period_joins_usable_days_with_the_same_loops() -> None:
    day = 86_400.0
    days = [
        _day(0 * day, 20.0),
        _day(1 * day, 30.0),
        _day(2 * day, 60.0),  # over the budget
        _day(3 * day, 10.0, refused="a perigee drops to 90 km altitude"),
        _day(4 * day, 10.0),
        _day(5 * day, 10.0, n=2),
    ]
    assert days[2].why_not is not None and "budget" in days[2].why_not
    assert phasing.launch_period(days) == [
        (0.0, day, 3),
        (4 * day, 4 * day, 3),
        (5 * day, 5 * day, 2),
    ]


# --- correction burns -------------------------------------------------------------


def _plan(tab: forces.Tables) -> tuple[lincov.Plan, lincov.Nominal]:
    y0 = _ellipse(7.0e6, 60.0e6)
    plan = lincov.Plan(0.0, y0, 40_000.0, (8_000.0, 20_000.0, 32_000.0))
    return plan, lincov.nominal(tab, KEPLER, plan)


def test_guidance_cancels_the_linear_miss_at_arrival() -> None:
    tab = _tables(days=1.0)
    plan, nom = _plan(tab)
    g = lincov.guidance(nom, 20_000.0, plan.t_arrive)
    phi = nom.between(plan.t_arrive, 20_000.0)
    rng = np.random.default_rng(1)
    for _ in range(5):
        dx = np.concatenate([rng.normal(0, 1e3, 3), rng.normal(0, 1.0, 3)])
        after = dx.copy()
        after[3:] += g @ dx
        assert np.max(np.abs(phi[:3] @ after)) < 1e-6 * np.max(np.abs(phi[:3] @ dx))


def test_state_transition_matrix_matches_a_small_deviation() -> None:
    tab = _tables(days=1.0)
    plan, nom = _plan(tab)
    dy = np.array([50.0, -20.0, 10.0, 0.01, 0.02, -0.01])
    base = propagate.propagate(tab, KEPLER, 0.0, plan.y_tli, 20_000.0).state[-1]
    left = []
    for s in (1.0, 0.5):
        moved = propagate.propagate(tab, KEPLER, 0.0, plan.y_tli + s * dy, 20_000.0).state[-1]
        lin = s * (nom.between(20_000.0, 0.0) @ dy)
        dev = float(np.linalg.norm(moved[:3] - base[:3]))
        left.append(float(np.linalg.norm(moved[:3] - base[:3] - lin[:3])))
        assert left[-1] < 1e-4 * dev
    # What is left is the second-order term: half the deviation leaves a quarter.
    assert 3.0 < left[0] / left[1] < 5.0


def test_gates_draws_have_the_model_spread() -> None:
    g = lincov.Gates(0.02, 0.01, 0.01, 0.005)
    dv = np.tile([10.0, 0.0, 0.0], (200_000, 1))
    e = lincov.execution_errors(dv, g, np.random.default_rng(4))
    assert abs(np.std(e[:, 0]) - math.hypot(0.2, 0.01)) < 0.003
    side = math.hypot(0.1, 0.005)
    assert abs(np.std(e[:, 1]) - side) < 0.002 and abs(np.std(e[:, 2]) - side) < 0.002
    assert abs(np.mean(e[:, 0])) < 0.002


def test_the_linear_budget_is_seeded_and_bootstrapped() -> None:
    tab = _tables(days=1.0)
    plan, nom = _plan(tab)
    err = lincov.Errors(
        (100.0,) * 3, (0.1,) * 3, 50.0, 0.001, lincov.Gates(0.01, 0.005, 0.01, 0.005)
    )
    a = lincov.linear(tab, nom, plan, err, samples=2000, seed=7)
    b = lincov.linear(tab, nom, plan, err, samples=2000, seed=7)
    assert np.array_equal(a.dv, b.dv) and np.array_equal(a.periapsis_alt_m, b.periapsis_alt_m)
    burns, total = a.pct(99)
    assert len(burns) == 3 and total >= max(burns)
    lo, hi = lincov.bootstrap(a.total, 99, n=300)
    assert lo <= total <= hi


def _b(t: float, dv: float, r_km: float, hours: float = 0.5) -> phasing.Burn:
    return phasing.Burn(
        t, np.array([dv, 0.0, 0.0]), t - 900.0, t - 900.0 + hours * 3600, r_km * 1e3, 0.0
    )


def test_burns_are_named_by_where_they_fire() -> None:
    day = 86_400.0
    burns = [
        _b(4 * day, 22.5, 335_000),
        _b(8 * day, 3.3, 13_000),
        _b(25 * day, 23.6, 12_000),
        _b(26 * day, 1.1, 196_000),
        _b(30 * day, 356.0, 398_000),
        _b(10 * day, 40.0, 300_000, hours=140.0),  # a leak, not a burn
    ]
    named, steady = phasing.name_burns(burns, 30 * day + 60.0)
    assert [n for _, n in named] == [
        "Burn near the highest point of the orbit",
        "Burn near the lowest point of the orbit",
        "Leaving Earth for the Moon",
        "Correction 1",
        "Entering lunar orbit",
    ]
    assert len(steady) == 1
    # A direct flight's reconstruction starts after its upper stage left Earth.
    named, _ = phasing.name_burns([_b(day, 2.0, 170_000), _b(2 * day, 9.7, 260_000)], None)
    assert [n for _, n in named] == ["Correction 1", "Correction 2"]


def test_the_runs_are_seeded_and_count_the_misses() -> None:
    tab = _tables(days=1.0)
    plan, nom = _plan(tab)
    err = lincov.Errors(
        (100.0,) * 3, (0.1,) * 3, 50.0, 0.001, lincov.Gates(0.01, 0.005, 0.01, 0.005)
    )
    seen: list[int] = []
    a = lincov.monte_carlo(
        tab, KEPLER, nom, plan, err, samples=4, seed=3, retarget=1, progress=seen.append
    )
    b = lincov.monte_carlo(tab, KEPLER, nom, plan, err, samples=4, seed=3, retarget=1)
    assert np.array_equal(a.dv, b.dv) and seen == [1, 2, 3, 4]
    # This ellipse never nears the Moon: every run is counted as a miss, none dropped.
    assert a.missed == 4 and a.dv.shape == (4, 3)
    c = lincov.monte_carlo(tab, KEPLER, nom, plan, err, samples=4, seed=4, retarget=1)
    assert not np.array_equal(a.dv, c.dv)
