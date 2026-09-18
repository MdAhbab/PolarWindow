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


@dataclass(frozen=True, slots=True)
class AutonomyPacket:
    """What the lander has to survive on its own resources.

    ``survival_needed_s`` is deliberately *not* the worst compound event when
    that event falls inside a longer night: if the radio is silent for 40 hours
    in the middle of a 230-hour night, the battery still has to carry the whole
    230 hours. Conflating the two under-sizes the battery, which is the
    dangerous direction to be wrong in.
    """

    worst_compound_s: float
    required_autonomy_s: float
    survival_needed_s: float
    compound_inside_dark: bool


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


def body_metrics(body: str, arcs: list[Run], *, grazing: bool = False) -> BodyMetrics:
    """Reduce an arc list to one body's metrics."""
    up_s = total(arcs, True)
    down_s = total(arcs, False)
    span = up_s + down_s
    worst = longest(arcs, False)
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
        survival_needed_s=metrics.longest_dark_s if inside else worst,
        compound_inside_dark=bool(inside),
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


def rank(
    entries: list[SiteMetrics], key: str, *, tie_tolerance_s: float = TIE_TOLERANCE_S
) -> tuple[list[SiteMetrics], list[list[str]]]:
    """Order sites by one metric, and report which ones are indistinguishable.

    Returns ``(ordered, tie_groups)``. Ties are surfaced rather than broken
    arbitrarily: with a 20 m DEM and a mean lunar ephemeris, ranking two sites
    that differ by twenty minutes over a month is inventing a distinction the
    data does not support.
    """
    higher_is_better = METRIC_KEYS[key]
    ordered = sorted(entries, key=lambda m: metric_value(m, key), reverse=higher_is_better)
    ties: list[list[str]] = []
    current: list[SiteMetrics] = []
    for m in ordered:
        if (
            current
            and abs(metric_value(m, key) - metric_value(current[-1], key)) <= tie_tolerance_s
        ):
            current.append(m)
        else:
            if len(current) > 1:
                ties.append([x.site_id for x in current])
            current = [m]
    if len(current) > 1:
        ties.append([x.site_id for x in current])
    return ordered, ties
