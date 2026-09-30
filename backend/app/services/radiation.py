"""Radiation along a flown trip and on the surface: a screening estimate (plan track E).

* Trapped belts: AE8/AP8 (``core.belts``) along NASA's reconstructed trajectory,
  every minute while within 15 Earth radii: time inside the belts, how many
  passes, and the fluence of electrons above 1 MeV and protons above 10 MeV,
  ×/÷2. The solar-minimum or solar-maximum map is chosen from the sunspot
  record (OMNI) of the year before the trip.
* Cosmic rays: a measured dose rate scaled by the Sun's modulation at the time
  (``core.gcr``, Matthiä et al. 2013, W from the Oulu neutron monitor), ±30 %:
  CRaTER in lunar orbit for the trip, Chang'e-4's LND for the surface, the latter
  times the landing site's share of open sky from its skyline.
* Solar particle events: which of NOAA's >10 MeV events (from NASA DONKI) fell
  during the trip, and what a past large event would have given.

Every number is labelled a screening estimate, to be confirmed in SPENVIS,
OLTARIS or CREME-MC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import numpy.typing as npt

from app.core import belts, gcr, spice
from app.core.quantity import Quantity
from app.data import space_climate
from app.services import lifecycle

FloatArray = npt.NDArray[np.float64]

STEP_S = 60.0
#: Beyond this AE8/AP8 hold nothing (their outermost shells are near L = 11).
NEAR_KM = 15 * belts.RE_KM
E_MEV = 1.0
P_MEV = 10.0
GCR_PM = 0.30
DAY_S = 86_400.0

CONFIRM_IN = ["SPENVIS (ESA)", "OLTARIS (NASA)", "CREME-MC (Vanderbilt University)"]
SCREENING_NOTE = (
    "Screening only: long-term average belt maps (good to about a factor of two), cosmic-ray "
    "dose scaled from measurements (±30 %), and past events as they were measured at 1 AU. "
    "None of it accounts for the spacecraft's own shielding. Confirm in SPENVIS, OLTARIS or "
    "CREME-MC before any design decision."
)
#: Dose rates measured by instruments, used as references (silicon).
CRATER: dict[str, Any] = {
    "gy_per_year": 0.189,
    "month": "2009-06",
    "words": "18.9 cGy a year in silicon, measured by CRaTER's microdosimeter on LRO on 20 "
    "June 2009, about 10,000 km from the Moon (Mazur et al. 2011, as given by Schwadron et al. "
    "2012, JGR 117, E00H13)",
    "url": "https://prediccs.sr.unh.edu/papers/schwadron2011JE003978.pdf",
}
LND: dict[str, Any] = {
    "ugy_per_hour": 13.2,
    "month": "2019-01",
    "words": "13.2 ± 1 µGy an hour in silicon, measured on the surface by Chang'e-4's LND from "
    "January 2019 (Zhang et al. 2020, Science Advances 6, eaaz1334), its horizon taken as flat",
    "url": "https://www.science.org/doi/10.1126/sciadv.aaz1334",
}


def _q(value: float, unit: str, **kw: Any) -> dict[str, Any]:
    return lifecycle.q(Quantity(value=value, unit=unit, provenance="computed", **kw))


# --- the solar cycle --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Phase:
    solar: belts.Solar
    words: str


def solar_phase(start: datetime) -> Phase | None:
    """AE8/AP8 MIN or MAX: MAX when the year before ``start`` averaged more sunspots than
    half-way between the lowest and highest yearly means of the 11 years before it."""
    o = space_climate.omni(start - timedelta(days=11 * 366), start)
    if o is None:
        return None
    t = np.array([x.timestamp() for x in o.t])
    r = o.sunspots
    year_s = 365.25 * DAY_S
    means = []
    edge = t[-1]
    while edge - year_s >= t[0]:
        sel = (t > edge - year_s) & (t <= edge) & np.isfinite(r)
        if sel.sum() > 24 * 200:
            means.append(float(np.mean(r[sel])))
        edge -= 30 * DAY_S
    if not means:
        return None
    now, lo, hi = means[0], min(means), max(means)
    solar: belts.Solar = "max" if now >= (lo + hi) / 2 else "min"
    return Phase(
        solar,
        f"the year before averaged {now:.0f} sunspots a day, against {lo:.0f} to {hi:.0f} "
        f"over the 11 years before (OMNI), so the solar-{solar}imum maps",
    )


def w_at(t: datetime) -> tuple[float, str] | None:
    got = space_climate.oulu_at(t)
    if got is None:
        return None
    n, month = got
    return min(gcr.W_MAX, max(gcr.W_MIN, gcr.w_from_oulu(n))), month


def _w_month(month: str) -> float | None:
    got = w_at(datetime.strptime(month + "-15", "%Y-%m-%d").replace(tzinfo=UTC))
    return None if got is None else got[0]


# --- along the trajectory --------------------------------------------------------------


def belt_samples(
    sc: str, cover: list[tuple[float, float]]
) -> tuple[FloatArray, list[datetime], FloatArray]:
    """Every minute of each covered stretch while within ``NEAR_KM`` of Earth: seconds
    from the first covered instant, UTC times, Earth-fixed (ITRF93) km."""
    t_out: list[FloatArray] = []
    x_out: list[FloatArray] = []
    et0 = cover[0][0]
    for a, b in cover:
        coarse = np.arange(a, b, 600.0)
        if coarse.size == 0:
            continue
        r = np.linalg.norm(
            spice.positions(sc, "EARTH", "J2000", "NONE", coarse, knot_s=None), axis=1
        )
        near = r < NEAR_KM * 1000.0 * 1.2
        if not near.any():
            continue
        ets = np.arange(a, b + 1e-6, STEP_S)
        keep = np.interp(ets, coarse, near.astype(float)) > 0
        ets = ets[keep]
        if ets.size == 0:
            continue
        pos = spice.positions(sc, "EARTH", "J2000", "NONE", ets, knot_s=None)
        rot = spice.rotations("J2000", "ITRF93", ets)
        geo = np.einsum("nij,nj->ni", rot, pos) / 1000.0
        inside = np.linalg.norm(geo, axis=1) < NEAR_KM
        t_out.append(ets[inside] - et0)
        x_out.append(geo[inside])
    if not t_out:
        return np.zeros(0), [], np.zeros((0, 3))
    t = np.concatenate(t_out)
    start = lifecycle.parse_time(spice.et_to_utc(et0))
    times = [start + timedelta(seconds=float(s)) for s in t]
    return t, times, np.concatenate(x_out)


def _segments(t: FloatArray) -> list[npt.NDArray[np.intp]]:
    """Index runs of consecutive one-minute samples (a jump means the path left the
    region, or the reconstruction has a gap)."""
    if t.size == 0:
        return []
    cut = np.where(np.diff(t) > STEP_S * 1.5)[0] + 1
    return [np.asarray(x, dtype=np.intp) for x in np.split(np.arange(t.size), cut)]


def trapped(
    t: FloatArray, times: list[datetime], geo_km: FloatArray, phase: Phase, first_s: float
) -> dict[str, Any]:
    e = belts.integral_flux("e", phase.solar, [E_MEV], times, geo_km)[0]
    p = belts.integral_flux("p", phase.solar, [P_MEV], times, geo_km)[0]
    other: belts.Solar = "min" if phase.solar == "max" else "max"
    e2 = belts.integral_flux("e", other, [E_MEV], times, geo_km)[0]
    p2 = belts.integral_flux("p", other, [P_MEV], times, geo_km)[0]
    inside = (e > 0) | (p > 0)
    hours = 0.0
    fe = fp = fe2 = fp2 = 0.0
    stretches: list[tuple[float, float]] = []
    for seg in _segments(t):
        ts = t[seg]
        hours += belts.time_inside(ts, inside[seg]) / 3600.0
        fe += belts.fluence(ts, e[seg])
        fp += belts.fluence(ts, p[seg])
        fe2 += belts.fluence(ts, e2[seg])
        fp2 += belts.fluence(ts, p2[seg])
        stretches += belts.passes(ts, inside[seg]).stretches
    open_ = bool(t.size and inside[0] and abs(t[0] - first_s) < STEP_S)
    return {
        "hours": hours,
        "passes": len(stretches),
        "e": fe,
        "p": fp,
        "e_other": fe2,
        "p_other": fp2,
        "open": open_,
        "other": other,
    }


def _events_during(start: datetime, end: datetime) -> tuple[list[dict[str, str]], str | None]:
    built, events = space_climate.donki_goes()
    if built is None:
        return [], "NASA DONKI's event list is not on this machine (make space-climate)."
    during = [e for e in events if start <= lifecycle.parse_time(e["t"]) <= end]
    return during, None


def _scenarios() -> list[dict[str, Any]]:
    out = []
    for e in space_climate.sep_scenarios():
        f = float(e["fluence_gt10_cm2"])  # type: ignore[arg-type]
        peak = e.get("peak_gt10_pfu")
        words = (
            f"{e['source']}, {e['start']} to {e['end']} UTC; peak {float(peak):,.0f} pfu above "  # type: ignore[arg-type]
            f"10 MeV (NOAA's list: {float(e['swpc_list_peak_pfu']):,.0f})."  # type: ignore[arg-type]
            if peak is not None
            else f"{e['source']}."
        )
        out.append(
            {
                "id": e["id"],
                "name": e["name"],
                "fluence_gt10mev": _q(
                    f,
                    "cm^-2",
                    no_margin_reason="As measured at 1 AU outside Earth's magnetic field "
                    "(taken as arriving evenly from all directions); " + words,
                ),
                "fluence_gt30mev": _q(
                    float(e["fluence_gt30_cm2"]),  # type: ignore[arg-type]
                    "cm^-2",
                    no_margin_reason="As above, above 30 MeV.",
                ),
                "source_url": e["source_url"],
            }
        )
    return out


def gcr_dose(month: str, ref: dict[str, Any], rate_mgy_day: float) -> tuple[float, str] | None:
    w_now = _w_month(month)
    w_ref = _w_month(str(ref["month"]))
    if w_now is None or w_ref is None:
        return None
    ratio = gcr.dose_ratio(w_now, w_ref)
    return rate_mgy_day * ratio, (
        f"From {ref['words']}, scaled by the cosmic-ray model's change between then (W = "
        f"{w_ref:.0f}) and {month} (W = {w_now:.0f}): ×{ratio:.2f} (Matthiä et al. 2013, W from "
        "the Oulu neutron monitor, NMDB). ±30 % covers the scaling."
    )


def belt_numbers(tr: dict[str, Any], r0_km: float, why_maps: str, before: str) -> dict[str, Any]:
    """Belt hours, passes and fluences. When nothing is counted and the reconstruction
    starts beyond the belts, the crossing is not in it: a zero times or over two means
    nothing, so the numbers are missing with that reason."""
    unseen = (
        f"NASA's reconstruction starts {r0_km - belts.RE_KM:,.0f} km above Earth, beyond the "
        "belts, so the crossing of them is not in it and is not counted."
        if tr["open"] and tr["hours"] == 0.0
        else None
    )

    def belt_q(value: float, unit: str, source: str) -> dict[str, Any]:
        if unseen is not None:
            return lifecycle.missing(unit, unseen)
        return _q(value, unit, factor=belts.FACTOR, open=tr["open"], source=source)

    return {
        "belt_hours": belt_q(
            tr["hours"],
            "h",
            f"Inside the belts: where the maps hold electrons above 1 MeV or protons "
            f"above 10 MeV. {why_maps}{before}",
        ),
        "belt_passes": tr["passes"],
        "electron_fluence_gt1mev": belt_q(
            tr["e"],
            "cm^-2",
            f"{why_maps} The solar-{tr['other']}imum maps give {tr['e_other']:.2g}.",
        ),
        "fluence_gt10mev": belt_q(
            tr["p"],
            "cm^-2",
            f"Trapped protons above 10 MeV. {why_maps} The solar-{tr['other']}imum maps "
            f"give {tr['p_other']:.2g}.",
        ),
    }


def sep_note(n: int) -> str:
    if n == 0:
        return (
            "No solar particle event crossed NOAA's threshold (10 pfu above 10 MeV at GOES) "
            "during the trip (NASA DONKI)."
        )
    events = "One solar particle event" if n == 1 else f"{n} solar particle events"
    return (
        f"{events} crossed NOAA's threshold (10 pfu above 10 MeV at GOES) during the trip, "
        f"from NASA DONKI; {'its' if n == 1 else 'their'} fluence is not worked out."
    )


def _surface_note(
    sky: dict[str, Any] | None, surface: dict[str, Any] | None, sky_note: str | None
) -> str | None:
    if sky is None:
        return "No skyline is worked out for this landing site, so the surface dose is not given."
    if surface is None and not sky.get("none_reason"):
        return (
            "The Oulu neutron monitor table does not reach the landing month, so the surface "
            "dose is not given."
        )
    return sky_note


def along_trip(
    sc: str,
    cover: list[tuple[float, float]],
    start: datetime,
    end: datetime,
    sky: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None, list[dict[str, Any]]]:
    """(radiation block, why none, sources). Runs on the SPICE thread."""
    if not belts.available():
        return None, "The belt model (IRBEM, in spacepy) is not installed on this machine.", []
    phase = solar_phase(start)
    if phase is None:
        return None, "OMNI's sunspot record does not reach the trip (polar-data sync).", []
    t, times, geo = belt_samples(sc, cover)
    tr = trapped(t, times, geo, phase, 0.0)
    month = f"{start:%Y-%m}"
    maps = f"AE8/AP8 {phase.solar.upper()} (IRBEM)"
    why_maps = f"{maps}: {phase.words}."
    r0_km = (
        float(
            np.linalg.norm(
                spice.positions(sc, "EARTH", "J2000", "NONE", np.array([cover[0][0]]), knot_s=None)[
                    0
                ]
            )
        )
        / 1000.0
    )
    # The climb from the parking orbit crosses the belts; if the reconstruction starts
    # above them, or inside them, that part is not seen and the numbers are lower bounds.
    tr["open"] = tr["open"] or r0_km > 1.2 * belts.RE_KM
    before = (
        f" NASA's reconstruction starts {r0_km - belts.RE_KM:,.0f} km above Earth, so the climb "
        "out of the parking orbit before it is not counted: a lower bound."
        if tr["open"]
        else ""
    )
    sources = [
        lifecycle.source_ref(
            "AE8/AP8 trapped radiation models, via IRBEM", "https://prbem.github.io/IRBEM/"
        ),
        lifecycle.source_ref("OMNI hourly sunspot numbers (NASA SPDF)", space_climate.OMNI_URL),
        lifecycle.source_ref(
            "Oulu neutron monitor via NMDB (" + space_climate.NMDB_ACK + ")", space_climate.OULU_URL
        ),
        lifecycle.source_ref(
            "Matthiä et al. 2013, doi:10.1016/j.asr.2012.09.022",
            "https://doi.org/10.1016/j.asr.2012.09.022",
        ),
        lifecycle.source_ref("CRaTER dose rate (Schwadron et al. 2012)", str(CRATER["url"])),
    ]
    trip_dose = gcr_dose(month, CRATER, float(CRATER["gy_per_year"]) * 1000.0 / 365.25)
    if trip_dose is None:
        gcr_q = lifecycle.missing(
            "mGy/d", "The Oulu neutron monitor table does not reach the trip."
        )
    else:
        v, words = trip_dose
        gcr_q = _q(v, "mGy/d", pm=v * GCR_PM, source=words)
    surface = None
    sky_note: str | None = None
    if sky is not None and sky.get("none_reason"):
        sky_note = str(sky["none_reason"])
    elif sky is not None:
        land_month = str(sky.get("month") or month)
        sd = gcr_dose(land_month, LND, float(LND["ugy_per_hour"]) * 24.0 / 1000.0)
        frac = float(sky["open_fraction"])
        flat = not sky.get("skyline_covered", True)
        if flat:
            sky_note = (
                "The elevation model does not cover this landing site, so its horizon is "
                "taken as flat (open sky 1); the surface dose is an assumption to that extent."
            )
        if sd is not None:
            v, words = sd
            surface = {
                "site_id": sky["site_id"],
                "open_sky": lifecycle.q(
                    Quantity(
                        value=frac,
                        unit="",
                        provenance="assumed",
                        no_margin_reason="A flat horizon, assumed: the elevation model does "
                        "not cover this site.",
                    )
                )
                if flat
                else _q(
                    frac,
                    "",
                    no_margin_reason="From the site's skyline, the cosmic rays taken as arriving "
                    "evenly from every direction; 1 is a flat horizon.",
                ),
                "gcr_dose_mgy_day": _q(
                    v * frac,
                    "mGy/d",
                    pm=v * frac * GCR_PM,
                    source=f"{words} Times the site's open sky ({frac:.3f}).",
                ),
            }
            sources.append(
                lifecycle.source_ref("Chang'e-4 LND dose rate (Zhang et al. 2020)", str(LND["url"]))
            )
    during, events_why = _events_during(start, end)
    sources.append(
        lifecycle.source_ref(
            "NASA DONKI solar particle events", "https://kauai.ccmc.gsfc.nasa.gov/DONKI/"
        )
    )
    block = {
        **belt_numbers(tr, r0_km, why_maps, before),
        "gcr_dose_mgy_day": gcr_q,
        "surface": surface,
        "surface_note": _surface_note(sky, surface, sky_note),
        "sep_events": [{"t": e["t"], "link": e["link"]} for e in during],
        "sep_note": events_why or sep_note(len(during)),
        "scenarios": _scenarios(),
        "screening_note": SCREENING_NOTE,
        "confirm_in": CONFIRM_IN,
    }
    return block, None, sources
