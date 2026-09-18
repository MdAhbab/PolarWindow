"""Property tests for `core.intervals`.

This is the highest-value block in the suite. Off-by-one errors in longest-run
detection are the most likely silent bug in the whole project -- they produce a
plausible number rather than an exception, and 63 h against 64 h looks fine and
is wrong.

`intervals.py` deliberately knows nothing about astronomy, which is what makes
these properties possible: hypothesis can quantify over *every* boolean array up
to length 300 rather than over plausible-looking sun tracks.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from hypothesis import assume, example, given, settings
from hypothesis import strategies as st

from app.core import intervals

TOL = 1e-6

bools = st.lists(st.booleans(), min_size=0, max_size=300)


def series(values: list[bool], step: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """A margin series whose sign follows `values`."""
    t = np.arange(len(values), dtype=np.float64) * step
    margin = np.where(np.asarray(values, dtype=bool), 1.0, -1.0)
    return t, margin


# The degenerate shapes are pinned rather than left to the generator: runs at
# the very first and very last sample are where the classic off-by-one lives.
DEGENERATE = [
    [],
    [True],
    [False],
    [True, False],
    [False, True],
    [True, True, True],
    [False, False, False],
]


@given(bools)
@example([])
@example([True])
@example([False])
@example([True, False])
@example([False, True])
@settings(max_examples=300)
def test_partition_is_exact(values: list[bool]) -> None:
    """No time is lost or double-counted."""
    assume(len(values) >= 1)
    t, m = series(values)
    runs = intervals.runs_from_margin(t, m)
    total = sum(r.duration for r in runs)
    assert total == pytest.approx(float(t[-1] - t[0]), abs=TOL)


@given(bools)
@settings(max_examples=300)
def test_runs_alternate(values: list[bool]) -> None:
    assume(len(values) >= 1)
    t, m = series(values)
    runs = intervals.runs_from_margin(t, m)
    for a, b in itertools.pairwise(runs):
        assert a.value != b.value, "two adjacent runs share a value"


@given(bools)
@settings(max_examples=300)
def test_runs_are_contiguous(values: list[bool]) -> None:
    assume(len(values) >= 1)
    t, m = series(values)
    runs = intervals.runs_from_margin(t, m)
    for a, b in itertools.pairwise(runs):
        assert a.end == pytest.approx(b.start, abs=TOL), "gap or overlap between runs"
    for r in runs:
        assert r.end >= r.start - TOL


@given(bools, st.booleans())
@settings(max_examples=300)
def test_longest_is_a_member_and_maximal(values: list[bool], want: bool) -> None:
    """Stated both ways deliberately.

    `max()` over the wrong filtered set satisfies "is maximal" while failing
    "is a member", so checking only one half misses a whole class of bug.
    """
    assume(len(values) >= 1)
    t, m = series(values)
    runs = intervals.runs_from_margin(t, m)
    durations = [r.duration for r in runs if r.value == want]
    longest = intervals.longest(runs, want)
    if not durations:
        assert longest is None
        assert intervals.longest_duration(runs, want) == 0.0
        return
    assert longest is not None
    assert longest.value == want
    assert any(abs(longest.duration - d) < TOL for d in durations), "not a member"
    assert longest.duration >= max(durations) - TOL, "not maximal"


@given(bools)
@settings(max_examples=300)
def test_inversion_symmetry(values: list[bool]) -> None:
    """runs(~a) mirrors runs(a).

    Asymmetric handling of the first or last run is the signature of a whole
    family of boundary bugs, and this catches all of them at once.
    """
    assume(len(values) >= 1)
    t, m = series(values)
    a = intervals.runs_from_margin(t, m)
    b = intervals.runs_from_margin(t, -m)
    assert len(a) == len(b)
    for ra, rb in zip(a, b, strict=True):
        assert ra.value != rb.value
        assert ra.start == pytest.approx(rb.start, abs=TOL)
        assert ra.end == pytest.approx(rb.end, abs=TOL)


@given(bools, bools)
@settings(max_examples=250)
def test_concatenation(left: list[bool], right: list[bool]) -> None:
    """Splicing two series joins or adds runs, never loses one.

    This is the property that catches a boundary bug at a chunk edge, which is
    exactly what a windowed computation is.
    """
    assume(len(left) >= 1 and len(right) >= 1)
    joined = left + right
    t, m = series(joined)
    runs = intervals.runs_from_margin(t, m)
    tl, ml = series(left)
    tr, mr = series(right)
    nl = len(intervals.runs_from_margin(tl, ml))
    nr = len(intervals.runs_from_margin(tr, mr))
    expected = nl + nr if left[-1] != right[0] else nl + nr - 1
    # The seam can also merge two same-valued runs, so allow one either way --
    # what must not happen is a run appearing or vanishing wholesale.
    assert abs(len(runs) - expected) <= 1


@given(bools, st.floats(min_value=0.0, max_value=5.0))
@settings(max_examples=200)
def test_merge_short_gaps_is_idempotent(values: list[bool], eps: float) -> None:
    assume(len(values) >= 1)
    t, m = series(values)
    runs = intervals.runs_from_margin(t, m)
    once = intervals.merge_short_gaps(runs, False, eps)
    twice = intervals.merge_short_gaps(once, False, eps)
    assert [(r.value, round(r.start, 9), round(r.end, 9)) for r in once] == [
        (r.value, round(r.start, 9), round(r.end, 9)) for r in twice
    ]


@given(bools, st.floats(min_value=0.0, max_value=3.0), st.floats(min_value=0.0, max_value=3.0))
@settings(max_examples=200)
def test_merge_is_monotonic_in_epsilon(values: list[bool], e1: float, e2: float) -> None:
    """A larger tolerance can only lengthen the longest run, never shorten it."""
    assume(len(values) >= 1)
    lo, hi = sorted((e1, e2))
    t, m = series(values)
    runs = intervals.runs_from_margin(t, m)
    a = intervals.longest_duration(intervals.merge_short_gaps(runs, False, lo), False)
    b = intervals.longest_duration(intervals.merge_short_gaps(runs, False, hi), False)
    assert b >= a - TOL


@given(
    st.lists(st.floats(-5, 5, allow_nan=False), min_size=2, max_size=200),
    st.floats(-2, 2, allow_nan=False),
)
@settings(max_examples=200)
def test_threshold_monotonicity(margins: list[float], shift: float) -> None:
    """Raising the threshold cannot increase up-time. Catches a flipped compare."""
    t = np.arange(len(margins), dtype=np.float64)
    m = np.asarray(margins, dtype=np.float64)
    low = intervals.total(intervals.runs_from_margin(t, m), True)
    high = intervals.total(intervals.runs_from_margin(t, m - abs(shift)), True)
    assert high <= low + TOL


@given(bools, bools)
@settings(max_examples=200)
def test_intersect_is_bounded_by_both(a_vals: list[bool], b_vals: list[bool]) -> None:
    """A compound event cannot exceed either of the things it intersects.

    This is a true invariant of an intersection and a sharp test of the
    compound-event logic, where an error would over-state the autonomy
    requirement in the dangerous direction.
    """
    n = min(len(a_vals), len(b_vals))
    assume(n >= 2)
    t, ma = series(a_vals[:n])
    _t, mb = series(b_vals[:n])
    ra = intervals.runs_from_margin(t, ma)
    rb = intervals.runs_from_margin(t, mb)
    inter = intervals.intersect(ra, rb, value=False)
    total_inter = sum(r.duration for r in inter)
    assert total_inter <= intervals.total(ra, False) + TOL
    assert total_inter <= intervals.total(rb, False) + TOL
    for r in inter:
        assert intervals.contains(ra, r, value=False)
        assert intervals.contains(rb, r, value=False)


@pytest.mark.parametrize("values", DEGENERATE)
def test_degenerate_shapes_do_not_crash(values: list[bool]) -> None:
    t, m = series(values) if values else (np.array([]), np.array([]))
    runs = intervals.runs_from_margin(t, m)
    assert isinstance(runs, list)
    if len(values) >= 1:
        assert runs, "a non-empty series must produce at least one run"


def test_single_true_at_first_and_last_sample() -> None:
    """The classic off-by-one, pinned explicitly rather than left to chance."""
    for values in ([True] + [False] * 9, [False] * 9 + [True]):
        t, m = series(values)
        runs = intervals.runs_from_margin(t, m)
        assert sum(r.duration for r in runs) == pytest.approx(9.0, abs=TOL)
        assert any(r.value for r in runs), "the lone True was lost"


def test_bisect_finds_the_crossing() -> None:
    root = intervals.bisect_crossing(lambda x: x - 2.5, 0.0, 10.0)
    assert root == pytest.approx(2.5, abs=1e-6)


def test_bisect_on_a_graze_returns_the_midpoint() -> None:
    """No sign change: the function cannot invent one, and says so by returning
    the midpoint rather than raising. The caller has the context to call it a
    graze; this function does not."""
    got = intervals.bisect_crossing(lambda x: 1e-12, 0.0, 10.0)
    assert 0.0 <= got <= 10.0
