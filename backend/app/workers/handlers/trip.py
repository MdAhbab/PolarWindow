"""The ``trip`` job for a flown mission (T2, C0): NASA's reconstructed trajectory.

Reads the mission's reconstructed trajectory from NAIF's CLPS SPICE archive
and works out, along it: the distance to Earth and to the Moon, when the
spacecraft was in Earth's or the Moon's shadow, when a Deep Space Network
antenna could see it, and where the Moon's pull overtook Earth's.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from app.config import get_settings
from app.core import eclipse, intervals, lincov, propagate, spice
from app.core import trip as core_trip
from app.core.contact import mask_elevation
from app.core.intervals import Run
from app.core.quantity import Quantity
from app.core.spice import R_EARTH_M, R_MOON_M, R_SUN_M
from app.data import catalogues
from app.db.repositories.jobs import InputRef
from app.services import ascent, flown_burns, lifecycle, radiation
from app.workers.compute import HandlerResult, JobContext, handler

H = 3600.0
DAY = 86_400.0
#: Seeded runs through the force model for the correction budget (plan C4).
BUDGET_RUNS = 1000
MAX_SAMPLES = 2000
#: Earth's atmosphere makes its shadow about 2 % larger than the solid Earth's
#: (the classical enlargement used for lunar eclipses); shadow edges are
#: worked out both ways and the difference is the margin.
ATMOSPHERE_ENLARGEMENT = 1.02
SMOOTH_MOON = (
    "Only the Moon's shadow is involved, cast by a smooth sphere: lunar mountains move its "
    "edges by seconds, which is not worked out here."
)


def _q(
    value_s: float, pm_s: float | None, *, open_: bool, why: str | None = None
) -> dict[str, Any]:
    if pm_s is None or pm_s == 0.0:
        return lifecycle.q(
            Quantity(
                value=value_s / H,
                unit="h",
                provenance="computed",
                open=open_,
                no_margin_reason=why or "No edge to time.",
            )
        )
    return lifecycle.q(
        Quantity(value=value_s / H, unit="h", provenance="computed", pm=pm_s / H, open=open_)
    )


def _longest(runs: list[Run], value: bool, t0: float, t1: float) -> tuple[float, bool]:
    r = intervals.longest(runs, value)
    if r is None or r.duration <= intervals.EPS_S:
        return 0.0, False  # nothing to cut short
    return r.duration, r.start <= t0 + intervals.EPS_S or r.end >= t1 - intervals.EPS_S


def _mps(value: float, **kw: Any) -> dict[str, Any]:
    return lifecycle.q(Quantity(value=value, unit="m/s", provenance="computed", **kw))


BURNS_NOTE = (
    "Found where NASA's reconstruction leaves the force model by more than 0.05 m/s in half "
    "an hour, up to the arrival at the Moon; each is shown as one instant. A burn in a gap "
    "of the reconstruction is not seen. Burns in lunar orbit are not listed: there the "
    "force model and the reconstruction part by about 1 m/s at each close pass of the Moon, "
    "as much as a small burn."
)
TCM_NAMES = (
    "First correction, a day after leaving Earth",
    "Second correction, half-way",
    "Third correction, a day before arriving",
)


async def _burns_and_budget(
    ctx: JobContext, p: dict[str, Any], at: Any, et_origin: float
) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None, str | None]:
    """The burns read from the reconstruction and the correction budget (C3, C4)."""
    mid = p["mission_id"]
    flights = await spice.run_async(ascent.measure, tuple(tuple(x) for x in p.get("flights", [])))
    f = flights.get(mid)
    if f is None:
        why = "The launch record this needs (pad, vehicle, liftoff) is not published."
        return [], why, None, why
    fl = f.launch
    # The burns are looked for up to an hour past the arrival, or over the whole
    # reconstruction for a lander that never arrived (Peregrine): the body tables must
    # cover either.
    last = await spice.run_async(lambda: ascent.coverage(mid)[-1][1])
    cover_end = max((fl.t_arrive or f.t0_et) + 4 * DAY, float(last) + 60.0)
    tables = await spice.run_async(propagate.environment, f.t0_et - DAY, cover_end)
    named, steady = await spice.run_async(flown_burns.burns, mid, fl, tables)
    ctx.progress(0.45, "Burns found in the reconstruction.")

    def when(et: float) -> datetime:
        out: datetime = at(et - et_origin)
        return out

    burns = [
        {
            "t": lifecycle.iso(when(b.t)),
            "name": name,
            "dv_m_s": _mps(
                b.dv_m_s,
                no_margin_reason=f"One instant stands for the burn; the paths before and after "
                f"it meet within {b.mismatch_m / 1000:.1f} km there.",
            ),
        }
        for b, name in named
    ]
    note = BURNS_NOTE
    if not burns and fl.t_arrive is not None:
        end = fl.t_arrive
        spans = await spice.run_async(lambda: ascent.coverage(mid))
        seen = [(a, min(b, end)) for a, b in spans if a < end] or [(end, end)]

        def day(et: float) -> str:
            return lifecycle.iso(when(et))[:16].replace("T", " ")

        hours = sum(b - a for a, b in seen) / 3600.0
        said = (
            f"{len(seen)} stretches, {hours:.0f} h in all, between {day(seen[0][0])} and "
            f"{day(seen[-1][1])} UTC"
            if len(seen) > 2
            else " and ".join(f"{day(a)} to {day(b)} UTC" for a, b in seen)
        )
        note = (
            f"No burn is found for this trip in the reconstruction, which covers {said} up to "
            "the arrival; "
            "any burn before it starts or in its gaps is not seen. " + note
        )
    if steady:
        a, b = min(x.start for x in steady), max(x.end for x in steady)
        note += (
            f" From {lifecycle.iso(when(a))[:10]} to {lifecycle.iso(when(b))[:10]} the "
            "reconstruction shows a steady push, not separate burns."
        )
    if fl.t_arrive is None:
        return burns, note, None, "It did not reach the Moon, so there is no arrival to budget for."

    def tick(n: int) -> None:
        if n % 50 == 0:
            ctx.progress(0.5 + 0.45 * n / BUDGET_RUNS, f"Correction runs: {n} of {BUDGET_RUNS}.")

    guide = flown_burns.guide_for(f.vehicle_id)
    bud = await spice.run_async(
        lambda: flown_burns.budget(
            mid, fl, tables, named, guide=guide, samples=BUDGET_RUNS, progress=tick
        )
    )
    if bud is None:
        why = (
            "The reconstruction, propagated back from the Moon, does not pass Earth near the "
            "flown departure, so the planned flight cannot be taken from it."
        )
        return burns, note, None, why
    plan, lin, runs = bud.planned.plan, bud.linear, bud.runs
    lo, hi = lincov.bootstrap(runs.total, 99)
    leave = next((x for x, n in named if n == "Leaving Earth for the Moon"), None)
    dep = leave.t if leave is not None else fl.t_tli
    shift = (plan.t_tli - dep) / 60.0
    flown = [(n, x.dv_m_s) for x, n in named if n.startswith("Correction")]
    budget = {
        "label": (
            "A budget for these errors, not a prediction of what the mission needed: the "
            "launch vehicle’s published injection accuracy where its guide gives one, every "
            "other error assumed."
            if bud.derived
            else "A budget for these assumed errors, not a prediction of what the mission "
            "needed."
        ),
        "burns": [
            {
                "name": TCM_NAMES[k] if k < len(TCM_NAMES) else f"Correction {k + 1}",
                "t": lifecycle.iso(when(t)),
                "p95_m_s": _mps(
                    runs.pct(95)[0][k],
                    no_margin_reason=f"95th percentile of {runs.dv.shape[0]} runs.",
                ),
                "p99_m_s": _mps(
                    runs.pct(99)[0][k],
                    no_margin_reason=f"99th percentile of {runs.dv.shape[0]} runs.",
                ),
            }
            for k, t in enumerate(plan.tcm_times)
        ],
        "total_p95_m_s": _mps(runs.pct(95)[1], no_margin_reason="95th percentile of the runs."),
        "total_p99_m_s": _mps(runs.pct(99)[1], lo=lo, hi=hi),
        "linear_p99_m_s": _mps(
            lin.pct(99)[1],
            no_margin_reason="The same errors pushed through the motion linearised about the plan.",
        ),
        "arrival_altitude_km": lifecycle.q(
            Quantity(
                value=runs.altitude_km(50),
                unit="km",
                provenance="computed",
                lo=runs.altitude_km(1),
                hi=runs.altitude_km(99),
            )
        ),
        "runs": int(runs.dv.shape[0]),
        "missed": runs.missed,
        "assumptions": [
            {"what": i.what, "value": i.value, "basis": i.basis, "source": i.source}
            for i in flown_burns.input_words(bud.errors, bud.derived, guide)
        ],
        "plan_note": (
            "The flight as planned: NASA's reconstruction just before entering lunar orbit, "
            "propagated back to where it passed closest to Earth "
            f"({bud.planned.perigee_alt_m / 1000:,.0f} km up, {abs(shift):.0f} min "
            f"{'after' if shift >= 0 else 'before'} the flown departure). Forward from there "
            "it arrives where and when the flown one did, with no burn on the way."
        ),
        "flown_note": (
            "The reconstruction shows corrections of "
            + ", ".join(f"{v:.2f} m/s" for _, v in flown)
            + " after leaving Earth (any in its gaps are not seen)."
            if flown
            else "No correction burn is seen in the reconstruction (any in its gaps are not seen)."
        ),
    }
    return burns, note, budget, None


@handler("trip")
async def run(ctx: JobContext) -> HandlerResult:
    p = ctx.job.params
    t_wall = time.perf_counter()
    spk = get_settings().data_dir / p["spk"]
    naif = int(p["naif_id"])
    sc = str(naif)
    step = float(p["step_s"])
    await spice.run_async(spice.load_extra, [Path(spk)])
    cover = await spice.run_async(spice.coverage, Path(spk), naif)
    if not cover:
        raise ValueError(f"{spk.name} has no coverage for {naif}")

    stations = [g for g in catalogues.load("ground_stations").records if g.status == "operating"]
    mu_e = await spice.run_async(spice.gm_m3_s2, "EARTH")
    mu_m = await spice.run_async(spice.gm_m3_s2, "MOON")
    et_origin = cover[0][0]

    samples_t: list[npt.NDArray[Any]] = []
    samples: dict[str, list[npt.NDArray[Any]]] = {"earth": [], "moon": [], "state": [], "heard": []}
    shadow_runs: list[Run] = []
    shadow_wide: list[Run] = []
    heard_runs: list[Run] = []
    pull_t: float | None = None
    d_em_at: list[float] = []
    covered_s = 0.0
    for k, (a, b) in enumerate(cover):
        n = max(2, int(np.ceil((b - a) / step)) + 1)
        ets = np.linspace(a, b, n)
        t = ets - et_origin
        geo = await spice.run_async(spice.positions, sc, "EARTH", "J2000", "NONE", ets, knot_s=None)
        # Directions from the spacecraft, as it would see them (light time and aberration).
        to_sun = await spice.run_async(
            spice.positions, "SUN", sc, "J2000", "LT+S", ets, knot_s=None
        )
        to_earth = await spice.run_async(
            spice.positions, "EARTH", sc, "J2000", "LT+S", ets, knot_s=None
        )
        to_moon = await spice.run_async(
            spice.positions, "MOON", sc, "J2000", "LT+S", ets, knot_s=None
        )
        earth_occ = eclipse.occultation(to_sun, to_earth, R_SUN_M, R_EARTH_M)
        earth_occ_wide = eclipse.occultation(
            to_sun, to_earth, R_SUN_M, R_EARTH_M * ATMOSPHERE_ENLARGEMENT
        )
        moon_occ = eclipse.occultation(to_sun, to_moon, R_SUN_M, R_MOON_M)
        st = eclipse.state([earth_occ, moon_occ])
        sh = eclipse.shadow_runs(t, [earth_occ, moon_occ])
        shw = eclipse.shadow_runs(t, [earth_occ_wide, moon_occ])
        looks = await spice.run_async(
            spice.station_look_to, [g.naif_name for g in stations], geo, ets
        )
        per: list[list[Run]] = []
        for g, look in zip(stations, looks, strict=True):
            mask = mask_elevation(
                np.array([q.az_deg for q in g.mask]),
                np.array([q.el_deg for q in g.mask]),
                look.az_deg,
            )
            per.append(intervals.runs_from_margin(t, look.el_deg - mask))
        hr = intervals.any_of(per)
        r_e = np.linalg.norm(to_earth, axis=1)
        r_m = np.linalg.norm(to_moon, axis=1)
        if pull_t is None:
            pc = core_trip.first_crossing(t, core_trip.pull_margin(r_e, r_m, mu_e, mu_m))
            if pc is not None:
                pull_t = pc
        em = await spice.run_async(
            spice.positions, "MOON", "EARTH", "J2000", "NONE", ets[[0, -1]], knot_s=None
        )
        d_em_at += list(np.linalg.norm(em, axis=1))
        shadow_runs += sh
        shadow_wide += shw
        heard_runs += hr
        covered_s += b - a
        samples_t.append(t)
        samples["earth"].append(r_e)
        samples["moon"].append(r_m)
        samples["state"].append(st)
        heard_mask = np.zeros(t.size, dtype=bool)
        for r in hr:
            if r.value:
                heard_mask |= (t >= r.start) & (t <= r.end)
        samples["heard"].append(heard_mask)
        ctx.progress(
            0.05 + 0.35 * (k + 1) / len(cover), f"Stretch {k + 1} of {len(cover)} worked out."
        )

    t_all = np.concatenate(samples_t)
    idx = core_trip.thin(t_all.size, MAX_SAMPLES)
    e_all = np.concatenate(samples["earth"])[idx]
    m_all = np.concatenate(samples["moon"])[idx]
    s_all = np.concatenate(samples["state"])[idx]
    h_all = np.concatenate(samples["heard"])[idx]
    words = {eclipse.LIT: "lit", eclipse.PENUMBRAL: "penumbral", eclipse.DARK: "dark"}
    start_dt = lifecycle.parse_time(await spice.run_async(spice.et_to_utc, et_origin))

    def at(ts: float) -> datetime:
        return start_dt + timedelta(seconds=float(ts))

    t_end = float(cover[-1][1] - et_origin)
    edges = [(a - et_origin, b - et_origin) for a, b in cover]

    def stretches(runs: list[Run]) -> list[dict[str, Any]]:
        out = []
        for r in runs:
            if not r.value:
                continue
            out.append(
                lifecycle.stretch(
                    at(r.start),
                    at(r.end),
                    any(abs(r.start - e0) < 1e-6 for e0, _ in edges),
                    any(abs(r.end - e1) < 1e-6 for _, e1 in edges),
                )
            )
        return out

    burns, burns_note, corrections, corrections_note = await _burns_and_budget(
        ctx, p, at, et_origin
    )
    ctx.progress(0.9, "Working out the radiation along the trip.")
    rad, rad_why, rad_sources = await spice.run_async(
        radiation.along_trip, sc, cover, start_dt, at(t_end), p.get("sky")
    )
    shadow_s = intervals.total(shadow_runs, True)
    shadow_wide_s = intervals.total(shadow_wide, True)
    heard_s = intervals.total(heard_runs, True)
    long_sh, long_sh_open = _longest(shadow_runs, True, 0.0, t_end)
    long_sh_w, _ = _longest(shadow_wide, True, 0.0, t_end)
    long_un, long_un_open = _longest(heard_runs, False, 0.0, t_end)
    d_em = float(np.mean(d_em_at))
    gaps = len(cover) > 1
    data = {
        "source": "flown",
        "none_reason": None,
        "start": lifecycle.iso(start_dt),
        "end": lifecycle.iso(at(t_end)),
        "coverage_note": (
            f"NASA's reconstruction covers {len(cover)} separate stretches "
            f"({covered_s / H:.1f} hours in all); the numbers describe only those."
            if gaps
            else "NASA's reconstruction covers the whole trip without gaps."
        ),
        "covered": [lifecycle.stretch(at(a), at(b), False, False) for a, b in edges],
        "samples": [
            {
                "t": lifecycle.iso(at(float(t_all[i]))),
                "earth_km": float(e_all[j]) / 1000.0,
                "moon_km": float(m_all[j]) / 1000.0,
                "light": words[int(s_all[j])],
                "heard": bool(h_all[j]),
            }
            for j, i in enumerate(idx)
        ],
        "shadow": stretches(shadow_runs),
        "heard": stretches(heard_runs),
        "numbers": {
            "sunlight_h": _q(
                covered_s - shadow_s, abs(shadow_wide_s - shadow_s), open_=False, why=SMOOTH_MOON
            ),
            "heard_h": _q(
                heard_s, None, open_=False, why="Station masks are published without a tolerance."
            ),
            "longest_shadow_h": _q(
                long_sh, abs(long_sh_w - long_sh), open_=long_sh_open, why=SMOOTH_MOON
            ),
            "longest_unheard_h": _q(
                long_un, None, open_=long_un_open or gaps, why="Its edges are set by station masks."
            ),
        },
        "burns": burns,
        "burns_note": burns_note,
        "corrections": corrections,
        "corrections_note": corrections_note,
        "moon_pull": {
            "equal_pull_km": core_trip.equal_pull_distance_m(d_em, mu_e, mu_m) / 1000.0,
            "sphere_of_influence_km": core_trip.sphere_of_influence_m(d_em, mu_e, mu_m) / 1000.0,
            "t_equal_pull": None if pull_t is None else lifecycle.iso(at(pull_t)),
        },
        "radiation": rad,
        "radiation_note": rad_why,
    }
    meta = lifecycle.meta(
        engines=("ecl", "traj", "rad"),
        sources=[
            lifecycle.source_ref(p["title"], p["url"]),
            lifecycle.source_ref(
                "NAIF DE440 planetary ephemeris and GM values",
                "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/",
            ),
            lifecycle.source_ref(
                "DSN 810-005 module 301 Rev. O horizon masks",
                stations[0].sources[1].url if stations else None,
            ),
            *rad_sources,
        ],
        parts=[
            (
                "Radiation",
                "A screening estimate: belt maps good to about a factor of two, cosmic-ray "
                "dose ±30 %; confirm in SPENVIS, OLTARIS or CREME-MC.",
            ),
            (
                "Reconstructed trajectory",
                "NASA's reconstruction as archived; its own accuracy " "is not published with it.",
            ),
            (
                "Shadow edges",
                "Spherical Earth and Moon; the ± on sunlight and the longest shadow "
                "is the change when Earth's shadow is made 2 % larger for its atmosphere.",
            ),
            (
                "Line of sight only",
                "A station 'can see' the spacecraft when it is above the "
                "station's mask; antenna pointing and bookings are not modelled.",
            ),
        ],
        compute_ms=(time.perf_counter() - t_wall) * 1000.0,
        computed_at=datetime.now(UTC),
    )
    inputs = [
        InputRef("dataset", p["dataset"], p["spk"]),
        InputRef("catalogue", "ground_stations", catalogues.load("ground_stations").version),
        InputRef("catalogue", "vehicles", catalogues.load("vehicles").version),
        InputRef("mission", p["mission_id"], p["data_version"]),
    ]
    return HandlerResult(
        result=lifecycle.jsonable({"data": data, "meta": meta}),
        inputs=inputs,
        message="Trip worked out.",
    )
