"""`core.quantity`: invariant 2 (margin or reason) and 10 (provenance) at construction."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.quantity import Quantity, computed, missing, share


def test_a_number_without_a_margin_is_refused() -> None:
    with pytest.raises(ValueError, match="margin or says why"):
        Quantity(value=3.0, unit="h", provenance="computed")


def test_a_number_may_say_why_it_has_no_margin() -> None:
    q = Quantity(value=3.0, unit="h", provenance="computed", no_margin_reason="grazing")
    assert q.bounds is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pm": 1.0, "factor": 2.0},
        {"pm": 1.0, "lo": 2.0, "hi": 4.0},
        {"lo": 2.0, "hi": 4.0, "factor": 2.0},
    ],
)
def test_only_one_margin_form(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="exactly one form"):
        Quantity(value=3.0, unit="h", provenance="computed", **kwargs)  # type: ignore[arg-type]


def test_range_must_contain_the_value() -> None:
    with pytest.raises(ValueError, match="outside"):
        Quantity(value=5.0, unit="h", provenance="computed", lo=1.0, hi=4.0)


def test_factor_bounds() -> None:
    q = Quantity(value=10.0, unit="rad", provenance="computed", factor=2.0)
    assert q.bounds == (5.0, 20.0)
    with pytest.raises(ValueError):
        Quantity(value=10.0, unit="rad", provenance="computed", factor=0.5)


def test_entered_and_published_numbers_name_their_source() -> None:
    with pytest.raises(ValueError, match="source"):
        Quantity(value=1.0, unit="%", provenance="entered", pm=0.0)
    Quantity(value=1.0, unit="%", provenance="entered", pm=0.0, source="A. Planner")


def test_missing_value_needs_a_reason_and_no_margin() -> None:
    q = missing("dB", "the lander's radio power is not published")
    assert q.value is None and q.bounds is None
    with pytest.raises(ValueError):
        Quantity(value=None, unit="dB", provenance="computed")
    with pytest.raises(ValueError):
        Quantity(value=None, unit="dB", provenance="computed", missing_reason="x", pm=1.0)


def test_symmetric_bounds() -> None:
    assert computed(10.0, "h", pm=0.5).bounds == (9.5, 10.5)


@given(st.integers(1, 200).flatmap(lambda n: st.tuples(st.integers(0, n), st.just(n))))
def test_interval_contains_the_share(kn: tuple[int, int]) -> None:
    k, n = kn
    s = share(k, n, checked=False)
    assert 0.0 <= s.lo <= s.value <= s.hi <= 1.0
    if k == 0:
        assert s.lo == 0.0
    if k == n:
        assert s.hi == 1.0


@pytest.mark.parametrize("p", [0.01, 0.05, 0.1, 0.3, 0.5, 0.9])
@pytest.mark.parametrize("n", [31, 40, 51])
def test_coverage_never_falls_below_nominal(p: float, n: int) -> None:
    """Exact coverage under Binomial(n, p) for the ensemble sizes we use (GEFS, ICON-EPS, ECMWF)."""
    from scipy import stats

    coverage = sum(
        stats.binom.pmf(k, n, p)
        for k in range(n + 1)
        if (s := share(k, n, checked=False)).lo <= p <= s.hi
    )
    assert coverage >= 0.95 - 1e-9
