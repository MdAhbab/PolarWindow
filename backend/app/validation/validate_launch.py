"""Launch instants against the flown Falcon 9 lunar launches (plan D1 and C2).

Run: ``make validate-trip`` (or ``uv run python -m app.validation.validate_launch``).
Prints the table in docs/validation.md; ``test_launch_vs_clps.py`` pins the
acceptance numbers from the same code.

Each flight being predicted is left out of the vehicle's climb constant:

* **Worked out again from the TLI** (``ascent.hold_one_out_s``): NASA's
  reconstruction gives the TLI time and point; the liftoff is solved from
  the climb constant of the other two flights.
* **Designed** (IM-1 and IM-2, the direct transfers): only the pad, the
  reconstructed arrival at the Moon (time, closest approach, inclination to
  the Moon's equator and the way round the orbit goes) and the other flights'
  climb are given. A climb at a given azimuth is corrected in the force model
  (``transfer.design``) until it reaches that arrival; the liftoff, coast and
  TLI speed it needs are compared with the flown ones. Three azimuths: due
  east (the assumption before), the direction the flight climbed (measured from
  the pad at liftoff and the TLI point) and the other direct flight's (held out).
* **Predicting the direction** (held out): the other direct flights' mean, due east
  (the most the Earth's turning helps) and the direction whose designed arrival has the
  flown arrival orbit's node about the Moon's pole (the arrival's plane, not only its
  inclination and the way round it goes), and the direction that reaches the orbit
  inclination the other flight had after TLI (to the equator of the day), with the same
  rule given the flight's own inclination as the check that it is not chance.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from app.config import get_settings
from app.core import forces, launchwin, propagate, spice, transfer
from app.core.vec import rotate, unit
from app.data import catalogues
from app.services import ascent

F9 = ("im-1", "blue-ghost-m1", "im-2")


@dataclass
class Row:
    mission: str
    published_t0: str
    from_tli_s: float
    flown_az_deg: float
    designed_t0_min: float | None  # due east
    designed_coast_min: float | None
    flown_coast_min: float
    designed_dv_m_s: float | None
    flown_dv_m_s: float
    designed_flight_d: float | None
    flown_flight_d: float | None
    converged: bool | None
    flown_az_t0_min: float | None  # designed at the azimuth the flight climbed
    held_az_deg: float | None  # the vehicle's other direct flights' mean azimuth
    held_az_t0_min: float | None
    #: The direction whose designed arrival has the flown arrival's node, and its liftoff.
    node_az_deg: float | None = None
    node_az_t0_min: float | None = None
    #: The designed arrival's node minus the flown one (deg) at the direction it climbed.
    node_at_flown_deg: float | None = None
    #: Node change per degree of climb direction (deg/deg).
    node_per_az: float | None = None
    #: Climbing to the other direct flight's orbit inclination after TLI, and to its own.
    inc_other_t0_min: float | None = None
    inc_own_t0_min: float | None = None
    #: Designed at the pad's two ground azimuth limits (min from the flown liftoff).
    window_open_min: float | None = None
    window_close_min: float | None = None


def _flights() -> dict[str, ascent.Flight]:
    s = get_settings()
    rows = []
    for m in json.loads((s.data_dir / "missions.json").read_text())["missions"]:
        if m["id"] in F9:
            rows.append((m["id"], m["vehicle_id"], m["pad_id"], m["t0"]["date"]))
    return ascent.measure(tuple(rows))


def _arrival(mid: str, flights: dict[str, ascent.Flight]) -> tuple[Any, ...]:
    """``(tables, target, climb constant held out, moon state, Moon's pole, r, v)`` of a
    direct flight's reconstructed arrival."""
    f = flights[mid]
    fl = f.launch
    assert fl.t_arrive is not None
    others = [o.launch.c_rad for k, o in flights.items() if k != mid]
    c = float(np.mean(others))
    tables = propagate.environment(f.t0_et - 2 * 86_400.0, fl.t_arrive + 4 * 86_400.0)
    st = ascent.states_of(mid)
    moon = forces.body_state(tables, forces.MOON, np.array([fl.t_arrive]))[0]
    if fl.arrival_from == "reconstruction":
        ya = st(np.array([fl.t_arrive]))[0]
        rr, vv = ya[:3] - moon[:3], ya[3:] - moon[3:]
    else:  # IM-1: the closest approach falls in a gap; propagate across it
        end = max(b for _, b in ascent.coverage(mid) if b < fl.t_arrive)
        enc = transfer.encounter(
            tables, forces.Model(), end, st(np.array([end]))[0], fl.t_arrive + 86_400.0
        )
        rr, vv = enc.r, enc.v
    k = transfer.moon_pole(tables, fl.t_arrive)
    inc = math.degrees(math.acos(float(unit(np.cross(rr, vv)) @ k)))
    # The arrival's orbit held with the way it goes round: IM-2 arrived in a near-polar
    # orbit, where the inclination alone also allows the mirror orbit going the other way.
    target = transfer.Target(
        fl.t_arrive, float(np.linalg.norm(rr)), inc, normal=unit(np.cross(rr, vv))
    )
    return tables, target, c, moon, k, rr, vv


def _designed(
    mid: str, flights: dict[str, ascent.Flight], az_deg: float = 90.0
) -> dict[str, Any] | None:
    """The day's designed launch nearest the flown one, climbing at ``az_deg``."""
    f = flights[mid]
    fl = f.launch
    if fl.t_arrive is None or not ascent.is_direct(fl):
        return None  # phasing loops are C3
    tables, target, c, moon, k, rr, vv = _arrival(mid, flights)
    pad_at = ascent.pad_j2000(f.pad_id)

    def parking_at(tl: float) -> transfer.Parking:
        ph = unit(pad_at(tl))
        h = launchwin.climb_plane(ph, az_deg)
        return transfer.Parking(tl, fl.r_park_m * rotate(ph, h, c), h, tables.gm_earth)

    mh = unit(moon[:3])
    day0 = f.t0_et - 12 * 3600.0
    roots = launchwin.roots(
        lambda t: launchwin.climb_gap(unit(pad_at(t)), mh, az_deg), day0, day0 + 86_400.0, 300.0
    )
    best: dict[str, Any] | None = None
    for root in roots:
        park = parking_at(root)
        coast0 = float(np.mean([o.launch.tau_s for o in flights.values()]))
        tg, dvg = transfer.guess(tables, park, fl.t_arrive, fl.t_arrive - root - coast0, root + 600)
        d = transfer.design(tables, target, parking_at, root, tg - root, dvg)
        if not d.converged or not 20 * 60 <= d.coast_s <= 75 * 60:
            continue
        enc = transfer.encounter(
            tables, forces.Model(), d.t_tli, np.concatenate([d.r_tli, d.v_tli]), d.t_peri + 3600.0
        )
        row = {
            "dnode_deg": _node_gap(unit(np.cross(enc.r, enc.v)), unit(np.cross(rr, vv)), k),
            "t0_min": (d.t_launch - f.t0_et) / 60.0,
            "coast_min": d.coast_s / 60.0,
            "dv": d.dv_tli_m_s,
            "flight_d": (d.t_peri - d.t_tli) / 86_400.0,
            "converged": d.converged,
        }
        if best is None or abs(row["t0_min"]) < abs(best["t0_min"]):
            best = row
    return best


def _node_gap(n: np.ndarray, n_ref: np.ndarray, k: np.ndarray) -> float:
    """The node of the orbit with normal ``n`` minus that of ``n_ref``, about the pole ``k``
    (deg)."""
    a, b = n - float(n @ k) * k, n_ref - float(n_ref @ k) * k
    return math.degrees(math.atan2(float(np.cross(b, a) @ k), float(a @ b)))


def _node_azimuth(
    mid: str, flights: dict[str, ascent.Flight], a0: float, a1: float
) -> tuple[float | None, float | None, float]:
    """The climb direction whose designed arrival has the flown arrival's node (secant
    from ``a0``, ``a1``), its liftoff, and the node change per degree of direction."""
    d0, d1 = _designed(mid, flights, a0), _designed(mid, flights, a1)
    assert d0 is not None and d1 is not None
    slope = (d1["dnode_deg"] - d0["dnode_deg"]) / (a1 - a0)
    for _ in range(8):
        assert d0 is not None and d1 is not None
        g0, g1 = d0["dnode_deg"], d1["dnode_deg"]
        if abs(g1) < 0.005:
            return a1, d1["t0_min"], slope
        a2 = a1 - g1 * (a1 - a0) / (g1 - g0)
        if not 0.0 < a2 < 180.0:
            return None, None, slope
        a0, d0 = a1, d1
        a1, d1 = a2, _designed(mid, flights, a2)
        if d1 is None:  # no transfer converges at that direction on the day
            return a2, None, slope
    return None, None, slope


def _of_date(mid: str, flights: dict[str, ascent.Flight]) -> tuple[float, np.ndarray, np.ndarray]:
    """The orbit's inclination after TLI to the equator of the day (deg), the pad at
    liftoff and the Earth's pole of the day (J2000)."""
    f = flights[mid]
    y = ascent.states_of(mid)(np.array([ascent.coverage(mid)[0][0]]))[0]
    z = spice.rotations(spice.ITRF93, spice.J2000, np.array([f.launch.t_tli]))[0][:, 2]
    inc = math.degrees(math.acos(float(unit(np.cross(y[:3], y[3:])) @ z)))
    return inc, unit(ascent.pad_j2000(f.pad_id)(f.t0_et)), z


def _inclination_t0(mid: str, flights: dict[str, ascent.Flight], inc: float) -> float | None:
    """The liftoff designed at the north-east climb that reaches ``inc`` (of the day)."""
    _, p, z = _of_date(mid, flights)
    az = launchwin.azimuth_for_inclination(math.degrees(math.asin(float(p @ z))), inc)
    if az is None:
        return None
    east = unit(np.cross(z, p))
    north = np.cross(p, east)
    a = math.radians(az[0])
    h = unit(np.cross(p, math.cos(a) * north + math.sin(a) * east))
    d = _designed(mid, flights, launchwin.climb_azimuth(p, h))
    return None if d is None else float(d["t0_min"])


def _window(
    mid: str, flights: dict[str, ascent.Flight], az_deg: float, ground: tuple[float, float]
) -> tuple[float | None, float | None]:
    """The designed liftoffs (min from the flown one) climbing at the pad's two ground
    azimuth limits, on the sweep of the instant designed at ``az_deg``: the launch window
    had the vehicle steered between them (plan D1)."""
    f = flights[mid]
    tables, target, c, moon, _, _, _ = _arrival(mid, flights)
    pad_at = ascent.pad_j2000(f.pad_id)
    site = catalogues.load("launch_sites").get(f.pad_id)
    v = math.sqrt(tables.gm_earth / f.launch.r_park_m)
    mh = unit(moon[:3])
    at = _designed(mid, flights, az_deg)
    assert at is not None
    t_nom = f.t0_et + 60.0 * at["t0_min"]

    def gap(t: float) -> float:
        return launchwin.climb_gap(unit(pad_at(t)), mh, az_deg)

    north = gap(t_nom + 60.0) > gap(t_nom - 60.0)
    coast0 = float(np.mean([o.launch.tau_s for o in flights.values()]))
    out: list[float | None] = []
    for g in ground:
        az = launchwin.inertial_azimuth(site.lat_deg, g, v)
        d = transfer.launch_at(
            tables,
            target,
            pad_at,
            az,
            c,
            f.launch.r_park_m,
            t_nom,
            north,
            (coast0, 600.0),
            span_s=12 * 3600.0,
        )
        out.append(None if d is None else (d.t_launch - f.t0_et) / 60.0)
    return out[0], out[1]


def results() -> list[Row]:
    spice.load(get_settings().kernel_dir)
    flights = _flights()
    a = ascent.ascent("falcon-9", flights, spice.gm_m3_s2("EARTH"))
    assert a is not None
    out = []
    for mid in F9:
        f = flights[mid]
        d = _designed(mid, flights)
        at_flown = _designed(mid, flights, f.launch.azimuth_deg)
        others = [a.azimuths_deg[m] for m in a.direct if m != mid]
        held = float(np.mean(others)) if others else None
        at_held = None if held is None else _designed(mid, flights, held)
        node_az = node_t0 = slope = None
        if at_flown is not None and held is not None:
            node_az, node_t0, slope = _node_azimuth(mid, flights, f.launch.azimuth_deg, held)
        inc_other = inc_own = w_lo = w_hi = None
        if held is not None and at_flown is not None:
            other = next(m for m in a.direct if m != mid)
            inc_other = _inclination_t0(mid, flights, _of_date(other, flights)[0])
            inc_own = _inclination_t0(mid, flights, _of_date(mid, flights)[0])
            site = catalogues.load("launch_sites").get(f.pad_id)
            if site.azimuth_min_deg is not None and site.azimuth_max_deg is not None:
                w_lo, w_hi = _window(
                    mid, flights, held, (site.azimuth_min_deg, site.azimuth_max_deg)
                )
        out.append(
            Row(
                mission=mid,
                published_t0=spice.et_to_utc(f.t0_et, precision=0),
                from_tli_s=a.hold_one_out_s[mid],
                flown_az_deg=f.launch.azimuth_deg,
                flown_az_t0_min=None if at_flown is None else at_flown["t0_min"],
                held_az_deg=held,
                held_az_t0_min=None if at_held is None else at_held["t0_min"],
                node_az_deg=node_az,
                node_az_t0_min=node_t0,
                node_at_flown_deg=None if at_flown is None else at_flown["dnode_deg"],
                node_per_az=slope,
                inc_other_t0_min=inc_other,
                inc_own_t0_min=inc_own,
                window_open_min=w_lo,
                window_close_min=w_hi,
                designed_t0_min=None if d is None else d["t0_min"],
                designed_coast_min=None if d is None else d["coast_min"],
                flown_coast_min=f.launch.tau_s / 60.0,
                designed_dv_m_s=None if d is None else d["dv"],
                flown_dv_m_s=f.launch.dv_tli_m_s,
                designed_flight_d=None if d is None else d["flight_d"],
                flown_flight_d=None if f.launch.flight_s is None else f.launch.flight_s / 86_400.0,
                converged=None if d is None else d["converged"],
            )
        )
    return out


def _min(x: float | None, what: str = "phasing loops (below)") -> str:
    return what if x is None else f"{x:+.1f} min"


def main() -> None:
    rows = results()
    print(
        "| Mission | Published liftoff | From its TLI | Designed (due east) "
        "| Coast designed / flown | TLI speed designed / flown | Flight designed / flown |"
    )
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        coast = (
            f"{r.flown_coast_min:.1f} min"
            if r.designed_coast_min is None
            else f"{r.designed_coast_min:.1f} / {r.flown_coast_min:.1f} min"
        )
        dv = (
            f"{r.flown_dv_m_s:.0f} m/s"
            if r.designed_dv_m_s is None
            else f"{r.designed_dv_m_s:.0f} / {r.flown_dv_m_s:.0f} m/s"
        )
        fl = (
            f"{r.flown_flight_d:.2f} d"
            if r.designed_flight_d is None
            else f"{r.designed_flight_d:.2f} / {r.flown_flight_d:.2f} d"
        )
        head = f"| {r.mission} | {r.published_t0} | {r.from_tli_s:+.0f} s"
        print(f"{head} | {_min(r.designed_t0_min)} | {coast} | {dv} | {fl} |")
    print()
    print(
        "| Mission | Climbed at | Designed: due east | at the azimuth it climbed "
        "| at the other direct flight's |"
    )
    print("|---|---|---|---|---|")
    for r in rows:
        held = (
            "none flown"
            if r.held_az_deg is None
            else _min(r.held_az_t0_min)
            if r.held_az_t0_min is None
            else f"{_min(r.held_az_t0_min)} ({r.held_az_deg:.1f}°)"
        )
        print(
            f"| {r.mission} | {r.flown_az_deg:.1f}° | {_min(r.designed_t0_min)} "
            f"| {_min(r.flown_az_t0_min)} | {held} |"
        )
    print()
    print(
        "| Mission | Other direct flights' mean | Due east | Arrival node: direction "
        "| its liftoff | node at the flown direction | node per degree "
        "| other flight's inclination after TLI | its own |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r.node_per_az is None:
            continue
        node_az = "none" if r.node_az_deg is None else f"{r.node_az_deg:.1f}°"
        node_t0 = "no transfer" if r.node_az_t0_min is None else _min(r.node_az_t0_min)
        print(
            f"| {r.mission} | {_min(r.held_az_t0_min)} | {_min(r.designed_t0_min)} "
            f"| {node_az} | {node_t0} | {r.node_at_flown_deg:+.2f}° | {r.node_per_az:+.3f} "
            f"| {_min(r.inc_other_t0_min, 'none')} | {_min(r.inc_own_t0_min, 'none')} |"
        )
    print()
    print("| Mission | Designed at the pad's lower limit | at its upper limit |")
    print("|---|---|---|")
    for r in rows:
        if r.node_per_az is not None:
            lo, hi = _min(r.window_open_min, "none"), _min(r.window_close_min, "none")
            print(f"| {r.mission} | {lo} | {hi} |")
    json.dump([asdict(r) for r in rows], sys.stderr, indent=1)


if __name__ == "__main__":
    main()
