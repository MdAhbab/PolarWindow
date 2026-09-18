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
looks decisive and hides which corner was given up. The frontend's CLAUDE.md
states this as an invariant; ``tests/unit/test_metrics.py`` asserts the response
model has no score field, so the rule is executable rather than aspirational.

"Earth contact" here means **geometric line of sight to Earth's centre above
the local skyline**. There is no link budget, no antenna pattern and no DSN
scheduling in this system, so the field is named ``earth_contact_s`` and never
"comms availability".
"""

from __future__ import annotations

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
# Ranking
# ---------------------------------------------------------------------------

#: The four metric keys, and whether more is better.
METRIC_KEYS: Final[dict[str, bool]] = {
    "sunlit_s": True,
    "earth_contact_s": True,
    "longest_dark_s": False,
    "longest_blackout_s": False,
}

#: Two sites whose metric differs by less than this are tied, not ordered.
#: One hour, because the inputs do not support finer discrimination between
#: sites and presenting a 12-minute difference as a ranking is a false claim.
TIE_TOLERANCE_S: Final[float] = 3600.0


def metric_value(m: SiteMetrics, key: str) -> float:
    if key not in METRIC_KEYS:
        raise KeyError(f"unknown metric: {key!r}. Known: {sorted(METRIC_KEYS)}")
    return float(getattr(m, key))


@dataclass(frozen=True, slots=True)
class Ranking:
    """An ordering that admits what it cannot distinguish.

    ``order`` is a strict order, because a list has to be drawn in *some*
    sequence. ``ranks`` is competition ranking over that order -- tied sites
    share the rank of the group's leader, and the next rank skips accordingly
    (1, 1, 3) -- because printing "1" and "2" for two sites the data cannot tell
    apart asserts a difference that is not there.
    """

    order: list[str]
    ranks: dict[str, int]
    ties: list[list[str]]


def rank_values(
    values: list[tuple[str, float]],
    *,
    higher_is_better: bool,
    tie_tolerance_s: float = TIE_TOLERANCE_S,
) -> Ranking:
    """Rank ``(id, value)`` pairs on one metric, reporting ties.

    A tie group is anchored on its leader: every member lies within
    ``tie_tolerance_s`` of the best value in the group. Chaining neighbours
    instead (A~B, B~C, therefore A~C) would call two sites 1.8 h apart "tied"
    under a one-hour tolerance, which is not what the word promises.

    The sort is stable, so equal inputs keep their request order and the
    result is deterministic.
    """
    ordered = sorted(values, key=lambda p: p[1], reverse=higher_is_better)
    ranks: dict[str, int] = {}
    ties: list[list[str]] = []
    group: list[str] = []
    leader_value = 0.0
    leader_rank = 0
    for position, (sid, v) in enumerate(ordered, start=1):
        if group and abs(v - leader_value) <= tie_tolerance_s:
            group.append(sid)
        else:
            if len(group) > 1:
                ties.append(group)
            group = [sid]
            leader_value = v
            leader_rank = position
        ranks[sid] = leader_rank
    if len(group) > 1:
        ties.append(group)
    return Ranking(order=[sid for sid, _ in ordered], ranks=ranks, ties=ties)


def rank(
    entries: list[SiteMetrics], key: str, *, tie_tolerance_s: float = TIE_TOLERANCE_S
) -> tuple[list[SiteMetrics], list[list[str]]]:
    """Order sites by one metric, and report which ones are indistinguishable.

    Returns ``(ordered, tie_groups)``. Ties are surfaced rather than broken
    arbitrarily: with a 20 m DEM and a mean lunar ephemeris, ranking two sites
    that differ by twenty minutes over a month is inventing a distinction the
    data does not support.
    """
    by_id = {m.site_id: m for m in entries}
    r = rank_values(
        [(m.site_id, metric_value(m, key)) for m in entries],
        higher_is_better=METRIC_KEYS[key],
        tie_tolerance_s=tie_tolerance_s,
    )
    return [by_id[sid] for sid in r.order], r.ties
