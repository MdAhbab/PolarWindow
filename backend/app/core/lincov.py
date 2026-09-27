"""Correction burns on the way to the Moon: how large they may need to be (T2, C4).

A transfer never leaves TLI exactly as planned, the team never knows the
spacecraft's state exactly, and no burn fires exactly as commanded. Three
correction burns fix the arrival: TCM-1 a day after TLI, TCM-2 half-way, TCM-3
a day before arrival. Each one aims the estimated state at the planned
position at the planned arrival time (fixed-time targeting: the burn is
``-Phi_rv^-1 (Phi_rr dr + Phi_rv dv)`` with ``Phi`` the state transition
matrix from the burn to the arrival).

Two ways of working out the sizes, which must agree:

* **Linear.** The motion is linearised about the plan (a state transition
  matrix per stretch, each by central differences over that stretch alone) and
  the errors are pushed through it: the deviation at TLI, the knowledge error
  at each burn, the execution error of each burn. Execution errors grow with
  the burn, so they are drawn, not carried as a covariance (a Gaussian would
  understate the tail of the burn that follows a large one).
* **Monte Carlo.** ``n`` seeded samples flown through the full force model,
  each correction worked out from the sample's own estimated state with the
  same targeting, executed with errors drawn from Gates' model (C. R. Gates,
  *A simplified model of midcourse maneuver execution errors*, JPL TR
  32-504, 1963: magnitude and pointing errors, each with a part proportional
  to the burn and a fixed part), and the closest approach to the Moon found.

The 99th-percentile total comes with a bootstrap interval. The numbers are a
budget for the errors assumed, never a prediction of what a mission needs.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from app.core import forces, propagate, transfer
from app.core.vec import unit

FloatArray = npt.NDArray[np.float64]

DAY = 86_400.0
#: Finite-difference steps for the state transition matrix.
FD_M = 10.0
FD_M_S = 0.001


@dataclass(frozen=True, slots=True)
class Gates:
    """Execution errors, one sigma: proportional magnitude (fraction), fixed magnitude
    (m/s), proportional pointing (rad), fixed pointing (m/s)."""

    mag_prop: float
    mag_fixed_m_s: float
    point_prop_rad: float
    point_fixed_m_s: float


@dataclass(frozen=True, slots=True)
class Errors:
    """One-sigma errors per axis. ``tli_*`` in the TLI's radial, along, cross frame."""

    tli_pos_m: tuple[float, float, float]
    tli_vel_m_s: tuple[float, float, float]
    od_pos_m: float  # knowledge at each correction
    od_vel_m_s: float
    gates: Gates


@dataclass(frozen=True, slots=True)
class Plan:
    t_tli: float
    y_tli: FloatArray  # Earth-centred J2000 just after TLI
    t_arrive: float  # the planned closest approach to the Moon
    tcm_times: tuple[float, ...]


def default_times(t_tli: float, t_arrive: float) -> tuple[float, float, float]:
    """TCM-1 a day after TLI, TCM-2 half-way, TCM-3 a day before arrival."""
    return (t_tli + DAY, 0.5 * (t_tli + t_arrive), t_arrive - DAY)


def rtn(y: FloatArray) -> FloatArray:
    """Rows: radial, along-track (in-plane, perpendicular to radial), orbit normal."""
    r_hat = unit(y[:3])
    n_hat = unit(np.cross(y[:3], y[3:]))
    return np.array([r_hat, np.cross(n_hat, r_hat), n_hat])


def tli_covariance(y: FloatArray, errors: Errors) -> FloatArray:
    rot = rtn(y)
    p = np.zeros((6, 6))
    p[:3, :3] = rot.T @ np.diag(np.square(errors.tli_pos_m)) @ rot
    p[3:, 3:] = rot.T @ np.diag(np.square(errors.tli_vel_m_s)) @ rot
    return p


@dataclass
class Nominal:
    """The planned trajectory; state transition matrices between any two of its times,
    each by central differences over that stretch alone (products of matrices through
    the Moon's pull lose accuracy)."""

    tables: forces.Tables
    model: forces.Model
    traj: propagate.Trajectory
    rtol: float
    cache: dict[tuple[float, float], FloatArray]

    def state(self, t: float) -> FloatArray:
        return np.asarray(self.traj.at(t)[0], dtype=np.float64)

    def between(self, t1: float, t0: float) -> FloatArray:
        """Phi(t1, t0)."""
        key = (t1, t0)
        if key not in self.cache:
            y0 = self.state(t0)
            cols = []
            for k in range(6):
                h = FD_M if k < 3 else FD_M_S
                dy = np.zeros(6)
                dy[k] = h
                ends = [
                    propagate.propagate(
                        self.tables, self.model, t0, y0 + s * dy, t1, rtol=self.rtol
                    ).state[-1]
                    for s in (1.0, -1.0)
                ]
                cols.append((ends[0] - ends[1]) / (2.0 * h))
            self.cache[key] = np.stack(cols, axis=1)
        return self.cache[key]


def nominal(
    tables: forces.Tables, model: forces.Model, plan: Plan, *, rtol: float = 1e-11
) -> Nominal:
    """The planned trajectory from TLI to the arrival."""
    base = propagate.propagate(tables, model, plan.t_tli, plan.y_tli, plan.t_arrive, rtol=rtol)
    return Nominal(tables, model, base, rtol, {})


def guidance(nom: Nominal, t_burn: float, t_arrive: float) -> FloatArray:
    """(3, 6) ``G``: the burn is ``G @ estimated deviation`` (fixed-time position targeting)."""
    phi = nom.between(t_arrive, t_burn)
    return np.asarray(-np.linalg.solve(phi[:3, 3:], phi[:3, :]), dtype=np.float64)


def execution_errors(dv: FloatArray, g: Gates, rng: np.random.Generator) -> FloatArray:
    """Draws of Gates' model for commanded burns ``dv`` (n, 3)."""
    m = np.linalg.norm(dv, axis=1)
    u = np.where(m[:, None] > 0.0, dv / np.where(m > 0.0, m, 1.0)[:, None], [1.0, 0.0, 0.0])
    ref = np.where(np.abs(u[:, 2:3]) < 0.9, [0.0, 0.0, 1.0], [1.0, 0.0, 0.0])
    a = np.cross(u, ref)
    a /= np.linalg.norm(a, axis=1)[:, None]
    b = np.cross(u, a)
    n = rng.standard_normal((dv.shape[0], 4))
    along = g.mag_prop * m * n[:, 0] + g.mag_fixed_m_s * n[:, 1]
    side_sd = np.hypot(g.point_prop_rad * m, g.point_fixed_m_s)
    return np.asarray(
        along[:, None] * u + side_sd[:, None] * (n[:, 2:3] * a + n[:, 3:4] * b), dtype=np.float64
    )


def execution_error(dv: FloatArray, g: Gates, rng: np.random.Generator) -> FloatArray:
    """One draw of Gates' model for the commanded burn ``dv``."""
    out: FloatArray = execution_errors(np.asarray(dv, dtype=np.float64)[None, :], g, rng)[0]
    return out


def periapsis_radius(tables: forces.Tables, t: float, y: FloatArray) -> float:
    """Closest-approach radius of the osculating Moon-centred orbit through ``y`` at ``t``."""
    m = forces.body_state(tables, forces.MOON, np.array([t]))[0]
    r, v = y[:3] - m[:3], y[3:] - m[3:]
    mu = tables.gm_moon
    h = np.cross(r, v)
    e = float(np.linalg.norm(np.cross(v, h) / mu - r / np.linalg.norm(r)))
    return float(h @ h) / mu / (1.0 + e)


@dataclass(frozen=True, slots=True)
class Budget:
    """Sizes of each correction and their total, and the arrival altitude, per method."""

    tcm_times: tuple[float, ...]
    dv: FloatArray  # (n_samples, n_tcm) burn sizes, m/s
    periapsis_alt_m: FloatArray  # (n_samples,)

    @property
    def missed(self) -> int:
        """Runs with no close pass of the Moon before half a day after the planned one."""
        return int(np.count_nonzero(np.isnan(self.periapsis_alt_m)))

    def altitude_km(self, q: float) -> float:
        return float(np.nanpercentile(self.periapsis_alt_m, q)) / 1000.0

    @property
    def total(self) -> FloatArray:
        return np.asarray(self.dv.sum(axis=1), dtype=np.float64)

    def pct(self, q: float) -> tuple[list[float], float]:
        """``q``-th percentile of each burn and of the total."""
        return (
            [float(np.percentile(self.dv[:, k], q)) for k in range(self.dv.shape[1])],
            float(np.percentile(self.total, q)),
        )


def linear(
    tables: forces.Tables,
    nom: Nominal,
    plan: Plan,
    errors: Errors,
    *,
    samples: int = 100_000,
    seed: int = 0,
) -> Budget:
    """The same runs with the motion linearised about the plan: each stretch is its state
    transition matrix, the arrival radius its gradient. The errors are drawn as in the
    Monte Carlo (Gates' execution errors grow with the burn, which no Gaussian shows)."""
    rng = np.random.default_rng(seed)
    l0 = np.linalg.cholesky(tli_covariance(plan.y_tli, errors) + 1e-18 * np.eye(6))
    sd_od = np.array([errors.od_pos_m] * 3 + [errors.od_vel_m_s] * 3)
    x = rng.standard_normal((samples, 6)) @ l0.T
    t_prev = plan.t_tli
    sizes = np.zeros((samples, len(plan.tcm_times)))
    for j, t in enumerate(plan.tcm_times):
        x = x @ nom.between(t, t_prev).T
        g = guidance(nom, t, plan.t_arrive)
        dv = (x + sd_od * rng.standard_normal((samples, 6))) @ g.T
        sizes[:, j] = np.linalg.norm(dv, axis=1)
        x[:, 3:] += dv + execution_errors(dv, errors.gates, rng)
        t_prev = t
    x = x @ nom.between(plan.t_arrive, t_prev).T
    y_arr = nom.state(plan.t_arrive)
    rp0 = periapsis_radius(tables, plan.t_arrive, y_arr)
    jac = np.zeros(6)
    for k in range(6):
        h = FD_M if k < 3 else FD_M_S
        dy = np.zeros(6)
        dy[k] = h
        jac[k] = (
            periapsis_radius(tables, plan.t_arrive, y_arr + dy)
            - periapsis_radius(tables, plan.t_arrive, y_arr - dy)
        ) / (2.0 * h)
    return Budget(plan.tcm_times, sizes, rp0 + x @ jac - tables.r_moon_m)


def monte_carlo(
    tables: forces.Tables,
    model: forces.Model,
    nom: Nominal,
    plan: Plan,
    errors: Errors,
    *,
    samples: int = 1000,
    seed: int = 0,
    rtol: float = 1e-10,
    retarget: int = 2,
    progress: Callable[[int], None] | None = None,
) -> Budget:
    """``samples`` seeded runs through the full force model with the same targeting,
    each burn refined ``retarget`` times on the sample's estimated state."""
    rng = np.random.default_rng(seed)
    p0 = tli_covariance(plan.y_tli, errors)
    l0 = np.linalg.cholesky(p0 + 1e-18 * np.eye(6))
    sd_od = np.array([errors.od_pos_m] * 3 + [errors.od_vel_m_s] * 3)
    gs = [guidance(nom, t, plan.t_arrive) for t in plan.tcm_times]
    t_max = plan.t_arrive + 0.5 * DAY
    sizes = np.zeros((samples, len(plan.tcm_times)))
    alts = np.zeros(samples)
    for s in range(samples):
        y = plan.y_tli + l0 @ rng.standard_normal(6)
        t = plan.t_tli
        for j, tb in enumerate(plan.tcm_times):
            y = propagate.propagate(tables, model, t, y, tb, rtol=rtol).state[-1].copy()
            est = y - nom.state(tb) + sd_od * rng.standard_normal(6)
            dv = gs[j] @ est
            # The linear burn misses by its second-order terms: correct it on the estimated
            # state through the full model (the team retargets the same way).
            y_est = nom.state(tb) + est
            r_goal = nom.state(plan.t_arrive)[:3]
            rv = nom.between(plan.t_arrive, tb)[:3, 3:]
            for _ in range(retarget):
                y_try = y_est.copy()
                y_try[3:] += dv
                r_end = propagate.propagate(tables, model, tb, y_try, plan.t_arrive, rtol=rtol)
                dv = dv - np.linalg.solve(rv, r_end.state[-1, :3] - r_goal)
            sizes[s, j] = float(np.linalg.norm(dv))
            y[3:] += dv + execution_error(dv, errors.gates, rng)
            t = tb
        try:
            enc = transfer.encounter(tables, model, t, y, t_max)
            alts[s] = float(np.linalg.norm(enc.r)) - tables.r_moon_m
        except ValueError:  # no close pass before t_max: counted, never hidden
            alts[s] = math.nan
        if progress is not None:
            progress(s + 1)
    return Budget(plan.tcm_times, sizes, alts)


def bootstrap(values: FloatArray, q: float, *, n: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% interval of the ``q``-th percentile by resampling ``values``."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, values.size, size=(n, values.size))
    est = np.percentile(values[idx], q, axis=1)
    return float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))
