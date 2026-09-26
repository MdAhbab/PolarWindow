"""Boolean/margin series -> runs, gaps, longest run.

This module deliberately knows **nothing about astronomy**. It takes a time
array and a margin array and returns runs. It does not know what "dark" means,
it does not know what a horizon is, and it has never heard of the Sun.

That ignorance is the point. Off-by-one errors in longest-run detection are the
most likely silent bug in this whole project -- they produce a plausible number,
not an exception -- and they are only cheaply falsifiable if the module under
test accepts *arbitrary* inputs rather than plausible-looking sun tracks. Because
this file is pure and domain-free, ``hypothesis`` can quantify over every
boolean array up to length 400 and check the partition, alternation,
contiguity, inversion and concatenation properties that pin the behaviour.

Conventions, chosen once and held everywhere
--------------------------------------------
* A run is a **half-open** interval ``[start, end)``. Half-open is what makes
  the partition property exact: adjacent runs share an endpoint and nothing is
  double-counted. Closed intervals force an epsilon somewhere, and that epsilon
  is where off-by-ones live.
* ``runs`` always covers exactly ``[t[0], t[-1]]``. No time is lost.
* State is determined at the *sample*, and transitions are placed at the
  interpolated (or bisected) crossing between samples -- not at a sample
  boundary. Snapping crossings to samples would quantise every arc edge to the
  step size, which would make the 900 s step visible in the output and the
  bisection pointless.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

#: Runs shorter than this are numerical dust from a tangential crossing, not
#: events. 1e-6 s over a 708 h window is ~4e-13 relative -- far below any
#: physical meaning, and above float64 noise on the time axis.
EPS_S: Final[float] = 1e-6


@dataclass(frozen=True, slots=True)
class Run:
    """A maximal half-open stretch ``[start, end)`` during which ``value`` held."""

    value: bool
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def _crossing(t0: float, t1: float, m0: float, m1: float) -> float:
    """Linearly interpolate the instant a margin crosses zero between two samples.

    The caller may refine this by bisection against the true function; linear
    interpolation is the bracket, and it is exact when the margin is locally
    linear, which over a 900 s step it very nearly is.
    """
    denom = m1 - m0
    if denom == 0.0:
        return t0
    frac = -m0 / denom
    # Guard against a crossing placed outside its own bracket by float error.
    frac = min(max(frac, 0.0), 1.0)
    return t0 + frac * (t1 - t0)


def runs_from_margin(
    t: FloatArray,
    margin: FloatArray,
    *,
    refine: Callable[[float, float], float] | None = None,
) -> list[Run]:
    """Split a margin series into alternating runs of ``margin > 0`` and ``<= 0``.

    Parameters
    ----------
    t:
        Strictly increasing time array, length n >= 1.
    margin:
        Same length. ``> 0`` means "up"/visible.
    refine:
        Optional ``(lo, hi) -> t`` that bisects the true crossing inside the
        bracket. When absent, the linear interpolation is used directly.

    Notes
    -----
    A margin of exactly 0.0 counts as **not** up. Choosing the tie consistently
    matters more than which way it goes: an inconsistent tie makes the inversion
    property (``runs(~a)`` mirrors ``runs(a)``) fail, and that failure is the
    signature of a whole family of boundary bugs.
    """
    if t.shape != margin.shape:
        raise ValueError(f"t and margin must match: {t.shape} vs {margin.shape}")
    n = t.shape[0]
    if n == 0:
        return []
    if n == 1:
        return [Run(value=bool(margin[0] > 0.0), start=float(t[0]), end=float(t[0]))]

    up = margin > 0.0
    out: list[Run] = []
    cursor = float(t[0])
    current = bool(up[0])

    # np.flatnonzero over the diff is O(n) and avoids a Python loop over 2,835
    # samples per body per request.
    changes = np.flatnonzero(up[1:] != up[:-1])
    for i in changes:
        lo, hi = float(t[i]), float(t[i + 1])
        cross = _crossing(lo, hi, float(margin[i]), float(margin[i + 1]))
        if refine is not None:
            cross = refine(lo, hi)
            cross = min(max(cross, lo), hi)
        if cross - cursor > EPS_S:
            out.append(Run(value=current, start=cursor, end=cross))
            cursor = cross
        current = bool(up[i + 1])

    end = float(t[-1])
    if end - cursor > EPS_S or not out:
        out.append(Run(value=current, start=cursor, end=end))
    else:
        # The final crossing landed within EPS of the window end. Extend the
        # last run rather than emitting a zero-length one, so the partition
        # property holds exactly.
        last = out[-1]
        out[-1] = Run(value=last.value, start=last.start, end=end)
    return _coalesce(out)


def _coalesce(runs: list[Run]) -> list[Run]:
    """Merge adjacent runs that share a value.

    Dropping a sub-EPS run is not enough on its own. When two refined crossings
    land on the same instant -- a body touching the skyline at exactly one
    sample, where bisection returns the bracket endpoint on both sides -- the
    dust run between them is discarded and its neighbours, which have the *same*
    value, are left side by side. One night then reads as two, and the longest
    dark gap comes out as the larger half. That is a plausible number rather
    than an error, which is the worst way for this module to be wrong.
    """
    if len(runs) < 2:
        return runs
    out: list[Run] = [runs[0]]
    for r in runs[1:]:
        prev = out[-1]
        if r.value == prev.value:
            out[-1] = Run(value=prev.value, start=prev.start, end=r.end)
        else:
            out.append(r)
    return out


def runs_from_bool(t: FloatArray, value: BoolArray) -> list[Run]:
    """Runs from a plain boolean series; transitions placed at the midpoint.

    Used where there is no continuous margin to interpolate (the three-state
    penumbra series, for instance). Midpoint rather than either endpoint keeps
    the inversion property intact.
    """
    margin = np.where(value, 1.0, -1.0).astype(np.float64)
    return runs_from_margin(t, margin)


def total(runs: list[Run], value: bool) -> float:
    """Total time spent in ``value``."""
    return float(sum(r.duration for r in runs if r.value == value))


def longest(runs: list[Run], value: bool) -> Run | None:
    """The single longest run of ``value``, or ``None`` if there is none.

    Returns the **run**, not the duration, because every caller also wants to
    know *when* it was -- and a function that returns only the number invites a
    second pass to find it, which is a second chance to pick the wrong one.
    """
    best: Run | None = None
    for r in runs:
        if r.value == value and (best is None or r.duration > best.duration):
            best = r
    return best


def longest_duration(runs: list[Run], value: bool) -> float:
    r = longest(runs, value)
    return r.duration if r is not None else 0.0


def fraction(runs: list[Run], value: bool) -> float:
    """Fraction of the covered span spent in ``value``."""
    span = covered_span(runs)
    return total(runs, value) / span if span > 0 else 0.0


def covered_span(runs: list[Run]) -> float:
    if not runs:
        return 0.0
    return runs[-1].end - runs[0].start


def merge_short_gaps(runs: list[Run], value: bool, min_gap_s: float) -> list[Run]:
    """Absorb runs of ``not value`` shorter than ``min_gap_s``.

    Physically: a two-minute glint of sunlight through a notch in a ridge does
    not end the night, and reporting it as two nights understates the longest
    dark gap -- which is one of the four numbers a mission is decided on.

    Idempotent, and ``longest_duration`` is non-decreasing in ``min_gap_s``.
    Both are property-tested.
    """
    if not runs:
        return []
    merged: list[Run] = [runs[0]]
    for r in runs[1:]:
        prev = merged[-1]
        is_short_interruption = r.value != value and r.duration < min_gap_s and prev.value == value
        if is_short_interruption:
            merged[-1] = Run(value=value, start=prev.start, end=r.end)
        elif r.value == prev.value:
            merged[-1] = Run(value=prev.value, start=prev.start, end=r.end)
        else:
            merged.append(r)
    # A merge can leave two same-valued runs adjacent; coalesce once more.
    return _coalesce(merged)


def intersect(a: list[Run], b: list[Run], *, value: bool = False) -> list[Run]:
    """Stretches where ``a`` and ``b`` are both ``value``.

    This is the compound event: no Sun **and** no link at the same time, which
    is what the autonomy packet is sized from. Implemented as a linear merge of
    two sorted lists rather than the O(n*m) double loop, because the arc counts
    can reach a few hundred each over a long window.
    """
    sel_a = [r for r in a if r.value == value]
    sel_b = [r for r in b if r.value == value]
    out: list[Run] = []
    i = j = 0
    while i < len(sel_a) and j < len(sel_b):
        lo = max(sel_a[i].start, sel_b[j].start)
        hi = min(sel_a[i].end, sel_b[j].end)
        if hi - lo > EPS_S:
            out.append(Run(value=value, start=lo, end=hi))
        if sel_a[i].end < sel_b[j].end:
            i += 1
        else:
            j += 1
    return out


def complement(runs: list[Run]) -> list[Run]:
    """The same partition with every value flipped.

    "Time without contact" is the complement of "time in contact"; keeping the
    flip here, rather than as ``not r.value`` scattered through callers, means
    the partition property carries over untouched.
    """
    return [Run(value=not r.value, start=r.start, end=r.end) for r in runs]


def clip(runs: list[Run], lo: float, hi: float) -> list[Run]:
    """Restrict a partition to ``[lo, hi]``.

    Runs that straddle an edge are cut at it; runs wholly outside are dropped.
    The result is still a partition of ``[max(lo, first start), min(hi, last
    end)]``, so ``covered_span`` and ``total`` stay exact after clipping.
    """
    if hi < lo:
        raise ValueError(f"clip bounds reversed: {lo} > {hi}")
    out: list[Run] = []
    for r in runs:
        s = max(r.start, lo)
        e = min(r.end, hi)
        if e - s > EPS_S:
            out.append(Run(value=r.value, start=s, end=e))
    return _coalesce(out)


def from_runs_of(value_runs: list[Run], start: float, end: float, *, value: bool) -> list[Run]:
    """A full partition of ``[start, end]`` from runs that all hold ``value``.

    ``intersect`` returns only the stretches where both inputs hold a value;
    the four-number machinery (``metrics.body_metrics``) wants the whole
    alternating partition. This fills the gaps with ``not value``.
    """
    if end < start:
        raise ValueError(f"span reversed: {start} > {end}")
    out: list[Run] = []
    cursor = start
    for r in sorted(value_runs, key=lambda x: x.start):
        if r.value != value:
            raise ValueError("from_runs_of expects runs that all hold `value`")
        s = max(r.start, cursor)
        e = min(r.end, end)
        if e - s <= EPS_S:
            continue
        if s - cursor > EPS_S:
            out.append(Run(value=not value, start=cursor, end=s))
        out.append(Run(value=value, start=s, end=e))
        cursor = e
    if end - cursor > EPS_S or not out:
        out.append(Run(value=not value, start=cursor, end=end))
    return _coalesce(out)


def combine(a: list[Run], b: list[Run], op: Callable[[bool, bool], bool]) -> list[Run]:
    """Pointwise ``op`` of two partitions, over the span both cover.

    Boundaries are the union of both inputs' boundaries; between consecutive
    boundaries each input holds one value, so ``op`` is evaluated once per
    piece. Linear in the total run count. ``union`` and ``both`` are the two
    uses: "in contact directly *or* through a relay" and "the station hears
    the site *and* the Moon is above its mask".
    """
    if not a or not b:
        return []
    lo = max(a[0].start, b[0].start)
    hi = min(a[-1].end, b[-1].end)
    if hi - lo <= EPS_S:
        return []
    ca, cb = clip(a, lo, hi), clip(b, lo, hi)
    edges = sorted({lo, hi, *(r.end for r in ca), *(r.end for r in cb)})
    out: list[Run] = []
    i = j = 0
    for s, e in itertools.pairwise(edges):
        if e - s <= EPS_S:
            continue
        mid = 0.5 * (s + e)
        while i < len(ca) - 1 and ca[i].end <= mid:
            i += 1
        while j < len(cb) - 1 and cb[j].end <= mid:
            j += 1
        out.append(Run(value=bool(op(ca[i].value, cb[j].value)), start=s, end=e))
    return _coalesce(out)


def union(a: list[Run], b: list[Run]) -> list[Run]:
    """True wherever either partition is true."""
    return combine(a, b, lambda x, y: x or y)


def both(a: list[Run], b: list[Run]) -> list[Run]:
    """True wherever both partitions are true (a full partition, unlike ``intersect``)."""
    return combine(a, b, lambda x, y: x and y)


def any_of(parts: list[list[Run]]) -> list[Run]:
    """``union`` over any number of partitions; empty in, empty out."""
    if not parts:
        return []
    acc = parts[0]
    for p in parts[1:]:
        acc = union(acc, p)
    return acc


def contains(outer: list[Run], inner: Run, *, value: bool) -> bool:
    """Is ``inner`` wholly inside some run of ``outer`` with ``value``?"""
    return any(
        r.value == value and r.start - EPS_S <= inner.start and inner.end <= r.end + EPS_S
        for r in outer
    )


def bisect_crossing(
    f: Callable[[float], float], lo: float, hi: float, *, iterations: int = 40
) -> float:
    """Bisect ``f`` for a sign change in ``[lo, hi]``.

    40 iterations over a 900 s bracket converges to ~1e-9 s, which is far past
    what the inputs justify -- but bisection is cheap here (each step is one
    vector dot product) and stopping early for tidiness would be a false economy.

    If the bracket does not actually contain a sign change -- which happens when
    a body grazes the skyline and the margin touches zero without crossing --
    the midpoint is returned. The caller decides what to do about it; this
    function does not have the context to call it a graze.
    """
    f_lo = f(lo)
    f_hi = f(hi)
    if f_lo == 0.0:
        return lo
    if f_hi == 0.0:
        return hi
    if (f_lo > 0.0) == (f_hi > 0.0):
        return 0.5 * (lo + hi)
    a, b = lo, hi
    for _ in range(iterations):
        mid = 0.5 * (a + b)
        f_mid = f(mid)
        if f_mid == 0.0:
            return mid
        if (f_lo > 0.0) == (f_mid > 0.0):
            a = mid
        else:
            b = mid
    return 0.5 * (a + b)
