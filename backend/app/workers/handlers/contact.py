"""The ``contact`` job (T1, F1 and F4): who can hear the lander, and how long a message waits.

Runs in the compute worker. Inputs: the mission record, its landing spot's
skyline, the DSN antennas and their published masks, and the relays; output:
the Contact section's ``data`` and ``meta``, and every input's version.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import numpy.typing as npt

from app.config import ENGINE_VERSION
from app.core import contact as core_contact
from app.core import intervals, network, spice, timeline, visibility
from app.core.quantity import Quantity
from app.core.spice import R_MOON_M
from app.data import catalogues
from app.db.repositories.jobs import InputRef
from app.db.repositories.missions import MissionRepository
from app.db.session import session_scope
from app.services import lifecycle, site_service
from app.workers.compute import HandlerResult, JobContext, handler
from app.workers.handlers import relay_sweep

C_M_S = 299_792_458.0
H = 3600.0


def _hours(
    runs_s: float, pm_s: float | None, *, open_: bool = False, no_margin: str | None = None
) -> dict[str, Any]:
    if pm_s == 0.0 and no_margin is None:
        no_margin = "No rise or set of Earth inside these dates, so no edge to time."
        pm_s = None
    if pm_s is None:
        return lifecycle.q(
            Quantity(
                value=runs_s / H,
                unit="h",
                provenance="computed",
                no_margin_reason=no_margin or "No timing margin.",
                open=open_,
            )
        )
    return lifecycle.q(
        Quantity(value=runs_s / H, unit="h", provenance="computed", pm=pm_s / H, open=open_)
    )


def _stretches(runs: list[intervals.Run], start: datetime, t1: float) -> list[dict[str, Any]]:
    out = []
    for r in runs:
        if not r.value:
            continue
        out.append(
            lifecycle.stretch(
                start + timedelta(seconds=r.start),
                start + timedelta(seconds=r.end),
                r.start <= intervals.EPS_S,
                r.end >= t1 - intervals.EPS_S,
            )
        )
    return out


@handler("contact")
async def run(ctx: JobContext) -> HandlerResult:
    p = ctx.job.params
    t_wall = time.perf_counter()
    start = lifecycle.parse_time(p["start"])
    end = lifecycle.parse_time(p["end"])
    async with session_scope() as s:
        m = await MissionRepository(s).get(p["mission_id"])
        if m is None or m.site_id is None:
            raise ValueError("the mission or its landing spot is gone")
        cw = await site_service.compute(s, m.site_id, start, end, int(p["site_step_s"]))
    ctx.progress(0.2, "Sun and Earth over the landing spot worked out.")
    r = cw.result
    site = cw.site
    t1 = (r.end - r.start).total_seconds()

    stations = [g for g in catalogues.load("ground_stations").records if g.status == "operating"]
    step = float(p["step_s"])
    t0_et = await spice.run_async(spice.utc_to_et, lifecycle.iso(r.start))
    ets = t0_et + np.arange(0.0, t1 + step / 2, step)
    ets[-1] = t0_et + t1
    site_pos = visibility.site_position(site.lat_deg, site.lon_deg, R_MOON_M + (site.elev_m or 0.0))
    looks = await spice.run_async(
        spice.station_look_angles, [g.naif_name for g in stations], site_pos, ets
    )
    ctx.progress(0.6, "Station geometry worked out.")
    t_s = ets - t0_et
    per_station: dict[str, list[intervals.Run]] = {}
    ranges: dict[str, npt.NDArray[np.float64]] = {}
    for g, look in zip(stations, looks, strict=True):
        az = np.array([pt.az_deg for pt in g.mask])
        el = np.array([pt.el_deg for pt in g.mask])
        per_station[g.id] = core_contact.station_runs(t_s, look.az_deg, look.el_deg, az, el)
        ranges[g.id] = look.range_m
    heard_by = core_contact.heard(r.earth.arcs, per_station)
    heard_any = core_contact.any_station(heard_by)
    hs = core_contact.Stretches(heard_any, 0.0, t1)

    earth_edges = [
        (a.end, e)
        for a, (_, e) in zip(r.earth.arcs, r.earth.arc_edge_tolerance_s, strict=True)
        if e is not None
    ]
    earth_tol = timeline.metric_tolerance(r.earth)
    sun_tol = timeline.metric_tolerance(r.sun)
    heard_tol = core_contact.edge_tolerance_s(heard_any, earth_edges)

    # Contacts for routing: lander -> Earth through each station's heard stretches.
    contacts: list[network.Contact] = []
    for g in stations:
        for run in heard_by[g.id]:
            if run.value:
                i = int(np.searchsorted(t_s, run.start).clip(0, len(t_s) - 1))
                contacts.append(
                    network.Contact(
                        "lander", "earth", run.start, run.end, float(ranges[g.id][i]) / C_M_S
                    )
                )
    wait_s, wait_at, wait_open = network.longest_wait(contacts, "lander", "earth", 0.0, t1)
    unheard_s, unheard_open = hs.longest(False)
    dark_unheard = intervals.both(intervals.complement(r.sun.arcs), intervals.complement(heard_any))
    du = core_contact.Stretches(dark_unheard, 0.0, t1)
    du_s, du_open = du.longest(True)

    earth_up_s = intervals.total(r.earth.arcs, True)
    rel_cat = catalogues.load("relays")
    own = list(p.get("relays") or [])
    specs: list[relay_sweep.Spec] = []
    for rid in own + [x for x in p.get("extra_relays") or [] if x not in own]:
        try:
            rec = rel_cat.get(rid)
        except KeyError:
            continue
        if rec.role == "relay":
            specs.append(relay_sweep.spec(rec, rid in own))
    usable = [s for s in specs if s.orbits]
    rng_all = np.concatenate([ranges[g.id] for g in stations])
    unheard_q = _hours(
        unheard_s,
        None,
        open_=unheard_open,
        no_margin="Its edges are set by station masks, which are published without a tolerance.",
    )
    wait_q = lifecycle.q(
        Quantity(
            value=wait_s / 60.0,
            unit="min",
            provenance="computed",
            open=wait_open,
            no_margin_reason="Set by the same edges as the longest time unheard, plus the "
            "light time to Earth.",
        )
    )
    via_relay: dict[str, Any]
    either: dict[str, Any]
    sweep: relay_sweep.Result | None = None
    if not specs:
        via_relay = lifecycle.missing("h", "No relay is planned for this mission.")
        either = _hours(earth_up_s, earth_tol.total_s)
    elif not usable:
        via_relay = lifecycle.missing(
            "h",
            "The planned relay's orbit is not published, so time through it is not "
            "worked out. It is added when its orbit is published or entered.",
        )
        either = lifecycle.missing(
            "h",
            "Needs the relay's orbit; time in contact with Earth directly is "
            f"{earth_up_s / H:.1f} hours.",
        )
    else:
        ctx.progress(0.65, "Placing the relay over every node and phase it could have.")
        geom = await spice.run_async(
            relay_sweep.geometry,
            t0_et,
            t1,
            site_pos,
            site.lat_deg,
            site.lon_deg,
            cw.mask_record.mask.azimuths(),
            np.asarray(cw.mask_record.mask.el_deg, dtype=np.float64),
            stations,
        )
        res: relay_sweep.Result = await spice.run_async(
            relay_sweep.sweep,
            geom,
            usable,
            t1,
            r.earth.arcs,
            heard_any,
            float(rng_all.max()) / C_M_S,
            lambda f: ctx.progress(0.65 + 0.3 * f),
        )
        sweep = res
        via_relay = relay_sweep.spread_q(res.via_any, H, "h")
        either = relay_sweep.spread_q(res.either, H, "h")

    nodes: list[dict[str, Any]] = [
        {
            "id": "lander",
            "kind": "lander",
            "name": p["lander_name"],
            "operator": p.get("provider"),
            "status": "operating" if p["flown"] else "planned",
            "orbit": None,
            "launch_note": None,
        },
        {
            "id": "earth",
            "kind": "earth",
            "name": "Earth",
            "operator": None,
            "status": "operating",
            "orbit": None,
            "launch_note": None,
        },
    ]
    for g in stations:
        nodes.append(
            {
                "id": g.id,
                "kind": "station",
                "name": g.name,
                "operator": g.operator,
                "status": "operating",
                "orbit": None,
                "launch_note": None,
            }
        )
    relay_rows = []
    note = relay_sweep.sweep_note(usable, sweep.n) if sweep is not None else None
    for sp in specs:
        rec = sp.rec
        nodes.append(
            {
                "id": rec.id,
                "kind": "relay",
                "name": rec.name,
                "operator": rec.operator,
                "status": "planned"
                if rec.status == "planned"
                else ("operating" if rec.status == "operating" else "not_launched"),
                "orbit": "planned" if sp.orbits else None,
                "launch_note": rec.launch_note,
            }
        )
        if sweep is not None and sp.orbits:
            k = usable.index(sp)
            adds = relay_sweep.spread_q(sweep.adds[k], H, "h")
            via = relay_sweep.spread_q(sweep.via[k], H, "h")
        else:
            why = sp.missing or "The relay's orbit is not published."
            adds = lifecycle.missing("h", why)
            via = lifecycle.missing("h", why)
        relay_rows.append(
            {
                "id": rec.id,
                "name": rec.name,
                "adds_h": adds,
                "via_h": via,
                "status": rec.launch_note or rec.status,
                "launch_status": rec.status,
                "for_this_mission": sp.for_this_mission,
                "orbit": relay_sweep.orbit_block(rec),
                "orbit_note": rec.orbit_note,
                "sweep_note": note if sp.orbits else None,
            }
        )
    for rv in p.get("rovers") or []:
        nodes.append(
            {
                "id": rv["id"],
                "kind": "rover",
                "name": rv["name"],
                "operator": rv.get("organisation"),
                "status": "planned",
                "orbit": None,
                "launch_note": None,
            }
        )

    links = [
        {
            "from": "lander",
            "to": g.id,
            "stretches": _stretches(heard_by[g.id], r.start, t1),
            "data_rate_kbps": None,
            "margin_db": None,
        }
        for g in stations
    ]
    data = {
        "start": lifecycle.iso(r.start),
        "end": lifecycle.iso(r.end),
        "window_note": p["window_note"],
        "nodes": nodes,
        "links": links,
        "numbers": {
            "direct_h": _hours(earth_up_s, earth_tol.total_s, open_=False),
            "via_relay_h": via_relay,
            "either_h": either,
            "station_hears_h": _hours(hs.total_s, heard_tol),
            "longest_unheard_h": unheard_q
            if sweep is None
            else relay_sweep.spread_q(sweep.unheard, H, "h"),
            "longest_message_wait_min": wait_q
            if sweep is None
            else relay_sweep.spread_q(sweep.wait, 60.0, "min"),
            "dark_and_unheard_h": _hours(
                du_s, None, open_=du_open, no_margin="Edges from the Sun and the station masks."
            ),
        },
        "relays": relay_rows,
        "direct_only": None
        if sweep is None
        else {"longest_unheard_h": unheard_q, "longest_message_wait_min": wait_q},
        "relay_note": None
        if sweep is None
        else "Numbers that use the relay are ranges over what its orbit could be, if it flies as "
        "planned; a message may wait on the relay until a ground station can hear it. "
        "The same two numbers without the relay are given beside them.",
        "link_budget_note": "Line of sight only: the lander's radio power and data rate "
        "are not published, so no data rate or link margin is given.",
        "light_time_s": {"min": float(rng_all.min() / C_M_S), "max": float(rng_all.max() / C_M_S)},
        "longest_wait_from": lifecycle.iso(r.start + timedelta(seconds=wait_at)),
        "sun_total_h": _hours(intervals.total(r.sun.arcs, True), sun_tol.total_s),
    }
    ms = (time.perf_counter() - t_wall) * 1000.0
    kset = ",".join(sorted(spice.STATION_KERNELS))
    meta = lifecycle.meta(
        engines=("vis", "net", "link"),
        sources=[
            lifecycle.source_ref(
                "DSN 810-005 module 301 Rev. O horizon masks",
                stations[0].sources[1].url if stations else None,
            ),
            lifecycle.source_ref(
                "NAIF DSN station and Earth orientation kernels",
                "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/",
            ),
            lifecycle.source_ref("LOLA terrain skyline at the landing spot", None),
        ],
        parts=[
            (
                "Terrain skyline",
                "Earth's rise and set at the lander carry the skyline's timing "
                "margin; the ± on each number is those edges in quadrature.",
            ),
            (
                "Station masks",
                "DSN masks are published to a tenth of a degree without a "
                "tolerance; edges they set carry no margin here.",
            ),
            (
                "DSN schedule",
                "When a station can hear, not whether it is booked: the DSN's "
                "load is not modelled. Booked passes entered by the team are listed.",
            ),
        ],
        compute_ms=ms,
        computed_at=datetime.now(UTC),
    )
    inputs = [
        InputRef("mission", m.id, m.data_version),
        InputRef("catalogue", "ground_stations", catalogues.load("ground_stations").version),
        InputRef("catalogue", "relays", rel_cat.version),
        InputRef("terrain", site.id, f"{cw.mask_record.dem_product}@{ENGINE_VERSION}"),
        InputRef("kernel_set", "stations", kset),
    ]
    if not math.isfinite(wait_s):
        raise ValueError("message wait is not finite")
    return HandlerResult(
        result=lifecycle.jsonable({"data": data, "meta": meta}),
        inputs=inputs,
        message="Contact worked out.",
    )
