"""Relays in the contact job (T1, F3 and F4): their orbits from the catalogue,
the geometry of the dates, and the sweep over what is not published.

Runs in the compute worker, on the SPICE thread (the geometry needs CSPICE;
the sweep itself is pure and runs there too so the job's heartbeat keeps going).
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.core import relay, spice
from app.core.intervals import Run
from app.core.quantity import Quantity
from app.core.visibility import enu_basis
from app.data.catalogues import GroundStation, Relay
from app.services import lifecycle

#: Time step of the relay geometry. A relay pass lasts hours; edges are placed
#: by linear interpolation between samples, so 5 minutes is well inside the
#: spread the unknown node and phase give.
STEP_S = 300.0
H = 3600.0

#: Orbit fields a relay needs before anything is worked out through it.
NEEDED = ("periapsis_km", "apoapsis_km", "inclination_deg", "arg_periapsis_deg")
#: Of those, the ones whose assumed range is swept end to end. The heights'
#: assumed ranges (if any) are narrow next to the node and phase sweep and are
#: taken at their stated value.
SWEPT = ("inclination_deg", "arg_periapsis_deg")


@dataclass(frozen=True, slots=True)
class Spec:
    rec: Relay
    for_this_mission: bool
    orbits: list[relay.Orbit]  # empty: not enough of the orbit is known
    missing: str | None


def spec(rec: Relay, for_this_mission: bool) -> Spec:
    gone = [f for f in NEEDED if getattr(rec, f) is None]
    if gone:
        return Spec(
            rec,
            for_this_mission,
            [],
            "Its orbit is not published or entered ("
            + ", ".join(f.replace("_", " ") for f in gone)
            + "), so nothing is worked out through it.",
        )
    ends: dict[str, list[float]] = {}
    for f in SWEPT:
        a = rec.assumed_fields.get(f)
        v = float(getattr(rec, f))
        ends[f] = [a.lo, a.hi] if a is not None and a.lo is not None and a.hi is not None else [v]
    orbits = [
        relay.Orbit.from_heights(
            float(rec.periapsis_km or 0.0) * 1000.0,
            float(rec.apoapsis_km or 0.0) * 1000.0,
            i,
            w,
            spice.R_MOON_M,
        )
        for i, w in itertools.product(ends["inclination_deg"], ends["arg_periapsis_deg"])
    ]
    return Spec(rec, for_this_mission, orbits, None)


def geometry(
    t0_et: float,
    t1: float,
    site_me_m: np.ndarray[Any, np.dtype[np.float64]],
    lat_deg: float,
    lon_deg: float,
    skyline_az_deg: np.ndarray[Any, np.dtype[np.float64]],
    skyline_el_deg: np.ndarray[Any, np.dtype[np.float64]],
    stations: list[GroundStation],
) -> relay.Geometry:
    """Everything the relay links need over the dates. Call on the SPICE thread."""
    t = np.arange(0.0, t1 + STEP_S / 2, STEP_S)
    t[-1] = t1
    ets = t0_et + t
    me2j = spice.rotations("MOON_ME", "J2000", ets)
    in_to_j2k = me2j[0]
    in_to_me = np.einsum("nji,jk->nik", me2j, in_to_j2k)  # (MOON_ME(t))^T . MOON_ME(t0)
    moon = spice.positions("MOON", "EARTH", "J2000", "LT+S", ets, knot_s=None)
    frames = spice.station_frames([str(g.naif_name) for g in stations], ets)
    return relay.Geometry(
        t_s=t,
        in_to_me=in_to_me,
        in_to_j2k=in_to_j2k,
        moon_from_earth_j2k_m=moon,
        site_me_m=np.asarray(site_me_m, dtype=np.float64),
        basis=enu_basis(lat_deg, lon_deg),
        skyline_az_deg=skyline_az_deg,
        skyline_el_deg=skyline_el_deg,
        stations=[
            relay.StationFrame(
                id=g.id,
                pos_j2k_m=pos,
                j2k_to_topo=rot,
                mask_az_deg=np.array([pt.az_deg for pt in g.mask]),
                mask_el_deg=np.array([pt.el_deg for pt in g.mask]),
            )
            for g, (pos, rot) in zip(stations, frames, strict=True)
        ],
        r_moon_m=spice.R_MOON_M,
        gm=spice.gm_m3_s2("MOON"),
    )


@dataclass(frozen=True, slots=True)
class Result:
    n: int
    via: list[relay.Spread]  # per usable relay, in order
    via_any: relay.Spread
    adds: list[relay.Spread]
    either: relay.Spread
    unheard: relay.Spread
    wait: relay.Spread
    #: Per usable relay: the placement (its index for :func:`placement`) whose time through the
    #: relay is nearest the middle of the range, and that time in seconds. The contact plan
    #: lists that one.
    nearest: list[tuple[int, float]]


def placement(sp: Spec, j: int) -> tuple[relay.Orbit, float, float]:
    """The ``j``-th placement of a relay: its orbit (an end of each assumed range), node, phase."""
    cells = relay.grid()
    raan, m0 = cells[j % len(cells)]
    return sp.orbits[j // len(cells)], raan, m0


def placements(sp: Spec) -> int:
    """How many placements of this relay the sweep tries."""
    return len(relay.grid()) * len(sp.orbits)


def sweep(
    geom: relay.Geometry,
    specs: list[Spec],
    t1: float,
    earth_up: list[Run],
    heard_any: list[Run],
    direct_owlt_s: float,
    progress: Callable[[float], None] | None = None,
) -> Result:
    """Every node and phase (and every end of an assumed range) of every usable relay.

    With more than one relay, point ``k`` of the sweep places each relay at its
    own ``k``-th placement (cycling a shorter list), rather than every pairing.
    """
    per = [placements(s) for s in specs]
    n = max(per)
    via: list[list[float]] = [[] for _ in specs]
    adds: list[list[float]] = [[] for _ in specs]
    via_any: list[float] = []
    either: list[float] = []
    unheard: list[float] = []
    unheard_open: list[bool] = []
    wait: list[float] = []
    wait_open: list[bool] = []
    for k in range(n):
        rl = []
        for s, m in zip(specs, per, strict=True):
            orbit, raan, m0 = placement(s, k % m)
            rl.append(relay.links(geom, orbit, raan, m0))
        c = relay.cell_numbers(t1, earth_up, heard_any, direct_owlt_s, rl)
        for r in range(len(specs)):
            via[r].append(c.via_s[r])
            adds[r].append(c.adds_s[r])
        via_any.append(c.via_any_s)
        either.append(c.either_s)
        unheard.append(c.unheard_s)
        unheard_open.append(c.unheard_open)
        wait.append(c.wait_s)
        wait_open.append(c.wait_open)
        if progress is not None and k % 200 == 0:
            progress(k / n)
    return Result(
        n=n,
        via=[relay.Spread.of(v) for v in via],
        via_any=relay.Spread.of(via_any),
        adds=[relay.Spread.of(a) for a in adds],
        either=relay.Spread.of(either),
        unheard=relay.Spread.of(unheard, unheard_open),
        wait=relay.Spread.of(wait, wait_open),
        nearest=[nearest_the_middle(v, m) for v, m in zip(via, per, strict=True)],
    )


def nearest_the_middle(values: list[float], n_placements: int) -> tuple[int, float]:
    """``(placement, value)`` of the point nearest the middle (median) of the sweep; the first on
    a tie.

    ``values[k]`` is the value at point ``k`` of the sweep, which put this relay at placement
    ``k % n_placements``.
    """
    a = np.asarray(values, dtype=np.float64)
    k = int(np.argmin(np.abs(a - np.median(a))))
    return k % n_placements, float(a[k])


def spread_q(s: relay.Spread, scale: float, unit: str) -> dict[str, Any]:
    """A spread over the sweep as a range: the middle value, both ends, "if it flies as planned"."""
    return lifecycle.q(
        Quantity(
            value=s.median / scale,
            unit=unit,
            provenance="assumed",
            lo=s.lo / scale,
            hi=s.hi / scale,
            open=s.open,
        )
    )


def plan_block(
    geom: relay.Geometry,
    sp: Spec,
    j: int,
    via_s: float,
    stretches: Callable[[list[Run]], list[dict[str, Any]]],
) -> dict[str, Any]:
    """One relay's links at one placement, for the contact plan (never shown as an answer).

    A planned relay has no schedule: its node and phase are not published, so the plan lists
    the links of one placement of the sweep (the one whose time through the relay is nearest
    the middle) and says so. Lander to relay is the relay above the landing spot's skyline;
    relay to station is above that station's mask with the Moon not in the way.
    """
    orbit, raan, m0 = placement(sp, j)
    rl = relay.links(geom, orbit, raan, m0)
    return {
        "id": sp.rec.id,
        "placement": {
            "node_deg": raan,
            "phase_deg": m0,
            "inclination_deg": orbit.i_deg,
            "arg_periapsis_deg": orbit.argp_deg,
            "of": placements(sp),
            "via_h": via_s / H,
        },
        "lander_relay": stretches(rl.lander_relay),
        "lander_relay_owlt_s": rl.lander_relay_owlt_s,
        "relay_station": {
            sid: {"stretches": stretches(runs), "owlt_s": owlt}
            for sid, (runs, owlt) in relay.station_links(geom, orbit, raan, m0).items()
        },
    }


def sweep_note(specs: list[Spec], n: int) -> str:
    swept = sorted(
        {
            f.replace("_deg", "").replace("arg_periapsis", "argument of periapsis")
            for s in specs
            for f in SWEPT
            if (a := s.rec.assumed_fields.get(f)) is not None and a.lo is not None
        }
    )
    ends = f", at both ends of its assumed {' and '.join(swept)}" if swept else ""
    return (
        f"Worked out for {n} placements of the relay: where its node sits and where it is "
        f"along its orbit, on a {relay.NODE_STEPS} x {relay.PHASE_STEPS} grid{ends}. "
        "The range is the least and the most over those placements, the value their middle. "
        "Two-body orbit: Earth's pull turns a frozen orbit's node about half a degree a day, "
        "which the node sweep covers but a single placement does not follow."
    )


def orbit_block(rec: Relay) -> dict[str, Any]:
    """The relay's orbit elements, each saying whether it is published or assumed."""
    units = {
        "periapsis_km": "km",
        "apoapsis_km": "km",
        "inclination_deg": "deg",
        "arg_periapsis_deg": "deg",
        "period_h": "h",
    }
    out: dict[str, Any] = {}
    for f, unit in units.items():
        v = getattr(rec, f)
        kind, why = rec.provenance(f)
        if v is None:
            out[f] = lifecycle.missing(unit, "Not published.")
        elif kind == "published":
            out[f] = lifecycle.q(
                Quantity(
                    value=float(v),
                    unit=unit,
                    provenance="published",
                    source=why,
                    no_margin_reason="Published without a tolerance.",
                )
            )
        else:
            a = rec.assumed_fields[f]
            if a.lo is not None and a.hi is not None:
                out[f] = lifecycle.q(
                    Quantity(value=float(v), unit=unit, provenance="assumed", lo=a.lo, hi=a.hi)
                )
            else:
                out[f] = lifecycle.q(
                    Quantity(
                        value=float(v), unit=unit, provenance="assumed", no_margin_reason=a.reason
                    )
                )
    return out
