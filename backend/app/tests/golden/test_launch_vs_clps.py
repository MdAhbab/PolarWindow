"""Launch instants against the flown Falcon 9 lunar launches (plan D1 and C2 acceptance).

See ``validate_launch`` for the method; ``make validate-trip`` prints the table
in docs/validation.md. The plan asks for the liftoff worked out again from a
flown TLI within 2 minutes (IM-1, IM-2) and 5 minutes (Blue Ghost), and for
a designed launch on the right day within 10 minutes. Designed with the
climb in the direction each flight flew, both land within a minute; due east
or in the other flight's direction they miss by 10 to 27 minutes, since each
degree of direction moves the liftoff about 7.5 minutes and the arrival does
not fix it. The test pins what is achieved so a change is seen, and
docs/validation.md says why.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.requires_kernels, pytest.mark.requires_clps_spice, pytest.mark.slow]


@pytest.fixture(scope="module")
def rows():
    from app.services import ascent
    from app.tests.golden import validate_launch

    for m in validate_launch.F9:
        if not ascent.spk_path(m).exists():
            pytest.skip(f"{m} reconstruction not on disk (polar-data sync)")
    return {r.mission: r for r in validate_launch.results()}


def test_liftoff_from_the_flown_tli(rows) -> None:
    assert abs(rows["im-1"].from_tli_s) <= 120
    assert abs(rows["im-2"].from_tli_s) <= 120
    assert abs(rows["blue-ghost-m1"].from_tli_s) <= 300
    # What is achieved: within 20 s each.
    assert max(abs(r.from_tli_s) for r in rows.values()) < 20


def test_designed_direct_transfers_reach_the_flown_arrival(rows) -> None:
    for mid in ("im-1", "im-2"):
        r = rows[mid]
        assert r.converged
        assert r.designed_t0_min is not None and abs(r.designed_t0_min) < 60  # right day
        assert abs(r.designed_coast_min - r.flown_coast_min) < 5
        assert abs(r.designed_dv_m_s - r.flown_dv_m_s) < 10
        assert abs(r.designed_flight_d - r.flown_flight_d) < 0.05
    assert abs(rows["im-1"].designed_t0_min) < 10  # the plan's 10 minutes, met for IM-1
    assert rows["blue-ghost-m1"].designed_t0_min is None  # phasing loops: C3


def test_the_direction_of_the_climb_decides_the_instant(rows) -> None:
    for mid in ("im-1", "im-2"):
        r = rows[mid]
        assert r.flown_az_t0_min is not None and abs(r.flown_az_t0_min) < 2  # plan: 10 min
        # Held out (the other Nova-C launch's direction): what is achieved.
        assert r.held_az_t0_min is not None and abs(r.held_az_t0_min) < 20
    assert 85 < rows["im-1"].flown_az_deg < 90 and 85 < rows["im-2"].flown_az_deg < 90
    assert 105 < rows["blue-ghost-m1"].flown_az_deg < 115  # inclined 35 degrees


def test_nothing_published_predicts_the_direction(rows) -> None:
    """Held out, no predictor of the climb's direction beats the other flight's for both
    Nova-C launches (docs/validation.md, D1): pinned so a change is seen."""
    im1, im2 = rows["im-1"], rows["im-2"]
    # The arrival's node moves 0.05 to 0.09 degrees per degree of direction; IM-1's
    # designed approach already sits 1.2 degrees off, so the node points far away.
    assert im1.node_per_az is not None and 0.02 < im1.node_per_az < 0.12
    assert im2.node_per_az is not None and 0.02 < im2.node_per_az < 0.12
    assert im1.node_az_t0_min is None or abs(im1.node_az_t0_min) > 60
    assert im2.node_az_t0_min is not None and 5 < abs(im2.node_az_t0_min) < 15
    # The other flight's inclination after TLI lands both within 10 minutes, but the same
    # rule given each flight's own inclination misses both by more: two flights' numbers
    # crossing, not a property of the climb.
    assert abs(im1.inc_other_t0_min) < 10 and abs(im2.inc_other_t0_min) < 10
    assert abs(im1.inc_own_t0_min) > 10 and abs(im2.inc_own_t0_min) > 10


def test_steering_between_the_pads_limits_would_open_hours(rows) -> None:
    """Designed at the pad's 35 and 120 degrees over the ground, the day's instant moves by
    hours; both Nova-C launches were published as single instants."""
    for mid in ("im-1", "im-2"):
        r = rows[mid]
        assert r.window_open_min is not None and r.window_open_min < -60
        assert r.window_close_min is not None and r.window_close_min > 60
