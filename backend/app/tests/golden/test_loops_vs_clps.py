"""Phasing loops and correction budgets against the flown landers (plan C3 and C4).

See ``validate_loops`` for the method; ``make validate-trip`` prints the tables
in docs/validation.md. The plan asks for Blue Ghost's replayed perigees and
apogees within an hour and its apogee radius within 1%; a design with the
flown number of loops whose launch period holds the flown date; and the
linear correction budget within 10% of the Monte Carlo one at the 95th and
99th percentiles, with a seeded run repeated bit for bit.
"""

from __future__ import annotations

import numpy as np
import pytest

pytestmark = [pytest.mark.requires_kernels, pytest.mark.requires_clps_spice, pytest.mark.slow]

MISSIONS = ("blue-ghost-m1", "im-1", "im-2")


@pytest.fixture(scope="module")
def ready():
    from app.config import get_settings
    from app.core import spice
    from app.services import ascent

    for m in MISSIONS:
        if not ascent.spk_path(m).exists():
            pytest.skip(f"{m} reconstruction not on disk (polar-data sync)")
    spice.load(get_settings().kernel_dir)


def test_blue_ghost_loops_replayed_from_the_burns_found(ready) -> None:
    from app.tests.golden import validate_loops

    rp = validate_loops.replay_check()
    names = [b.name for b in rp.burns]
    assert names == [
        "Burn near the highest point of the orbit",
        "Burn near the lowest point of the orbit",
        "Leaving Earth for the Moon",
        "Correction 1",
        "Entering lunar orbit",
    ]
    assert len(rp.pairs) == 6
    assert rp.worst_min <= 60.0 and rp.worst_apogee_pct <= 1.0  # the plan's acceptance
    # What is achieved: within 5 minutes and 0.05 %.
    assert rp.worst_min < 5.0 and rp.worst_apogee_pct < 0.05 and rp.worst_perigee_pct < 0.05


def test_designed_loops_match_the_flown_ones_on_the_flown_day(ready) -> None:
    from app.tests.golden import validate_loops

    lp = validate_loops.design_days()
    by_day = {d.day: d for d in lp.days}
    flown = by_day[0]
    assert flown.loops == lp.flown_loops == 3
    period = next(p for p in lp.periods if p[0] <= 0 <= p[1])
    assert period[2] == lp.flown_loops  # the plan's acceptance
    # What is achieved: the flown day is the cheapest nearby, within 2 m/s of the flown burns.
    assert flown.total_m_s == min(d.total_m_s for d in lp.days if d.total_m_s is not None)
    assert abs(flown.total_m_s - sum(lp.flown_burns_m_s)) < 2.0


@pytest.mark.parametrize("mission", MISSIONS)
def test_linear_and_monte_carlo_budgets_agree(ready, mission) -> None:
    from app.tests.golden import validate_loops

    r = validate_loops.corrections(mission)
    assert r.missed == 0
    for lin, mc in ((r.p95_linear, r.p95_mc), (r.p99_linear, r.p99_mc)):
        assert abs(lin - mc) <= 0.10 * mc  # the plan's acceptance
    lo, hi = r.p99_mc_interval
    assert lo <= r.p99_mc <= hi


def test_a_seeded_run_repeats_bit_for_bit(ready) -> None:
    from app.core import forces, lincov
    from app.services import flown_burns
    from app.tests.golden import validate_launch, validate_loops

    f = validate_launch._flights()["im-2"]
    tables = validate_loops._tables_for(f)
    named, _ = flown_burns.burns("im-2", f.launch, tables)
    planned = flown_burns.planned_flight("im-2", f.launch, tables, named)
    assert planned is not None
    nom = lincov.nominal(tables, forces.Model(), planned.plan)
    runs = [
        lincov.monte_carlo(
            tables, forces.Model(), nom, planned.plan, flown_burns.ASSUMED, samples=20, seed=11
        )
        for _ in range(2)
    ]
    assert np.array_equal(runs[0].dv, runs[1].dv)
    assert np.array_equal(runs[0].periapsis_alt_m, runs[1].periapsis_alt_m)


def test_blue_ghost_climbing_as_flown_lands_on_its_liftoff(ready) -> None:
    """Due east the design lands 139 min early; in the direction it flew, within minutes."""
    from app.tests.golden import validate_loops

    az, d0 = validate_loops.flown_direction()
    assert 105 < az < 115
    assert d0.loops == 3 and d0.t0_min is not None and abs(d0.t0_min) < 5  # plan: 5 min
