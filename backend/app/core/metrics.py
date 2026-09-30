"""The four numbers, and the compound events underneath them.

Pure. Takes arc lists from ``intervals`` and returns the quantities a mission
is actually decided on:

    1. sunlit seconds in the window          (power)
    2. Earth-contact seconds in the window   (comms)
    3. longest unbroken dark gap             (survival)
    4. longest unbroken comms blackout       (autonomy)

There is deliberately **no composite score**. A score would rank sites on one
axis, which is precisely the information-destroying move this product exists to
avoid: averaging 80 % sunlight with a 300-hour night produces a number that
looks decisive and hides which corner was given up. The project's conventions
states this as an invariant; ``tests/unit/test_metrics.py`` asserts the response
model has no score field, so the rule is executable rather than aspirational.

"Earth contact" here means **geometric line of sight to Earth's centre above
the local skyline**. There is no link budget, no antenna pattern and no DSN
scheduling in this system, so the field is named ``earth_contact_s`` and never
"comms availability".
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Final

from app.core.intervals import Run, contains, intersect, longest, total

#: Compound events shorter than this are not operationally meaningful -- a
#: two-minute overlap between a dark stretch and a blackout does not size a
#: battery. Matches the frontend's 0.25 h threshold in metrics.ts.
MIN_COMPOUND_S: Final[float] = 900.0

#: Margin applied on top of the worst compound event when sizing autonomy.
AUTONOMY_MARGIN: Final[float] = 0.2


@dataclass(frozen=True, slots=True)
class BodyMetrics:
    """Everything derived from one body's arc list."""

    body: str
    arcs: list[Run]
    up_s: float
    down_s: float
    fraction_up: float
    longest_down_s: float
    longest_down_start: float | None
    longest_down_end: float | None
    #: True when at least one crossing was too shallow to time. The number is
    #: still reported; the flag says not to trust its edges.
    grazing: bool = False
    #: True when the longest down arc touches an edge of the window, so the
    #: window -- not the terrain or the orbit -- ended it. The stretch it belongs
    #: to is longer than ``longest_down_s`` by an unknown amount, and the value
    #: is a lower bound. Measured on real data this is not a corner case: a
    #: window that opens mid-night at Malapert reports 167 h for a 322 h night.
    longest_down_open: bool = False


@dataclass(frozen=True, slots=True)
class AutonomyPacket:
    """What the lander has to survive on its own resources.

    Two different budgets, kept apart on purpose:

    * ``required_autonomy_s`` sizes *autonomy*: the longest stretch with no Sun
      and no link at once, plus a margin. Nobody on Earth can help during it.
    * ``survival_needed_s`` sizes the *battery*: the longest night in the
      window, whatever the radio is doing. If the radio is silent for 40 hours
      in the middle of a 230-hour night, the battery still carries 230 hours --
      and if the radio is never silent at all, it still carries 230 hours.

    An earlier version returned the compound event as the survival figure when
    no blackout overlapped a night, which reported 0 h of survival for a site
    with a 288-hour night. Under-sizing the battery is the dangerous direction
    to be wrong in, so survival is now the night itself, always.
    """

    worst_compound_s: float
    required_autonomy_s: float
    survival_needed_s: float
    compound_inside_dark: bool
    #: The night that sizes the battery is cut by a window edge: a lower bound.
    survival_open: bool = False
    #: The worst compound event is cut by a window edge: a lower bound.
    worst_compound_open: bool = False


@dataclass(frozen=True, slots=True)
class SiteMetrics:
    """The four numbers plus the context needed to read them honestly."""

    site_id: str
    window_start_s: float
    window_s: float
    sun: BodyMetrics
    earth: BodyMetrics
    compound: list[Run] = field(default_factory=list)
    worst_compound_s: float = 0.0

    # --- the four numbers, named exactly as the product names them ---------
    @property
    def sunlit_s(self) -> float:
        return self.sun.up_s

    @property
    def earth_contact_s(self) -> float:
        return self.earth.up_s

    @property
    def longest_dark_s(self) -> float:
        return self.sun.longest_down_s

    @property
    def longest_blackout_s(self) -> float:
        return self.earth.longest_down_s

    @property
    def longest_dark_open(self) -> bool:
        return self.sun.longest_down_open

    @property
    def longest_blackout_open(self) -> bool:
        return self.earth.longest_down_open

    @property
    def worst_compound_open(self) -> bool:
        worst = max(self.compound, key=lambda r: r.duration, default=None)
        return worst is not None and touches_edge(worst, self.window_start_s, self.window_end_s)

    @property
    def window_end_s(self) -> float:
        return self.window_start_s + self.window_s


def touches_edge(run: Run, window_start_s: float, window_end_s: float) -> bool:
    """Did the window, rather than the geometry, end this run?

    A run that begins at the first sample or ends at the last one was cut by
    the window: the body was already down (or still is) beyond it, so the
    duration is a lower bound. Half a step of slack absorbs float noise in the
    time axis without ever mistaking a real crossing for the window edge.
    """
    return run.start <= window_start_s + EDGE_SLACK_S or run.end >= window_end_s - EDGE_SLACK_S


#: How close to a window edge a run must be to count as cut by it. Crossings
#: are bisected to far better than a second, so a genuine one never lands this
#: close to the edge unless it really is the edge.
EDGE_SLACK_S: Final[float] = 1e-3


def body_metrics(body: str, arcs: list[Run], *, grazing: bool = False) -> BodyMetrics:
    """Reduce an arc list to one body's metrics."""
    up_s = total(arcs, True)
    down_s = total(arcs, False)
    span = up_s + down_s
    worst = longest(arcs, False)
    is_open = worst is not None and bool(arcs) and touches_edge(worst, arcs[0].start, arcs[-1].end)
    return BodyMetrics(
        body=body,
        arcs=arcs,
        up_s=up_s,
        down_s=down_s,
        fraction_up=(up_s / span) if span > 0 else 0.0,
        longest_down_s=worst.duration if worst is not None else 0.0,
        longest_down_start=worst.start if worst is not None else None,
        longest_down_end=worst.end if worst is not None else None,
        grazing=grazing,
        longest_down_open=is_open,
    )


def compound_events(sun_arcs: list[Run], earth_arcs: list[Run]) -> list[Run]:
    """Stretches with no Sun **and** no link: the autonomy-sizing case."""
    raw = intersect(sun_arcs, earth_arcs, value=False)
    return [r for r in raw if r.duration >= MIN_COMPOUND_S]


def autonomy(metrics: SiteMetrics) -> AutonomyPacket:
    worst_run = max(metrics.compound, key=lambda r: r.duration, default=None)
    worst = worst_run.duration if worst_run is not None else 0.0
    inside = worst_run is not None and contains(metrics.sun.arcs, worst_run, value=False)
    return AutonomyPacket(
        worst_compound_s=worst,
        required_autonomy_s=worst * (1.0 + AUTONOMY_MARGIN),
        survival_needed_s=metrics.longest_dark_s,
        compound_inside_dark=bool(inside),
        survival_open=metrics.longest_dark_open,
        worst_compound_open=metrics.worst_compound_open,
    )


def assemble(
    site_id: str,
    window_start_s: float,
    window_s: float,
    sun_arcs: list[Run],
    earth_arcs: list[Run],
    *,
    sun_grazing: bool = False,
    earth_grazing: bool = False,
) -> SiteMetrics:
    compound = compound_events(sun_arcs, earth_arcs)
    return SiteMetrics(
        site_id=site_id,
        window_start_s=window_start_s,
        window_s=window_s,
        sun=body_metrics("sun", sun_arcs, grazing=sun_grazing),
        earth=body_metrics("earth", earth_arcs, grazing=earth_grazing),
        compound=compound,
        worst_compound_s=max((r.duration for r in compound), default=0.0),
    )


# ---------------------------------------------------------------------------
# Ranking that respects censoring and each site's own uncertainty
# ---------------------------------------------------------------------------

#: The four metric keys, and whether more is better.
METRIC_KEYS: Final[dict[str, bool]] = {
    "sunlit_s": True,
    "earth_contact_s": True,
    "longest_dark_s": False,
    "longest_blackout_s": False,
}

# Ordering raw floats with a fixed one-hour tolerance would be wrong in two ways
# the review measured (D20, D21):
#
# * A longest gap cut by the window edge is a *lower bound*. Ordering 112 h
#   ("at least") ahead of a measured 122 h asserts something the data does not
#   support, because the censored night may be far longer.
# * The tolerance that matters is each site's own arc-edge uncertainty, which
#   ranges from minutes to seventeen hours, not a constant.
#
# So each value becomes an interval, and one site "beats" another only when
# their intervals do not overlap in its favour. That relation is a strict
# partial order, which is why the result is a rank *range*, not a single rank.


@dataclass(frozen=True, slots=True)
class RankInput:
    """One site's value on one metric, with what we know about its error."""

    id: str
    value: float
    #: Half-width of the band the true value lies in, in the metric's units.
    uncertainty: float = 0.0
    #: The value is a lower bound: the true value is ``>= value``.
    censored: bool = False

    @property
    def unbounded(self) -> bool:
        """Censored, or an edge that cannot be timed: its place cannot be pinned."""
        return self.censored or math.isinf(self.uncertainty)

    def interval(self) -> tuple[float, float]:
        if self.censored:
            return self.value, float("inf")
        u = max(0.0, self.uncertainty)
        return self.value - u, self.value + u


@dataclass(frozen=True, slots=True)
class RankedItem:
    """Where one site stands, stated no more precisely than the data allows."""

    id: str
    #: A definite rank, or None when a censored value makes the place unknowable.
    rank: int | None
    rank_min: int
    rank_max: int
    #: Measured sites whose intervals overlap this one: indistinguishable.
    tied_with: tuple[str, ...]
    #: Sites this one cannot be ordered against because a censored value is involved.
    incomparable_with: tuple[str, ...]
    censored: bool


def beats(a: RankInput, b: RankInput, *, higher_is_better: bool) -> bool:
    """True when ``a`` is better than ``b`` whatever the true values are."""
    a_lo, a_hi = a.interval()
    b_lo, b_hi = b.interval()
    return a_lo > b_hi if higher_is_better else a_hi < b_lo


def rank_with_uncertainty(items: list[RankInput], *, higher_is_better: bool) -> list[RankedItem]:
    """Rank sites on one metric without claiming more than the data supports.

    For each site: ``rank_min = 1 + |sites that beat it|`` and
    ``rank_max = n - |sites it beats|``. If every pair it cannot order is a tie
    between two *measured* values, it gets the definite rank ``rank_min``,
    shared with the sites it ties (competition ranking: 1, 1, 3). If any pair
    it cannot order involves a censored value, ``rank`` is None and the range
    is what can be said.

    The output is in display order: best value first, a stable sort, so equal
    inputs keep their request order. A censored value sorts by its known lower
    bound, which is the most it can be credited with.
    """
    n = len(items)
    beat_by: dict[str, int] = {it.id: 0 for it in items}
    beats_n: dict[str, int] = {it.id: 0 for it in items}
    tied: dict[str, list[str]] = {it.id: [] for it in items}
    incomparable: dict[str, list[str]] = {it.id: [] for it in items}
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            if beats(a, b, higher_is_better=higher_is_better):
                beats_n[a.id] += 1
                beat_by[b.id] += 1
            elif beats(b, a, higher_is_better=higher_is_better):
                beats_n[b.id] += 1
                beat_by[a.id] += 1
            elif a.unbounded or b.unbounded:
                incomparable[a.id].append(b.id)
                incomparable[b.id].append(a.id)
            else:
                tied[a.id].append(b.id)
                tied[b.id].append(a.id)

    ordered = sorted(items, key=lambda it: it.value, reverse=higher_is_better)
    out: list[RankedItem] = []
    for it in ordered:
        lo = 1 + beat_by[it.id]
        hi = n - beats_n[it.id]
        definite = not incomparable[it.id]
        out.append(
            RankedItem(
                id=it.id,
                rank=lo if definite else None,
                rank_min=lo,
                rank_max=hi,
                tied_with=tuple(tied[it.id]),
                incomparable_with=tuple(incomparable[it.id]),
                censored=it.censored,
            )
        )
    return out


def tie_groups(ranked: list[RankedItem]) -> list[list[str]]:
    """Connected groups of the tie relation, in display order.

    Overlap is not transitive, so a group can hold two sites that do not
    overlap each other directly but share a neighbour. The group says "the data
    cannot separate this cluster", which is the claim the UI draws.
    """
    position = {r.id: i for i, r in enumerate(ranked)}
    neighbours = {r.id: set(r.tied_with) for r in ranked}
    seen: set[str] = set()
    groups: list[list[str]] = []
    for r in ranked:
        if r.id in seen or not neighbours[r.id]:
            continue
        stack, group = [r.id], []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            group.append(x)
            stack.extend(neighbours[x] - seen)
        groups.append(sorted(group, key=position.__getitem__))
    return groups


# ---------------------------------------------------------------------------
# Calendar buckets (contract v2, docs/system-design.md 10.6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BucketStat:
    """One body's numbers inside one calendar bucket ``[start, end)``."""

    start: float
    end: float
    up_s: float
    fraction_up: float
    longest_down_s: float
    #: The longest down stretch in this bucket was cut by the bucket's edge or
    #: the window's, so it is a lower bound: the same rule as a window edge.
    longest_down_open: bool


def bucket_stats(arcs: list[Run], edges: list[float]) -> list[BucketStat]:
    """Split a body's arcs into consecutive buckets.

    ``edges`` are the bucket boundaries in the arcs' time base, strictly
    increasing, spanning the window. A down run that crosses a boundary is
    clipped, and each clipped piece is reported as open: the calendar, not the
    geometry, ended it there.
    """
    out: list[BucketStat] = []
    for b0, b1 in itertools.pairwise(edges):
        span = b1 - b0
        up = 0.0
        longest = 0.0
        longest_open = False
        for r in arcs:
            s, e = max(r.start, b0), min(r.end, b1)
            if e <= s:
                continue
            if r.value:
                up += e - s
                continue
            length = e - s
            # Touching either edge of the bucket means a boundary ended it (the
            # first and last buckets' outer edges are the window's own).
            clipped = s <= b0 + EDGE_SLACK_S or e >= b1 - EDGE_SLACK_S
            if length > longest:
                longest, longest_open = length, clipped
        out.append(
            BucketStat(
                start=b0,
                end=b1,
                up_s=up,
                fraction_up=up / span if span > 0 else 0.0,
                longest_down_s=longest,
                longest_down_open=longest_open,
            )
        )
    return out
