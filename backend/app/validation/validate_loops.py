"""Phasing loops and correction burns against the flown landers (plan C3 and C4).

Run: ``make validate-trip`` (or ``uv run python -m app.validation.validate_loops``).
Prints the tables in docs/validation.md; ``test_loops_vs_clps.py`` pins the
acceptance numbers from the same code.

* **Replay** (Blue Ghost 1): the burns found in NASA's reconstruction are put
  back as instants on its first state, and the perigees and apogees of that
  flight are compared with the reconstruction's (the plan asks for the
  times within an hour and the apogee radius within 1%).
* **Designed loops**: for each launch day around the flown one, the due-east
  liftoff instants, the vehicle's injection as flown, the perigee raised to
  the flown first perigee's radius, and the loops corrected in the force
  model to reach the flown arrival at the Moon. Each day keeps its cheapest
  design over one loop fewer, as many as the two-body period gives, and one
  more. The plan asks for the same loop count as flown and a launch period
  that holds the flown date.
* **Correction budget** (Blue Ghost 1, IM-1, IM-2): the flown flight from
  leaving Earth to the Moon as planned (``flown_burns.planned_flight``), worked
  out linearly and by 1,000 seeded runs through the force model; the plan asks
  for the two within 10% at the 95th and 99th percentiles. Twice: with every error
  assumed (how it was first worked out) and with the errors at leaving Earth that
  the vehicle's own guide publishes (Falcon 9's, for all three) in place of the
  assumed ones, as the service does.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass, field

import numpy as np

from app.config import get_settings
from app.core import forces, launchwin, lincov, phasing, propagate, spice, transfer
from app.core.vec import rotate, unit
from app.services import ascent, flown_burns
from app.validation.validate_launch import F9, _flights

LOOPS = "blue-ghost-m1"
DAYS = range(-5, 6)
DAY = 86_400.0


@dataclass
class BurnRow:
    utc: str
    name: str
    dv_m_s: float
    r_km: float
    mismatch_m: float


@dataclass
class ReplayResult:
    burns: list[BurnRow]
    pairs: list[tuple[str, str, float, float]]  # kind, flown utc, minutes off, radius % off
    worst_min: float
    worst_apogee_pct: float
    worst_perigee_pct: float


@dataclass
class DayRow:
    day: int  # from the flown launch date
    loops: int | None
    t0_min: float | None  # designed liftoff from the flown one (same clock time on day 0)
    raise_m_s: float | None
    period_m_s: float | None
    final_m_s: float | None
    total_m_s: float | None
    why_not: str | None


@dataclass
class LoopsResult:
    flown_loops: int
    flown_burns_m_s: tuple[float, float, float]  # raise, period, leave
    raise_to_km: float
    days: list[DayRow] = field(default_factory=list)
    periods: list[tuple[int, int, int]] = field(default_factory=list)  # first, last, loops


@dataclass
class CorrectionRow:
    mission: str
    periapsis_km: float
    departure_alt_km: float  # the planned flight's perigee
    departure_shift_min: float  # from the flown departure
    p95_linear: float
    p95_mc: float
    p99_linear: float
    p99_mc: float
    p99_mc_interval: tuple[float, float]
    alt_spread_km: tuple[float, float]  # 1st and 99th percentile, Monte Carlo
    missed: int
    flown: list[tuple[str, float]]  # corrections found in the reconstruction
    #: "assumed", or "published" when the vehicle's guide gave the errors at leaving Earth.
    errors: str = "assumed"
    #: The one-sigma errors at leaving Earth: position (m) and speed (m/s) up, along, sideways.
    tli_sigma: tuple[float, ...] = ()
    #: 95th and 99th percentile of each of the three corrections (Monte Carlo), m/s.
    burns_p95: tuple[float, ...] = ()
    burns_p99: tuple[float, ...] = ()


def _tables_for(f: ascent.Flight) -> forces.Tables:
    assert f.launch.t_arrive is not None
    return propagate.environment(f.t0_et - 12 * DAY, f.launch.t_arrive + 4 * DAY)


def replay_check() -> ReplayResult:
    f = _flights()[LOOPS]
    fl = f.launch
    assert fl.t_arrive is not None
    tables = _tables_for(f)
    named, _ = flown_burns.burns(LOOPS, fl, tables)
    st = ascent.states_of(LOOPS)
    a0 = ascent.coverage(LOOPS)[0][0]
    stop = fl.t_arrive - 3600.0
    before = [b for b, _ in named if b.t < stop]
    rp = phasing.replay(tables, forces.Model(), a0, st(np.array([a0]))[0], before, stop)
    flown_aps = phasing.apsides(st, a0, stop)
    pairs = []
    for a, b in phasing.match(flown_aps, rp.apsides):
        if b is None:
            pairs.append((a.kind, spice.et_to_utc(a.t, precision=0), math.inf, math.inf))
        else:
            pairs.append(
                (
                    a.kind,
                    spice.et_to_utc(a.t, precision=0),
                    (b.t - a.t) / 60.0,
                    100.0 * (b.r_m - a.r_m) / a.r_m,
                )
            )
    return ReplayResult(
        burns=[
            BurnRow(
                spice.et_to_utc(b.t, precision=0),
                n,
                b.dv_m_s,
                b.r_m / 1000.0,
                b.mismatch_m,
            )
            for b, n in named
        ],
        pairs=pairs,
        worst_min=max(abs(p[2]) for p in pairs),
        worst_apogee_pct=max(abs(p[3]) for p in pairs if p[0] == "apogee"),
        worst_perigee_pct=max(abs(p[3]) for p in pairs if p[0] == "perigee"),
    )


def design_days(days: range = DAYS, az_deg: float = 90.0) -> LoopsResult:
    """The cheapest loop design of each launch day, climbing at ``az_deg`` (inertial)."""
    flights = _flights()
    f = flights[LOOPS]
    fl = f.launch
    assert fl.t_arrive is not None
    tables = _tables_for(f)
    named, _ = flown_burns.burns(LOOPS, fl, tables)
    planned = flown_burns.planned_flight(LOOPS, fl, tables, named)
    assert planned is not None
    enc = planned.arrival
    k = transfer.moon_pole(tables, enc.t)
    inc = math.degrees(math.acos(float(unit(np.cross(enc.r, enc.v)) @ k)))
    target = transfer.Target(enc.t, float(np.linalg.norm(enc.r)), inc)
    leave = next(b for b, n in named if n == "Leaving Earth for the Moon")
    flight_s = enc.t - leave.t
    # The flown loops: perigees between the injection and the burn that left Earth.
    st = ascent.states_of(LOOPS)
    aps = phasing.apsides(st, ascent.coverage(LOOPS)[0][0], leave.t + 3600.0)
    perigees = [a for a in aps if a.kind == "perigee"]
    early = [b for b, n in named if b.t < leave.t]
    raise_b = next(b for b in early if b.r_m > 100_000e3)
    period_b = next(b for b in early if b.r_m < 100_000e3)
    out = LoopsResult(
        flown_loops=len(perigees),
        flown_burns_m_s=(raise_b.dv_m_s, period_b.dv_m_s, leave.dv_m_s),
        raise_to_km=perigees[0].r_m / 1000.0,
    )
    c = float(np.mean([o.launch.c_rad for m, o in flights.items() if m != LOOPS and m in F9]))
    pad_at = ascent.pad_j2000(f.pad_id)

    def parking_at(tl: float) -> transfer.Parking:
        ph = unit(pad_at(tl))
        h = launchwin.climb_plane(ph, az_deg)
        return transfer.Parking(tl, fl.r_park_m * rotate(ph, h, c), h, tables.gm_earth)

    moon = unit(forces.body_state(tables, forces.MOON, np.array([target.t_arrive]))[0][:3])
    picked: list[phasing.Day] = []
    for dd in days:
        day0 = f.t0_et - 12 * 3600.0 + dd * DAY
        tried: list[phasing.LoopDesign | str] = []
        for root in launchwin.roots(
            lambda t: launchwin.climb_gap(unit(pad_at(t)), moon, az_deg), day0, day0 + DAY, 300.0
        ):
            park = parking_at(root)
            t_g, _ = transfer.guess(tables, park, target.t_arrive, flight_s, root + 600.0)
            y = transfer.tli_state(park, t_g, fl.dv_tli_m_s)
            n0 = phasing.loops_for(
                tables.gm_earth,
                park.radius,
                float(np.linalg.norm(y[3:])),
                t_g,
                target.t_arrive - flight_s,
            )
            for n in (n0 - 1, n0, n0 + 1):
                if n < 1:
                    continue
                try:
                    tried.append(
                        phasing.design(
                            tables,
                            target,
                            parking_at,
                            root,
                            t_g - root,
                            fl.dv_tli_m_s,
                            n,
                            flight_guess_s=flight_s,
                            raise_to_m=perigees[0].r_m,
                        )
                    )
                except (ValueError, RuntimeError) as exc:
                    tried.append(str(exc))
        d = phasing.pick(day0, tried, None)
        picked.append(d)
        ld = d.design
        ok = ld is not None and d.why_not is None
        out.days.append(
            DayRow(
                day=dd,
                loops=ld.n_loops if ok and ld else None,
                t0_min=(ld.t_launch - f.t0_et - dd * DAY) / 60.0 if ok and ld else None,
                raise_m_s=ld.dv_raise_m_s if ok and ld else None,
                period_m_s=ld.dv_period_m_s if ok and ld else None,
                final_m_s=ld.dv_final_m_s if ok and ld else None,
                total_m_s=ld.lander_dv_m_s if ok and ld else None,
                why_not=d.why_not,
            )
        )
    base = f.t0_et - 12 * 3600.0
    out.periods = [
        (round((a - base) / DAY), round((b - base) / DAY), n)
        for a, b, n in phasing.launch_period(picked)
    ]
    return out


def flown_direction() -> tuple[float, DayRow]:
    """Blue Ghost's flown day designed with the climb in the direction it flew (plan D1:
    its orbit was inclined 35 degrees, which a due-east climb from Florida does not give)."""
    az = _flights()[LOOPS].launch.azimuth_deg
    return az, design_days(range(0, 1), az_deg=az).days[0]


def corrections(
    mission_id: str, samples: int = 1000, seed: int = 0, *, published: bool = False
) -> CorrectionRow:
    """The budget for ``mission_id``; ``published`` puts in the errors its vehicle's guide
    gives (where it has one) in place of the assumed ones."""
    f = _flights()[mission_id]
    fl = f.launch
    tables = _tables_for(f)
    named, _ = flown_burns.burns(mission_id, fl, tables)
    guide = flown_burns.guide_for(f.vehicle_id) if published else None
    b = flown_burns.budget(mission_id, fl, tables, named, guide=guide, samples=samples, seed=seed)
    assert b is not None
    planned, lin, mc = b.planned, b.linear, b.runs
    leave = next((x for x, n in named if n == "Leaving Earth for the Moon"), None)
    flown_dep = leave.t if leave is not None else fl.t_tli
    return CorrectionRow(
        mission=mission_id,
        periapsis_km=(float(np.linalg.norm(planned.arrival.r)) - tables.r_moon_m) / 1000.0,
        departure_alt_km=planned.perigee_alt_m / 1000.0,
        departure_shift_min=(planned.plan.t_tli - flown_dep) / 60.0,
        p95_linear=lin.pct(95)[1],
        p95_mc=mc.pct(95)[1],
        p99_linear=lin.pct(99)[1],
        p99_mc=mc.pct(99)[1],
        p99_mc_interval=lincov.bootstrap(mc.total, 99),
        alt_spread_km=(mc.altitude_km(1), mc.altitude_km(99)),
        missed=mc.missed,
        flown=[(n, b.dv_m_s) for b, n in named if n.startswith("Correction")],
        errors="published" if b.derived else "assumed",
        tli_sigma=(*b.errors.tli_pos_m, *b.errors.tli_vel_m_s),
        burns_p95=tuple(mc.pct(95)[0]),
        burns_p99=tuple(mc.pct(99)[0]),
    )


BUDGET_MISSIONS = ("blue-ghost-m1", "im-1", "im-2")


def print_budgets() -> tuple[list[CorrectionRow], list[CorrectionRow]]:
    """The correction budget of each flown mission, first with every error assumed and then
    with the vehicle's published injection accuracy where its guide gives one."""
    assumed = [corrections(m) for m in BUDGET_MISSIONS]
    published = [corrections(m, published=True) for m in BUDGET_MISSIONS]
    for title, rows in (
        ("Every error assumed", assumed),
        ("Published injection accuracy", published),
    ):
        print(f"\n{title}:")
        print(
            "| Mission | Planned departure | Errors at leaving Earth | 95th linear / runs "
            "| 99th linear / runs (interval) | Arrival altitude 1 to 99 % | Flown corrections |"
        )
        print("|---|---|---|---|---|---|---|")
        for r in rows:
            fl = ", ".join(f"{v:.2f}" for _, v in r.flown) or "none in the reconstruction"
            x = r.tli_sigma
            print(
                f"| {r.mission} | {r.departure_alt_km:,.0f} km up, "
                f"{r.departure_shift_min:+.0f} min "
                f"| {x[0] / 1000:.1f} / {x[1] / 1000:.1f} / {x[2] / 1000:.1f} km; "
                f"{x[3]:.1f} / {x[4]:.1f} / {x[5]:.1f} m/s "
                f"| {r.p95_linear:.2f} / {r.p95_mc:.2f} m/s | {r.p99_linear:.2f} / "
                f"{r.p99_mc:.2f} m/s ({r.p99_mc_interval[0]:.2f} to {r.p99_mc_interval[1]:.2f}) | "
                f"{r.alt_spread_km[0]:.1f} to {r.alt_spread_km[1]:.1f} km | {fl} |"
            )
    print("\nEach correction, 95th / 99th percentile of the runs (m/s), assumed then published:")
    print("| Mission | First | Second | Third |")
    print("|---|---|---|---|")
    for a_, p_ in zip(assumed, published, strict=True):
        cells = " | ".join(
            f"{a_.burns_p95[k]:.2f} / {a_.burns_p99[k]:.2f} then {p_.burns_p95[k]:.2f} / "
            f"{p_.burns_p99[k]:.2f}"
            for k in range(3)
        )
        print(f"| {a_.mission} | {cells} |")
    for a_, p_ in zip(assumed, published, strict=True):
        print(
            f"{a_.mission}: total 95th {a_.p95_mc:.2f} -> {p_.p95_mc:.2f} m/s "
            f"(x{p_.p95_mc / a_.p95_mc:.2f}), 99th {a_.p99_mc:.2f} -> {p_.p99_mc:.2f} m/s "
            f"(x{p_.p99_mc / a_.p99_mc:.2f}); linear against runs at 95th/99th: "
            f"{100 * (p_.p95_linear / p_.p95_mc - 1):+.1f} % / "
            f"{100 * (p_.p99_linear / p_.p99_mc - 1):+.1f} %"
        )
    return assumed, published


def main(budget_only: bool = False) -> None:
    spice.load(get_settings().kernel_dir)
    if budget_only:
        assumed, published = print_budgets()
        json.dump(
            {
                "corrections": [asdict(r) for r in assumed],
                "corrections_published": [asdict(r) for r in published],
            },
            sys.stderr,
            indent=1,
            default=str,
        )
        return
    rp = replay_check()
    print("| Burn found | Size | Distance from Earth | Arcs meet within |")
    print("|---|---|---|---|")
    for b in rp.burns:
        print(
            f"| {b.utc} {b.name} | {b.dv_m_s:.2f} m/s | {b.r_km:,.0f} km | {b.mismatch_m:.0f} m |"
        )
    print()
    print("| Flown | Time | Replayed: minutes off | radius off |")
    print("|---|---|---|---|")
    for kind, utc, dm, dr in rp.pairs:
        print(f"| {kind} | {utc} | {dm:+.1f} | {dr:+.3f} % |")
    print()
    lp = design_days()
    print(
        f"Flown: {lp.flown_loops} loops, burns {lp.flown_burns_m_s[0]:.1f} / "
        f"{lp.flown_burns_m_s[1]:.1f} / {lp.flown_burns_m_s[2]:.1f} m/s, "
        f"first perigee raised to {lp.raise_to_km:,.0f} km"
    )
    print("| Day | Loops | Liftoff (min) | Raise | Period | Leave | Total | Why not |")
    print("|---|---|---|---|---|---|---|---|")
    for d in lp.days:
        if d.loops is None:
            print(f"| {d.day:+d} | | | | | | | {d.why_not} |")
        else:
            print(
                f"| {d.day:+d} | {d.loops} | {d.t0_min:+.0f} | {d.raise_m_s:.1f} | "
                f"{d.period_m_s:+.1f} | {d.final_m_s:.1f} | {d.total_m_s:.1f} | |"
            )
    print(f"Launch periods (first day, last day, loops): {lp.periods}")
    az, d0 = flown_direction()
    print(
        f"Day 0 climbing as flown ({az:.1f}°): "
        + (
            f"{d0.loops} loops, liftoff {d0.t0_min:+.1f} min, total {d0.total_m_s:.1f} m/s"
            if d0.loops is not None and d0.t0_min is not None and d0.total_m_s is not None
            else f"no design ({d0.why_not})"
        )
    )
    print()
    rows, published = print_budgets()
    json.dump(
        {
            "replay": asdict(rp),
            "loops": asdict(lp),
            "flown_direction": {"azimuth_deg": az, "day0": asdict(d0)},
            "corrections": [asdict(r) for r in rows],
            "corrections_published": [asdict(r) for r in published],
        },
        sys.stderr,
        indent=1,
        default=str,
    )


if __name__ == "__main__":
    main(budget_only="--budget" in sys.argv)
