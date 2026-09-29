"""Burns read from a flown lander's reconstruction, and its flight as planned (T2, C3/C4).

``burns`` finds where NASA's reconstruction leaves the force model up to the
arrival at the Moon (``core.phasing.find_burns``) and names each one in plain
words. ``planned_flight`` is a flight from leaving Earth to the first close pass
of the Moon with no burn in between that arrives where and when the flown one
did. It is the plan the flown corrections steered towards, and what the
correction budget (``core.lincov``) is worked out about. Synchronous: call on the SPICE thread.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

from app.core import forces, lincov, phasing, propagate, transfer
from app.core.flown import FlownLaunch
from app.data import catalogues
from app.services.ascent import coverage, states_of

FloatArray = npt.NDArray[np.float64]

DAY = 86_400.0
#: The planned departure is looked for this close to the flown one.
DEPARTURE_WITHIN_S = 6 * 3600.0
#: A planned departure lower than this would pass through the air: no plan.
MIN_PERIGEE_ALT_M = 150e3
#: Perigees farther than this from the Earth's centre are not departures.
LEAVE_WITHIN_M = 60_000e3

#: Errors assumed for the correction budget (one sigma). A vehicle whose user guide prints
#: its injection accuracy has the errors at leaving Earth that it gives put in place of the
#: assumed ones (``guide_for``); the lander makers publish no navigation or engine
#: figures, so every other error is assumed and said so.
ASSUMED = lincov.Errors(
    tli_pos_m=(1000.0, 1000.0, 1000.0),
    tli_vel_m_s=(0.5, 1.0, 0.5),
    od_pos_m=1000.0,
    od_vel_m_s=0.001,
    gates=lincov.Gates(
        mag_prop=0.01, mag_fixed_m_s=0.01, point_prop_rad=0.0175, point_fixed_m_s=0.01
    ),
)
ASSUMED_WORDS: tuple[tuple[str, str], ...] = (
    ("Leaving Earth, position", "1 km in each direction"),
    ("Leaving Earth, speed", "0.5 m/s up or down, 1 m/s along the path, 0.5 m/s sideways"),
    ("Where the team thinks the lander is, at each correction", "1 km and 1 mm/s"),
    ("How well a burn fires", "1 % of its size and 1 degree of pointing, plus 1 cm/s"),
)


@dataclass(frozen=True, slots=True)
class Guide:
    """A launch vehicle guide's published injection accuracy, in the row of the table nearest
    a departure for the Moon (its lunar transfer row when it has one, else its transfer
    orbit to geosynchronous)."""

    vehicle: str
    row: lincov.GuideRow
    orbit: str  # the guide's words for the row's orbit
    cited: str  # the guide, table and page
    sigma_assumed: bool  # the guide does not say how many standard deviations its ± is


def guide_for(vehicle_id: str | None) -> Guide | None:
    """The vehicle's published injection accuracy (``vehicles`` catalogue), or None when its
    guide prints none."""
    if vehicle_id is None:
        return None
    v = catalogues.load("vehicles").get(vehicle_id)
    if not v.injection_accuracy or v.injection_sigma is None:
        return None
    rows = v.injection_accuracy
    picked = (
        [r for r in rows if r.kind == "lunar_transfer"]
        or [
            r
            for r in rows
            if r.kind == "gto" and r.perigee_alt_km is not None and r.apogee_alt_km is not None
        ]
        or [r for r in rows if r.kind == "gto"]
    )
    if not picked:
        return None
    r = picked[0]
    row = lincov.GuideRow(
        r.perigee_alt_km,
        r.apogee_alt_km,
        r.perigee_pm_km,
        r.apogee_pm_km,
        r.inclination_pm_deg,
        v.injection_sigma,
    )
    return Guide(v.name, row, r.orbit, r.cited, "injection_sigma" in v.assumed_fields)


@dataclass(frozen=True, slots=True)
class Input:
    """One error the budget rests on, in words: ``basis`` says whether it is a published
    figure or an assumed one, and ``source`` where a published one is from."""

    what: str
    value: str
    basis: Literal["published", "assumed"]
    source: str | None


def _km(m: float) -> str:
    return f"{m / 1000.0:.2g} km"


def _speed(m_s: float) -> str:
    return f"{m_s:.1f} m/s" if m_s >= 1.0 else f"{m_s:.2g} m/s"


def _deviations(sigma: float) -> str:
    n = {1.0: "one", 3.0: "three"}.get(sigma, f"{sigma:g}")
    return f"{n} standard {'deviation' if sigma == 1.0 else 'deviations'}"


def input_words(
    errors: lincov.Errors, derived: list[lincov.Derived], guide: Guide | None
) -> list[Input]:
    """The errors the budget rests on, one row each: what the guide gave (``derived``, what
    ``lincov.from_guide`` put in place of the assumed values) with where it is from, and
    what is assumed."""
    if guide is None or not derived:
        return [Input(w, v, "assumed", None) for w, v in ASSUMED_WORDS]
    got = {d.axis for d in derived}
    row = guide.row
    pos, vel = errors.tli_pos_m, errors.tli_vel_m_s
    unsaid = (
        " The guide does not say how many standard deviations its figure is; three is taken."
        if guide.sigma_assumed
        else ""
    )
    cite = f"{guide.cited}; row: {guide.orbit}. "
    dev = _deviations(row.sigma)
    out: list[Input] = []
    if "pos_radial" in got:
        out.append(
            Input(
                "Leaving Earth, position up or down",
                _km(pos[0]),
                "published",
                f"{cite}The orbit’s lowest point within {row.perigee_pm_km:g} km at {dev}, so "
                f"one standard deviation is {_km(pos[0])}.{unsaid}",
            )
        )
        out.append(
            Input(
                "Leaving Earth, position along the path and sideways",
                f"{_km(pos[1])} each",
                "assumed",
                None,
            )
        )
    else:
        out.append(
            Input("Leaving Earth, position", f"{_km(pos[0])} in each direction", "assumed", None)
        )
    how = (
        "The orbit’s highest point within {pm:g} km at {dev}. The speed error at the lowest "
        "point that would move the highest point that far is {v} at one standard deviation, "
        "taken as the same at leaving Earth."
    )
    tilt = (
        "The orbit’s tilt within {pm:g}° at {dev}. The sideways speed error at the lowest "
        "point that would tilt it that far is {v} at one standard deviation, taken as the "
        "same at leaving Earth."
    )
    out.append(Input("Leaving Earth, speed up or down", _speed(vel[0]), "assumed", None))
    if "vel_along" in got:
        out.append(
            Input(
                "Leaving Earth, speed along the path",
                _speed(vel[1]),
                "published",
                cite + how.format(pm=row.apogee_pm_km, dev=dev, v=_speed(vel[1])) + unsaid,
            )
        )
    else:
        out.append(Input("Leaving Earth, speed along the path", _speed(vel[1]), "assumed", None))
    if "vel_cross" in got:
        out.append(
            Input(
                "Leaving Earth, speed sideways",
                _speed(vel[2]),
                "published",
                cite + tilt.format(pm=row.inclination_pm_deg, dev=dev, v=_speed(vel[2])) + unsaid,
            )
        )
    else:
        out.append(Input("Leaving Earth, speed sideways", _speed(vel[2]), "assumed", None))
    out += [Input(w, v, "assumed", None) for w, v in ASSUMED_WORDS[2:]]
    return out


def burns(
    mission_id: str, fl: FlownLaunch, tables: forces.Tables
) -> tuple[list[tuple[phasing.Burn, str]], list[phasing.Burn]]:
    """Named burns up to an hour after the first close pass of the Moon, and steady pushes."""
    st = states_of(mission_id)
    end = fl.t_arrive + 3600.0 if fl.t_arrive is not None else float("inf")
    found: list[phasing.Burn] = []
    for a, b in coverage(mission_id):
        if a >= end or min(b, end) - a < phasing.WINDOW_S:
            continue
        found += phasing.find_burns(tables, forces.Model(), st, a, min(b, end))
    return phasing.name_burns(found, fl.t_arrive)


@dataclass(frozen=True, slots=True)
class Planned:
    plan: lincov.Plan
    arrival: transfer.Encounter  # the planned first close pass, Moon-centred
    perigee_alt_m: float  # where the planned flight passes closest to Earth
    t_ref: float  # the reconstructed state it is worked out from


def planned_flight(
    mission_id: str, fl: FlownLaunch, tables: forces.Tables, named: list[tuple[phasing.Burn, str]]
) -> Planned | None:
    """The flight from leaving Earth to the Moon with no burn between, or None.

    NASA's reconstruction just before the lander entered lunar orbit (or before the
    gap the arrival falls in) is propagated back to where it passed closest to Earth,
    within six hours of the flown departure; that perigee is the planned departure.
    Forward from there, it arrives exactly where and when the flown one did. Its
    departure differs from the flown one by what the flown corrections changed.
    """
    if fl.t_arrive is None:
        return None
    leave = next((b for b, n in named if n == "Leaving Earth for the Moon"), None)
    capture = next((b for b, n in named if n == "Entering lunar orbit"), None)
    t_ref = capture.start if capture else fl.t_arrive
    covered = [(a, min(b, t_ref)) for a, b in coverage(mission_id) if a < t_ref]
    if not covered:
        return None
    t_ref = covered[-1][1]
    t_dep = leave.t if leave is not None else fl.t_tli
    model = forces.Model()
    y_ref = states_of(mission_id)(np.array([t_ref]))[0]
    goal = transfer.encounter(tables, model, t_ref, y_ref, fl.t_arrive + DAY)

    def perigee(t: float, y: FloatArray) -> float:
        return float(y[:3] @ y[3:])

    back = propagate.propagate(
        tables, model, t_ref, y_ref, t_dep - DEPARTURE_WITHIN_S, events=[perigee], rtol=1e-12
    )
    near = [
        (float(t), y)
        for t, y in zip(back.events[0], back.event_states[0], strict=True)
        if abs(float(t) - t_dep) <= DEPARTURE_WITHIN_S
        and float(np.linalg.norm(y[:3])) < LEAVE_WITHIN_M
    ]
    if not near:
        return None
    t_tli, y_tli = min(near, key=lambda x: abs(x[0] - t_dep))
    alt = float(np.linalg.norm(y_tli[:3])) - tables.r_earth_m
    if alt < MIN_PERIGEE_ALT_M:
        return None
    plan = lincov.Plan(
        t_tli, np.asarray(y_tli, dtype=np.float64), goal.t, lincov.default_times(t_tli, goal.t)
    )
    return Planned(plan, goal, alt, t_ref)


@dataclass(frozen=True, slots=True)
class Budget:
    planned: Planned
    linear: lincov.Budget
    runs: lincov.Budget
    #: The errors it was worked out for, and which of them the vehicle's guide gave.
    errors: lincov.Errors
    derived: list[lincov.Derived]


def budget(
    mission_id: str,
    fl: FlownLaunch,
    tables: forces.Tables,
    named: list[tuple[phasing.Burn, str]],
    *,
    guide: Guide | None = None,
    samples: int = 1000,
    seed: int = 0,
    progress: Callable[[int], None] | None = None,
) -> Budget | None:
    """The correction budget about the planned flight, linear and by seeded runs: with the
    errors at leaving Earth that the vehicle's ``guide`` gives, in place of the assumed
    ones, when there is one."""
    planned = planned_flight(mission_id, fl, tables, named)
    if planned is None:
        return None
    errors = ASSUMED
    derived: list[lincov.Derived] = []
    if guide is not None:
        errors, derived = lincov.from_guide(
            ASSUMED, guide.row, planned.plan.y_tli, tables.gm_earth, tables.r_earth_m
        )
    model = forces.Model()
    nom = lincov.nominal(tables, model, planned.plan)
    lin = lincov.linear(tables, nom, planned.plan, errors, seed=seed)
    runs = lincov.monte_carlo(
        tables, model, nom, planned.plan, errors, samples=samples, seed=seed, progress=progress
    )
    return Budget(planned, lin, runs, errors, derived)
