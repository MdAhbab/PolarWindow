"""When a ground station can hear a lander (T1, F1). Pure.

A station hears the lander when two things hold at once:

1. Earth is above the lander's skyline (the existing *time in contact with
   Earth*, from the terrain), and
2. the lander is above the station's own horizon mask (DSN 810-005 module
   301: the lowest elevation the antenna can track, per degree of azimuth).

Both come in as runs on one time axis; the answer is their intersection, and
the union over stations is *time a ground station can hear the lander*.
Crossings of the station mask are placed by linear interpolation of the
elevation margin between samples, exact for a margin linear across a step.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from app.core import intervals
from app.core.intervals import Run

FloatArray = npt.NDArray[np.float64]


def mask_elevation(mask_az: FloatArray, mask_el: FloatArray, az_deg: FloatArray) -> FloatArray:
    """The mask's elevation at each azimuth: linear, wrapping at 360."""
    order = np.argsort(mask_az)
    a = np.asarray(mask_az, dtype=np.float64)[order]
    e = np.asarray(mask_el, dtype=np.float64)[order]
    a = np.concatenate([a, [a[0] + 360.0]])
    e = np.concatenate([e, [e[0]]])
    return np.asarray(np.interp(np.mod(az_deg, 360.0), a, e), dtype=np.float64)


def station_runs(
    t_s: FloatArray,
    az_deg: FloatArray,
    el_deg: FloatArray,
    mask_az: FloatArray,
    mask_el: FloatArray,
) -> list[Run]:
    """Runs of "the point is above this station's mask"."""
    margin = el_deg - mask_elevation(mask_az, mask_el, az_deg)
    return intervals.runs_from_margin(np.asarray(t_s, dtype=np.float64), margin)


@dataclass(frozen=True, slots=True)
class Stretches:
    """A partition's true stretches, with whether each touches the window edge."""

    runs: list[Run]
    t0: float
    t1: float

    @property
    def total_s(self) -> float:
        return intervals.total(self.runs, True)

    def longest(self, value: bool) -> tuple[float, bool]:
        r = intervals.longest(self.runs, value)
        if r is None:
            return 0.0, False
        return r.duration, (
            r.start <= self.t0 + intervals.EPS_S or r.end >= self.t1 - intervals.EPS_S
        )


def heard(earth_up: list[Run], stations: dict[str, list[Run]]) -> dict[str, list[Run]]:
    """Per station: Earth up at the lander AND the lander above the station mask."""
    return {k: intervals.both(earth_up, v) for k, v in stations.items()}


def any_station(per_station: dict[str, list[Run]]) -> list[Run]:
    return intervals.any_of(list(per_station.values()))


def edge_tolerance_s(heard_runs: list[Run], earth_edges: list[tuple[float, float]]) -> float:
    """Quadrature sum of the terrain timing tolerance of every heard edge set by Earth.

    ``earth_edges`` is ``(time, tolerance_s)`` for each Earth rise or set at
    the lander. An edge of a heard stretch that coincides with one of them
    carries that tolerance; an edge set by a station mask carries none here
    (810-005 publishes masks without a tolerance), which the answer says.
    """
    tol2 = 0.0
    times = np.array([e[0] for e in earth_edges]) if earth_edges else np.array([])
    tols = np.array([e[1] for e in earth_edges]) if earth_edges else np.array([])
    for r in heard_runs:
        if not r.value:
            continue
        for t in (r.start, r.end):
            if times.size:
                i = int(np.argmin(np.abs(times - t)))
                if abs(times[i] - t) < 1.0:
                    tol2 += float(tols[i]) ** 2
    return float(np.sqrt(tol2))
