"""Propagate a spacecraft through the Earth-Moon system (T2, C1).

The accelerations are :mod:`app.core.forces`; the integrator is SciPy's
DOP853 (Dormand-Prince 8(5,3)) at ``rtol`` 1e-12, the plan's setting. The body
tables are read from SPICE once per span by :func:`environment`; everything
after that is arithmetic on arrays, so a propagation can run on any thread.

States are J2000, metres and metres per second, relative to the model's
origin (Earth or Moon); :func:`rebase` moves them between the two.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy.integrate import OdeSolution, solve_ivp

from app.core import forces, spice

FloatArray = npt.NDArray[np.float64]

#: The integrator's relative tolerance (plan, C1).
RTOL = 1e-12
#: Absolute tolerances: 1 micrometre and 1 nanometre per second.
ATOL_M = 1e-6
ATOL_M_S = 1e-9


def environment(et0: float, et1: float, *, knot_s: float = 300.0) -> forces.Tables:
    """Body tables from SPICE covering ``[et0, et1]`` (either order) with a margin."""
    lo, hi = min(et0, et1), max(et0, et1)
    ets = np.arange(lo - 2 * knot_s, hi + 3 * knot_s, knot_s, dtype=np.float64)
    j2000 = spice.J2000
    return forces.Tables(
        t0=float(ets[0]),
        dt=knot_s,
        moon=spice.states("MOON", "EARTH", j2000, "NONE", ets),
        sun=spice.states("SUN", "EARTH", j2000, "NONE", ets),
        moon_pa=spice.rotations(j2000, spice.MOON_PA, ets),
        itrf=spice.rotations(j2000, spice.ITRF93, ets),
        gm_earth=spice.gm_m3_s2("EARTH"),
        gm_moon=spice.gm_m3_s2("MOON"),
        gm_sun=spice.gm_m3_s2("SUN"),
        r_earth_m=float(spice.radii_m("EARTH")[0]),
        r_moon_m=float(spice.radii_m("MOON")[0]),
        r_sun_m=float(spice.radii_m("SUN")[0]),
    )


@dataclass(frozen=True)
class Trajectory:
    """A propagated arc: samples, a dense interpolant and any event times."""

    et: FloatArray
    state: FloatArray  # (n, 6)
    origin: int
    sol: Any  # scipy OdeSolution
    events: list[FloatArray] = field(default_factory=list)
    event_states: list[FloatArray] = field(default_factory=list)
    nfev: int = 0

    def at(self, ets: FloatArray | float) -> FloatArray:
        """(n, 6) states at any times inside the arc (dense output, same accuracy)."""
        t = np.atleast_1d(np.asarray(ets, dtype=np.float64))
        return np.asarray(self.sol(t).T, dtype=np.float64)


Event = Callable[[float, FloatArray], float]


def propagate(
    tables: forces.Tables,
    model: forces.Model,
    et0: float,
    y0: FloatArray,
    et1: float,
    *,
    t_eval: FloatArray | None = None,
    events: Sequence[Event] = (),
    rtol: float = RTOL,
) -> Trajectory:
    """Integrate from ``(et0, y0)`` to ``et1`` (backwards when ``et1 < et0``).

    With sunlight pressure on, the Sun's visible fraction has kinks at each
    shadow contact, where an eighth-order step loses its order; a quick first
    pass finds the contacts and the integration restarts at each one. Without
    the restarts a 24 h lunar orbit forward and back misses by metres; with
    them, by millimetres (test_propagate.py).
    """
    lo, hi = tables.span
    if not (lo <= min(et0, et1) and max(et0, et1) <= hi):
        raise ValueError("the propagation span is outside the body tables")
    f = forces.derivatives(tables, model)
    atol = np.array([ATOL_M] * 3 + [ATOL_M_S] * 3)
    y = np.asarray(y0, dtype=np.float64)
    forward = et1 >= et0
    cuts: list[float] = []
    nfev = 0
    if model.cr_am > 0.0:
        scout = solve_ivp(
            f,
            (et0, et1),
            y,
            method="DOP853",
            rtol=1e-10,
            atol=atol * 100,
            events=forces.shadow_events(tables, model),
        )
        nfev += int(scout.nfev)
        inside = {
            float(t) for arr in scout.t_events for t in arr if min(et0, et1) < t < max(et0, et1)
        }
        cuts = sorted(inside, reverse=not forward)
    bounds = [et0, *cuts, et1]
    ts: list[float] = []
    interps: list[Any] = []
    step_t: list[FloatArray] = []
    step_y: list[FloatArray] = []
    ev_t: list[list[FloatArray]] = [[] for _ in events]
    ev_y: list[list[FloatArray]] = [[] for _ in events]
    for a, b in itertools.pairwise(bounds):
        if abs(b - a) < 1e-6:
            continue
        res = solve_ivp(
            f,
            (a, b),
            y,
            method="DOP853",
            rtol=rtol,
            atol=atol,
            dense_output=True,
            events=list(events) or None,
        )
        if not res.success:
            raise RuntimeError(f"propagation failed: {res.message}")
        nfev += int(res.nfev)
        seg_ts = list(res.sol.ts)
        ts.extend(seg_ts if not ts else seg_ts[1:])
        interps.extend(res.sol.interpolants)
        step_t.append(res.t if not step_t else res.t[1:])
        step_y.append(res.y.T if not step_y else res.y.T[1:])
        for k in range(len(events)):
            ev_t[k].append(np.asarray(res.t_events[k], dtype=np.float64))
            ev_y[k].append(np.asarray(res.y_events[k], dtype=np.float64).reshape(-1, 6))
        y = np.asarray(res.y[:, -1], dtype=np.float64)
    sol = OdeSolution(np.asarray(ts), interps)
    if t_eval is not None:
        et = np.asarray(t_eval, dtype=np.float64)
        state = np.asarray(sol(et).T, dtype=np.float64)
    else:
        et = np.concatenate(step_t)
        state = np.concatenate(step_y)
    return Trajectory(
        et=et,
        state=state,
        origin=model.origin,
        sol=sol,
        events=[np.concatenate(e) if e else np.empty(0) for e in ev_t],
        event_states=[np.concatenate(e) if e else np.empty((0, 6)) for e in ev_y],
        nfev=nfev,
    )


def rebase(
    tables: forces.Tables, ets: FloatArray, states: FloatArray, *, frm: int, to: int
) -> FloatArray:
    """Move (n, 6) J2000 states between the Earth and Moon origins."""
    if frm == to:
        return np.asarray(states, dtype=np.float64)
    moon = forces.body_state(tables, forces.MOON, np.atleast_1d(ets))
    sign = 1.0 if (frm == forces.MOON and to == forces.EARTH) else -1.0
    return np.asarray(np.atleast_2d(states) + sign * moon, dtype=np.float64)


def residual_acceleration(
    tables: forces.Tables,
    model: forces.Model,
    ets: FloatArray,
    states: FloatArray,
    *,
    h_s: float = 10.0,
    state_at: Callable[[FloatArray], FloatArray] | None = None,
) -> FloatArray:
    """(n,) |observed - modelled| acceleration along a reconstructed trajectory, m/s^2.

    ``state_at(ets)`` returns reconstructed states about the model's origin; the
    observed acceleration is the five-point central difference of its velocity
    at spacing ``h_s`` (truncation ``h^4/30 |v^(5)|``: 3e-10 m/s^2 in a two-hour
    lunar orbit at 10 s).
    What is left over is what the model does not explain: engine burns, thruster
    firings, outgassing or a leak (the Peregrine case), and model error.
    """
    if state_at is None:
        raise ValueError("state_at is required")
    f = forces.derivatives(tables, model)
    v = [state_at(ets + k * h_s)[:, 3:] for k in (-2, -1, 1, 2)]
    observed = (v[0] - 8.0 * v[1] + 8.0 * v[2] - v[3]) / (12.0 * h_s)
    modelled = np.array([f(float(t), y)[3:] for t, y in zip(ets, states, strict=True)])
    return np.asarray(np.linalg.norm(observed - modelled, axis=1), dtype=np.float64)
