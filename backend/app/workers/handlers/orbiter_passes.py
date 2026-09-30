"""Real lunar orbiters over the landing spot, for the contact job (T1, F2).

LRO, Danuri, Chandrayaan-2 and CAPSTONE fly real orbits; their passes over
the lander are "could see the lander" geometry. None of them relays for a
CLPS lander, and the answer never calls them relays.

The trajectory is JPL Horizons' (recorded by the feeds worker), turned into
an SPK type 13 kernel here and read through CSPICE with the light time and
aberration seen from the site. A pass is the orbiter above the terrain
skyline (a point: angular radius 0), sampled every 30 s, each edge found by
bisection to a millisecond.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from app.config import get_settings
from app.core import intervals, spice, visibility
from app.core.quantity import Quantity
from app.core.timeline import GRAZING_DEG_PER_S
from app.services import lifecycle

FloatArray = npt.NDArray[np.float64]

STEP_S = 30.0
#: An edge whose time moves by more than this for the skyline's own angular
#: uncertainty is a graze, not a timed edge (an orbiter's pass lasts minutes
#: to hours; the Sun's and Earth's 24 h cap would hide that).
MAX_EDGE_TOL_S = 3600.0
NOTE = (
    "A real orbiter's passes over the landing spot: when it could see the lander. None of "
    "these orbiters offers to relay for a lander; this is geometry, not a service."
)


def kernel_path(orbiter_id: str, snapshot_id: int, digest: str) -> Path:
    """Named by the snapshot and its content, so two databases never share a file."""
    return get_settings().kernel_dir / "orbiters" / f"{orbiter_id}-{snapshot_id}-{digest[:12]}.bsp"


def ensure_kernel(
    orbiter_id: str, snapshot_id: int, digest: str | None, parsed: dict[str, Any]
) -> Path:
    """The SPK for one recorded trajectory, written once and loaded. SPICE thread."""
    if not digest:
        digest = hashlib.sha256(json.dumps(parsed["rows"]).encode()).hexdigest()
    p = kernel_path(orbiter_id, snapshot_id, digest)
    if not p.exists():
        rows = np.asarray(parsed["rows"], dtype=np.float64)
        spice.write_spk13(p, int(parsed["naif_id"]), rows[:, 0], rows[:, 1:], segment=orbiter_id)
    spice.load_extra([p])
    return p


@dataclass(frozen=True, slots=True)
class Passes:
    runs: list[intervals.Run]  # over [a, b], seconds from the start of the dates
    a: float
    b: float
    edge_tol_s: list[float]  # per timed edge
    grazes: int
    max_el_deg: list[float]  # per pass, above the flat horizon


def passes(
    naif_id: int,
    t0_et: float,
    t1: float,
    cover: tuple[float, float],
    site_me_m: FloatArray,
    basis: visibility.ENUBasis,
    sky_az: FloatArray,
    sky_el: FloatArray,
    sky_tol: FloatArray,
) -> Passes | None:
    """The orbiter above the skyline over the part of ``[0, t1]`` its kernel covers."""
    a = max(0.0, cover[0] - t0_et)
    b = min(t1, cover[1] - t0_et)
    if b - a < STEP_S:
        return None
    t = np.arange(a, b + STEP_S / 2, STEP_S)
    t[-1] = b
    target = str(naif_id)

    def margin_at(ts: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
        v = spice.site_look(target, site_me_m, t0_et + ts)
        az, el = visibility.look_angles(basis, v)
        return el - visibility.interp_horizon(sky_el, az), az, el

    m, _az, el = margin_at(t)

    def refine(lo: float, hi: float) -> float:
        mlo = float(margin_at(np.array([lo]))[0][0])
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            mm = float(margin_at(np.array([mid]))[0][0])
            if (mm > 0.0) == (mlo > 0.0):
                lo, mlo = mid, mm
            else:
                hi = mid
            if hi - lo < 1e-3:
                break
        return 0.5 * (lo + hi)

    runs = intervals.runs_from_margin(t, m, refine=refine)
    tols: list[float] = []
    grazes = 0
    peaks: list[float] = []
    for r in runs:
        if not r.value:
            continue
        inside = (t >= r.start) & (t <= r.end)
        peaks.append(float(el[inside].max()) if inside.any() else float("nan"))
        for edge, cut in ((r.start, r.start <= a + intervals.EPS_S), (r.end, r.end >= b - 1e-6)):
            if cut:
                continue
            h = 1.0
            (m2, az2, _e2) = margin_at(np.array([edge - h, edge + h]))
            rate = abs(float(m2[1] - m2[0])) / (2 * h)
            tol = float(visibility.interp_horizon(sky_tol, az2[:1])[0])
            if rate < GRAZING_DEG_PER_S or tol / rate > MAX_EDGE_TOL_S:
                grazes += 1
            else:
                tols.append(tol / rate)
    return Passes(runs, a, b, tols, grazes, peaks)


def edges(name: str, got: Passes, start: datetime, t1: float) -> str | None:
    """Where the recorded trajectory starts after the dates begin or ends before they end."""
    said = []
    if got.a > intervals.EPS_S:
        at = start + timedelta(seconds=got.a)
        said.append(
            lifecycle.trajectory_edge(name, at, ends=False) + " No pass before then is worked out."
        )
    if got.b < t1 - 1e-6:
        at = start + timedelta(seconds=got.b)
        said.append(
            lifecycle.trajectory_edge(name, at, ends=True) + " No pass after then is worked out."
        )
    return " ".join(said) or None


def block(
    rec: Any,
    snap: dict[str, Any] | None,
    got: Passes | None,
    start: datetime,
    t1: float,
    missing: str | None,
    trajectory_gap: str | None = None,
) -> dict[str, Any]:
    """One orbiter in the Contact answer. Its ``note`` says only what is its own: where the
    recorded trajectory stops short of the dates (the section's note says the rest)."""
    src = None
    if snap is not None:
        src = lifecycle.source_ref(
            f"JPL Horizons trajectory ({snap.get('source') or 'merged'})",
            "https://ssd.jpl.nasa.gov/horizons/",
            fetched_at=snap.get("fetched_at"),
            licence="NASA/JPL Horizons (US government work, public domain)",
            snapshot_id=snap.get("snapshot_id"),
        )
    out: dict[str, Any] = {
        "id": rec.id,
        "name": rec.name,
        "operator": rec.operator,
        "naif_id": rec.naif_id,
        "note": trajectory_gap if got is None else edges(rec.name, got, start, t1),
        "source": src,
        "covered": None,
        "passes": [],
        "pass_count": 0,
        "in_view_h": lifecycle.missing("h", missing or "No trajectory for these dates."),
        "longest_pass_min": lifecycle.missing("min", missing or "No trajectory for these dates."),
        "longest_gap_h": lifecycle.missing("h", missing or "No trajectory for these dates."),
    }
    if got is None:
        return out
    on = [r for r in got.runs if r.value]
    out["covered"] = lifecycle.stretch(
        start + timedelta(seconds=got.a),
        start + timedelta(seconds=got.b),
        got.a <= intervals.EPS_S,
        got.b >= t1 - 1e-6,
    )
    out["passes"] = [
        {
            **lifecycle.stretch(
                start + timedelta(seconds=r.start),
                start + timedelta(seconds=r.end),
                r.start <= got.a + intervals.EPS_S,
                r.end >= got.b - 1e-6,
            ),
            "max_elevation_deg": None if math.isnan(p) else round(p, 3),
        }
        for r, p in zip(on, got.max_el_deg, strict=True)
    ]
    out["pass_count"] = len(on)
    total = intervals.total(got.runs, True)
    pm = math.sqrt(sum(x * x for x in got.edge_tol_s))
    graze = f" {got.grazes} edge(s) only graze the skyline and are not timed." if got.grazes else ""
    out["in_view_h"] = lifecycle.q(
        Quantity(value=total / 3600.0, unit="h", provenance="computed", pm=pm / 3600.0)
        if pm > 0.0
        else Quantity(
            value=total / 3600.0,
            unit="h",
            provenance="computed",
            no_margin_reason="No timed edge inside these dates." + graze,
        )
    )
    longest = intervals.longest(got.runs, True)
    gap = intervals.longest(got.runs, False)
    out["longest_pass_min"] = lifecycle.q(
        Quantity(
            value=(longest.duration if longest else 0.0) / 60.0,
            unit="min",
            provenance="computed",
            open=bool(longest and (longest.start <= got.a + 1e-6 or longest.end >= got.b - 1e-6)),
            no_margin_reason="Edges from the terrain skyline; the ± on the time in view "
            "sums them." + graze,
        )
    )
    out["longest_gap_h"] = lifecycle.q(
        Quantity(
            value=(gap.duration if gap else 0.0) / 3600.0,
            unit="h",
            provenance="computed",
            open=bool(gap and (gap.start <= got.a + 1e-6 or gap.end >= got.b - 1e-6)),
            no_margin_reason="Edges from the terrain skyline; the ± on the time in view "
            "sums them." + graze,
        )
    )
    return out
