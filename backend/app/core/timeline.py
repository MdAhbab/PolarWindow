"""Compose a horizon mask and a body ephemeris into arcs and metrics.

Pure. Takes body position vectors as an ``(n, 3)`` array -- it does not know or
care whether they came from de440 or from a fixture -- plus a horizon mask, and
produces the visibility series, the refined arcs and the four numbers.

This module exists so that ``visibility`` stays "angles", ``intervals`` stays
"runs", ``metrics`` stays "the four numbers", and the *composition* of those
three has one obvious home. It is the piece the service layer calls, and the
piece the golden tests pin.

Crossing refinement
-------------------
Sign changes between samples are bracketed at the 900 s grid and then bisected
against a continuously-interpolated margin. The interpolation is on the body's
az/el track (smooth, and genuinely near-linear over 900 s) against the mask
(piecewise-linear in azimuth), so the refined crossing is exact to the mask's
own angular resolution rather than to the time step. Snapping crossings to
samples instead would quantise every arc edge to 15 minutes, which would be
visible in the output and would make the reported tolerances meaningless.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from app.core import intervals, metrics, visibility
from app.core.horizon import HorizonMask
from app.core.intervals import Run

FloatArray = npt.NDArray[np.float64]

#: Below this rate of change, a crossing is a graze and its timing is not
#: knowable from this data. Matches the frontend's GRAZING_DEG_PER_H, converted
#: to per-second.
GRAZING_DEG_PER_S: float = 0.0025 / 3600.0

#: Never report a timing tolerance larger than this; say "grazing" instead.
#: Showing "+/- 40 h" is worse than saying the edge cannot be timed, because it
#: looks like a measurement.
MAX_REPORTED_TOLERANCE_S: float = 24 * 3600.0


@dataclass(frozen=True, slots=True)
class BodyTrack:
    """A body's sampled track against a site's skyline."""

    body: str
    t_s: FloatArray
    az_deg: FloatArray
    el_deg: FloatArray
    mask_el_deg: FloatArray
    margin_deg: FloatArray
    state: npt.NDArray[np.int8]
    angular_radius_deg: FloatArray
    arcs: list[Run]
    arc_tolerance_s: list[float]
    #: Per-edge timing tolerance, ``(start, end)``; ``None`` where the edge is
    #: the window boundary rather than a crossing. The arc tolerance above is
    #: their quadrature sum; the edges are kept so a chart can draw the margin
    #: at each crossing rather than a blend of two.
    arc_edge_tolerance_s: list[tuple[float | None, float | None]]
    arc_grazing: list[bool]
    blocked_by_bearing_deg: list[float | None]
    blocked_by_el_deg: list[float | None]
    grazing: bool

    @property
    def worst_tolerance_s(self) -> float:
        finite = [t for t in self.arc_tolerance_s if np.isfinite(t)]
        return max(finite) if finite else 0.0


def _interp_track(t_s: FloatArray, values: FloatArray, at: float) -> float:
    """Linear interpolation of a track quantity at an arbitrary time."""
    return float(np.interp(at, t_s, values))


def build_track(
    body: str,
    t_s: FloatArray,
    vectors: FloatArray,
    mask: HorizonMask,
    basis: visibility.ENUBasis,
    site_pos: FloatArray,
    body_radius_m: float,
) -> BodyTrack:
    """Sample one body against the skyline and extract its arcs."""
    az, el = visibility.look_angles(basis, vectors, site_pos=site_pos)
    # Converted once. The bisection below evaluates the skyline forty times per
    # crossing, and re-casting 1440 float32s on every evaluation was the single
    # largest allocation on the request path.
    mask_el64 = mask.el_deg.astype(np.float64)
    mask_tol64 = mask.tol_deg.astype(np.float64)
    mask_el = visibility.interp_horizon(mask_el64, az)
    margin = el - mask_el

    dist = np.linalg.norm(vectors - site_pos[None, :], axis=1)
    ang_r = visibility.sun_earth_angular_radius_deg(dist, body_radius_m)
    state = visibility.visibility_state(margin, ang_r)

    # Interpolating 359.9 and 0.1 linearly gives 180, which would look up the
    # horizon on the opposite side of the sky. Unwrapping first is not optional:
    # near the pole the Sun's azimuth sweeps a full turn every lunar day, so the
    # wrap is crossed every month at every site.
    unwrapped_az = np.degrees(np.unwrap(np.radians(az)))

    def margin_at(at: float) -> float:
        """Continuous margin, for bisection."""
        a = float(np.mod(np.interp(at, t_s, unwrapped_az), 360.0))
        e = _interp_track(t_s, el, at)
        m = visibility.interp_horizon(mask_el64, np.array([a], dtype=np.float64))
        return e - float(m[0])

    def refine(lo: float, hi: float) -> float:
        return intervals.bisect_crossing(margin_at, lo, hi)

    arcs = intervals.runs_from_margin(t_s, margin, refine=refine)

    tolerances: list[float] = []
    edge_pairs: list[tuple[float | None, float | None]] = []
    grazings: list[bool] = []
    bearings: list[float | None] = []
    block_els: list[float | None] = []
    any_grazing = False

    for arc in arcs:
        # Tolerance of an arc is the quadrature sum of its two edges' timing
        # uncertainties. An edge's uncertainty is the mask's angular error at
        # that bearing divided by the rate the body is crossing the skyline --
        # NOT by the body's elevation rate, which near the pole is nearly zero
        # and would make every tolerance enormous. What actually times a
        # crossing here is azimuth sweeping past a steep piece of skyline.
        edge_tols: list[float] = []
        per_edge: dict[bool, float] = {}
        edge_graze = False
        for edge, is_start in ((arc.start, True), (arc.end, False)):
            if (is_start and edge <= t_s[0] + 1e-9) or (not is_start and edge >= t_s[-1] - 1e-9):
                continue  # window boundary, not a real crossing
            h = 60.0
            lo = max(t_s[0], edge - h)
            hi = min(t_s[-1], edge + h)
            if hi <= lo:
                continue
            rate = abs((margin_at(hi) - margin_at(lo)) / (hi - lo))
            a = float(np.mod(np.interp(edge, t_s, unwrapped_az), 360.0))
            tol_deg = float(
                visibility.interp_horizon(mask_tol64, np.array([a], dtype=np.float64))[0]
            )
            if rate < GRAZING_DEG_PER_S:
                edge_graze = True
                edge_tols.append(MAX_REPORTED_TOLERANCE_S)
                per_edge[is_start] = MAX_REPORTED_TOLERANCE_S
                continue
            dt = tol_deg / rate
            if dt > MAX_REPORTED_TOLERANCE_S:
                edge_graze = True
                dt = MAX_REPORTED_TOLERANCE_S
            edge_tols.append(dt)
            per_edge[is_start] = dt

        if len(edge_tols) == 2:
            tol = float(np.hypot(edge_tols[0], edge_tols[1]))
        else:
            tol = edge_tols[0] if edge_tols else 0.0
        tolerances.append(tol)
        edge_pairs.append((per_edge.get(True), per_edge.get(False)))
        grazings.append(edge_graze)
        any_grazing = any_grazing or edge_graze

        if arc.value:
            bearings.append(None)
            block_els.append(None)
        else:
            # Name the cause, not just the state. "Blocked" without a blocking
            # feature is the kind of answer that made the existing tools hard
            # to trust.
            probe = np.linspace(arc.start, arc.end, 13)
            az_probe = np.mod(np.interp(probe, t_s, unwrapped_az), 360.0)
            el_probe = visibility.interp_horizon(mask_el64, az_probe)
            k = int(np.argmax(el_probe))
            bearings.append(float(az_probe[k]))
            block_els.append(float(el_probe[k]))

    return BodyTrack(
        body=body,
        t_s=t_s,
        az_deg=az,
        el_deg=el,
        mask_el_deg=mask_el,
        margin_deg=margin,
        state=state,
        angular_radius_deg=ang_r,
        arcs=arcs,
        arc_tolerance_s=tolerances,
        arc_edge_tolerance_s=edge_pairs,
        arc_grazing=grazings,
        blocked_by_bearing_deg=bearings,
        blocked_by_el_deg=block_els,
        grazing=any_grazing,
    )


def site_metrics_from_tracks(site_id: str, sun: BodyTrack, earth: BodyTrack) -> metrics.SiteMetrics:
    """The four numbers from two tracks."""
    t0 = float(sun.t_s[0])
    span = float(sun.t_s[-1] - sun.t_s[0])
    return metrics.assemble(
        site_id,
        t0,
        span,
        sun.arcs,
        earth.arcs,
        sun_grazing=sun.grazing,
        earth_grazing=earth.grazing,
    )
