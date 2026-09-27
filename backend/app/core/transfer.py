"""Direct transfers from a parking orbit to the Moon (T2, C2).

The patched-conic guess (``patched_conic``) puts the TLI point on the far
side of the Earth from the Moon's arrival position and gives a tangential
speed. The n-body correction then adjusts three unknowns: the liftoff time
(which turns the parking orbit's plane with the Earth), the coast to TLI
(where along the circular parking orbit TLI fires) and the speed TLI adds,
until the trajectory reaches the Moon with the wanted closest-approach
radius, inclination to the Moon's equator and time,
expressed as the B-plane components ``B.T``, ``B.R`` (Kizner's
target plane, as in Vallado, *Fundamentals of Astrodynamics*, 4th ed.,
section 12.6) and the time of closest approach: all three vary smoothly with
the unknowns, where the closest-approach radius itself does not. The plane
is steered by the liftoff time, not by a sideways push at TLI: for a
transfer of nearly 180 degrees such a push barely moves the arrival (TLI
point and arrival lie on the line where the two planes meet), so the
correction would find a far, costly answer. Newton steps use a forward-difference
Jacobian; the Moon is a point mass here,
which moves the arrival by metres, not kilometres (its harmonics act only
inside ten lunar radii, for about two hours of a four-day trip).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.optimize import brentq

from app.core import forces, propagate
from app.core.vec import rotate, unit

FloatArray = npt.NDArray[np.float64]

#: Closest approach is looked for only this close to the Moon.
ENCOUNTER_M = 150_000e3
#: Relative tolerance of the design integrations (the validation uses 1e-12).
DESIGN_RTOL = 1e-10


@dataclass(frozen=True, slots=True)
class Target:
    t_arrive: float  # ET of closest approach to the Moon
    r_peri_m: float  # closest-approach radius from the Moon's centre
    inc_deg: float  # to the Moon's equator (MOON_PA)


@dataclass(frozen=True, slots=True)
class Parking:
    """A circular parking orbit through ``r0`` (Earth-centred J2000, m) at ``t0``."""

    t0: float
    r0: FloatArray
    h: FloatArray  # unit normal; the orbit moves counter-clockwise about it
    gm: float

    @property
    def radius(self) -> float:
        return float(np.linalg.norm(self.r0))

    @property
    def n(self) -> float:
        return math.sqrt(self.gm / self.radius**3)

    @property
    def period(self) -> float:
        return 2.0 * math.pi / self.n

    def state(self, t: float) -> FloatArray:
        r = rotate(self.r0, self.h, self.n * (t - self.t0))
        v = math.sqrt(self.gm / self.radius) * unit(np.cross(self.h, r))
        return np.concatenate([r, v])

    def time_at(self, direction: FloatArray, after: float) -> float:
        """First time from ``after`` the orbit passes ``direction`` projected on its plane."""
        d = direction - float(direction @ self.h) * self.h
        r = self.state(after)[:3]
        ang = math.atan2(float(np.cross(r, d) @ self.h), float(r @ d)) % (2.0 * math.pi)
        return after + ang / self.n


def patched_conic(
    r_park_m: float, r_moon_m: float, flight_s: float, gm: float
) -> tuple[float, float]:
    """``(true anomaly at the Moon's distance, perigee speed)`` of the Earth-centred ellipse
    that leaves perigee ``r_park`` and reaches ``r_moon`` in ``flight_s``; the Moon's pull is
    left out (it is the guess the n-body correction starts from)."""

    def shape(r_a: float) -> tuple[float, float, float]:
        a = 0.5 * (r_park_m + r_a)
        e = (r_a - r_park_m) / (r_a + r_park_m)
        nu = math.acos(min(1.0, max(-1.0, (a * (1 - e * e) / r_moon_m - 1.0) / e)))
        return a, e, nu

    def t_to(r_a: float) -> float:
        a, e, nu = shape(r_a)
        big_e = 2.0 * math.atan(math.sqrt((1 - e) / (1 + e)) * math.tan(nu / 2.0))
        return (big_e - e * math.sin(big_e)) / math.sqrt(gm / a**3)

    lo, hi = r_moon_m * 1.000001, r_moon_m * 20.0
    r_a = (
        lo
        if t_to(lo) <= flight_s
        else float(brentq(lambda x: t_to(x) - flight_s, lo, hi, xtol=1.0))
    )
    a, _, nu = shape(r_a)
    return nu, math.sqrt(gm * (2.0 / r_park_m - 1.0 / a))


@dataclass(frozen=True, slots=True)
class Design:
    t_launch: float  # liftoff (ET)
    coast_s: float  # liftoff to TLI
    t_tli: float
    r_tli: FloatArray  # Earth-centred J2000, m
    v_tli: FloatArray  # m/s
    dv_tli_m_s: float  # added to the circular parking orbit's speed, along it
    t_peri: float
    r_peri_m: float
    inc_deg: float
    v_inf_m_s: float
    miss_km: float  # remaining B-plane miss
    dt_s: float  # remaining arrival-time miss
    iterations: int
    converged: bool


@dataclass(frozen=True, slots=True)
class Encounter:
    t: float
    r: FloatArray  # Moon-centred J2000 at closest approach
    v: FloatArray


def moon_pole(tables: forces.Tables, t: float) -> FloatArray:
    """The Moon's rotation pole (MOON_PA z) in J2000 at ``t``."""
    u = (t - tables.t0) / tables.dt
    i = min(max(int(math.floor(u)), 0), tables.moon_pa.shape[0] - 2)
    s = u - i
    m = (1.0 - s) * tables.moon_pa[i] + s * tables.moon_pa[i + 1]
    return unit(m[2])


def bplane(
    r: FloatArray, v: FloatArray, mu: float, k_hat: FloatArray
) -> dict[str, float | FloatArray]:
    """B-plane of the osculating Moon-centred hyperbola through ``(r, v)``."""
    h = np.cross(r, v)
    h_hat = unit(h)
    rn = float(np.linalg.norm(r))
    e_vec = np.cross(v, h) / mu - r / rn
    e = float(np.linalg.norm(e_vec))
    energy = float(v @ v) / 2.0 - mu / rn
    if e <= 1.0 or energy <= 0.0:
        raise ValueError("the arrival is not a hyperbola about the Moon")
    v_inf = math.sqrt(2.0 * energy)
    e_hat = e_vec / e
    s_hat = unit(e_hat / e + math.sqrt(e * e - 1.0) / e * np.cross(h_hat, e_hat))
    t_hat = unit(np.cross(s_hat, k_hat))
    r_hat = np.cross(s_hat, t_hat)
    b = float(np.linalg.norm(h)) / v_inf
    b_vec = b * np.cross(s_hat, h_hat)
    return {
        "bt": float(b_vec @ t_hat),
        "br": float(b_vec @ r_hat),
        "v_inf": v_inf,
        "s_hat": s_hat,
        "t_hat": t_hat,
        "r_hat": r_hat,
        "rp": float(np.linalg.norm(h)) ** 2 / mu / (1.0 + e),
        "inc_deg": math.degrees(math.acos(max(-1.0, min(1.0, float(h_hat @ k_hat))))),
    }


def b_target(
    bp: dict[str, float | FloatArray], k_hat: FloatArray, target: Target, mu: float
) -> tuple[float, float]:
    """``(B.T, B.R)`` for the wanted radius and inclination, the branch nearest the current one."""
    v_inf = float(bp["v_inf"])
    b = target.r_peri_m * math.sqrt(1.0 + 2.0 * mu / (target.r_peri_m * v_inf**2))
    rk = float(np.asarray(bp["r_hat"]) @ k_hat)
    c = -math.cos(math.radians(target.inc_deg)) / rk if abs(rk) > 1e-12 else 0.0
    c = max(-1.0, min(1.0, c))
    th = math.acos(c)
    now = math.atan2(float(bp["br"]), float(bp["bt"]))
    best = min((th, -th), key=lambda x: abs(math.remainder(x - now, 2 * math.pi)))
    return b * math.cos(best), b * math.sin(best)


def encounter(
    tables: forces.Tables, model: forces.Model, t1: float, y1: FloatArray, t_max: float
) -> Encounter:
    """Closest approach to the Moon between ``t1`` and ``t_max``."""

    def g(t: float, y: FloatArray) -> float:
        m = forces.body_state(tables, forces.MOON, np.array([t]))[0]
        d = y[:3] - m[:3]
        if float(d @ d) > ENCOUNTER_M**2:
            return -1.0
        return float(d @ (y[3:] - m[3:]))

    g.terminal = True  # type: ignore[attr-defined]
    g.direction = 1.0  # type: ignore[attr-defined]
    tr = propagate.propagate(tables, model, t1, y1, t_max, events=[g], rtol=DESIGN_RTOL)
    if not tr.events or tr.events[0].size == 0:
        raise ValueError("the trajectory does not come near the Moon")
    t = float(tr.events[0][0])
    y = tr.event_states[0][0]
    m = forces.body_state(tables, forces.MOON, np.array([t]))[0]
    return Encounter(t, y[:3] - m[:3], y[3:] - m[3:])


def tli_state(parking: Parking, t_tli: float, dv_along: float) -> FloatArray:
    """The state just after TLI: the parking state with speed added along the orbit."""
    y = parking.state(t_tli)
    return np.concatenate([y[:3], y[3:] * (1.0 + dv_along / float(np.linalg.norm(y[3:])))])


def guess(
    tables: forces.Tables, parking: Parking, t_arrive: float, flight_s: float, earliest: float
) -> tuple[float, float]:
    """``(t_tli, dv_along)`` from the patched conic, with the TLI point in the parking plane,
    at the first pass of that point from ``earliest``."""
    moon = forces.body_state(tables, forces.MOON, np.array([t_arrive]))[0][:3]
    nu, v_p = patched_conic(parking.radius, float(np.linalg.norm(moon)), flight_s, parking.gm)
    m_in = moon - float(moon @ parking.h) * parking.h
    tli_dir = rotate(unit(m_in), parking.h, -nu)
    return parking.time_at(tli_dir, earliest), v_p - math.sqrt(parking.gm / parking.radius)


def design(
    tables: forces.Tables,
    target: Target,
    parking_at: Callable[[float], Parking],
    t_launch: float,
    coast_s: float,
    dv_along: float,
    *,
    model: forces.Model | None = None,
    max_iter: int = 25,
) -> Design:
    """Correct the liftoff time, the coast to TLI and the TLI speed to reach ``target``.

    ``parking_at(t_launch)`` is the parking orbit a liftoff at ``t_launch`` reaches:
    moving the liftoff turns its plane with the Earth (the sideways control), the coast
    moves the TLI point along it, and the speed sets the arrival time.
    """
    model = model or forces.Model()
    mu = tables.gm_moon
    t_max = target.t_arrive + 2.0 * 86_400.0
    k_hat = moon_pole(tables, target.t_arrive)
    #: Unknowns: liftoff shift in minutes, coast shift in tens of seconds, TLI speed in m/s.
    x = np.array([0.0, 0.0, dv_along])
    fd = np.array([0.01, 0.1, 0.01])
    scale = np.array([60.0, 10.0])

    def at(xx: FloatArray) -> tuple[float, float, FloatArray]:
        tl = t_launch + scale[0] * float(xx[0])
        tt = tl + coast_s + scale[1] * float(xx[1])
        return tl, tt, tli_state(parking_at(tl), tt, float(xx[2]))

    def evaluate(xx: FloatArray) -> tuple[FloatArray, dict[str, float | FloatArray], Encounter]:
        _, tt, y = at(xx)
        enc = encounter(tables, model, tt, y, t_max)
        bp = bplane(enc.r, enc.v, mu, k_hat)
        bt_s, br_s = b_target(bp, k_hat, target, mu)
        scale_t = float(bp["v_inf"]) / 1000.0  # seconds to km at the arrival speed
        f = np.array(
            [
                (float(bp["bt"]) - bt_s) / 1000.0,
                (float(bp["br"]) - br_s) / 1000.0,
                (enc.t - target.t_arrive) * scale_t,
            ]
        )
        return f, bp, enc

    f, bp, enc = evaluate(x)
    iterations = 0
    converged = False
    for _ in range(max_iter):
        iterations += 1
        jac = np.empty((3, 3))
        for k in range(3):
            dx = np.zeros(3)
            dx[k] = fd[k]
            jac[:, k] = (evaluate(x + dx)[0] - f) / fd[k]
        step = np.linalg.lstsq(jac, -f, rcond=None)[0]
        # Keep a step inside the region where the linear model holds.
        n_step = float(np.linalg.norm(step))
        if n_step > 20.0:
            step *= 20.0 / n_step
        x = x + step
        f, bp, enc = evaluate(x)
        if math.hypot(f[0], f[1]) < 0.1 and abs(enc.t - target.t_arrive) < 1.0:
            converged = True
            break
    tl, tt, y = at(x)
    return Design(
        t_launch=tl,
        coast_s=tt - tl,
        t_tli=tt,
        r_tli=y[:3],
        v_tli=y[3:],
        dv_tli_m_s=float(x[2]),
        t_peri=enc.t,
        r_peri_m=float(np.linalg.norm(enc.r)),
        inc_deg=float(bp["inc_deg"]),
        v_inf_m_s=float(bp["v_inf"]),
        miss_km=math.hypot(f[0], f[1]),
        dt_s=enc.t - target.t_arrive,
        iterations=iterations,
        converged=converged,
    )
