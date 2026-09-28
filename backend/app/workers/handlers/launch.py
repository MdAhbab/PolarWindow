"""The ``launch`` job (T2, D1/D2): launch opportunities for a mission.

A flown mission gets the launch it flew, worked out again from NASA's
reconstructed trajectory (its TLI) and the climb of the vehicle's other
flights, beside the published liftoff. A planned mission with a pad, a
vehicle and a landing spot gets a calendar backed out from the landing:
the times the spot allows a landing (``core.landing_windows``), minus the
time in lunar orbit, minus the flight, then the day's launch instant from a
climb in the direction the vehicle's direct lunar flights climbed (due east
when there are none), inside the pad's azimuth limits, corrected in the full
force model (``core.transfer.design``).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

from app.core import forces, landing_windows, launchwin, propagate, spice, transfer
from app.core.intervals import Run
from app.core.quantity import Quantity
from app.core.spice import R_MOON_M
from app.core.vec import rotate, unit
from app.data import catalogues, climatology, thunder_climatology
from app.db.repositories.jobs import InputRef
from app.db.session import session_scope
from app.services import ascent, launch_service, lifecycle, site_service
from app.workers.compute import HandlerResult, JobContext, handler

H = 3600.0
DAY = 86_400.0
#: Direct transfers considered, days (assumed; the flown ones took 4.5 and 6.3).
FLIGHT_DAYS = (3.5, 6.5)
#: Closest approach aimed at: a 100 km lunar orbit (assumed, as IM-1 and IM-2 flew).
PERI_ALT_M = 100_000.0
#: A coast this much shorter than any flown one is still accepted.
COAST_SLACK_S = 15 * 60.0
#: The longest coast accepted (assumed): a little over one parking orbit. When the Moon
#: is south of the equator a due-east climb reaches the TLI point only after most of an
#: orbit, and upper-stage coast limits are not published; such a coast is flagged.
COAST_MAX_S = 120 * 60.0
#: How far the corrected liftoff may move from the due-east guess.
MAX_SHIFT_S = 3 * H
#: The designed instant against the flown liftoff, given the flown arrival and climbing in
#: the other direct flight's direction: IM-1 15.8 min early and IM-2 17.5 min late
#: (docs/validation.md, D1).
#: The larger is the margin.
DESIGN_PM_S = 18 * 60.0
#: With no direct flight of the vehicle measured, a due-east climb: IM-1 9.8 min and IM-2
#: 43.8 min late designed that way with the arrival orbit's way round left free, as the
#: calendar leaves it (docs/validation.md, D1).
DUE_EAST_PM_S = 44 * 60.0
#: Beyond this lead the ensemble forecasts do not reach.
FORECAST_LEAD_S = 16 * DAY
MAX_DESIGNS = 150
#: Landing times tried in each allowed stretch: its start, then a day apart.
LANDINGS_PER_WINDOW = 5
#: A climb's plane sweeps past the Moon's direction twice a sidereal day, once
#: northward and once southward. Launches aimed at different landings move each instant
#: by hours, so instants of the same sweep within half a day are one opportunity.
SAME_OPPORTUNITY_S = 12 * H
SITE_STEP_S = 1800


def _q(value: float | None, unit_: str, **kw: Any) -> dict[str, Any]:
    return lifecycle.q(Quantity(value=value, unit=unit_, **kw))


def _epoch(et: float) -> float:
    return lifecycle.parse_time(spice.et_to_utc(et)).timestamp()


@dataclass
class Track:
    """Sun and Earth over the landing spot, on the site engine's time grid."""

    start: datetime
    t_s: Any
    sun_el: Any
    sun_margin: Any
    sun_up: list[Run]
    earth_up: list[Run]
    t1: float

    def at(self, epoch: float) -> float:
        return epoch - self.start.timestamp()


async def _track(site_id: str, start: datetime, end: datetime) -> Track:
    async with session_scope() as s:
        cw = await site_service.compute(s, site_id, start, end, SITE_STEP_S)
    r = cw.result
    return Track(
        start=r.start,
        t_s=r.sun.t_s,
        sun_el=r.sun.el_deg,
        sun_margin=r.sun.margin_deg,
        sun_up=r.sun.arcs,
        earth_up=r.earth.arcs,
        t1=(r.end - r.start).total_seconds(),
    )


def _landing_numbers(tr: Track, t: float, span: tuple[float, float] | None) -> dict[str, Any]:
    """Sun height, sunlight left and Earth at a landing time ``t`` (track seconds)."""
    el = float(landing_windows.value_at(tr.t_s, tr.sun_el, t))
    if span is not None:
        lo_t, hi_t = max(span[0], 0.0), min(span[1], tr.t1)
        sel = (tr.t_s >= lo_t) & (tr.t_s <= hi_t)
        vals = tr.sun_el[sel] if sel.any() else np.array([el])
        sun = _q(el, "deg", provenance="computed", lo=float(vals.min()), hi=float(vals.max()))
    else:
        sun = _q(
            el,
            "deg",
            provenance="computed",
            no_margin_reason="The Sun's centre at the chosen landing time.",
        )
    left, cut = landing_windows.sunlight_after(t, tr.sun_up, tr.t1)
    return {
        "sun_elevation_deg": sun,
        "sunlight_after_h": _q(
            left / H,
            "h",
            provenance="computed",
            open=cut,
            no_margin_reason="Set by the skyline from the elevation model.",
        ),
        "earth_up": landing_windows.inside(tr.earth_up, t),
    }


# ---------------------------------------------------------------------------
# A flown mission: the launch it flew, worked out again from its TLI
# ---------------------------------------------------------------------------


def _flown_azimuth_reason(pad_id: str, fl: Any, gm: float) -> str:
    pad = catalogues.load("launch_sites").get(pad_id)
    ground = launchwin.ground_azimuth(pad.lat_deg, fl.azimuth_deg, math.sqrt(gm / fl.r_park_m))
    lo, hi = pad.azimuth_min_deg, pad.azimuth_max_deg
    limits = (
        f", {'inside' if lo <= ground <= hi else 'outside'} the pad's {lo:.0f} to {hi:.0f}°"
        if lo is not None and hi is not None
        else ""
    )
    return (
        "The climb's direction is not published. This is the inertial one worked out from "
        "NASA's reconstruction: the plane through the pad at liftoff and the point where it "
        f"left Earth for the Moon (an orbit inclined {fl.inc_deg:.2f} degrees to the "
        f"equator). Over the ground it is {ground:.1f}°{limits}."
    )


async def _flown(ctx: JobContext, p: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    flights = await spice.run_async(ascent.measure, tuple(tuple(x) for x in p["flights"]))
    mid = p["mission_id"]
    f = flights.get(mid)
    if f is None:
        return [], "NASA's reconstructed trajectory for this mission is not on this machine yet."
    gm = await spice.run_async(ascent.gm_earth)
    asc = await spice.run_async(ascent.ascent, p["vehicle_id"], flights, gm)
    ctx.progress(0.4, "The flown climb measured.")
    fl = f.launch
    t0_pub = _epoch(f.t0_et)
    names: dict[str, str] = p.get("names", {})
    others = [m for m in asc.flights if m != mid] if asc else []
    if asc is not None and mid in asc.hold_one_out_s:
        err = asc.hold_one_out_s[mid]
        pm = max(abs(v) for v in asc.hold_one_out_s.values())
        t0 = _q(t0_pub + err, lifecycle.EPOCH_UNIT, provenance="computed", pm=max(pm, 1.0))
        basis = "reconstructed"
        used = ", ".join(names.get(o, o) for o in others)
        note = (
            f"Worked out from NASA's reconstructed trajectory: the time and place it left Earth "
            f"for the Moon, and "
            f"the climb of this vehicle's other flights ({used}). It is "
            f"{abs(err):.0f} s {'after' if err > 0 else 'before'} the published liftoff; "
            f"the margin is the largest such difference over those flights."
        )
    else:
        t0 = lifecycle.published_date(p["t0"], p["t0_source"])
        basis = "published"
        note = (
            "The published liftoff. This vehicle has one reconstructed lunar launch here, "
            "so its climb cannot be checked against another flight."
        )
    arrive_et = fl.t_arrive
    landing = p.get("landing")
    if arrive_et is None:
        flight = lifecycle.missing("d", "It did not reach the Moon.")
        wait = lifecycle.missing("d", "It did not reach the Moon.")
        kind = "direct"
    else:
        days = (arrive_et - fl.t_tli) / DAY
        kind = "phasing_loops" if days > 10.0 else "direct"
        flight = _q(
            days,
            "d",
            provenance="computed",
            no_margin_reason="From leaving Earth for the Moon to the first close pass of the "
            "Moon in NASA's reconstruction.",
        )
        if landing:
            lt = lifecycle.published_date(landing, p["landing_source"])
            wait = _q(
                (lt["value"] - _epoch(arrive_et)) / DAY,
                "d",
                provenance="computed",
                pm=lt["pm"] / DAY,
            )
        else:
            wait = lifecycle.missing("d", "The landing time is not published.")
    land: dict[str, Any]
    if landing and p.get("site_id"):
        lt = lifecycle.published_date(landing, p["landing_source"])
        mid_t = datetime.fromtimestamp(lt["value"], UTC)
        tr = await _track(p["site_id"], mid_t - timedelta(days=2), mid_t + timedelta(days=18))
        t = tr.at(lt["value"])
        span = (t - lt["pm"], t + lt["pm"]) if lt["pm"] > 60.0 else None
        land = {"time": lt, **_landing_numbers(tr, t, span)}
        rule, _ = launch_service.landing_rule(p["parameters"], p.get("surface_days"))
        ok = landing_windows.windows(
            tr.t_s,
            tr.sun_el,
            tr.sun_margin,
            tr.sun_up,
            tr.earth_up,
            landing_windows.Rule(rule.sun_min_deg, rule.sun_max_deg, None),
        )
        inside = landing_windows.inside(ok, t)
        note += (
            " The landing fell inside the times the landing rule allows."
            if inside
            else " The landing fell outside the times the landing rule allows."
        )
    else:
        why = "It did not land." if arrive_et is None or not landing else "No landing spot."
        land = {
            "time": lifecycle.missing(lifecycle.EPOCH_UNIT, why),
            "sun_elevation_deg": lifecycle.missing("deg", why),
            "sunlight_after_h": lifecycle.missing("h", why),
            "earth_up": False,
        }
    opp = {
        "id": f"{p['pad_id']}-flown",
        "pad_id": p["pad_id"],
        "pad_name": launch_service.pads(p["pad_id"])[0]["name"],
        "vehicle_id": p["vehicle_id"],
        "t0": t0,
        "kind": "instantaneous",
        "window_open": None,
        "window_close": None,
        "transfer": {"type": kind, "flight_days": flight, "orbit_wait_days": wait},
        "landing": land,
        "weather": "none",
        "weather_note": "This launch has flown: the weather rules show the rules and limits "
        "that applied; the forecasts made before it were not kept.",
        "basis": basis,
        "note": note,
        "azimuth_deg": _q(
            fl.azimuth_deg,
            "deg",
            provenance="computed",
            no_margin_reason=_flown_azimuth_reason(p["pad_id"], fl, gm),
        ),
        "dv_tli_m_s": _q(
            fl.dv_tli_m_s,
            "m/s",
            provenance="computed",
            no_margin_reason="Speed on leaving Earth for the Moon minus the speed in the circular "
            "parking orbit, from NASA's reconstruction propagated back to that point.",
        ),
        "coast_min": _q(
            fl.tau_s / 60.0,
            "min",
            provenance="computed",
            no_margin_reason="Published liftoff to leaving Earth for the Moon, as found in the "
            "reconstruction.",
        ),
    }
    return [opp], None


# ---------------------------------------------------------------------------
# A planned mission: a calendar backed out from the landing spot
# ---------------------------------------------------------------------------


def _wait(p: dict[str, Any], flights: dict[str, ascent.Flight]) -> tuple[float, dict[str, Any]]:
    """Days in lunar orbit before landing: the lander's flown precedent, else assumed."""
    waits: dict[str, float] = {}
    for mid, landing in p["precedents"].items():
        f = flights.get(mid)
        if f is None or f.launch.t_arrive is None or landing is None:
            continue
        lt = lifecycle.published_date(landing, "mission record")
        waits[mid] = (lt["value"] - _epoch(f.launch.t_arrive)) / DAY
    same = [waits[m] for m in p["same_lander"] if m in waits]
    if same:
        v = float(np.mean(same))
        names = ", ".join(m for m in p["same_lander"] if m in waits)
        src = f"As this lander's flown missions waited ({names})."
        if len(same) == 1:
            return v, _q(v, "d", provenance="assumed", no_margin_reason=src, source=src)
        return v, _q(v, "d", provenance="assumed", lo=min(same), hi=max(same), source=src)
    flown = (
        f" Flown landers waited from {min(waits.values()):.1f} to {max(waits.values()):.1f} "
        "days, a choice each team made, so their spread is not a margin for this one."
        if waits
        else ""
    )
    why = "No lunar-orbit time is published for this lander; one day is assumed." + flown
    return 1.0, _q(1.0, "d", provenance="assumed", no_margin_reason=why, source=why)


def climb_direction(asc: ascent.Ascent) -> float:
    """The inertial azimuth a designed launch climbs at: the mean of the vehicle's direct
    lunar flights (phasing loops fly their own way), due east when it has none."""
    return asc.direct_azimuth_deg if asc.direct_azimuth_deg is not None else 90.0


def _design_all(
    p: dict[str, Any],
    asc: ascent.Ascent,
    tr: Track,
    windows: list[Run],
    wait_d: float,
    t_from: float,
    t_to: float,
) -> list[dict[str, Any]]:
    """Synchronous (SPICE thread): every opportunity whose design converges."""
    start_et = spice.utc_to_et(lifecycle.iso(tr.start)[:-1])
    et_from = spice.utc_to_et(datetime.fromtimestamp(t_from, UTC).isoformat()[:19])
    et_to = spice.utc_to_et(datetime.fromtimestamp(t_to, UTC).isoformat()[:19])
    tables = propagate.environment(et_from - DAY, et_to + (FLIGHT_DAYS[1] + 3) * DAY)
    pad_at = ascent.pad_j2000(p["pad_id"])
    gm = tables.gm_earth
    site_lat = abs(float(p["site_lat_deg"]))
    inc = 90.0 if site_lat >= 60.0 else min(90.0, site_lat + 10.0)
    coast_lo = min(asc.coasts_s) - COAST_SLACK_S
    coast_hi = COAST_MAX_S
    coast_nom = float(np.mean(asc.coasts_s))
    az = climb_direction(asc)

    def parking_at(tl: float) -> transfer.Parking:
        ph = unit(pad_at(tl))
        h = launchwin.climb_plane(ph, az)
        return transfer.Parking(tl, asc.r_park_m * rotate(ph, h, asc.c_rad), h, gm)

    out: list[dict[str, Any]] = []
    designs = 0
    lower = t_from + coast_lo + FLIGHT_DAYS[0] * DAY + wait_d * DAY - tr.start.timestamp()
    upper = t_to + coast_hi + FLIGHT_DAYS[1] * DAY + wait_d * DAY - tr.start.timestamp()
    for w in windows:
        if not w.value or w.end < lower or w.start > upper:
            continue
        first = max(w.start, lower)
        tries = [first + k * DAY for k in range(LANDINGS_PER_WINDOW)]
        for land_t in [t for t in tries if t <= min(w.end, upper)]:
            designs = _design_landing(
                land_t,
                w,
                start_et,
                wait_d,
                tables,
                pad_at,
                parking_at,
                inc,
                az,
                (coast_lo, coast_hi, coast_nom),
                asc,
                (t_from, t_to),
                out,
                designs,
            )
    return out


def _design_landing(
    land_t: float,
    w: Run,
    start_et: float,
    wait_d: float,
    tables: forces.Tables,
    pad_at: Any,
    parking_at: Any,
    inc: float,
    az: float,
    coasts: tuple[float, float, float],
    asc: ascent.Ascent,
    dates: tuple[float, float],
    out: list[dict[str, Any]],
    designs: int,
) -> int:
    """Every launch that lands at ``land_t``: one design per instant in reach at which a
    climb at ``az`` (inertial) holds the Moon's direction at arrival."""
    coast_lo, coast_hi, coast_nom = coasts
    t_from, t_to = dates
    arrive_et = start_et + land_t - wait_d * DAY
    target = transfer.Target(arrive_et, R_MOON_M + PERI_ALT_M, inc)
    moon = unit(forces.body_state(tables, forces.MOON, np.array([arrive_et]))[0][:3])

    def gap(t: float, moon: Any = moon) -> float:
        return launchwin.climb_gap(unit(pad_at(t)), moon, az)

    lo_et = arrive_et - FLIGHT_DAYS[1] * DAY - coast_hi
    hi_et = arrive_et - FLIGHT_DAYS[0] * DAY - coast_lo
    for root in launchwin.roots(gap, lo_et, hi_et, step_s=600.0):
        if designs >= MAX_DESIGNS:
            break
        designs += 1
        park = parking_at(root)
        try:
            t_g, dv_g = transfer.guess(
                tables, park, arrive_et, arrive_et - root - coast_nom, root + coast_lo
            )
            d = transfer.design(tables, target, parking_at, root, t_g - root, dv_g)
        except (ValueError, RuntimeError):
            continue
        flight_d = (d.t_peri - d.t_tli) / DAY
        if not (
            d.converged
            and coast_lo <= d.coast_s <= coast_hi
            and FLIGHT_DAYS[0] <= flight_d <= FLIGHT_DAYS[1]
            and abs(d.t_launch - root) <= MAX_SHIFT_S
        ):
            continue
        t0 = _epoch(d.t_launch)
        if not (t_from <= t0 <= t_to):
            continue
        out.append(
            {
                "t0": float(t0),
                "northward": bool(gap(root + 60.0) > gap(root - 60.0)),
                "coast_s": float(d.coast_s),
                "long_coast": bool(d.coast_s > max(asc.coasts_s) + 300.0),
                "flown_coasts": (float(min(asc.coasts_s)), float(max(asc.coasts_s))),
                "dv": float(d.dv_tli_m_s),
                "flight_d": float(flight_d),
                "land_t": float(land_t),
                "window": (float(w.start), float(w.end)),
            }
        )
    return designs


async def _designed(ctx: JobContext, p: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    flights = await spice.run_async(ascent.measure, tuple(tuple(x) for x in p["flights"]))
    gm = await spice.run_async(ascent.gm_earth)
    asc_vehicle = p["ascent_vehicle"]
    asc = await spice.run_async(ascent.ascent, asc_vehicle, flights, gm)
    if asc is None:
        return [], (
            "No lunar launch of this vehicle has been reconstructed here, so how it climbs "
            "to orbit is not known and launch instants cannot be worked out."
        )
    ctx.progress(0.15, "The vehicle's climb measured from its flown launches.")
    names: dict[str, str] = p.get("names", {})
    az = climb_direction(asc)
    pad = catalogues.load("launch_sites").get(p["pad_id"])
    az_ground = launchwin.ground_azimuth(pad.lat_deg, az, math.sqrt(gm / asc.r_park_m))
    lo_az, hi_az = pad.azimuth_min_deg, pad.azimuth_max_deg
    if lo_az is not None and hi_az is not None and not (lo_az <= az_ground <= hi_az):
        return [], (
            f"The vehicle's lunar climb heads {az_ground:.1f} degrees from north over the "
            f"ground, outside this pad's allowed {lo_az:.0f} to {hi_az:.0f} degrees."
        )
    wait_d, wait_q = _wait(p, flights)
    rule, _ = launch_service.landing_rule(p["parameters"], p.get("surface_days"))
    t_from = lifecycle.parse_time(p["from"]).timestamp()
    t_to = lifecycle.parse_time(p["to"]).timestamp()
    tr_start = datetime.fromtimestamp(t_from, UTC) + timedelta(days=FLIGHT_DAYS[0])
    tr_end = datetime.fromtimestamp(t_to, UTC) + timedelta(
        days=FLIGHT_DAYS[1] + wait_d + 1 + max(15.0, rule.surface_days or 0.0)
    )
    tr = await _track(p["site_id"], tr_start, tr_end)
    ctx.progress(0.35, "Sunlight and Earth over the landing spot worked out.")
    wins = landing_windows.windows(tr.t_s, tr.sun_el, tr.sun_margin, tr.sun_up, tr.earth_up, rule)
    if not any(w.value for w in wins):
        return [], "The landing rule allows no landing time in these dates."
    found = await spice.run_async(_design_all, p, asc, tr, wins, wait_d, t_from, t_to)
    ctx.progress(0.9, "Launch instants worked out.")
    now = datetime.now(UTC).timestamp()
    pad_name = launch_service.pads(p["pad_id"])[0]["name"]
    assumed_climb = asc_vehicle != p["vehicle_id"]
    # One opportunity per sweep of the climb plane past the Moon (at most two a sidereal
    # day): of the landings a launch then reaches, the earliest (most sunlight after it).
    clusters: list[list[dict[str, Any]]] = []
    for sweep in (True, False):
        mine: list[list[dict[str, Any]]] = []
        for o in sorted((x for x in found if x["northward"] is sweep), key=lambda x: x["t0"]):
            if mine and o["t0"] - mine[-1][0]["t0"] < SAME_OPPORTUNITY_S:
                mine[-1].append(o)
            else:
                mine.append([o])
        clusters += mine
    clusters.sort(key=lambda g: min(x["t0"] for x in g))
    flown_az = ", ".join(f"{names.get(m, m)} {asc.azimuths_deg[m]:.1f}°" for m in asc.direct)
    limits = (
        f", inside the pad's {lo_az:.0f} to {hi_az:.0f}°"
        if lo_az is not None and hi_az is not None
        else ""
    )
    if asc.direct:
        pm_s = DESIGN_PM_S
        climb_words = (
            f"A climb from the pad at {az:.1f}° from north (inertial; {az_ground:.1f}° over "
            f"the ground{limits}), the mean of the vehicle's direct lunar flights ({flown_az})."
        )
        az_reason = (
            f"The direction the vehicle's direct lunar flights climbed ({flown_az}), measured "
            f"from the pad at liftoff and where each left Earth for the Moon; over the ground "
            f"it is {az_ground:.1f}°{limits}. Each degree moves the launch instant by about "
            "7 minutes, which sets the margin on the liftoff."
        )
    else:
        pm_s = DUE_EAST_PM_S
        climb_words = (
            f"A due-east climb from the pad{limits}: the vehicle has no direct lunar flight "
            "measured here."
        )
        az_reason = (
            "Due east is assumed: the vehicle has no direct lunar flight measured here "
            "(phasing loops climb their own way)."
        )
    opps: list[dict[str, Any]] = []
    for group in clusters:
        o = min(group, key=lambda x: (x["land_t"], x["flight_d"]))
        land_epoch = tr.start.timestamp() + o["land_t"]
        weather, weather_note = _weather(o["t0"] - now, p["pad_id"], p["vehicle_id"])
        a, b = o["window"]
        when = datetime.fromtimestamp(o["t0"], UTC)
        note = (
            f"{climb_words} The flight is corrected in the full force model to reach a "
            "100 km lunar orbit when the landing time allows; the margin is the largest "
            "difference from a flown liftoff seen when designing that way."
        )
        if o["long_coast"]:
            lo_c, hi_c = o["flown_coasts"]
            note += (
                f" Its coast before leaving Earth for the Moon, {o['coast_s'] / 60:.0f} min, is "
                f"longer than any flown one "
                f"({lo_c / 60:.0f} to {hi_c / 60:.0f} min); whether the upper stage can coast "
                "that long is not published."
            )
        if assumed_climb:
            note += (
                f" This vehicle has no reconstructed lunar launch; the climb of the "
                f"{catalogues.load('vehicles').get(asc_vehicle).name} is assumed."
            )
        opps.append(
            {
                "id": f"{p['pad_id']}-{when:%Y%m%dT%H%M}",
                "pad_id": p["pad_id"],
                "pad_name": pad_name,
                "vehicle_id": p["vehicle_id"],
                "t0": _q(o["t0"], lifecycle.EPOCH_UNIT, provenance="computed", pm=pm_s),
                "kind": "instantaneous",
                "window_open": None,
                "window_close": None,
                "transfer": {
                    "type": "direct",
                    "flight_days": _q(
                        o["flight_d"],
                        "d",
                        provenance="computed",
                        no_margin_reason="From leaving Earth for the Moon to the closest "
                        "approach of the "
                        "designed flight.",
                    ),
                    "orbit_wait_days": wait_q,
                },
                "landing": {
                    "time": _q(
                        land_epoch,
                        lifecycle.EPOCH_UNIT,
                        provenance="computed",
                        lo=tr.start.timestamp() + a,
                        hi=tr.start.timestamp() + b,
                    ),
                    **_landing_numbers(tr, o["land_t"], None),
                },
                "weather": weather,
                "weather_note": weather_note,
                "basis": "designed",
                "note": note,
                "azimuth_deg": _q(
                    az,
                    "deg",
                    provenance="assumed",
                    no_margin_reason=az_reason,
                ),
                "dv_tli_m_s": _q(
                    o["dv"],
                    "m/s",
                    provenance="computed",
                    no_margin_reason="Designed with the Moon as a point mass.",
                ),
                "coast_min": _q(
                    o["coast_s"] / 60.0,
                    "min",
                    provenance="computed",
                    no_margin_reason="Liftoff to leaving Earth for the Moon, in the designed "
                    "flight.",
                ),
            }
        )
    if not opps:
        return [], (
            "No launch in these dates reaches the Moon for a landing the rule allows with a "
            "direct transfer of 3.5 to 6.5 days."
        )
    return opps, None


def _climatologies(pad_id: str, vehicle_id: str) -> tuple[bool, bool]:
    """Whether a wind climatology (built for the pad's region, and the vehicle has a
    published wind limit to read it against) and a thunder climatology (built for the
    region, and a lightning rule applies to the vehicle) can be shown."""
    site = catalogues.load("launch_sites").get(pad_id)
    region = catalogues.MODEL_REGION_OF_RANGE.get(site.launch_range, "")
    rules = [r for r in catalogues.load("weather_rules").records if vehicle_id in r.applies_to]
    wind = climatology.load(region) is not None and any(
        r.variable == "wind_speed" and r.threshold is not None for r in rules
    )
    thunder = thunder_climatology.load(region) is not None and any(
        r.variable == "lightning_distance" for r in rules
    )
    return wind, thunder


def _weather(lead_s: float, pad_id: str, vehicle_id: str) -> tuple[str, str]:
    """What the weather rules can show for a designed opportunity, and why."""
    if lead_s < 0:
        return "none", "This launch time has passed; the weather rules show the rules and limits."
    if lead_s <= FORECAST_LEAD_S:
        return "forecast", (
            "Forecasts reach this launch: the weather rules show what they say for each rule."
        )
    wind, thunder = _climatologies(pad_id, vehicle_id)
    shows = [
        *(
            ["how often the wind limit was broken in this month and hour since 2001"]
            if wind
            else []
        ),
        *(
            ["how often thunder was heard at the pad in this month and hour since 2019"]
            if thunder
            else []
        ),
    ]
    if shows:
        return "climatology", (
            "More than 16 days away, beyond the forecasts: the weather rules show "
            f"{' and '.join(shows)}, and the other rules."
        )
    return "none", (
        "More than 16 days away, beyond the forecasts, and there is no climatology to read "
        "for this vehicle at this pad: the weather rules show the rules and limits."
    )


@handler("launch")
async def run(ctx: JobContext) -> HandlerResult:
    p = ctx.job.params
    t_wall = time.perf_counter()
    await spice.run_async(
        spice.load_extra,
        [ascent.spk_path(m) for m, *_ in p["flights"] if ascent.spk_path(m).exists()],
    )
    if p["basis"] == "flown":
        opps, why = await _flown(ctx, p)
    else:
        opps, why = await _designed(ctx, p)
    _, landing_rule = launch_service.landing_rule(p["parameters"], p.get("surface_days"))
    data = {
        "none_reason": why,
        "start": p.get("from"),
        "end": p.get("to"),
        "dates_note": p["dates_note"],
        "vehicle_id": p["vehicle_id"],
        "pads": launch_service.pads(p["pad_id"]),
        "opportunities": opps,
        "landing_rule": landing_rule,
        "published_t0": (
            lifecycle.published_date(p["t0"], p["t0_source"]) if p.get("t0") else None
        ),
    }
    meta = lifecycle.meta(
        engines=("lw", "traj", "vis"),
        sources=[
            lifecycle.source_ref(
                "NASA's reconstructed CLPS trajectories (NAIF CLPS SPICE archive)",
                "https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/",
            ),
            lifecycle.source_ref(
                "NAIF DE440 planetary ephemeris, Earth orientation and GM values",
                "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/",
            ),
            lifecycle.source_ref("Launch Library 2 (published liftoff times)", p["t0_source"]),
        ],
        parts=[
            (
                "Launch instant",
                "A flown launch is worked out again from where it left Earth for the Moon "
                "and the vehicle's other flights (within seconds); a designed one climbs in "
                "the direction the vehicle's direct lunar flights climbed, which put IM-1 "
                "16 minutes before and IM-2 18 minutes after their real liftoffs when each "
                "was designed from the other's direction.",
            ),
            (
                "Flight",
                "Direct transfers of 3.5 to 6.5 days to a 100 km lunar orbit (assumed); the "
                "Moon is a point mass during the design, which moves the arrival by metres. "
                "Phasing loops (as Blue Ghost 1 flew) are designed only for the validation, "
                "since no planned mission has published one; low-energy transfers are not "
                "modelled.",
            ),
            (
                "Landing times",
                "Sun and Earth over the skyline from the elevation model; the time in "
                "lunar orbit before landing is the lander's flown one, or assumed.",
            ),
        ],
        compute_ms=(time.perf_counter() - t_wall) * 1000.0,
        computed_at=datetime.now(UTC),
    )
    inputs = [
        InputRef("catalogue", "launch_sites", catalogues.load("launch_sites").version),
        InputRef("catalogue", "vehicles", catalogues.load("vehicles").version),
        InputRef("mission", p["mission_id"], p["data_version"]),
    ]
    return HandlerResult(
        result=lifecycle.jsonable({"data": data, "meta": meta}),
        inputs=inputs,
        message="Launch opportunities worked out.",
    )
