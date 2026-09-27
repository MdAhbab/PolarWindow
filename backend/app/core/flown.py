"""What a flown lunar launch did, read from its reconstructed trajectory (T2, D1).

From the first reconstructed state after TLI the trajectory is propagated
back to its perigee, which is where TLI fired (the burn is centred on the
perigee of the orbit it produces). That gives the TLI time and point, the
parking orbit's radius and, with the published liftoff time and the pad, the
ascent constant ``c`` of :mod:`app.core.launchwin`. The first close pass of
the Moon gives the flight time from TLI to arrival at the Moon.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.optimize import minimize_scalar

from app.core import forces, launchwin, propagate, transfer
from app.core.vec import unit

FloatArray = npt.NDArray[np.float64]

#: A close pass of the Moon closer than this counts as arrival.
ARRIVAL_M = 30_000e3


@dataclass(frozen=True, slots=True)
class FlownLaunch:
    t0: float  # published liftoff (ET)
    t_tli: float
    r_tli: FloatArray  # Earth-centred J2000
    dv_tli_m_s: float  # speed after TLI minus the circular parking orbit's
    r_park_m: float
    inc_deg: float  # of the post-TLI orbit to Earth's equator (J2000)
    c_rad: float
    tau_s: float
    t_arrive: float | None  # first closest approach to the Moon (ET)
    r_arrive_m: float | None
    arrival_from: str  # "reconstruction" or "propagated across a gap"

    @property
    def flight_s(self) -> float | None:
        return None if self.t_arrive is None else self.t_arrive - self.t_tli


def measure(
    tables: forces.Tables,
    state_at: Callable[[FloatArray], FloatArray],
    coverage: list[tuple[float, float]],
    t0: float,
    pad_j2000_at: Callable[[float], FloatArray],
) -> FlownLaunch:
    """``state_at(ets)``: Earth-centred J2000 states of the spacecraft (n, 6)."""
    first = coverage[0][0]
    y0 = state_at(np.array([first]))[0]

    def perigee(t: float, y: FloatArray) -> float:
        return float(y[:3] @ y[3:]) if float(y[:3] @ y[:3]) < (20_000e3) ** 2 else 1.0

    tr = propagate.propagate(
        tables, forces.Model(), first, y0, t0, events=[perigee], rtol=transfer.DESIGN_RTOL
    )
    if not tr.events or tr.events[0].size == 0:
        raise ValueError("no perigee between liftoff and the first reconstructed state")
    t_tli = float(tr.events[0][0])
    y_tli = tr.event_states[0][0]
    r_park = float(np.linalg.norm(y_tli[:3]))
    h = unit(np.cross(y_tli[:3], y_tli[3:]))
    n = math.sqrt(tables.gm_earth / r_park**3)
    p = unit(pad_j2000_at(t0))
    r_hat = unit(y_tli[:3])
    hp = launchwin.plane_normal(p, r_hat)
    c = launchwin.angle_along(p, r_hat, hp) - n * (t_tli - t0)

    t_arr, r_arr, how = _arrival(tables, state_at, coverage)
    return FlownLaunch(
        t0=t0,
        t_tli=t_tli,
        r_tli=np.asarray(y_tli[:3], dtype=np.float64),
        dv_tli_m_s=float(np.linalg.norm(y_tli[3:])) - math.sqrt(tables.gm_earth / r_park),
        r_park_m=r_park,
        inc_deg=math.degrees(math.acos(max(-1.0, min(1.0, float(h[2]))))),
        c_rad=launchwin.wrap(c),
        tau_s=t_tli - t0,
        t_arrive=t_arr,
        r_arrive_m=r_arr,
        arrival_from=how,
    )


def _arrival(
    tables: forces.Tables,
    state_at: Callable[[FloatArray], FloatArray],
    coverage: list[tuple[float, float]],
) -> tuple[float | None, float | None, str]:
    for a, b in coverage:
        ets = np.arange(a, b, 300.0)
        if ets.size < 3:
            continue
        moon = forces.body_state(tables, forces.MOON, ets)
        d = np.linalg.norm(state_at(ets)[:, :3] - moon[:, :3], axis=1)
        for i in range(1, ets.size - 1):
            if d[i] < ARRIVAL_M and d[i] <= d[i - 1] and d[i] <= d[i + 1]:

                def dist(t: float) -> float:
                    m = forces.body_state(tables, forces.MOON, np.array([t]))[0]
                    return float(np.linalg.norm(state_at(np.array([t]))[0, :3] - m[:3]))

                res = minimize_scalar(
                    dist,
                    bounds=(float(ets[i - 1]), float(ets[i + 1])),
                    method="bounded",
                    options={"xatol": 0.01},
                )
                return float(res.x), float(res.fun), "reconstruction"
        if float(d.min()) < ARRIVAL_M:
            continue
    # Not inside any covered stretch: propagate from the last state before a gap.
    for (_, b), nxt in zip(coverage, [*coverage[1:], None], strict=True):
        y = state_at(np.array([b]))[0]
        stop = nxt[0] if nxt is not None else b + 3 * 86_400.0
        try:
            enc = transfer.encounter(tables, forces.Model(), b, y, min(stop, tables.span[1]))
        except ValueError:
            continue
        if float(np.linalg.norm(enc.r)) < ARRIVAL_M:
            return enc.t, float(np.linalg.norm(enc.r)), "propagated across a gap"
    return None, None, "not found"
