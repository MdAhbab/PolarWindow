"""The four numbers, and the rules about what they must never become."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.core import intervals, metrics
from app.core.intervals import Run

H = 3600.0


def arcs(spec: list[tuple[bool, float, float]]) -> list[Run]:
    return [Run(value=v, start=a * H, end=b * H) for v, a, b in spec]


def test_four_numbers_from_known_arcs() -> None:
    sun = arcs([(True, 0, 100), (False, 100, 180), (True, 180, 300), (False, 300, 320)])
    earth = arcs([(True, 0, 60), (False, 60, 250), (True, 250, 320)])
    m = metrics.assemble("s", 0.0, 320 * H, sun, earth)
    assert m.sunlit_s == pytest.approx(220 * H)
    assert m.earth_contact_s == pytest.approx(130 * H)
    assert m.longest_dark_s == pytest.approx(80 * H)
    assert m.longest_blackout_s == pytest.approx(190 * H)


def test_compound_is_the_intersection_of_both_being_down() -> None:
    sun = arcs([(True, 0, 100), (False, 100, 180), (True, 180, 300)])
    earth = arcs([(True, 0, 60), (False, 60, 250), (True, 250, 300)])
    m = metrics.assemble("s", 0.0, 300 * H, sun, earth)
    assert len(m.compound) == 1
    assert m.compound[0].start == pytest.approx(100 * H)
    assert m.compound[0].end == pytest.approx(180 * H)
    assert m.worst_compound_s == pytest.approx(80 * H)


def test_touching_intervals_do_not_make_an_event() -> None:
    sun = arcs([(True, 0, 100), (False, 100, 200)])
    earth = arcs([(False, 0, 100), (True, 100, 200)])
    m = metrics.assemble("s", 0.0, 200 * H, sun, earth)
    assert m.compound == []


def test_autonomy_uses_the_whole_night_when_the_blackout_is_inside_it() -> None:
    """Under-sizing the battery is the dangerous direction to be wrong in.

    If the radio is silent for 40 h in the middle of a 230 h night, the battery
    still has to carry the whole 230 h.
    """
    sun = arcs([(True, 0, 50), (False, 50, 280), (True, 280, 320)])
    earth = arcs([(True, 0, 100), (False, 100, 140), (True, 140, 320)])
    m = metrics.assemble("s", 0.0, 320 * H, sun, earth)
    packet = metrics.autonomy(m)
    assert packet.compound_inside_dark is True
    assert packet.worst_compound_s == pytest.approx(40 * H)
    assert packet.survival_needed_s == pytest.approx(230 * H)
    assert packet.required_autonomy_s == pytest.approx(40 * H * 1.2)


def test_metrics_has_no_composite_score() -> None:
    """An executable form of a product rule, not a style preference.

    A score ranks sites on one axis and hides which corner was given up, and the
    trade is the product.
    """
    m = metrics.assemble("s", 0.0, 10 * H, arcs([(True, 0, 10)]), arcs([(True, 0, 10)]))
    for forbidden in ("score", "rating", "overall", "index", "grade"):
        assert not hasattr(m, forbidden), f"a composite '{forbidden}' appeared"


def test_rank_reports_ties_rather_than_ordering_them() -> None:
    """Ordering two sites that differ by twenty minutes over a month asserts a
    distinction a 20 m DEM and a lunar ephemeris cannot support."""

    def make(sid: str, dark_h: float) -> metrics.SiteMetrics:
        return metrics.assemble(
            sid,
            0.0,
            400 * H,
            arcs([(True, 0, 400 - dark_h), (False, 400 - dark_h, 400)]),
            arcs([(True, 0, 400)]),
        )

    entries = [make("a", 100), make("b", 100.2), make("c", 300)]
    ordered, ties = metrics.rank(entries, "longest_dark_s")
    assert [m.site_id for m in ordered] == ["a", "b", "c"]
    assert ties == [["a", "b"]]


def test_rank_direction_is_correct_per_metric() -> None:
    def make(sid: str, sun_h: float) -> metrics.SiteMetrics:
        return metrics.assemble(
            sid,
            0.0,
            400 * H,
            arcs([(True, 0, sun_h), (False, sun_h, 400)]),
            arcs([(True, 0, 400)]),
        )

    entries = [make("low", 100), make("high", 300)]
    ordered, _ = metrics.rank(entries, "sunlit_s")
    assert ordered[0].site_id == "high", "more sunlight should rank first"
    ordered, _ = metrics.rank(entries, "longest_dark_s")
    assert ordered[0].site_id == "high", "a shorter night should rank first"


def test_unknown_metric_raises() -> None:
    m = metrics.assemble("s", 0.0, H, arcs([(True, 0, 1)]), arcs([(True, 0, 1)]))
    with pytest.raises(KeyError, match="unknown metric"):
        metrics.metric_value(m, "vibes")


@given(
    st.lists(st.booleans(), min_size=4, max_size=200),
    st.lists(st.booleans(), min_size=4, max_size=200),
)
@settings(max_examples=200)
def test_invariants_hold_for_any_pair_of_series(sun_v: list[bool], earth_v: list[bool]) -> None:
    """The invariants a reader is entitled to assume, over arbitrary inputs."""
    n = min(len(sun_v), len(earth_v))
    assume(n >= 4)
    t = np.arange(n, dtype=np.float64) * H
    sun = intervals.runs_from_margin(t, np.where(np.array(sun_v[:n]), 1.0, -1.0))
    earth = intervals.runs_from_margin(t, np.where(np.array(earth_v[:n]), 1.0, -1.0))
    m = metrics.assemble("s", 0.0, float(t[-1]), sun, earth)

    span = float(t[-1])
    assert m.sun.up_s + m.sun.down_s == pytest.approx(span, abs=1e-6)
    assert m.longest_dark_s <= m.sun.down_s + 1e-6
    assert m.longest_blackout_s <= m.earth.down_s + 1e-6
    # A compound event cannot outlast either of the things it intersects.
    assert m.worst_compound_s <= m.longest_dark_s + 1e-6
    assert m.worst_compound_s <= m.longest_blackout_s + 1e-6
    assert 0.0 <= m.sun.fraction_up <= 1.0


def test_survival_is_the_longest_night_even_with_no_blackout() -> None:
    """The battery carries the night whatever the radio is doing.

    Found on real data: Malapert keeps Earth in view through its nights, so no
    compound event exists -- and the old packet reported 0 h of survival for a
    site with a 288 h night.
    """
    sun = arcs([(True, 0, 100), (False, 100, 388), (True, 388, 700)])
    earth = arcs([(True, 0, 700)])
    m = metrics.assemble("s", 0.0, 700 * H, sun, earth)
    packet = metrics.autonomy(m)
    assert m.compound == []
    assert packet.worst_compound_s == 0.0
    assert packet.survival_needed_s == pytest.approx(288 * H)


def test_a_night_cut_by_the_window_is_flagged_as_a_lower_bound() -> None:
    """The window ended it, not the terrain: report it, and say so."""
    sun = arcs([(False, 0, 40), (True, 40, 600), (False, 600, 700)])
    earth = arcs([(True, 0, 650), (False, 650, 700)])
    m = metrics.assemble("s", 0.0, 700 * H, sun, earth)
    assert m.longest_dark_s == pytest.approx(100 * H)
    assert m.longest_dark_open is True
    assert m.longest_blackout_open is True
    assert m.worst_compound_open is True
    assert metrics.autonomy(m).survival_open is True


def test_an_interior_night_is_not_flagged() -> None:
    sun = arcs([(True, 0, 100), (False, 100, 300), (True, 300, 700)])
    earth = arcs([(True, 0, 700)])
    m = metrics.assemble("s", 0.0, 700 * H, sun, earth)
    assert m.longest_dark_open is False
    assert metrics.autonomy(m).survival_open is False


def test_competition_ranks_give_tied_sites_the_same_rank() -> None:
    """1, 1, 3 -- never 1, 2, 3 for sites the data cannot tell apart."""
    r = metrics.rank_values(
        [("a", 100 * H), ("b", 100.4 * H), ("c", 150 * H)], higher_is_better=False
    )
    assert r.order == ["a", "b", "c"]
    assert r.ranks == {"a": 1, "b": 1, "c": 3}
    assert r.ties == [["a", "b"]]


def test_ties_are_anchored_on_the_leader_not_chained() -> None:
    """A ~ B and B ~ C does not make A ~ C when A and C are 1.8 h apart."""
    r = metrics.rank_values([("a", 0.0), ("b", 0.9 * H), ("c", 1.8 * H)], higher_is_better=False)
    assert r.ties == [["a", "b"]]
    assert r.ranks == {"a": 1, "b": 1, "c": 3}
