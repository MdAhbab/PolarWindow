"""When a lander may touch down at a spot (T2, D2). Pure.

A landing time is allowed when

* L1: the Sun's centre is above the skyline, inside the Sun-height band the
  project entered (when it did) and rising, so the landing is followed by
  the rest of the morning rather than the evening;
* L2: the Sun then stays up for at least the planned days on the surface
  (when they are known);
* L3: the Earth is above the skyline, so the landing can be watched.

L4, the lunar orbit's plane passing over the spot at the right time, is not
applied: an orbiter in a polar orbit passes over any spot twice a day, and
near the poles the lighting decides; the answer says so.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from app.core import intervals
from app.core.intervals import Run

FloatArray = npt.NDArray[np.float64]

#: An allowed stretch shorter than this is dropped: too short to plan a landing into,
#: and usually a glint through a notch in the skyline.
MIN_WINDOW_S = 3600.0


@dataclass(frozen=True, slots=True)
class Rule:
    sun_min_deg: float | None
    sun_max_deg: float | None
    surface_days: float | None
    rising: bool = True
    earth_required: bool = True


def sun_margin(
    t_s: FloatArray, el_deg: FloatArray, skyline_margin_deg: FloatArray, rule: Rule
) -> FloatArray:
    """One margin, positive where L1 holds: the smallest of the parts, in degrees
    (the rise rate in degrees per hour, so a crossing is placed by the part that crosses)."""
    parts = [np.asarray(skyline_margin_deg, dtype=np.float64)]
    if rule.sun_min_deg is not None:
        parts.append(el_deg - rule.sun_min_deg)
    if rule.sun_max_deg is not None:
        parts.append(rule.sun_max_deg - el_deg)
    if rule.rising and t_s.size > 1:
        parts.append(np.gradient(el_deg, t_s) * 3600.0)
    return np.asarray(np.min(np.vstack(parts), axis=0), dtype=np.float64)


def lit_long_enough(sun_up: list[Run], days: float, t0: float, t1: float) -> list[Run]:
    """A partition of ``[t0, t1]``: True where the Sun stays up at least ``days`` more.

    A lit stretch that runs to the end of the dates is kept whole: whether it
    lasts long enough is not known from these dates.
    """
    keep: list[Run] = []
    need = days * 86_400.0
    for r in sun_up:
        if not r.value:
            continue
        end = r.end if r.end >= t1 - intervals.EPS_S else r.end - need
        if end > r.start:
            keep.append(Run(True, r.start, end))
    return intervals.from_runs_of(keep, t0, t1, value=True)


def windows(
    t_s: FloatArray,
    sun_el_deg: FloatArray,
    sun_skyline_margin_deg: FloatArray,
    sun_up: list[Run],
    earth_up: list[Run],
    rule: Rule,
) -> list[Run]:
    """Allowed landing stretches (L1 and L2 and L3) as a partition of the sampled span."""
    t0, t1 = float(t_s[0]), float(t_s[-1])
    ok = intervals.runs_from_margin(t_s, sun_margin(t_s, sun_el_deg, sun_skyline_margin_deg, rule))
    if rule.earth_required:
        ok = intervals.both(ok, earth_up)
    if rule.surface_days is not None:
        ok = intervals.both(ok, lit_long_enough(sun_up, rule.surface_days, t0, t1))
    return intervals.merge_short_gaps(ok, False, MIN_WINDOW_S)


def sunlight_after(t: float, sun_up: list[Run], t1: float) -> tuple[float, bool]:
    """Seconds of sunlight left from ``t`` in the lit stretch holding it, and whether the
    dates cut that stretch short (an at-least number)."""
    for r in sun_up:
        if r.value and r.start - intervals.EPS_S <= t < r.end:
            return r.end - t, r.end >= t1 - intervals.EPS_S
    return 0.0, False


def value_at(t_s: FloatArray, values: FloatArray, t: float) -> float:
    return float(np.interp(t, t_s, values))


def inside(runs: list[Run], t: float) -> bool:
    return any(r.value and r.start - intervals.EPS_S <= t <= r.end + intervals.EPS_S for r in runs)
