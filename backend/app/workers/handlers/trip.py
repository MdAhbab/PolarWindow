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
from app.core import eclipse, intervals, spice
from app.core import trip as core_trip
from app.core.contact import mask_elevation
from app.core.intervals import Run
from app.core.quantity import Quantity
from app.core.spice import R_EARTH_M, R_MOON_M, R_SUN_M
from app.data import catalogues
from app.db.repositories.jobs import InputRef
from app.services import lifecycle
from app.workers.compute import HandlerResult, JobContext, handler

H = 3600.0
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
            0.1 + 0.8 * (k + 1) / len(cover), f"Stretch {k + 1} of {len(cover)} worked out."
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
        "burns": [],
        "burns_note": "Engine burns are not published with the reconstruction; they are not "
        "listed rather than guessed.",
        "moon_pull": {
            "equal_pull_km": core_trip.equal_pull_distance_m(d_em, mu_e, mu_m) / 1000.0,
            "sphere_of_influence_km": core_trip.sphere_of_influence_m(d_em, mu_e, mu_m) / 1000.0,
            "t_equal_pull": None if pull_t is None else lifecycle.iso(at(pull_t)),
        },
        "radiation": None,
    }
    meta = lifecycle.meta(
        engines=("ecl", "traj"),
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
        ],
        parts=[
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
        InputRef("mission", p["mission_id"], p["data_version"]),
    ]
    return HandlerResult(
        result=lifecycle.jsonable({"data": data, "meta": meta}),
        inputs=inputs,
        message="Trip worked out.",
    )
