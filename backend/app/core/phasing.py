"""Phasing loops: burns read from a reconstruction, the loops flown again, loops designed (T2, C3).

Blue Ghost Mission 1 did not go straight to the Moon. Falcon 9 left it in a
long Earth orbit (apogee about 330,000 km, about eight days round); its own
engine fired a few times, and at the third perigee a last burn sent it on.

* :func:`find_burns` finds where a reconstruction leaves the force model. The
  reconstruction is cut into windows; each window's first state is propagated
  to the window's end and compared with the reconstructed end. A window whose
  velocities differ by more than a threshold holds a burn, and a run of such
  windows is one burn. Its impulsive equivalent is taken where the arc before
  it (propagated forward) and the arc after it (propagated back) come closest:
  the velocity difference there is the burn, the distance left between the two
  arcs says how far a finite burn is from an impulse.
* :func:`apsides` and :func:`replay`: the perigees and apogees of a
  reconstruction, and of its first state propagated with the burns as
  impulses (the plan's acceptance: epochs within one hour, apogee radius
  within 1%).
* :func:`design` builds the loops for a fixed arrival at the Moon: liftoff at
  the day's instant, the vehicle's injection at perigee, optionally a burn at
  the first apogee that raises the perigee (Blue Ghost's did, out of the air),
  ``N`` loops, one burn at the first perigee that sets the period of the
  remaining loops, and a last burn at the ``N``-th perigee. The liftoff time,
  the coast, the period burn, the last burn and the raise are corrected until
  the arrival matches in the B-plane and in time and the first perigee is at
  the radius asked for (four conditions, five unknowns; without a raise three
  and four). Each step is the smallest change, so the answer stays near the
  two-body plan it starts from. The Sun's pull over an eight-day loop moves
  the perigee by thousands of kilometres, so the raise a day needs depends
  on where the Sun is: on Blue Ghost's launch day it was a quarter of the
  two-body figure.
* :func:`launch_period` runs the design day by day. A day belongs to the
  period when the design converges, the perigee stays out of the air, the
  loops keep outside the Moon's sphere of influence before the last burn, and
  the burns add up to no more than the budget given.

Low-energy transfers (through the Sun-Earth L1/L2 region) are not modelled.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
from scipy.optimize import brentq, minimize_scalar

from app.core import forces, propagate, transfer
from app.core.trip import sphere_of_influence_m

FloatArray = npt.NDArray[np.float64]

DAY = 86_400.0
#: Apsides are looked for only this close to the Earth's centre (the Moon's
#: distance is about 384,000 km; farther out the Earth-centred orbit means little).
APSIS_WITHIN_M = 450_000e3
#: A perigee lower than this passes through enough air to cost more than a few m/s;
#: a design whose perigee drops below it is refused.
PERIGEE_MIN_ALT_M = 150e3
#: Burn search windows and the velocity jump that marks one (m/s). Over half an hour
#: the force model and a reconstruction agree to about 1e-4 m/s outside burns.
WINDOW_S = 1800.0
THRESHOLD_M_S = 0.05


@dataclass(frozen=True, slots=True)
class Burn:
    t: float  # ET of the impulsive equivalent
    dv: FloatArray  # J2000, m/s
    start: float  # the windows that hold it
    end: float
    r_m: float  # distance from the model's origin at the burn
    mismatch_m: float  # distance left between the arcs before and after at ``t``

    @property
    def dv_m_s(self) -> float:
        return float(np.linalg.norm(self.dv))


@dataclass(frozen=True, slots=True)
class Apsis:
    t: float
    kind: str  # "perigee" | "apogee"
    r_m: float


def _merge(flags: list[bool], starts: FloatArray, width: float) -> list[tuple[float, float]]:
    runs: list[tuple[float, float]] = []
    for on, a in zip(flags, starts, strict=True):
        if not on:
            continue
        if runs and abs(runs[-1][1] - float(a)) < 1e-6:
            runs[-1] = (runs[-1][0], float(a) + width)
        else:
            runs.append((float(a), float(a) + width))
    return runs


def find_burns(
    tables: forces.Tables,
    model: forces.Model,
    state_at: Callable[[FloatArray], FloatArray],
    t0: float,
    t1: float,
    *,
    window_s: float = WINDOW_S,
    threshold_m_s: float = THRESHOLD_M_S,
    rtol: float = 1e-11,
) -> list[Burn]:
    """Burns in a reconstruction between ``t0`` and ``t1``.

    ``state_at(ets)`` gives (n, 6) J2000 states about the model's origin.
    """
    starts = np.arange(t0, t1 - window_s + 1e-6, window_s)
    if starts.size == 0:
        return []
    ys = state_at(np.concatenate([starts, starts + window_s]))
    n = starts.size
    flags = []
    for i, t in enumerate(starts):
        tr = propagate.propagate(tables, model, float(t), ys[i], float(t) + window_s, rtol=rtol)
        flags.append(float(np.linalg.norm(tr.state[-1, 3:] - ys[n + i, 3:])) > threshold_m_s)
    out = []
    for a, b in _merge(flags, starts, window_s):
        ya, yb = state_at(np.array([a, b]))
        fwd = propagate.propagate(tables, model, a, ya, b, rtol=rtol)
        back = propagate.propagate(tables, model, b, yb, a, rtol=rtol)

        def gap(
            t: float, fwd: propagate.Trajectory = fwd, back: propagate.Trajectory = back
        ) -> float:
            return float(np.linalg.norm(fwd.at(t)[0, :3] - back.at(t)[0, :3]))

        res = minimize_scalar(gap, bounds=(a, b), method="bounded", options={"xatol": 0.5})
        tc = float(res.x)
        yf, yb2 = fwd.at(tc)[0], back.at(tc)[0]
        out.append(
            Burn(
                t=tc,
                dv=np.asarray(yb2[3:] - yf[3:], dtype=np.float64),
                start=a,
                end=b,
                r_m=float(np.linalg.norm(yf[:3])),
                mismatch_m=float(res.fun),
            )
        )
    return out


def apsides(
    state_at: Callable[[FloatArray], FloatArray],
    t0: float,
    t1: float,
    *,
    step_s: float = 600.0,
    within_m: float = APSIS_WITHIN_M,
) -> list[Apsis]:
    """Perigees and apogees (``r . v = 0``) of an Earth-centred trajectory."""
    ets = np.arange(t0, t1, step_s)
    if ets.size < 2:
        return []
    y = state_at(ets)
    g = np.einsum("ij,ij->i", y[:, :3], y[:, 3:])

    def rv(t: float) -> float:
        s = state_at(np.array([t]))[0]
        return float(s[:3] @ s[3:])

    out = []
    for i in range(ets.size - 1):
        if g[i] == 0.0 or g[i] * g[i + 1] > 0.0:
            continue
        t = float(brentq(rv, float(ets[i]), float(ets[i + 1]), xtol=0.01))
        r = float(np.linalg.norm(state_at(np.array([t]))[0, :3]))
        if r <= within_m:
            out.append(Apsis(t, "perigee" if g[i] < 0.0 else "apogee", r))
    return out


def _apsis_events() -> list[propagate.Event]:
    def peri(t: float, y: FloatArray) -> float:
        return float(y[:3] @ y[3:])

    def apo(t: float, y: FloatArray) -> float:
        return float(y[:3] @ y[3:])

    peri.direction = 1.0  # type: ignore[attr-defined]
    apo.direction = -1.0  # type: ignore[attr-defined]
    return [peri, apo]


def _events_to_apsides(tr: propagate.Trajectory, within_m: float) -> list[Apsis]:
    out = []
    for kind, ts, ys in zip(("perigee", "apogee"), tr.events, tr.event_states, strict=True):
        for t, y in zip(ts, ys, strict=True):
            r = float(np.linalg.norm(y[:3]))
            if r <= within_m:
                out.append(Apsis(float(t), kind, r))
    return sorted(out, key=lambda a: a.t)


@dataclass(frozen=True, slots=True)
class Replay:
    apsides: list[Apsis]
    end_state: FloatArray


def replay(
    tables: forces.Tables,
    model: forces.Model,
    t0: float,
    y0: FloatArray,
    burns: list[Burn],
    t1: float,
    *,
    rtol: float = 1e-11,
    within_m: float = APSIS_WITHIN_M,
) -> Replay:
    """Propagate ``(t0, y0)`` to ``t1`` with ``burns`` added as impulses."""
    y = np.asarray(y0, dtype=np.float64)
    t = t0
    found: list[Apsis] = []
    for b in [*sorted((b for b in burns if t0 < b.t < t1), key=lambda b: b.t), None]:
        stop = t1 if b is None else b.t
        tr = propagate.propagate(tables, model, t, y, stop, events=_apsis_events(), rtol=rtol)
        found += _events_to_apsides(tr, within_m)
        y = tr.state[-1].copy()
        if b is not None:
            y[3:] += b.dv
        t = stop
    return Replay(found, y)


def match(flown: list[Apsis], other: list[Apsis]) -> list[tuple[Apsis, Apsis | None]]:
    """Each flown apsis with the same kind's nearest one in ``other`` (within 2 days)."""
    out: list[tuple[Apsis, Apsis | None]] = []
    for a in flown:
        same = [o for o in other if o.kind == a.kind and abs(o.t - a.t) < 2 * DAY]
        out.append((a, min(same, key=lambda o: abs(o.t - a.t)) if same else None))
    return out


# --- design -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LoopDesign:
    t_launch: float
    coast_s: float
    t_inject: float
    dv_inject_m_s: float  # the vehicle's, above the circular parking speed
    n_loops: int
    raise_to_m: float | None  # perigee radius the first apogee's burn raises it to
    dv_raise_m_s: float
    dv_period_m_s: float  # at the first perigee, along the orbit (0 with one loop)
    dv_final_m_s: float  # at the n-th perigee
    perigees: list[Apsis]  # after the injection, up to the last burn
    apogees: list[Apsis]
    periods_d: list[float]
    min_perigee_alt_m: float
    min_moon_m: float  # closest to the Moon before the last burn
    t_peri: float  # closest approach to the Moon
    r_peri_m: float
    inc_deg: float
    miss_km: float
    dt_s: float
    iterations: int
    converged: bool
    refused: str | None = None  # why this design is not usable, in plain words
    notes: list[str] = field(default_factory=list)

    @property
    def lander_dv_m_s(self) -> float:
        return abs(self.dv_raise_m_s) + abs(self.dv_period_m_s) + abs(self.dv_final_m_s)


@dataclass(frozen=True, slots=True)
class _Flight:
    perigees: list[Apsis]
    apogees: list[Apsis]
    min_moon_m: float
    enc: transfer.Encounter


def _along(y: FloatArray, dv: float) -> FloatArray:
    out = np.asarray(y, dtype=np.float64).copy()
    out[3:] *= 1.0 + dv / float(np.linalg.norm(out[3:]))
    return out


def _fly(
    tables: forces.Tables,
    model: forces.Model,
    t_inj: float,
    y_inj: FloatArray,
    n_loops: int,
    dv_period: float,
    dv_final: float,
    t_max: float,
    rtol: float,
    dv_raise: float | None,
) -> _Flight:
    """Injection state -> (perigee raised at the first apogee) -> ``n_loops`` perigees
    (burns at the first and the last) -> the Moon."""

    r_ground = tables.r_earth_m
    min_moon = math.inf
    perigees: list[Apsis] = []
    apogees: list[Apsis] = []

    def ground(t: float, y: FloatArray) -> float:
        return float(y[:3] @ y[:3]) - r_ground**2

    ground.terminal = True  # type: ignore[attr-defined]
    ground.direction = -1.0  # type: ignore[attr-defined]

    def leg(t: float, y: FloatArray, stop: float, until: int | None) -> tuple[float, FloatArray]:
        """Propagate to ``stop``, or to the next perigee (``until=0``) or apogee (1)."""
        nonlocal min_moon
        ev = _apsis_events()
        if until is not None:
            ev[until].terminal = True  # type: ignore[attr-defined]
        tr = propagate.propagate(tables, model, t, y, stop, events=[*ev, ground], rtol=rtol)
        if tr.events[2].size:
            raise ValueError("the loops come down into the Earth")
        m = forces.body_state(tables, forces.MOON, tr.et)
        min_moon = min(min_moon, float(np.min(np.linalg.norm(tr.state[:, :3] - m[:, :3], axis=1))))
        for kind, found in ((0, perigees), (1, apogees)):
            found.extend(
                Apsis(float(tt), ("perigee", "apogee")[kind], float(np.linalg.norm(yy[:3])))
                for tt, yy in zip(tr.events[kind], tr.event_states[kind], strict=True)
            )
        if until is None:
            return stop, tr.state[-1]
        if tr.events[until].size == 0:
            raise ValueError("no perigee or apogee before the arrival: the loops escape")
        return float(tr.events[until][0]), tr.event_states[until][0]

    # The injection is itself a perigee: leave it for a day before looking for the next.
    t, y = leg(t_inj, y_inj, t_inj + DAY, None)
    if dv_raise is not None:
        t, y = leg(t, y, t_max, 1)
        y = _along(y, dv_raise)
    for k in range(1, n_loops + 1):
        t, y = leg(t, y, t_max, 0)
        if k == 1 and n_loops > 1:
            y = _along(y, dv_period)
        if k == n_loops:
            y = _along(y, dv_final)
        else:  # step off the perigee so the next search does not find it again
            t, y = leg(t, y, t + DAY, None)
    enc = transfer.encounter(tables, model, t, y, t_max)

    def once(found: list[Apsis]) -> list[Apsis]:
        out: list[Apsis] = []
        for a in sorted(found, key=lambda a: a.t):
            if a.t > t_inj + 600.0 and (not out or a.t - out[-1].t > 3600.0):
                out.append(a)
        return out

    return _Flight(once(perigees), once(apogees), min_moon, enc)


def two_body_plan(
    gm: float,
    r_p: float,
    v_p: float,
    t_inj: float,
    t_final: float,
    n_loops: int,
    r_moon: float,
    flight_s: float,
    raise_to_m: float | None = None,
) -> tuple[float, float, float]:
    """``(raise burn, period burn, last burn)`` in m/s. Loop 1 is the injection orbit (with its
    perigee raised to ``raise_to_m`` at the first apogee, if given); loops 2..N share
    the period that puts the ``N``-th perigee at ``t_final``; the last burn gives the
    patched-conic flight."""
    a1 = 1.0 / (2.0 / r_p - v_p**2 / gm)
    r_q = r_p if raise_to_m is None else raise_to_m
    a_q = 0.5 * (2.0 * a1 - r_p + r_q)  # same apogee, perigee r_q
    p1 = math.pi * (math.sqrt(a1**3 / gm) + math.sqrt(a_q**3 / gm))
    v_q = math.sqrt(gm * (2.0 / r_q - 1.0 / a_q))
    v2 = v_q
    if n_loops > 1:
        p2 = (t_final - t_inj - p1) / (n_loops - 1)
        a2 = (gm * (p2 / (2.0 * math.pi)) ** 2) ** (1.0 / 3.0)
        v2 = math.sqrt(gm * (2.0 / r_q - 1.0 / a2))
    _, v_need = transfer.patched_conic(r_q, r_moon, flight_s, gm)
    r_a = 2.0 * a1 - r_p
    dv_raise = math.sqrt(gm * (2.0 / r_a - 1.0 / a_q)) - math.sqrt(gm * (2.0 / r_a - 1.0 / a1))
    return dv_raise, v2 - v_q, v_need - v2


def design(
    tables: forces.Tables,
    target: transfer.Target,
    parking_at: Callable[[float], transfer.Parking],
    t_launch: float,
    coast_s: float,
    dv_inject: float,
    n_loops: int,
    *,
    flight_guess_s: float = 4.5 * DAY,
    raise_to_m: float | None = None,
    model: forces.Model | None = None,
    max_iter: int = 20,
    rtol: float = transfer.DESIGN_RTOL,
) -> LoopDesign:
    """Correct liftoff, coast, the period burn and the last burn to reach ``target``.

    The vehicle's injection (``dv_inject`` above the circular parking speed, at the
    parking orbit's point ``coast_s`` after liftoff) is kept: it is the vehicle's.
    """
    model = model or forces.Model()
    mu = tables.gm_moon
    gm = tables.gm_earth
    t_max = target.t_arrive + 2.0 * DAY
    k_hat = transfer.moon_pole(tables, target.t_arrive)
    r_min = tables.r_earth_m + PERIGEE_MIN_ALT_M

    park0 = parking_at(t_launch)
    y0 = transfer.tli_state(park0, t_launch + coast_s, dv_inject)
    moon_arr = forces.body_state(tables, forces.MOON, np.array([target.t_arrive]))[0][:3]
    dv0, dv1, dv2 = two_body_plan(
        gm,
        park0.radius,
        float(np.linalg.norm(y0[3:])),
        t_launch + coast_s,
        target.t_arrive - flight_guess_s,
        n_loops,
        float(np.linalg.norm(moon_arr)),
        flight_guess_s,
        raise_to_m,
    )
    #: Unknowns: liftoff shift (min), coast shift (tens of s), period burn, last burn,
    #: raise burn (m/s). Conditions: B.T, B.R, arrival time (km), and with a raise the
    #: first perigee's radius (km).
    x = np.array([0.0, 0.0, dv1 if n_loops > 1 else 0.0, dv2, dv0])
    fd = np.array([0.01, 0.1, 0.002, 0.002, 0.002])
    active = [k for k in range(5) if (k != 2 or n_loops > 1) and (k != 4 or raise_to_m)]
    n_eq = 4 if raise_to_m else 3

    def at(xx: FloatArray) -> tuple[float, float, FloatArray]:
        tl = t_launch + 60.0 * float(xx[0])
        ti = tl + coast_s + 10.0 * float(xx[1])
        return tl, ti, transfer.tli_state(parking_at(tl), ti, dv_inject)

    def evaluate(xx: FloatArray) -> tuple[FloatArray, dict[str, float | FloatArray], _Flight]:
        _, ti, y = at(xx)
        fl = _fly(
            tables,
            model,
            ti,
            y,
            n_loops,
            float(xx[2]),
            float(xx[3]),
            t_max,
            rtol,
            float(xx[4]) if raise_to_m else None,
        )
        bp = transfer.bplane(fl.enc.r, fl.enc.v, mu, k_hat)
        bt_s, br_s = transfer.b_target(bp, k_hat, target, mu)
        f = [
            (float(bp["bt"]) - bt_s) / 1000.0,
            (float(bp["br"]) - br_s) / 1000.0,
            (fl.enc.t - target.t_arrive) * float(bp["v_inf"]) / 1000.0,
        ]
        if raise_to_m:
            f.append((fl.perigees[0].r_m - raise_to_m) / 1000.0 if fl.perigees else 1e6)
        return np.array(f), bp, fl

    f, bp, fl = evaluate(x)  # a first guess that fails raises: no design this day
    iterations = 0
    converged = False
    for _ in range(max_iter):
        iterations += 1
        jac = np.zeros((n_eq, 5))
        try:
            for k in active:
                dx = np.zeros(5)
                dx[k] = fd[k]
                jac[:, k] = (evaluate(x + dx)[0] - f) / fd[k]
        except (ValueError, RuntimeError):
            break
        step = np.linalg.lstsq(jac, -f, rcond=None)[0]
        n_step = float(np.linalg.norm(step))
        if n_step > 10.0:
            step *= 10.0 / n_step
        try:
            f_new, bp_new, fl_new = evaluate(x + step)
        except (ValueError, RuntimeError):
            break
        x, f, bp, fl = x + step, f_new, bp_new, fl_new
        if (
            math.hypot(f[0], f[1]) < 0.1
            and abs(fl.enc.t - target.t_arrive) < 1.0
            and (not raise_to_m or abs(f[3]) < 1.0)
        ):
            converged = True
            break
    tl, ti, _ = at(x)
    peri_times = [ti] + [p.t for p in fl.perigees]
    min_peri = min(p.r_m for p in fl.perigees) if fl.perigees else park0.radius
    soi = _soi(tables, target.t_arrive)
    refused = None
    if not converged:
        refused = "the design does not converge"
    elif min_peri < r_min:
        refused = f"a perigee drops to {(min_peri - tables.r_earth_m) / 1000:.0f} km altitude"
    elif fl.min_moon_m < soi:
        refused = "the loops pass inside the Moon's sphere of influence before the last burn"
    return LoopDesign(
        t_launch=tl,
        coast_s=ti - tl,
        t_inject=ti,
        dv_inject_m_s=dv_inject,
        n_loops=n_loops,
        raise_to_m=raise_to_m,
        dv_raise_m_s=float(x[4]) if raise_to_m else 0.0,
        dv_period_m_s=float(x[2]),
        dv_final_m_s=float(x[3]),
        perigees=fl.perigees,
        apogees=fl.apogees,
        periods_d=[(b - a) / DAY for a, b in itertools.pairwise(peri_times)],
        min_perigee_alt_m=min_peri - tables.r_earth_m,
        min_moon_m=fl.min_moon_m,
        t_peri=fl.enc.t,
        r_peri_m=float(np.linalg.norm(fl.enc.r)),
        inc_deg=float(bp["inc_deg"]),
        miss_km=math.hypot(f[0], f[1]),
        dt_s=fl.enc.t - target.t_arrive,
        iterations=iterations,
        converged=converged,
        refused=refused,
    )


def _soi(tables: forces.Tables, t: float) -> float:
    d = float(np.linalg.norm(forces.body_state(tables, forces.MOON, np.array([t]))[0][:3]))
    return sphere_of_influence_m(d, tables.gm_earth, tables.gm_moon)


def loops_for(gm: float, r_p: float, v_p: float, t_inj: float, t_final: float) -> int:
    """The loop count whose two-body period is nearest the injection orbit's."""
    a1 = 1.0 / (2.0 / r_p - v_p**2 / gm)
    p1 = 2.0 * math.pi * math.sqrt(a1**3 / gm)
    return max(1, round((t_final - t_inj) / p1))


@dataclass(frozen=True, slots=True)
class Day:
    t_day: float  # the start of the day searched (ET)
    design: LoopDesign | None  # the cheapest usable one, else the last tried
    why_not: str | None  # None when the day is usable within the budget


def usable(d: LoopDesign, budget_m_s: float | None) -> str | None:
    """Why ``d`` cannot be flown, or None."""
    if d.refused is not None:
        return d.refused
    if budget_m_s is not None and d.lander_dv_m_s > budget_m_s:
        return (
            f"its burns add up to {d.lander_dv_m_s:.0f} m/s, over the {budget_m_s:.0f} m/s budget"
        )
    return None


def pick(t_day: float, tried: list[LoopDesign | str], budget_m_s: float | None) -> Day:
    """The day's cheapest usable design; ``tried`` holds designs or why one failed."""
    ok = [d for d in tried if isinstance(d, LoopDesign) and usable(d, budget_m_s) is None]
    if ok:
        return Day(t_day, min(ok, key=lambda d: d.lander_dv_m_s), None)
    designs = [d for d in tried if isinstance(d, LoopDesign)]
    if designs:
        best = min(designs, key=lambda d: (d.refused is not None, d.lander_dv_m_s))
        return Day(t_day, best, usable(best, budget_m_s))
    return Day(t_day, None, str(tried[-1]) if tried else "no launch instant that day")


def launch_period(days: list[Day]) -> list[tuple[float, float, int]]:
    """Runs of consecutive usable days with the same loop count: ``(first, last, loops)``."""
    runs: list[tuple[float, float, int]] = []
    for d in sorted(days, key=lambda d: d.t_day):
        if d.why_not is not None or d.design is None:
            continue
        n = d.design.n_loops
        if runs and runs[-1][2] == n and abs(d.t_day - runs[-1][1] - DAY) < 1.0:
            runs[-1] = (runs[-1][0], d.t_day, n)
        else:
            runs.append((d.t_day, d.t_day, n))
    return runs


# --- burns read from a reconstruction, in plain words ---------------------------------

#: A run of burn windows longer than this is a steady push (Peregrine's leak, or the
#: force model and the reconstruction parting near the Moon), not one burn.
BURN_MAX_S = 3 * 3600.0
#: The burn that leaves Earth fires below this distance from the Earth's centre.
LEAVE_WITHIN_M = 60_000e3
#: A burn at the arrival larger than this puts the lander into lunar orbit.
CAPTURE_M_S = 50.0


def name_burns(
    burns: list[Burn], t_arrive: float | None
) -> tuple[list[tuple[Burn, str]], list[Burn]]:
    """``(burns with a plain name, steady pushes)`` for burns found up to the arrival.

    Before the burn that leaves Earth (the largest one below 60,000 km, if the
    reconstruction holds it), a burn is named by where in the orbit it fired;
    after it, burns are numbered corrections; one at the arrival larger than
    50 m/s enters lunar orbit.
    """
    short = sorted((b for b in burns if b.end - b.start <= BURN_MAX_S), key=lambda b: b.t)
    steady = [b for b in burns if b.end - b.start > BURN_MAX_S]
    capture = None
    if t_arrive is not None:
        near = [
            b
            for b in short
            if b.start - 3600.0 <= t_arrive <= b.end + 3600.0 and b.dv_m_s > CAPTURE_M_S
        ]
        capture = near[0] if near else None
    low = [b for b in short if b.r_m < LEAVE_WITHIN_M and b is not capture]
    leave = max(low, key=lambda b: b.dv_m_s) if low else None
    out: list[tuple[Burn, str]] = []
    k = 0
    for b in short:
        if b is capture:
            name = "Entering lunar orbit"
        elif b is leave:
            name = "Leaving Earth for the Moon"
        elif leave is not None and b.t < leave.t:
            where = "highest" if b.r_m > 100_000e3 else "lowest"
            name = f"Burn near the {where} point of the orbit"
        else:
            k += 1
            name = f"Correction {k}"
        out.append((b, name))
    return out, steady
