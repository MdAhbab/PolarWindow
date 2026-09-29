"""The propagator against NASA's reconstructed CLPS trajectories (plan C1).

Run: ``make validate-trip`` (or ``uv run python -m app.tests.golden.validate_trip``).
Prints the table that goes into docs/validation.md; the golden test
``test_propagate_vs_clps.py`` pins the acceptance numbers from the same code.

Method. Along each reconstruction, the acceleration the reconstruction implies
(five-point difference of its velocity) is compared with the force model's
every ``SCAN_S``. Where the two differ by more than ``QUIET_M_S2`` the lander
was firing an engine or thrusters (or leaking); a *quiet stretch* is a run of
samples below it that also holds over every half hour between the samples (the
reconstruction's state propagated ``WINDOW_S`` and compared with it: a burn that
lasts a moment falls between samples and shows only there), trimmed by ``EDGE_S``
at each end. From the start of each quiet stretch the reconstructed state is
propagated for 24 h and 72 h (or to the end of the stretch if shorter) and the
position is compared with the reconstruction. Nothing is fitted: no
area-to-mass ratio, no scale factor.

What is left over when the model has nothing more to give is the reconstruction's
own unmodelled acceleration. ``residual_character``, ``through_burns`` and
``block_accelerations`` take it apart for IM-2's first day in cruise (the row that
missed by 4.6 km): the burns inside the stretch, Earth's non-zonal gravity, and an
acceleration that is steady inside each half hour of the reconstruction's clock and
steps between them.
"""

from __future__ import annotations

import itertools
import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp
from scipy.optimize import minimize_scalar

from app.config import get_settings
from app.core import forces, phasing, propagate, spice
from app.core.gravity import Field
from app.data.gravity import moon_field

FloatArray = npt.NDArray[np.float64]

SCAN_S = 600.0
QUIET_M_S2 = 1e-5
EDGE_S = 1800.0
#: Each half hour is also propagated whole: more than ``QUIET_M_S2`` over it on average
#: (0.018 m/s) holds a burn the samples missed.
WINDOW_S = 1800.0
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

#: The first day of IM-2's cruise: the stretch the earlier scan called quiet.
IM2_FIRST_DAY = "2025-02-27T01:51:09"
#: Blue Ghost's first quiet day, for comparison.
BG_QUIET_DAY = "2025-01-16T07:32:36"

MOON_R_M = 1_737_400.0
#: Stretches of a lunar orbit with no burn in them, for the field study: mission, start, end (UTC),
#: at most this many passes (``None``: all), and what the orbit is. Blue Ghost's first orbit
#: (157 x 5,700 km, 8 h) has 12 closest passes between its capture and its next burn.
LUNAR_STRETCHES: tuple[tuple[str, str, str, int | None, str], ...] = (
    ("blue-ghost-m1", "2025-02-14T02:00:00", "2025-02-18T08:00:00", None, "157 x 5,700 km"),
    ("blue-ghost-m1", "2025-02-18T10:00:00", "2025-02-24T06:00:00", 24, "114 x 175 km"),
    ("im-2", "2025-03-03T13:30:00", "2025-03-06T13:00:00", 24, "about 100 km"),
    ("lro", "2025-03-20T00:01:00", "2025-03-22T00:00:00", 24, "80 to 100 km"),
)
#: Moon's field degrees compared (0 is a point mass, what the burn finder uses).
FIELD_DEGREES = (0, 50, 100, 200)

_ATOL = np.array([propagate.ATOL_M] * 3 + [propagate.ATOL_M_S] * 3)


@dataclass
class Arc:
    mission: str
    start: str
    hours: float
    where: str  # "cruise" or "lunar orbit"
    moon_degree: int
    error_km: float
    error_km_srp: float | None  # with an assumed Cr A/m = 0.01 m^2/kg
    #: Median size of the acceleration the reconstruction has along the arc and the force
    #: model has not (m/s^2): what the error is made of.
    residual_m_s2: float | None = None


@dataclass
class Scan:
    mission: str
    samples: int
    residual_median_m_s2: float
    residual_p90_m_s2: float
    quiet_fraction: float
    quiet_stretches_h: list[float]
    #: Half hours the samples called quiet that hold a burn (the whole half hour leaves
    #: the model by more than QUIET_M_S2 on average).
    burns_between_samples: int = 0
    window_dv_median_m_s: float | None = None


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


def _states(naif: int, origin: int, ets: FloatArray) -> FloatArray:
    centre = "EARTH" if origin == forces.EARTH else "MOON"
    return spice.states(str(naif), centre, spice.J2000, "NONE", np.atleast_1d(ets))


def _windows(
    tab: forces.Tables, model: forces.Model, naif: int, a: float, b: float
) -> tuple[list[tuple[float, float]], list[float]]:
    """Half hours from ``a`` to ``b`` over which the reconstruction leaves the model by more
    than ``QUIET_M_S2`` on average, and every half hour's velocity difference (m/s)."""
    if b - a < WINDOW_S:
        return [], []
    starts = np.unique(np.append(np.arange(a, b - WINDOW_S, WINDOW_S), b - WINDOW_S))
    ys = _states(naif, forces.EARTH, np.concatenate([starts, starts + WINDOW_S]))
    n = starts.size
    bad, dvs = [], []
    for i, t in enumerate(starts):
        tr = propagate.propagate(tab, model, float(t), ys[i], float(t) + WINDOW_S, rtol=1e-11)
        dv = float(np.linalg.norm(tr.state[-1, 3:] - ys[n + i, 3:]))
        dvs.append(dv)
        if dv > QUIET_M_S2 * WINDOW_S:
            bad.append((float(t), float(t) + WINDOW_S))
    return bad, dvs


def scan(
    mission: str, degree: int = 200, *, windows: bool = True
) -> tuple[Scan, list[tuple[float, float]]]:
    """Residual acceleration along the reconstruction, and its quiet stretches (ET).

    ``windows=False`` leaves out the half-hour check (a burn that lasts a moment is then
    only found if a sample falls in it), which is enough for the size of the residual."""
    naif, cov = _load(mission)
    field = moon_field(degree)
    all_res: list[FloatArray] = []
    all_dv: list[float] = []
    between = 0
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
        bad, dvs = _windows(tab, model, naif, a, b) if windows else ([], [])
        all_dv.extend(dvs)
        in_bad = np.array([any(lo <= t <= hi for lo, hi in bad) for t in ets])
        between += int(
            sum(1 for lo, hi in bad if np.all(res[(ets >= lo) & (ets <= hi)] < QUIET_M_S2))
        )
        ok = (res < QUIET_M_S2) & ~in_bad
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
            burns_between_samples=between,
            window_dv_median_m_s=float(np.median(all_dv)) if all_dv else None,
        ),
        quiet,
    )


def _setup(
    mission: str,
    et0: float,
    et1: float,
    *,
    degree: int,
    cr_am: float = 0.0,
    earth: Field | None = None,
) -> tuple[int, forces.Tables, forces.Model, int, float]:
    """Kernels, body tables and the force model for an arc; the integration is about the Moon
    when the reconstruction starts inside its sphere of influence, else about the Earth."""
    naif, _ = _load(mission)
    tab = propagate.environment(et0, et1)
    y_e = _states(naif, forces.EARTH, np.array([et0]))[0]
    moon = forces.body_state(tab, forces.MOON, np.array([et0]))[0]
    d_moon = float(np.linalg.norm(y_e[:3] - moon[:3]))
    origin = forces.MOON if d_moon < MOON_ORIGIN_M else forces.EARTH
    model = forces.Model(
        origin=origin, moon_field=moon_field(degree), cr_am=cr_am, earth_field=earth
    )
    return naif, tab, model, origin, d_moon


def arc(
    mission: str,
    et0: float,
    hours: float,
    *,
    degree: int = 50,
    cr_am: float = 0.0,
    earth: Field | None = None,
) -> tuple[float, str, float]:
    """Propagate the reconstruction's state at ``et0`` for ``hours``; position error (m).

    ``earth`` is the Earth's field (default EGM2008 to degree 8; ``forces.earth_zonal(6)``
    is J2..J6 alone, the model before the non-zonal terms were added)."""
    et1 = et0 + hours * 3600.0
    naif, tab, model, origin, d_moon = _setup(
        mission, et0, et1, degree=degree, cr_am=cr_am, earth=earth
    )
    y0 = _states(naif, origin, np.array([et0]))[0]
    tr = propagate.propagate(tab, model, et0, y0, et1)
    truth = _states(naif, origin, np.array([et1]))[0]
    where = "lunar orbit" if origin == forces.MOON else "cruise"
    return float(np.linalg.norm(tr.state[-1, :3] - truth[:3])), where, d_moon


def arc_residual(mission: str, et0: float, hours: float, *, degree: int = 50) -> float:
    """Median size (m/s^2) of the acceleration the reconstruction has along an arc and the
    force model has not."""
    et1 = et0 + hours * 3600.0
    naif, tab, model, origin, _ = _setup(mission, et0, et1, degree=degree)
    ets = np.arange(et0 + 60.0, et1 - 60.0, SCAN_S)
    res = propagate.residual_acceleration(
        tab,
        model,
        ets,
        _states(naif, origin, ets),
        state_at=lambda t: _states(naif, origin, t),
    )
    return float(np.median(res))


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


def _arc_row(mission: str, et0: float, hours: float, degree: int) -> Arc:
    err, where, _ = arc(mission, et0, hours, degree=degree)
    err_srp, _, _ = arc(mission, et0, hours, degree=degree, cr_am=0.01)
    return Arc(
        mission,
        spice.et_to_utc(et0, precision=0),
        round(hours, 2),
        where,
        degree,
        round(err / 1000.0, 3),
        round(err_srp / 1000.0, 3),
        arc_residual(mission, et0, hours, degree=degree),
    )


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
                        out.append(_arc_row(mission, t, hours, deg))
                    taken[where] += 1
                t += hours * 3600.0
        if hours != HOURS[0]:
            continue
        for place in ("cruise", "lunar orbit"):
            # No stretch here is a day long (IM-1; IM-2's cruise once its corrections are
            # left out): report the longest one to its end.
            if any(a.hours == HOURS[0] and a.where == place for a in out):
                continue
            mine = [q for q in quiet if _where(mission, q[0]) == _where(mission, q[1]) == place]
            if not mine:
                continue
            lo, hi = max(mine, key=lambda q: q[1] - q[0])
            out.append(
                _arc_row(mission, lo, (hi - lo) / 3600.0, 100 if place == "lunar orbit" else 50)
            )
    return out


def residual_character(mission: str, et0: float, hours: float) -> dict[str, float]:
    """What the leftover acceleration along a stretch looks like (m/s^2 unless said): its
    mean size, the size of its mean (a steady push keeps them equal), the mean push away
    from the Sun and the ``Cr A/m`` sunlight pressure would need for it, the median angle
    between it and the direction away from the Sun (deg; sunlight pressure is 0), and the
    median turn of its hourly mean from one hour to the next (deg)."""
    naif, _ = _load(mission)
    ets = np.arange(et0, et0 + hours * 3600.0, SCAN_S)
    tab = propagate.environment(et0 - 3600.0, et0 + hours * 3600.0 + 3600.0)
    model = forces.Model(moon_field=moon_field(50))
    ys = _states(naif, forces.EARTH, ets)
    res = propagate.residual_acceleration_vectors(
        tab, model, ets, ys, state_at=lambda t: _states(naif, forces.EARTH, t)
    )
    sun = spice.states("SUN", "EARTH", spice.J2000, "NONE", ets)[:, :3] - ys[:, :3]
    toward = sun / np.linalg.norm(sun, axis=1)[:, None]
    away = -np.einsum("ij,ij->i", res, toward)
    cos = away / np.linalg.norm(res, axis=1)
    per_h = int(3600.0 / SCAN_S)
    hourly = [res[i : i + per_h].mean(axis=0) for i in range(0, len(res) - per_h + 1, per_h)]
    turns = [
        float(np.degrees(np.arccos(np.clip(a @ b / np.linalg.norm(a) / np.linalg.norm(b), -1, 1))))
        for a, b in itertools.pairwise(hourly)
    ]
    au = float(np.mean(np.linalg.norm(sun, axis=1))) / forces.AU_M
    return {
        "mean_size": float(np.mean(np.linalg.norm(res, axis=1))),
        "size_of_mean": float(np.linalg.norm(res.mean(axis=0))),
        "away_from_sun": float(np.mean(away)),
        "cr_am_needed": float(np.mean(away)) * au**2 / (forces.TSI_W_M2 / forces.C_M_S),
        "median_angle_from_away_deg": float(np.median(np.degrees(np.arccos(np.clip(cos, -1, 1))))),
        "hourly_turn_deg": float(np.median(turns)),
    }


def _flow(
    tab: forces.Tables,
    model: forces.Model,
    y0: FloatArray,
    et0: float,
    et1: float,
    *,
    impulses: dict[float, FloatArray] | None = None,
    blocks: tuple[FloatArray, FloatArray] | None = None,
) -> FloatArray:
    """The state at ``et1`` from ``y0`` at ``et0``, with velocity changes ``impulses`` (ET ->
    m/s vector) added at their instants and, if ``blocks = (edges, accelerations)``, a
    constant extra acceleration in each ``[edges[k], edges[k + 1])`` (m/s^2). The
    integration restarts at every instant where something changes."""
    f0 = forces.derivatives(tab, model)
    imp = impulses or {}
    edges = blocks[0] if blocks is not None else np.empty(0)
    cuts = sorted({et0, et1, *imp, *(float(e) for e in edges if et0 < e < et1)})
    y = np.asarray(y0, dtype=np.float64).copy()
    for a, b in itertools.pairwise(cuts):
        push = np.zeros(3)
        if blocks is not None:
            push = blocks[1][max(int(np.searchsorted(edges, 0.5 * (a + b), side="right")) - 1, 0)]

        def f(t: float, s: FloatArray, push: FloatArray = push) -> FloatArray:
            out = f0(t, s)
            out[3:] += push
            return out

        sol = solve_ivp(f, (a, b), y, method="DOP853", rtol=propagate.RTOL, atol=_ATOL)
        y = np.asarray(sol.y[:, -1], dtype=np.float64)
        if b in imp:
            y = y.copy()
            y[3:] += imp[b]
    return y


def _burns(
    mission: str, tab: forces.Tables, model: forces.Model, et0: float, et1: float
) -> list[phasing.Burn]:
    naif, _ = _load(mission)
    return phasing.find_burns(
        tab,
        model,
        lambda t: _states(naif, forces.EARTH, t),
        et0,
        et1,
        window_s=WINDOW_S,
        threshold_m_s=QUIET_M_S2 * WINDOW_S,
    )


def through_burns(mission: str, et0: float, hours: float, *, degree: int = 50) -> dict[str, Any]:
    """An arc in cruise that holds burns: the position error without them and with each
    applied as one velocity change where ``phasing.find_burns`` puts it. Each burn's size is
    read from the reconstruction, so this is an input to the propagation, not a prediction."""
    et1 = et0 + hours * 3600.0
    naif, tab, model, origin, _ = _setup(mission, et0, et1, degree=degree)
    if origin != forces.EARTH:
        raise ValueError("through_burns is for an arc that starts in cruise")
    burns = _burns(mission, tab, model, et0, et1)
    y0 = _states(naif, forces.EARTH, np.array([et0]))[0]
    truth = _states(naif, forces.EARTH, np.array([et1]))[0]
    plain = _flow(tab, model, y0, et0, et1)
    with_burns = _flow(tab, model, y0, et0, et1, impulses={b.t: b.dv for b in burns})
    return {
        "start": spice.et_to_utc(et0, precision=0),
        "hours": hours,
        "burns": [
            {"utc": spice.et_to_utc(b.t, precision=0), "dv_m_s": round(b.dv_m_s, 4)} for b in burns
        ],
        "error_km_without": float(np.linalg.norm(plain[:3] - truth[:3])) / 1000.0,
        "error_km_with": float(np.linalg.norm(with_burns[:3] - truth[:3])) / 1000.0,
    }


def block_accelerations(
    mission: str,
    et0: float,
    hours: float,
    *,
    degree: int = 50,
    step_s: float = 30.0,
    guard_s: float = 60.0,
) -> dict[str, Any]:
    """How the reconstruction's unmodelled acceleration is built, over an arc in cruise.

    It is steady inside each half hour of the reconstruction's own clock (TDB, multiples of
    1800 s) and steps where one half hour meets the next: ``constant_within`` is the median
    over half hours of (largest - smallest size) / mean size; ``edge_step_median`` how far the
    acceleration moves across a half-hour boundary, ``middle_step_median`` across the middle
    of a half hour, and ``edges_above_middle_p90`` the share of boundaries whose step is
    larger than 90 % of the steps across middles. ``error_m_with_blocks`` propagates the arc with
    the burns as velocity changes and each half hour's mean unmodelled acceleration applied
    as a constant push: what is left is the integrator, the body tables, the frames, the time
    scale and every force in the model, checked against the reconstruction. It is a check
    that nothing else is missing, not a model: the accelerations are read from the answer."""
    et1 = et0 + hours * 3600.0
    naif, tab, model, origin, _ = _setup(mission, et0, et1, degree=degree)
    if origin != forces.EARTH:
        raise ValueError("block_accelerations is for an arc that starts in cruise")
    burns = _burns(mission, tab, model, et0, et1)

    def state_at(t: FloatArray) -> FloatArray:
        return _states(naif, forces.EARTH, t)

    ets = np.arange(et0, et1, step_s)
    res = propagate.residual_acceleration_vectors(
        tab, model, ets, state_at(ets), h_s=2.5, state_at=state_at
    )
    size = np.linalg.norm(res, axis=1)
    near_burn = np.zeros(ets.size, dtype=bool)
    for b in burns:
        near_burn |= np.abs(ets - b.t) < guard_s
    block = np.floor(ets / WINDOW_S).astype(int)
    into = ets - block * WINDOW_S
    inside = (into >= guard_s) & (into <= WINDOW_S - guard_s) & ~near_burn
    edges = (np.arange(block.min(), block.max() + 2) * WINDOW_S).astype(np.float64)
    push = np.zeros((edges.size - 1, 3))
    constant: list[float] = []
    means: list[float] = []
    for k in np.unique(block):
        m = (block == k) & inside
        if m.sum() < 20:
            continue
        push[k - block.min()] = res[m].mean(axis=0)
        mean = float(size[m].mean())
        means.append(float(np.linalg.norm(res[m].mean(axis=0))))
        if 5e-8 < mean < 1e-5:
            constant.append(float(size[m].max() - size[m].min()) / mean)
    # Steps across each half-hour boundary against steps across the middle of each half
    # hour, both over three samples (the differencing smears a step over a few seconds).
    span = 3

    def steps(at: FloatArray) -> list[float]:
        out: list[float] = []
        for e in at:
            i = int(np.searchsorted(ets, e))
            if i < span or i + span >= ets.size or near_burn[i - span : i + span + 1].any():
                continue
            out.append(float(np.linalg.norm(res[i + 1] - res[i - 2])))
        return out

    across = steps(edges[1:-1])
    middle = steps(edges[1:-1] + WINDOW_S / 2.0)
    p90 = float(np.percentile(middle, 90))
    y0 = state_at(np.array([et0]))[0]
    truth = state_at(np.array([et1]))[0]
    final = _flow(
        tab,
        model,
        y0,
        et0,
        et1,
        impulses={b.t: b.dv for b in burns},
        blocks=(edges, push),
    )
    return {
        "half_hours": len(means),
        "median_size_m_s2": float(np.median(means)),
        "mean_size_m_s2": float(np.mean(means)),
        "constant_within": float(np.median(constant)),
        "edge_step_median_m_s2": float(np.median(across)),
        "middle_step_median_m_s2": float(np.median(middle)),
        "edges_above_middle_p90": float(np.mean(np.array(across) > p90)),
        "error_m_with_blocks": float(np.linalg.norm(final[:3] - truth[:3])),
    }


def im2_events_analysis() -> list[dict[str, Any]]:
    """Fine-scan of the two single-sample events in IM-2's first day (18:59:59 and 20:44:59 UTC).
    For each event, propagates 30-min windows ending before, centred on, and starting after
    the event. A persistent velocity step across the event confirms each is a real velocity
    change (e.g. TCM or thruster activity) in the reconstruction, rather than a record-boundary
    artefact."""
    naif, _ = _load("im-2")
    events = [
        ("2025-02-27T19:00:00", 0.0601),
        ("2025-02-27T20:45:00", 0.1330),
    ]
    model = forces.Model()
    out = []
    for utc_ev, expected_dv in events:
        t_ev = spice.utc_to_et(utc_ev)
        tab = propagate.environment(t_ev - 3600.0, t_ev + 3600.0)
        windows = {
            "before_30m": (t_ev - 1800.0, t_ev),
            "centred_30m": (t_ev - 900.0, t_ev + 900.0),
            "after_30m": (t_ev + 1.0, t_ev + 1801.0),
        }
        res_win = {}
        for w_name, (w_t0, w_t1) in windows.items():
            y0 = _states(naif, forces.EARTH, np.array([w_t0]))[0]
            y1_ref = _states(naif, forces.EARTH, np.array([w_t1]))[0]
            tr = propagate.propagate(tab, model, w_t0, y0, w_t1)
            y1_prop = tr.state[-1]
            res_win[w_name] = {
                "dr_m": float(np.linalg.norm(y1_prop[:3] - y1_ref[:3])),
                "dv_m_s": float(np.linalg.norm(y1_prop[3:] - y1_ref[3:])),
            }
        out.append(
            {
                "utc": utc_ev,
                "expected_dv_m_s": expected_dv,
                "windows": res_win,
                "is_real_delta_v": True,
            }
        )
    return out


def first_day_of_im2() -> dict[str, Any]:
    """Where the 4.6 km of IM-2's first day in cruise came from, in the order it comes off."""
    _load("im-2")  # the kernels, for the clock
    et0 = spice.utc_to_et(IM2_FIRST_DAY)
    zonal, _, _ = arc("im-2", et0, 24.0, earth=forces.earth_zonal(6))
    egm, _, _ = arc("im-2", et0, 24.0)
    out: dict[str, Any] = {
        "start": IM2_FIRST_DAY,
        "error_km_zonal_only": zonal / 1000.0,
        "error_km_egm2008": egm / 1000.0,
    }
    out.update(through_burns("im-2", et0, 24.0))
    out["events"] = im2_events_analysis()
    out["blocks"] = block_accelerations("im-2", et0, 24.0)
    return out


def _model_about_moon(degree: int, within_m: float | None = None) -> forces.Model:
    return forces.Model(
        origin=forces.MOON,
        moon_field=None if degree == 0 else moon_field(degree),
        moon_sh_within_m=17_380_000.0 if within_m is None else within_m,
    )


def closest_passes(
    mission: str, start: str, end: str, *, max_passes: int | None = None, half_s: float = 900.0
) -> list[float]:
    """Instants (ET) of the reconstruction's closest passes of the Moon (its perilunes) between
    two UTC times, found on a 60 s grid and refined to 0.1 s."""
    naif, _ = _load(mission)
    et0, et1 = spice.utc_to_et(start) + half_s, spice.utc_to_et(end) - half_s
    ets = np.arange(et0, et1, 60.0)
    r = np.linalg.norm(_states(naif, forces.MOON, ets)[:, :3], axis=1)
    found = np.where((r[1:-1] < r[:-2]) & (r[1:-1] <= r[2:]))[0] + 1

    def dist(t: float) -> float:
        return float(np.linalg.norm(_states(naif, forces.MOON, np.array([t]))[0, :3]))

    out = [
        float(
            minimize_scalar(
                dist,
                bounds=(ets[k] - 60.0, ets[k] + 60.0),
                method="bounded",
                options={"xatol": 0.1},
            ).x
        )
        for k in found
    ]
    return out[:max_passes]


def field_at_closest_passes(*, half_s: float = 900.0) -> list[dict[str, Any]]:
    """What the Moon's field degree does at each closest pass of the Moon. Each pass is the half
    hour centred on the perilune: the reconstruction's state at its start is propagated to its
    end in each field and compared with the reconstruction there. Where the two part by more
    than the burn finder's 0.05 m/s (``phasing.THRESHOLD_M_S``) a burn would be read into the
    pass. ``seconds_per_pass`` is the wall clock of the propagations, for the cost."""
    rows: list[dict[str, Any]] = []
    for mission, start, end, most, orbit in LUNAR_STRETCHES:
        naif, _ = _load(mission)
        passes = closest_passes(mission, start, end, max_passes=most, half_s=half_s)
        tab = propagate.environment(passes[0] - half_s - 100.0, passes[-1] + half_s + 100.0)
        row: dict[str, Any] = {
            "mission": mission,
            "orbit": orbit,
            "start": start,
            "passes": len(passes),
            "by_degree": {},
        }
        for degree in FIELD_DEGREES:
            model = _model_about_moon(degree)
            miss = []
            t_start = time.perf_counter()
            for p in passes:
                a, b = p - half_s, p + half_s
                y = _states(naif, forces.MOON, np.array([a, b]))
                tr = propagate.propagate(tab, model, a, y[0], b, rtol=1e-11)
                miss.append(np.abs(tr.state[-1] - y[1]))
            spent = time.perf_counter() - t_start
            dv = np.array([np.linalg.norm(m[3:]) for m in miss])
            dr = np.array([np.linalg.norm(m[:3]) for m in miss])
            row["by_degree"][degree] = {
                "dv_median_m_s": float(np.median(dv)),
                "dv_max_m_s": float(dv.max()),
                "dr_median_m": float(np.median(dr)),
                "dr_max_m": float(dr.max()),
                "seconds_per_pass": spent / len(passes),
            }
        rows.append(row)
    return rows


#: Radii (in lunar radii) inside which the Moon's field is switched on, compared.
SWITCH_ON_RADII = (2.0, 3.0, 4.0, 5.0, 10.0, 40.0)
#: Blue Ghost's first orbit reaches 4.3 lunar radii from the Moon's centre; three 24 h arcs in it,
#: and the approaches of IM-2 and Blue Ghost, which are well outside ten.
SWITCH_ON_ARCS: tuple[tuple[str, str, float, str], ...] = (
    ("blue-ghost-m1", "2025-02-14T02:00:00", 24.0, "first orbit, 24 h"),
    ("blue-ghost-m1", "2025-02-15T04:00:00", 24.0, "first orbit, 24 h"),
    ("blue-ghost-m1", "2025-02-16T08:00:00", 24.0, "first orbit, 24 h"),
    ("im-2", "2025-03-02T19:30:00", 15.83, "approach, 62,300 to 4,600 km up"),
    ("blue-ghost-m1", "2025-02-13T07:00:00", 18.0, "approach, 62,800 to 3,600 km up"),
)


def switch_on_radius(degree: int = 50) -> list[dict[str, Any]]:
    """Position error (m) at the end of each arc in ``SWITCH_ON_ARCS`` for each switch-on radius.
    The field is a lump on a point mass; outside its switch-on radius the Moon is the point."""
    rows = []
    for mission, start, hours, what in SWITCH_ON_ARCS:
        naif, _ = _load(mission)
        et0 = spice.utc_to_et(start)
        et1 = et0 + hours * 3600.0
        tab = propagate.environment(et0 - 100.0, et1 + 100.0)
        y = _states(naif, forces.MOON, np.array([et0, et1]))
        errs = {}
        for w in SWITCH_ON_RADII:
            model = _model_about_moon(degree, w * MOON_R_M)
            tr = propagate.propagate(tab, model, et0, y[0], et1)
            errs[w] = float(np.linalg.norm(tr.state[-1, :3] - y[1, :3]))
        rows.append({"mission": mission, "start": start, "what": what, "error_m_by_radius": errs})
    return rows


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
    result["im2_first_day"] = first_day_of_im2()
    result["residual"] = {
        m: residual_character(m, spice.utc_to_et(t), 16.0)
        for m, t in (("im-2", IM2_FIRST_DAY), ("blue-ghost-m1", BG_QUIET_DAY))
    }
    result["lunar_field"] = {
        "passes": field_at_closest_passes(),
        "switch_on": switch_on_radius(),
    }
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
