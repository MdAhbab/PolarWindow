"""Compose ephemeris + mask into timelines, windows and metrics.

Services hold policy and never import ``fastapi`` -- which is what lets the
precompute worker and the agent tool layer call exactly the same functions the
HTTP routes do, so the three can never disagree about a number.

Quantisation happens here, at the top of every entry point, because it is the
mechanism ADR-1 and system-design section 6 depend on: a slider drag emits
starts 41 seconds apart, and without snapping them to the step grid the cache
hit rate on the product's primary interaction is zero.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import numpy as np

from app.config import ENGINE_VERSION, get_settings
from app.core import metrics as core_metrics
from app.core import spice, timeline, visibility
from app.core.horizon import HorizonMask
from app.core.spice import R_EARTH_M, R_MOON_M, R_SUN_M

#: Mean Sun and Earth distances from the Moon, metres. Used only to state the
#: nominal disc radius in responses that describe a *set* of sites or a stored
#: mask, where no window -- and so no actual distance -- is involved.
MEAN_SUN_DISTANCE_M: Final[float] = 1.495_978_707e11
MEAN_EARTH_DISTANCE_M: Final[float] = 3.844e8


def nominal_penumbra_deg() -> tuple[float, float]:
    """Apparent angular radius of the Sun and Earth at their mean distances.

    Derived, not typed in: the `/sites` envelope used to carry 0.266 and 0.95
    as literals, which is exactly the "number nobody computed" the API promises
    never to return.
    """
    sun = float(np.degrees(np.arcsin(R_SUN_M / MEAN_SUN_DISTANCE_M)))
    earth = float(np.degrees(np.arcsin(R_EARTH_M / MEAN_EARTH_DISTANCE_M)))
    return sun, earth


log = logging.getLogger(__name__)


class WindowTooLong(ValueError):
    pass


class StepOutOfRange(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GeometryResult:
    """Everything one (site, window, step) computation produces."""

    site_id: str
    start: datetime
    end: datetime
    step_s: int
    sun: timeline.BodyTrack
    earth: timeline.BodyTrack
    metrics: core_metrics.SiteMetrics
    autonomy: core_metrics.AutonomyPacket
    computed_at: datetime
    compute_ms: float


def quantise(dt: datetime, step_s: int) -> datetime:
    """Snap a timestamp down to the step grid, in UTC.

    Floor rather than round, so that a window's start never moves later than
    asked -- a window that silently began after the event you were looking for
    is a bad way to lose an hour.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    epoch = datetime(2000, 1, 1, tzinfo=UTC)
    n = int((dt - epoch).total_seconds() // step_s)
    return epoch + timedelta(seconds=n * step_s)


def validate_window(start: datetime, end: datetime, step_s: int) -> tuple[datetime, datetime, int]:
    """Bound-check and quantise. Raises rather than clamping silently.

    The start snaps *down* to the step grid and the **length** snaps to the
    nearest whole number of steps; the end follows from both. Flooring start
    and end independently -- the previous rule -- made a fixed-length window
    that slides in time alternate between two lengths (2,834 and 2,835 steps
    for a lunar day) depending on its phase against the grid. Every drag then
    produced two cache keys instead of one, and the totals wobbled by a step
    for a reason nobody could see on screen.
    """
    s = get_settings()
    if not (s.min_step_s <= step_s <= s.max_step_s):
        raise StepOutOfRange(
            f"step_s must be between {s.min_step_s} and {s.max_step_s} seconds; got {step_s}"
        )
    start = start if start.tzinfo is not None else start.replace(tzinfo=UTC)
    end = end if end.tzinfo is not None else end.replace(tzinfo=UTC)
    if end <= start:
        raise WindowTooLong(
            f"end must be after start; got {start.isoformat()} .. {end.isoformat()}"
        )
    qs = quantise(start, step_s)
    steps = max(1, round((end - start).total_seconds() / step_s))
    qe = qs + timedelta(seconds=steps * step_s)
    span_days = (qe - qs).total_seconds() / 86400.0
    if span_days > s.max_window_days:
        raise WindowTooLong(
            f"window is {span_days:.0f} days; the maximum is {s.max_window_days}. "
            f"Narrow the window."
        )
    return qs, qe, step_s


async def compute_window_metrics(
    *,
    site_id: str,
    lat_deg: float,
    lon_deg: float,
    elev_m: float,
    mask: HorizonMask,
    start: datetime,
    end: datetime,
    step_s: int,
) -> GeometryResult:
    """The whole geometry pipeline for one site and one window.

    One vectorised ``spkpos`` per body for the entire window -- not one per
    sample. For a 708 h window at 900 s that is 2 calls instead of 5,670, which
    is the difference between ~15 ms and ~200 ms and is the main reason the
    slider budget in N1 is achievable at all.
    """
    t0 = time.perf_counter()
    start, end, step_s = validate_window(start, end, step_s)

    # One hop to the SPICE thread for the whole window: both UTC conversions,
    # the time grid and both bodies. Four hops cost four queue waits behind
    # whatever else is on that thread.
    eph = await spice.ephemeris_async(
        start.isoformat().replace("+00:00", "Z"),
        end.isoformat().replace("+00:00", "Z"),
        float(step_s),
    )
    t_s = (eph.ets - eph.ets[0]).astype(np.float64)

    basis = visibility.enu_basis(lat_deg, lon_deg)
    site_pos = visibility.site_position(lat_deg, lon_deg, R_MOON_M + elev_m)

    sun = timeline.build_track("sun", t_s, eph.sun, mask, basis, site_pos, R_SUN_M)
    earth = timeline.build_track("earth", t_s, eph.earth, mask, basis, site_pos, R_EARTH_M)

    m = timeline.site_metrics_from_tracks(site_id, sun, earth)
    packet = core_metrics.autonomy(m)

    return GeometryResult(
        site_id=site_id,
        start=start,
        end=end,
        step_s=step_s,
        sun=sun,
        earth=earth,
        metrics=m,
        autonomy=packet,
        computed_at=datetime.now(UTC),
        compute_ms=(time.perf_counter() - t0) * 1000.0,
    )


def uncertainty_block(
    result: GeometryResult,
    *,
    dem_vertical_error_m: float,
    dem_resolution_m: float,
    coverage: float,
    mask: HorizonMask,
) -> dict[str, object]:
    """The `meta.uncertainty` payload.

    Never omitted and never null. Where a value genuinely cannot be computed the
    field carries the reason instead: ``grazing: true`` with
    ``edge_timing_s: null`` says the edge is untimeable, which is a different
    and more honest claim than a large number.
    """
    grazing = result.sun.grazing or result.earth.grazing
    worst = max(result.sun.worst_tolerance_s, result.earth.worst_tolerance_s)
    blocker_range = float(np.median(mask.range_m)) if mask.range_m.size else 0.0

    notes = [
        f"Terrain is modelled to {mask.max_range_m / 1000:.0f} km around the site; "
        f"ground beyond that is not included.",
        "Shadow edges are resolution-limited: a "
        f"{dem_resolution_m:.0f} m elevation post cannot resolve a boulder, so the "
        "lit/dark boundary is soft at the scale of the terrain model.",
    ]
    if coverage < 0.999:
        notes.append(
            f"The elevation model covers {coverage * 100:.1f}% of the sampled terrain; "
            "bearings without coverage fall back to a smooth-sphere horizon and are "
            "likely to be optimistic."
        )
    if grazing:
        notes.append(
            "At least one crossing is too shallow to time: the body approaches the "
            "skyline almost tangentially, so the hour it crosses is not knowable from "
            "this data. The totals stand; their edges do not."
        )
    m = result.metrics
    cut = [
        label
        for label, is_open in (
            ("longest night", m.longest_dark_open),
            ("longest blackout", m.longest_blackout_open),
        )
        if is_open
    ]
    if cut:
        notes.append(
            f"The {' and the '.join(cut)} touch{'es' if len(cut) == 1 else ''} an edge of "
            "the window, so the window -- not the terrain -- ended "
            f"{'it' if len(cut) == 1 else 'them'}. The stretch continues beyond the window "
            "and the figure is a lower bound."
        )

    return {
        "dem_vertical_error_m": dem_vertical_error_m,
        "dem_resolution_m": dem_resolution_m,
        "coverage": round(coverage, 4),
        "horizon_el_deg": round(
            float(np.degrees(np.arctan2(dem_vertical_error_m, max(blocker_range, 1.0)))), 4
        ),
        "edge_timing_s": None if grazing else round(worst, 1),
        "grazing": grazing,
        "penumbra_sun_deg": round(float(np.mean(result.sun.angular_radius_deg)), 4),
        "penumbra_earth_deg": round(float(np.mean(result.earth.angular_radius_deg)), 4),
        "notes": notes,
    }


def resolution_block(
    mask: HorizonMask, step_s: int, dem_product: str, dem_resolution_m: float
) -> dict[str, object]:
    return {
        "azimuth_deg": mask.azimuth_step_deg,
        "azimuth_count": mask.azimuth_count,
        "time_step_s": step_s,
        "max_range_m": mask.max_range_m,
        "dem_product": dem_product,
        "dem_resolution_m": dem_resolution_m,
        "ephemeris": spice.describe()["ephemeris"],
        "frame": spice.describe()["frame"],
    }


def meta(
    result: GeometryResult,
    mask: HorizonMask,
    *,
    dem_product: str,
    dem_resolution_m: float,
    dem_vertical_error_m: float,
    coverage: float,
    cache: str = "miss",
) -> dict[str, object]:
    return {
        "computed_at": result.computed_at.isoformat().replace("+00:00", "Z"),
        "resolution": resolution_block(mask, result.step_s, dem_product, dem_resolution_m),
        "uncertainty": uncertainty_block(
            result,
            dem_vertical_error_m=dem_vertical_error_m,
            dem_resolution_m=dem_resolution_m,
            coverage=coverage,
            mask=mask,
        ),
        "engine_version": ENGINE_VERSION,
        "cache": cache,
        "compute_ms": round(result.compute_ms, 1),
    }
