"""Ranking that respects censoring and each site's own uncertainty.

The review's sharpest finding (D20) was a comparison that called a window-cut
"at least 112 h" night the best, ahead of a measured 122 h one. These tests pin
the replacement: a value is an interval, a censored value is ``[v, inf)``, and
a site is placed above another only when the intervals say so.
"""

from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from app.core.metrics import RankInput, beats, rank_with_uncertainty, tie_groups

H = 3600.0


def places(xs: list[RankInput], hib: bool) -> dict[str, tuple[int | None, int, int]]:
    return {
        r.id: (r.rank, r.rank_min, r.rank_max)
        for r in rank_with_uncertainty(xs, higher_is_better=hib)
    }


def item(id_: str, v: float, u: float = 0.0, censored: bool = False) -> RankInput:
    return RankInput(id=id_, value=v, uncertainty=u, censored=censored)


inputs = st.lists(
    st.builds(
        RankInput,
        id=st.just(""),
        value=st.floats(min_value=0, max_value=1000 * H, allow_nan=False),
        uncertainty=st.one_of(
            st.floats(min_value=0, max_value=50 * H, allow_nan=False), st.just(math.inf)
        ),
        censored=st.booleans(),
    ),
    min_size=1,
    max_size=8,
).map(lambda xs: [RankInput(f"s{i}", x.value, x.uncertainty, x.censored) for i, x in enumerate(xs)])

directions = st.booleans()


# --------------------------------------------------------------------- named


def test_the_reviewed_case_declines_to_call_a_lower_bound_best() -> None:
    """Connecting Ridge 122 +/- 17 h, de Gerlache rim >= 112 h, Malapert >= 288 h."""
    r = rank_with_uncertainty(
        [
            item("connecting-ridge", 122 * H, 17 * H),
            item("de-gerlache-rim", 112 * H, censored=True),
            item("malapert-massif", 288 * H, censored=True),
        ],
        higher_is_better=False,
    )
    by = {x.id: x for x in r}
    assert (by["connecting-ridge"].rank_min, by["connecting-ridge"].rank_max) == (1, 2)
    assert (by["de-gerlache-rim"].rank_min, by["de-gerlache-rim"].rank_max) == (1, 3)
    assert (by["malapert-massif"].rank_min, by["malapert-massif"].rank_max) == (2, 3)
    assert by["de-gerlache-rim"].rank is None
    assert by["connecting-ridge"].rank is None  # cannot be placed against de Gerlache
    assert all(x.rank != 1 for x in r), "no site may be called best here"


def test_measured_overlap_is_a_shared_rank() -> None:
    r = rank_with_uncertainty(
        [item("a", 100 * H, 2 * H), item("b", 103 * H, 2 * H), item("c", 150 * H, 1 * H)],
        higher_is_better=False,
    )
    by = {x.id: x for x in r}
    assert by["a"].rank == 1 and by["b"].rank == 1
    assert by["c"].rank == 3
    assert tie_groups(r) == [["a", "b"]]


def test_clear_separation_is_a_definite_order() -> None:
    r = rank_with_uncertainty(
        [item("a", 10 * H, 1 * H), item("b", 50 * H, 1 * H), item("c", 90 * H, 1 * H)],
        higher_is_better=True,
    )
    assert [(x.id, x.rank) for x in r] == [("c", 1), ("b", 2), ("a", 3)]


def test_a_censored_night_far_longer_than_everything_is_still_last() -> None:
    """Censoring only hides an order when the bound is inside another interval."""
    r = rank_with_uncertainty(
        [item("short", 50 * H, 5 * H), item("long", 400 * H, censored=True)],
        higher_is_better=False,
    )
    by = {x.id: x for x in r}
    assert by["short"].rank == 1 and by["long"].rank == 2


def test_an_untimeable_edge_is_incomparable_not_tied() -> None:
    r = rank_with_uncertainty(
        [item("graze", 100 * H, math.inf), item("clean", 300 * H, 1 * H)],
        higher_is_better=False,
    )
    by = {x.id: x for x in r}
    assert by["graze"].rank is None and by["clean"].rank is None
    assert by["graze"].incomparable_with == ("clean",)
    assert tie_groups(r) == []


# ---------------------------------------------------------------- properties


@given(inputs)
def test_censored_never_beats_on_smaller_is_better(xs: list[RankInput]) -> None:
    for a in xs:
        if a.censored:
            assert not any(beats(a, b, higher_is_better=False) for b in xs if b is not a)


@given(inputs, directions)
def test_range_is_well_formed(xs: list[RankInput], hib: bool) -> None:
    n = len(xs)
    for r in rank_with_uncertainty(xs, higher_is_better=hib):
        assert 1 <= r.rank_min <= r.rank_max <= n
        if r.rank is not None:
            assert r.rank == r.rank_min


@given(inputs, directions, st.randoms(use_true_random=False))
def test_order_invariant(xs: list[RankInput], hib: bool, rnd: object) -> None:
    shuffled = list(xs)
    rnd.shuffle(shuffled)  # type: ignore[attr-defined]
    assert places(xs, hib) == places(shuffled, hib)


@given(inputs, directions)
def test_removal_never_widens(xs: list[RankInput], hib: bool) -> None:
    full = {r.id: r for r in rank_with_uncertainty(xs, higher_is_better=hib)}
    for drop in xs:
        rest = [x for x in xs if x is not drop]
        for r in rank_with_uncertainty(rest, higher_is_better=hib):
            f = full[r.id]
            assert (r.rank_max - r.rank_min) <= (f.rank_max - f.rank_min)


@given(inputs, directions)
def test_no_best_under_censoring(xs: list[RankInput], hib: bool) -> None:
    by = {x.id: x for x in xs}
    for r in rank_with_uncertainty(xs, higher_is_better=hib):
        if r.rank == 1:
            assert not r.incomparable_with
            assert not any(by[o].unbounded for o in r.tied_with)


@given(inputs)
def test_mirror_symmetry(xs: list[RankInput]) -> None:
    """Larger-is-better on values equals smaller-is-better on negated values.

    Censoring is a direction-bound claim (a lower bound), so it only mirrors
    when absent; the property is stated for uncensored inputs.
    """
    plain = [RankInput(x.id, x.value, x.uncertainty, False) for x in xs]
    neg = [RankInput(x.id, -x.value, x.uncertainty, False) for x in plain]
    assert places(plain, True) == places(neg, False)


@given(inputs, directions)
def test_definite_ranks_are_consistent_with_beats(xs: list[RankInput], hib: bool) -> None:
    ranked = rank_with_uncertainty(xs, higher_is_better=hib)
    by = {x.id: x for x in xs}
    rank_of = {r.id: r for r in ranked}
    for a in xs:
        for b in xs:
            if a is not b and beats(a, b, higher_is_better=hib):
                assert rank_of[a.id].rank_max < rank_of[b.id].rank_max or (
                    rank_of[a.id].rank_min < rank_of[b.id].rank_min
                )
                assert rank_of[a.id].rank_min < rank_of[b.id].rank_min
    assert set(by) == set(rank_of)
