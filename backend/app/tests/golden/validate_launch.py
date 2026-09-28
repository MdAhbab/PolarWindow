"""Launch instants against the flown Falcon 9 lunar launches (plan D1 and C2).

Run: ``make validate-trip`` (or ``uv run python -m app.tests.golden.validate_launch``).
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


def _flights() -> dict[str, ascent.Flight]:
    s = get_settings()
    rows = []
    for m in json.loads((s.data_dir / "missions.json").read_text())["missions"]:
        if m["id"] in F9:
            rows.append((m["id"], m["vehicle_id"], m["pad_id"], m["t0"]["date"]))
    return ascent.measure(tuple(rows))


def _designed(
    mid: str, flights: dict[str, ascent.Flight], az_deg: float = 90.0
) -> dict[str, Any] | None:
    """The day's designed launch nearest the flown one, climbing at ``az_deg``."""
    f = flights[mid]
    fl = f.launch
    if fl.t_arrive is None or not ascent.is_direct(fl):
        return None  # phasing loops are C3
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
        row = {
            "t0_min": (d.t_launch - f.t0_et) / 60.0,
            "coast_min": d.coast_s / 60.0,
            "dv": d.dv_tli_m_s,
            "flight_d": (d.t_peri - d.t_tli) / 86_400.0,
            "converged": d.converged,
        }
        if best is None or abs(row["t0_min"]) < abs(best["t0_min"]):
            best = row
    return best


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
        out.append(
            Row(
                mission=mid,
                published_t0=spice.et_to_utc(f.t0_et, precision=0),
                from_tli_s=a.hold_one_out_s[mid],
                flown_az_deg=f.launch.azimuth_deg,
                flown_az_t0_min=None if at_flown is None else at_flown["t0_min"],
                held_az_deg=held,
                held_az_t0_min=None if at_held is None else at_held["t0_min"],
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
    json.dump([asdict(r) for r in rows], sys.stderr, indent=1)


if __name__ == "__main__":
    main()
