"""Calendar buckets: a gap cut by a boundary is a lower bound (docs/test-plan.md 10.4)."""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from app.core.horizon import SMOOTH_SPHERE_PRODUCT, is_terrain_modelled, smooth_mask
from app.core.intervals import Run
from app.core.metrics import bucket_stats
from app.services.site_service import calendar_edges


def runs(pattern: list[tuple[bool, float]]) -> list[Run]:
    out, t = [], 0.0
    for v, dur in pattern:
        out.append(Run(value=v, start=t, end=t + dur))
        t += dur
    return out


def test_edges_partition_the_window() -> None:
    e = calendar_edges(
        datetime(2027, 1, 15, 6, tzinfo=UTC), datetime(2027, 4, 2, tzinfo=UTC), "month"
    )
    assert e[0] == datetime(2027, 1, 15, 6, tzinfo=UTC)
    assert e[1:4] == [datetime(2027, m, 1, tzinfo=UTC) for m in (2, 3, 4)]
    assert e[-1] == datetime(2027, 4, 2, tzinfo=UTC)
    assert e == sorted(e) and len(set(e)) == len(e)


def test_a_night_split_by_a_boundary_is_open_on_both_sides() -> None:
    arcs = runs([(True, 50), (False, 100), (True, 50)])  # night spans 50..150
    a, b = bucket_stats(arcs, [0.0, 100.0, 200.0])
    assert a.longest_down_s == 50 and a.longest_down_open
    assert b.longest_down_s == 50 and b.longest_down_open


def test_a_night_inside_a_bucket_is_measured() -> None:
    arcs = runs([(True, 20), (False, 30), (True, 150)])
    (a,) = bucket_stats(arcs, [0.0, 200.0])
    assert a.longest_down_s == 30 and not a.longest_down_open
    assert a.up_s == 170 and abs(a.fraction_up - 0.85) < 1e-12


@given(
    st.lists(st.tuples(st.booleans(), st.floats(1, 500)), min_size=1, max_size=40),
    st.lists(st.floats(0.01, 0.99), max_size=8),
)
def test_up_time_sums_across_buckets(pattern: list[tuple[bool, float]], cuts: list[float]) -> None:
    arcs = runs(pattern)
    total = arcs[-1].end
    edges = sorted({0.0, total, *(c * total for c in cuts)})
    stats = bucket_stats(arcs, edges)
    whole = sum(r.duration for r in arcs if r.value)
    assert abs(sum(s.up_s for s in stats) - whole) < 1e-6 * max(1.0, total)


def test_smooth_mask_is_flat_and_flagged() -> None:
    m = smooth_mask(azimuth_step_deg=0.25)
    assert m.azimuth_count == 1440
    assert float(m.el_deg.max()) == 0.0 and float(m.tol_deg.max()) == 0.0
    assert m.coverage == 0.0
    assert not is_terrain_modelled(SMOOTH_SPHERE_PRODUCT)
    assert is_terrain_modelled("LOLA_LDEM_80S_20M")
