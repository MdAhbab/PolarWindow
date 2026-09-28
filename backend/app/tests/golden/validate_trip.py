"""The propagator against NASA's reconstructed CLPS trajectories (plan C1).

Run: ``make validate-trip`` (or ``uv run python -m app.tests.golden.validate_trip``).
Prints the table that goes into docs/validation.md; the golden test
``test_propagate_vs_clps.py`` pins the acceptance numbers from the same code.

Method. Along each reconstruction, the acceleration the reconstruction implies
(five-point difference of its velocity) is compared with the force model's
every ``SCAN_S``. Where the two differ by more than ``QUIET_M_S2`` the lander
was firing an engine or thrusters (or leaking); a *quiet stretch* is a run of
samples below it, trimmed by ``EDGE_S`` at each end. From the start of each
quiet stretch the reconstructed state is propagated for 24 h and 72 h (or to
the end of the stretch if shorter) and the position is compared with the
reconstruction. Nothing is fitted: no area-to-mass ratio, no scale factor.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from app.config import get_settings
from app.core import forces, propagate, spice
from app.data.gravity import moon_field

SCAN_S = 600.0
QUIET_M_S2 = 1e-5
EDGE_S = 1800.0
HOURS = (24.0, 72.0)
#: Within this distance of the Moon the integration is about the Moon (its sphere of influence).
MOON_ORIGIN_M = 66_000e3

FLOWN: dict[str, tuple[str, int, str]] = {
    "im-1": ("clps/clps_to2im_im1_cru_rec_240216_240221_v01.bsp", -370011, "IM-1 Odysseus"),
    "blue-ghost-m1": (
        "clps/clps_to19d_bgm1_cru_rec_250115_250302_v01.bsp",
        -2711,
        "Blue Ghost Mission 1",
    ),
    "im-2": ("clps/clps_prime1_im2_cru_rec_250227_250306_v01.bsp", -370021, "IM-2 Athena"),
    "peregrine-m1": ("clps/clps_to2ab_apm1_cru_rec_240108_240118_v02.bsp", -244, "Peregrine"),
    # Not CLPS: NASA's Lunar Reconnaissance Orbiter, the plan's low-lunar-orbit reference.
    "lro": ("validation/lro/lrorg_2025074_2025166_v01.bsp", -85, "LRO"),
}
#: Only part of a long reconstruction is scanned.
WINDOW: dict[str, tuple[str, str]] = {"lro": ("2025-03-20T00:00:00", "2025-03-27T00:00:00")}


@dataclass
class Arc:
    mission: str
    start: str
    hours: float
    where: str  # "cruise" or "lunar orbit"
    moon_degree: int
    error_km: float
    error_km_srp: float | None  # with an assumed Cr A/m = 0.01 m^2/kg


@dataclass
class Scan:
    mission: str
    samples: int
    residual_median_m_s2: float
    residual_p90_m_s2: float
    quiet_fraction: float
    quiet_stretches_h: list[float]


def _load(mission: str) -> tuple[int, list[tuple[float, float]]]:
    s = get_settings()
    spice.load(s.kernel_dir)
    path, naif, _ = FLOWN[mission]
    p = s.data_dir / path
    if not p.exists():
        raise FileNotFoundError(f"{path} is not on disk (polar-data sync)")
    spice.load_extra([p])
    cov = spice.coverage(p, naif)
    if mission in WINDOW:
        lo, hi = (spice.utc_to_et(t) for t in WINDOW[mission])
        cov = [(max(a, lo), min(b, hi)) for a, b in cov if b > lo and a < hi]
    return naif, cov


def _states(naif: int, origin: int, ets: np.ndarray) -> np.ndarray:
    centre = "EARTH" if origin == forces.EARTH else "MOON"
    return spice.states(str(naif), centre, spice.J2000, "NONE", np.atleast_1d(ets))


def scan(mission: str, degree: int = 200) -> tuple[Scan, list[tuple[float, float]]]:
    """Residual acceleration along the reconstruction, and its quiet stretches (ET)."""
    naif, cov = _load(mission)
    field = moon_field(degree)
    all_res: list[np.ndarray] = []
    quiet: list[tuple[float, float]] = []
    for a, b in cov:
        ets = np.arange(a + 60.0, b - 60.0, SCAN_S)
        if ets.size < 2:
            continue
        tab = propagate.environment(a, b)
        model = forces.Model(moon_field=field)
        res = propagate.residual_acceleration(
            tab,
            model,
            ets,
            _states(naif, forces.EARTH, ets),
            state_at=lambda t: _states(naif, forces.EARTH, t),
        )
        all_res.append(res)
        ok = res < QUIET_M_S2
        i = 0
        while i < ok.size:
            if not ok[i]:
                i += 1
                continue
            j = i
            while j + 1 < ok.size and ok[j + 1]:
                j += 1
            lo = ets[i] + (EDGE_S if i > 0 else 0.0)
            hi = ets[j] - (EDGE_S if j < ok.size - 1 else 0.0)
            if hi - lo > 3600.0:
                quiet.append((float(lo), float(hi)))
            i = j + 1
    r = np.concatenate(all_res)
    total = sum(b - a for a, b in cov)
    return (
        Scan(
            mission=mission,
            samples=int(r.size),
            residual_median_m_s2=float(np.median(r)),
            residual_p90_m_s2=float(np.percentile(r, 90)),
            quiet_fraction=float(sum(b - a for a, b in quiet) / total),
            quiet_stretches_h=[round((b - a) / 3600.0, 1) for a, b in quiet],
        ),
        quiet,
    )


def arc(
    mission: str, et0: float, hours: float, *, degree: int = 50, cr_am: float = 0.0
) -> tuple[float, str, float]:
    """Propagate the reconstruction's state at ``et0`` for ``hours``; position error (m)."""
    naif, _ = _load(mission)
    et1 = et0 + hours * 3600.0
    tab = propagate.environment(et0, et1)
    y_e = _states(naif, forces.EARTH, np.array([et0]))[0]
    d_moon = float(
        np.linalg.norm(y_e[:3] - forces.body_state(tab, forces.MOON, np.array([et0]))[0, :3])
    )
    origin = forces.MOON if d_moon < MOON_ORIGIN_M else forces.EARTH
    model = forces.Model(origin=origin, moon_field=moon_field(degree), cr_am=cr_am)
    y0 = _states(naif, origin, np.array([et0]))[0]
    tr = propagate.propagate(tab, model, et0, y0, et1)
    truth = _states(naif, origin, np.array([et1]))[0]
    where = "lunar orbit" if origin == forces.MOON else "cruise"
    return float(np.linalg.norm(tr.state[-1, :3] - truth[:3])), where, d_moon


def round_trip(mission: str, et0: float, hours: float = 24.0, degree: int = 50) -> float:
    """Forward ``hours`` then back: distance from the starting position (m)."""
    naif, _ = _load(mission)
    et1 = et0 + hours * 3600.0
    tab = propagate.environment(et0, et1)
    model = forces.Model(moon_field=moon_field(degree))
    y0 = _states(naif, forces.EARTH, np.array([et0]))[0]
    fwd = propagate.propagate(tab, model, et0, y0, et1)
    back = propagate.propagate(tab, model, et1, fwd.state[-1], et0)
    return float(np.linalg.norm(back.state[-1, :3] - y0[:3]))


def _where(mission: str, et: float) -> str:
    naif, _ = _load(mission)
    y = _states(naif, forces.MOON, np.array([et]))[0]
    return "lunar orbit" if float(np.linalg.norm(y[:3])) < MOON_ORIGIN_M else "cruise"


def arcs(mission: str, quiet: list[tuple[float, float]], *, per_kind: int = 3) -> list[Arc]:
    """Up to ``per_kind`` arcs per length and per place (cruise, lunar orbit)."""
    out: list[Arc] = []
    for hours in HOURS:
        taken: dict[str, int] = {"cruise": 0, "lunar orbit": 0}
        for lo, hi in quiet:
            t = lo
            while t + hours * 3600.0 <= hi:
                where = _where(mission, t)
                if taken[where] < per_kind and _where(mission, t + hours * 3600.0) == where:
                    for deg in (100, 200) if where == "lunar orbit" else (50,):
                        err, _, _ = arc(mission, t, hours, degree=deg)
                        err_srp, _, _ = arc(mission, t, hours, degree=deg, cr_am=0.01)
                        out.append(
                            Arc(
                                mission,
                                spice.et_to_utc(t, precision=0),
                                hours,
                                where,
                                deg,
                                round(err / 1000.0, 3),
                                round(err_srp / 1000.0, 3),
                            )
                        )
                    taken[where] += 1
                t += hours * 3600.0
        if not any(a.hours == HOURS[0] for a in out) and hours == HOURS[0] and quiet:
            # No stretch is a day long (IM-1): report the longest one to its end.
            lo, hi = max(quiet, key=lambda q: q[1] - q[0])
            h = (hi - lo) / 3600.0
            err, where, _ = arc(mission, lo, h)
            err_srp, _, _ = arc(mission, lo, h, cr_am=0.01)
            out.append(
                Arc(
                    mission,
                    spice.et_to_utc(lo, precision=0),
                    round(h, 2),
                    where,
                    50,
                    round(err / 1000.0, 3),
                    round(err_srp / 1000.0, 3),
                )
            )
    return out


def main() -> None:
    result: dict[str, Any] = {"scans": [], "arcs": [], "round_trip_m": None}
    for mission in FLOWN:
        sc, quiet = scan(mission)
        result["scans"].append(asdict(sc))
        if mission != "peregrine-m1":
            per_kind = 2 if mission == "lro" else 3
            result["arcs"].extend(asdict(a) for a in arcs(mission, quiet, per_kind=per_kind))
        if mission == "blue-ghost-m1" and quiet:
            lo, hi = max(quiet, key=lambda q: q[1] - q[0])
            result["round_trip_m"] = round(round_trip(mission, lo, min(24.0, (hi - lo) / 3600)), 4)
        print(json.dumps(asdict(sc)), file=sys.stderr)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
