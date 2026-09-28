"""One shape for every number the product shows.

The surface engine carries its margins in a terrain-specific block
(``meta.uncertainty``). The lifecycle sections -- launch weather, the trip,
radiation, relays, entered readiness dates -- have margins of different kinds:

* a symmetric ``±`` (a timing edge, a trajectory dispersion),
* a range ("3.1-7.4 h through the relay, if it flies as planned"),
* a multiplicative factor (a radiation-belt fluence good to a factor of 2),
* a share of model runs with its interval ("12 of 31 runs", 23-56 %).

Invariant 2 still holds for all of them: every number carries its margin *or
says why it cannot*. ``Quantity`` enforces that at construction, so a number
without a margin is a ``ValueError`` in a test rather than a bare figure on a
screen. Invariant 10 (provenance) is enforced the same way: a number is
computed, published, entered or assumed, and an entered number says who
entered it.

Pure: no I/O. ``scipy.stats`` is used only for the share interval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from scipy import stats

Provenance = Literal["computed", "published", "entered", "assumed"]
PROVENANCES: Final[tuple[Provenance, ...]] = ("computed", "published", "entered", "assumed")


@dataclass(frozen=True, slots=True)
class Quantity:
    """A value, its unit, its margin in exactly one form, and where it came from.

    ``value`` may be ``None`` only with ``missing_reason`` ("the lander's radio
    power is not published"). A present value needs exactly one of ``pm``,
    ``lo``/``hi``, ``factor`` -- or a ``no_margin_reason``.
    """

    value: float | None
    unit: str
    provenance: Provenance
    pm: float | None = None
    lo: float | None = None
    hi: float | None = None
    factor: float | None = None
    #: The value is a lower bound: the dates cut the stretch short ("≥").
    open: bool = False
    no_margin_reason: str | None = None
    missing_reason: str | None = None
    #: For ``entered`` numbers: who entered it. For ``published``: the source URL.
    source: str | None = None

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCES:
            raise ValueError(f"unknown provenance {self.provenance!r}")
        if (
            self.value is not None
            and self.provenance in ("entered", "published")
            and not self.source
        ):
            raise ValueError(f"a {self.provenance} number must name its source")
        if self.value is None:
            if not self.missing_reason:
                raise ValueError("a missing value must say why it is missing")
            if any(x is not None for x in (self.pm, self.lo, self.hi, self.factor)):
                raise ValueError("a missing value cannot carry a margin")
            return
        if self.missing_reason:
            raise ValueError("a present value cannot also have a missing_reason")
        forms = [
            self.pm is not None,
            self.lo is not None or self.hi is not None,
            self.factor is not None,
        ]
        if sum(forms) > 1:
            raise ValueError("give the margin in exactly one form: ±, range, or factor")
        if sum(forms) == 0 and not self.no_margin_reason:
            raise ValueError("every number carries its margin or says why it cannot")
        if sum(forms) == 1 and self.no_margin_reason:
            raise ValueError("a number with a margin cannot also say it has none")
        if self.pm is not None and self.pm < 0:
            raise ValueError("± must be non-negative")
        if (self.lo is None) != (self.hi is None):
            raise ValueError("a range needs both ends")
        if self.lo is not None and self.hi is not None:
            if self.lo > self.hi:
                raise ValueError("range reversed")
            if not self.lo <= self.value <= self.hi:
                raise ValueError("value outside its own range")
        if self.factor is not None and self.factor < 1.0:
            raise ValueError("a multiplicative factor is at least 1")

    @property
    def bounds(self) -> tuple[float, float] | None:
        """The interval the margin describes, whatever its form."""
        if self.value is None:
            return None
        if self.pm is not None:
            return (self.value - self.pm, self.value + self.pm)
        if self.lo is not None and self.hi is not None:
            return (self.lo, self.hi)
        if self.factor is not None:
            return (self.value / self.factor, self.value * self.factor)
        return None


def computed(value: float, unit: str, *, pm: float) -> Quantity:
    return Quantity(value=value, unit=unit, provenance="computed", pm=pm)


def missing(unit: str, reason: str, *, provenance: Provenance = "computed") -> Quantity:
    return Quantity(value=None, unit=unit, provenance=provenance, missing_reason=reason)


@dataclass(frozen=True, slots=True)
class Share:
    """``k`` of ``n`` model runs, with an exact 95 % interval.

    Invariant 12: a probability states its sample. The share is never pooled
    across forecast systems and never called "the chance of a scrub"; whether
    it has been checked against observations is carried alongside, not implied.
    """

    k: int
    n: int
    lo: float
    hi: float
    checked: bool

    @property
    def value(self) -> float:
        return self.k / self.n


def share(k: int, n: int, *, checked: bool, confidence: float = 0.95) -> Share:
    """Clopper-Pearson (exact) interval for ``k`` of ``n``.

    Exact rather than Jeffreys on purpose. Jeffreys is shorter on average, but
    its coverage oscillates and falls to ~0.89 for a rare rule at 51 members
    (p = 0.05) -- and a rare rule is exactly what a launch-weather row is. The
    exact interval never covers less than the stated level, so the ± can only
    overstate our uncertainty, never understate it. The coverage is pinned in
    ``test_quantity.py``.
    """
    if n <= 0:
        raise ValueError("a share needs at least one run")
    if not 0 <= k <= n:
        raise ValueError(f"k={k} outside 0..{n}")
    a = (1.0 - confidence) / 2.0
    lo = 0.0 if k == 0 else float(stats.beta.ppf(a, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1.0 - a, k + 1, n - k))
    return Share(k=k, n=n, lo=lo, hi=hi, checked=checked)
