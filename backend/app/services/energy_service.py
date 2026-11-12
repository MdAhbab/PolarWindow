"""Battery state of charge and bus temperature at a site (ADR-21).

Takes the Sun's track against the site's skyline from ``site_service.compute``,
the lander's figures from the caller, and the Diviner annual mean and bolometric
maximum ground temperatures, and runs the coupled single-node power-and-thermal
model at both ends of that steady-state ground temperature range. Computes a
bounding envelope on the entered figures, never a time-resolved thermal forecast
or prediction. Stores nothing.

Every lander figure is an input. Each is echoed back with where it came from:
entered by the caller, or filled from a catalogue example that says whether it
is published (with a URL) or assumed (with how it was derived).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import numpy.typing as npt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import power, thermal
from app.core.quantity import Quantity
from app.core.spice import R_SUN_M
from app.data import diviner
from app.services import site_service
from app.services.lifecycle import q

FloatArray = npt.NDArray[np.float64]

MAX_POINTS = 600
#: Longest RK4 sub-step, seconds, before the bus's own time constant shortens it.
MAX_SUBSTEP_S = 120.0
MAX_SUBSTEPS_PER_STEP = 2000

# name -> (unit, kind). kind: "pos" > 0, "frac" in [0, 1], "nonneg" >= 0, "any".
FIGURES: dict[str, tuple[str, str]] = {
    "array_area_m2": ("m2", "pos"),
    "cell_efficiency": ("1", "frac"),
    "dust_loss_fraction": ("1", "frac"),
    "battery_capacity_wh": ("Wh", "pos"),
    "initial_soc_fraction": ("1", "frac"),
    "avionics_w": ("W", "nonneg"),
    "payload_w": ("W", "nonneg"),
    "load_dissipation_fraction": ("1", "frac"),
    "heater_power_w": ("W", "nonneg"),
    "heater_setpoint_c": ("degC", "any"),
    "initial_bus_temp_c": ("degC", "any"),
    "operational_min_c": ("degC", "any"),
    "survival_min_c": ("degC", "any"),
    "bus_absorptivity": ("1", "frac"),
    "bus_side_area_m2": ("m2", "nonneg"),
    "bus_top_area_m2": ("m2", "nonneg"),
    "bus_emissivity": ("1", "frac"),
    "regolith_emissivity": ("1", "frac"),
    "regolith_absorptivity": ("1", "frac"),
    "view_factor": ("1", "frac"),
    "base_area_m2": ("m2", "nonneg"),
    "radiator_emissivity": ("1", "frac"),
    "radiator_area_m2": ("m2", "nonneg"),
    "heat_capacity_j_per_k": ("J/K", "pos"),
}
VERTICAL_ONLY: dict[str, tuple[str, str]] = {
    "face_count": ("faces", "int"),
    "face_azimuth_offset_deg": ("deg", "any"),
}

NOT_MODELLED = [
    "Solar-panel temperature and cell degradation (efficiency is the number entered).",
    "Multi-node thermal gradients and internal conduction paths: the entire bus is one lumped "
    "node at one uniform temperature, not a multi-node spacecraft thermal model.",
    "Multi-layer insulation detail: it is inside the emissivities and areas entered.",
    "Heat conducted through the landing legs into the ground.",
    "Light and infrared reflected from sunlit terrain onto the lander.",
    "Shading of one array face by the lander or by another face.",
    "Battery charge and discharge efficiency, ageing, and temperature limits on charging.",
    "The ground's time-resolved temperature through the lunar day and regolith thermal inertia: "
    "Diviner gives only an annual average and an annual bolometric maximum per triangle, so "
    "sunlit ground is taken at steady-state radiative equilibrium capped by the Diviner annual "
    "maximum, and dark ground is bounded between 2.725 K (space) and the Diviner annual average. "
    "The output is a steady-state-bounded range, not a diurnal temperature curve or prediction.",
    "The Sun's partial-disc fraction at the skyline: a step an arc edge falls in is lit for "
    "the share of it inside the arc.",
]


class BadFigure(ValueError):
    """A lander figure that is missing or out of range; ``field`` names it."""

    def __init__(self, field: str, why: str) -> None:
        super().__init__(f"{field}: {why}")
        self.field = field
        self.why = why


@dataclass(frozen=True, slots=True)
class Figure:
    value: float | str
    provenance: str
    source: str


def _catalogue() -> dict[str, Any]:
    path = get_settings().data_dir / "catalogues" / "lander_examples.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(e["id"]): e for e in data.get("examples", [])}


def resolve_inputs(lander: dict[str, Any], example_id: str | None) -> dict[str, Figure]:
    """Merge the caller's figures over a catalogue example; validate all of them.

    A figure is a bare number (entered by the caller) or ``{value, provenance,
    source}``. Nothing is defaulted: a missing required figure raises ``BadFigure``.
    """
    merged: dict[str, Any] = {}
    if example_id is not None:
        ex = _catalogue().get(example_id)
        if ex is None:
            raise BadFigure("lander_example_id", f"no example lander '{example_id}'")
        merged.update(ex["figures"])
    merged.update({k: v for k, v in lander.items() if v is not None})

    out: dict[str, Figure] = {}
    for name, raw in merged.items():
        if isinstance(raw, dict):
            prov = str(raw.get("provenance", "entered"))
            src = str(raw.get("source") or ("the caller" if prov == "entered" else ""))
            if prov not in ("entered", "published", "assumed"):
                raise BadFigure(name, "provenance must be entered, published or assumed")
            if not src:
                raise BadFigure(name, f"a {prov} figure must give its source")
            out[name] = Figure(raw["value"], prov, src)
        else:
            out[name] = Figure(raw, "entered", "the caller")

    geom = out.get("array_geometry")
    if geom is None:
        raise BadFigure("array_geometry", "is required")
    if geom.value not in power.GEOMETRIES:
        raise BadFigure("array_geometry", f"must be one of {', '.join(power.GEOMETRIES)}")
    need = dict(FIGURES)
    if geom.value == "vertical_faces":
        need.update(VERTICAL_ONLY)
    for name, (_unit, kind) in need.items():
        fig = out.get(name)
        if fig is None:
            raise BadFigure(name, "is required")
        v = fig.value
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
            raise BadFigure(name, "must be a finite number")
        if kind == "pos" and v <= 0:
            raise BadFigure(name, "must be greater than 0")
        if kind == "nonneg" and v < 0:
            raise BadFigure(name, "must not be negative")
        if kind == "frac" and not 0 <= v <= 1:
            raise BadFigure(name, "must be between 0 and 1")
        if kind == "int" and (v != int(v) or v < 3):
            raise BadFigure(name, "must be a whole number of at least 3")
    if out["radiator_area_m2"].value == 0 and out["base_area_m2"].value == 0:
        raise BadFigure("radiator_area_m2", "the bus needs a radiator or a base area to lose heat")
    if out["survival_min_c"].value > out["operational_min_c"].value:  # type: ignore[operator]
        raise BadFigure("survival_min_c", "must not be above operational_min_c")
    return {k: v for k, v in out.items() if k in need or k == "array_geometry"}


def echo_inputs(figs: dict[str, Figure]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, f in figs.items():
        unit = FIGURES.get(name, VERTICAL_ONLY.get(name, ("", "")))[0]
        if isinstance(f.value, str):
            out[name] = {
                "value": f.value,
                "unit": unit,
                "provenance": f.provenance,
                "source": f.source,
            }
            continue
        out[name] = q(
            Quantity(
                value=float(f.value),
                unit=unit,
                provenance=f.provenance,  # type: ignore[arg-type]
                source=f.source,
                no_margin_reason="a figure given as an input; no margin was stated",
            )
        )
    return out


def _num(figs: dict[str, Figure], name: str) -> float:
    return float(figs[name].value)


def _arcs(
    arcs: list[Any], tol: list[tuple[float | None, float | None]], sign: float, t_end: float
) -> list[tuple[float, float]]:
    """Lit arcs, shifted outward (sign +1) or inward (-1) by each edge's timing tolerance."""
    out: list[tuple[float, float]] = []
    for arc, (ts, te) in zip(arcs, tol, strict=False):
        if not arc.value:
            continue
        start = arc.start - sign * (ts or 0.0)
        end = arc.end + sign * (te or 0.0)
        start, end = max(0.0, start), min(t_end, end)
        if end > start:
            out.append((start, end))
    return out


def _series_envelope(
    runs: list[thermal.Coupled],
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray, FloatArray, FloatArray]:
    t = np.vstack([r.t_bus_k for r in runs])
    s = np.vstack([r.soc_wh for r in runs])
    return t.min(0), t.mean(0), t.max(0), s.min(0), s.mean(0), s.max(0)


def _qty(
    value: float | None,
    unit: str,
    lo: float | None,
    hi: float | None,
    *,
    cold_only: str | None,
    missing: str | None = None,
    open_: bool = False,
) -> dict[str, Any]:
    if value is None:
        return q(
            Quantity(value=None, unit=unit, provenance="computed", missing_reason=missing or "n/a")
        )
    if cold_only is not None or lo is None or hi is None:
        return q(
            Quantity(
                value=value,
                unit=unit,
                provenance="computed",
                no_margin_reason=cold_only or "the range is not defined",
                open=open_,
            )
        )
    return q(
        Quantity(
            value=value,
            unit=unit,
            provenance="computed",
            lo=min(lo, value),
            hi=max(hi, value),
            open=open_,
        )
    )


def _utc(start: datetime, t_s: float | None) -> str | None:
    return (
        None if t_s is None else (start + timedelta(seconds=t_s)).isoformat().replace("+00:00", "Z")
    )


def _time_qty(
    start: datetime,
    t_end: float,
    lo: float | None,
    val: float | None,
    hi: float | None,
    *,
    cold_only: str | None,
    never: str,
) -> dict[str, Any]:
    """A time as hours after the window start, with UTC copies. ``never`` is the reason for null."""
    if val is None:
        out = q(Quantity(value=None, unit="h", provenance="computed", missing_reason=never))
        out.update(value_utc=None, lo_utc=_utc(start, lo), hi_utc=None)
        if lo is not None:
            out["missing_reason"] = never + f" The cold end reaches it at {_utc(start, lo)}."
        return out
    hv = val / 3600.0
    if cold_only is not None:
        out = q(Quantity(value=hv, unit="h", provenance="computed", no_margin_reason=cold_only))
        out.update(value_utc=_utc(start, val), lo_utc=None, hi_utc=None)
        return out
    lo_h = (lo if lo is not None else val) / 3600.0
    censored = hi is None
    hi_h = (t_end if hi is None else hi) / 3600.0
    out = q(
        Quantity(
            value=hv,
            unit="h",
            provenance="computed",
            lo=min(lo_h, hv),
            hi=max(hi_h, hv),
            open=censored,
        )
    )
    out.update(
        value_utc=_utc(start, val),
        lo_utc=_utc(start, lo if lo is not None else val),
        hi_utc=_utc(start, hi) if hi is not None else None,
    )
    return out


def _ground(
    lat: float, lon: float, radius_m: float
) -> tuple[diviner.GroundTemps | None, str | None]:
    try:
        g = diviner.at(lat, lon, radius_m)
    except diviner.DivinerMissing:
        return None, (
            "The Diviner lookup has not been built on this server, so the ground's warm end "
            "is unknown."
        )
    if g is None:
        return None, (
            f"No Diviner Polar Resource Product triangle lies within {radius_m:.0f} m of this "
            "site (the product covers roughly south of 75.9 deg S), so the ground's warm end "
            "is unknown."
        )
    return g, None


async def energy(
    session: AsyncSession,
    site_id: str,
    start: datetime,
    end: datetime,
    step_s: int,
    lander: dict[str, Any],
    example_id: str | None,
    ground_radius_m: float,
) -> dict[str, Any]:
    figs = resolve_inputs(lander, example_id)
    cw = await site_service.compute(session, site_id, start, end, step_s)
    return _run(cw, figs, ground_radius_m)


def _run(
    cw: site_service.ComputedWindow, figs: dict[str, Figure], radius_m: float
) -> dict[str, Any]:
    r = cw.result
    sun = r.sun
    t_s = np.asarray(sun.t_s, dtype=np.float64)
    t_end = float(t_s[-1])
    geom = str(figs["array_geometry"].value)
    n_track = len(t_s) - 1

    ground, why_cold = _ground(cw.site.lat_deg, cw.site.lon_deg, radius_m)
    cold_reason = (
        None
        if ground is not None
        else (why_cold or "").rstrip(".") + ". Only the cold end was run: the ground in the dark "
        "is taken at the temperature of space, so temperatures are lower bounds and SoC is "
        "pessimistic."
    )

    bus = thermal.BusParams(
        absorptivity=_num(figs, "bus_absorptivity"),
        side_area_m2=_num(figs, "bus_side_area_m2"),
        top_area_m2=_num(figs, "bus_top_area_m2"),
        bus_emissivity=_num(figs, "bus_emissivity"),
        regolith_emissivity=_num(figs, "regolith_emissivity"),
        view_factor=_num(figs, "view_factor"),
        base_area_m2=_num(figs, "base_area_m2"),
        radiator_emissivity=_num(figs, "radiator_emissivity"),
        radiator_area_m2=_num(figs, "radiator_area_m2"),
        heat_capacity_j_per_k=_num(figs, "heat_capacity_j_per_k"),
    )
    pw = thermal.PowerParams(
        capacity_wh=_num(figs, "battery_capacity_wh"),
        avionics_w=_num(figs, "avionics_w"),
        payload_w=_num(figs, "payload_w"),
        load_dissipation_fraction=_num(figs, "load_dissipation_fraction"),
        heater_w=_num(figs, "heater_power_w"),
        heater_setpoint_k=_num(figs, "heater_setpoint_c") + thermal.ZERO_C_K,
    )

    # Fine grid, a whole number of sub-steps per track step, sampled at half sub-steps.
    step = float(np.median(np.diff(t_s)))
    k_reg = thermal.SIGMA * bus.bus_emissivity * bus.regolith_emissivity * bus.view_factor
    k_reg *= bus.base_area_m2
    k_sp = thermal.SIGMA * bus.radiator_emissivity * bus.radiator_area_m2
    tau = bus.heat_capacity_j_per_k / (4.0 * (k_reg + k_sp) * 300.0**3)
    h_max = min(MAX_SUBSTEP_S, tau / 10.0)
    sub = min(MAX_SUBSTEPS_PER_STEP, max(1, math.ceil(step / h_max)))
    n = n_track * sub
    tf = np.linspace(t_s[0], t_end, 2 * n + 1)
    az_unwrapped = np.degrees(np.unwrap(np.radians(sun.az_deg)))
    az_f = np.mod(np.interp(tf, t_s, az_unwrapped), 360.0)
    el_f = np.interp(tf, t_s, sun.el_deg)
    arcs_lit = [(a.start, a.end) for a in sun.arcs if a.value]
    lit_f = power.lit_at(tf, arcs_lit)

    sun_dist = R_SUN_M / np.sin(np.radians(np.asarray(sun.angular_radius_deg, dtype=np.float64)))
    s_irr = np.interp(tf, t_s, power.irradiance(sun_dist, len(t_s)))
    a_eff = power.effective_area(
        geom,
        az_f,
        el_f,
        area_m2=_num(figs, "array_area_m2"),
        face_count=int(_num(figs, "face_count")) if "face_count" in figs else None,
        face_offset_deg=_num(figs, "face_azimuth_offset_deg")
        if "face_azimuth_offset_deg" in figs
        else None,
    )
    p_gen = power.generated_power(
        a_eff,
        s_irr,
        lit_f,
        efficiency=_num(figs, "cell_efficiency"),
        dust_loss=_num(figs, "dust_loss_fraction"),
    )
    q_sol = thermal.solar_heat(bus, el_f, s_irr, lit_f)

    def drive(cap_k: float, dark_k: float) -> thermal.Drive:
        ts = thermal.ground_temperature(
            el_f,
            s_irr,
            lit_f,
            regolith_absorptivity=_num(figs, "regolith_absorptivity"),
            regolith_emissivity=bus.regolith_emissivity,
            cap_k=cap_k,
            dark_k=dark_k,
        )
        return thermal.Drive(float(tf[2] - tf[0]), p_gen, q_sol, ts)

    t0_k = _num(figs, "initial_bus_temp_c") + thermal.ZERO_C_K
    soc0 = _num(figs, "initial_soc_fraction") * pw.capacity_wh
    cold_cap = ground.temp_max_k.lo if ground is not None else math.inf
    runs = [thermal.integrate_coupled(bus, pw, drive(cold_cap, thermal.T_SPACE_K), t0_k, soc0)]
    if ground is not None:
        runs.append(
            thermal.integrate_coupled(
                bus, pw, drive(ground.temp_max_k.hi, ground.temp_avg_k.hi), t0_k, soc0
            )
        )
    t_lo, t_val, t_hi, s_lo, s_val, s_hi = _series_envelope(runs)
    if ground is None:
        t_val, t_hi, s_val, s_hi = t_lo, t_lo, s_lo, s_lo

    # Energy generated, with the arc edges moved by their timing tolerance.
    p_sunlit = power.generated_power(
        a_eff,
        s_irr,
        np.ones_like(tf),
        efficiency=_num(figs, "cell_efficiency"),
        dust_loss=_num(figs, "dust_loss_fraction"),
    )
    cum = np.concatenate([[0.0], np.cumsum(0.5 * (p_sunlit[1:] + p_sunlit[:-1]) * np.diff(tf))])

    def energy_wh(arcs: list[tuple[float, float]]) -> float:
        # Integrated exactly to each arc edge, not to the sub-step grid.
        return sum(float(np.interp(b, tf, cum) - np.interp(a, tf, cum)) for a, b in arcs) / 3600.0

    e_val = energy_wh(arcs_lit)
    tol = sun.arc_edge_tolerance_s
    e_lo = energy_wh(_arcs(sun.arcs, tol, -1.0, t_end))
    e_hi = energy_wh(_arcs(sun.arcs, tol, +1.0, t_end))

    # Derived times and thresholds.
    op_k = _num(figs, "operational_min_c") + thermal.ZERO_C_K
    sv_k = _num(figs, "survival_min_c") + thermal.ZERO_C_K
    cold_only = cold_reason

    te = tf[::2]

    def hours(series: FloatArray, thr: float) -> float:
        return thermal.hours_below(te, series, thr)

    empties = [power.first_empty_time(te, s) for s in (s_lo, s_val, s_hi)]
    crosses = [thermal.first_below(te, t, sv_k) for t in (t_lo, t_val, t_hi)]

    key = {
        "energy_generated": _qty(e_val, "Wh", e_lo, e_hi, cold_only=None),
        "lowest_soc": _qty(
            float(s_val.min()), "Wh", float(s_lo.min()), float(s_hi.min()), cold_only=cold_only
        ),
        "battery_empty_at": _time_qty(
            cw.result.start,
            t_end,
            empties[0],
            empties[1],
            empties[2],
            cold_only=cold_only,
            never="The battery does not reach 0 in this window.",
        ),
        "lowest_bus_temperature": _qty(
            float(t_val.min()) - thermal.ZERO_C_K,
            "degC",
            float(t_lo.min()) - thermal.ZERO_C_K,
            float(t_hi.min()) - thermal.ZERO_C_K,
            cold_only=cold_only,
        ),
        "hours_below_operational": _qty(
            hours(t_val, op_k), "h", hours(t_hi, op_k), hours(t_lo, op_k), cold_only=cold_only
        ),
        "survival_threshold_crossed_at": _time_qty(
            cw.result.start,
            t_end,
            crosses[0],
            crosses[1],
            crosses[2],
            cold_only=cold_only,
            never="The bus stays above the survival threshold in this window.",
        ),
    }

    # Decimated series at track samples (the end of each sub-step group).
    idx = np.unique(np.linspace(0, n_track, min(n_track + 1, MAX_POINTS)).round().astype(int))
    fine = idx * sub

    def c(a: FloatArray) -> list[float | None]:
        return [round(float(x) - thermal.ZERO_C_K, 3) for x in a[fine]]

    def w(a: FloatArray) -> list[float | None]:
        return [round(float(x), 3) for x in a[fine]]

    t_hi_out: list[float | None] = c(t_hi) if ground is not None else [None] * len(idx)
    s_hi_out: list[float | None] = w(s_hi) if ground is not None else [None] * len(idx)
    series = {
        "t_s": [int(x) for x in t_s[idx]],
        "t_utc": [_utc(cw.result.start, float(x)) for x in t_s[idx]],
        "p_gen_w": [round(float(x), 3) for x in p_gen[2 * fine]],
        "lit": [round(float(x), 3) for x in lit_f[2 * fine]],
        "soc_wh": {"lo": w(s_lo), "value": w(s_val), "hi": s_hi_out},
        "t_bus_c": {"lo": c(t_lo), "value": c(t_val), "hi": t_hi_out},
    }

    meta = cw.meta("bypass")
    unc = dict(meta["uncertainty"])
    unc["notes"] = [
        *unc["notes"],
        "Power and thermal: a single-node lumped bus model bounded by steady-state radiative "
        "equilibrium and Diviner annual average and bolometric maximum ground temperatures -- "
        "a bounding range on entered figures, not a time-resolved thermal prediction. The "
        "range on bus temperature and state of charge is the ground-temperature range in the "
        "dark (and the Diviner triangle spread on the sunlit cap) only. Arc-edge timing is "
        "carried into the energy generated, not into the temperature or charge curves, and "
        "lander figures are taken as entered, with no margin of their own.",
        "The central curve is the midpoint of the cold and warm bounding ends. It is not a "
        "prediction, and no single value is more probable than another.",
    ]
    meta["uncertainty"] = unc

    ground_out: dict[str, Any] = {
        "covered": ground is not None,
        "reason": cold_reason,
        "radius_m": radius_m,
        "source": diviner.SOURCE_URL,
        "basis": (
            "Steady-state bounding range from the LRO Diviner Polar Resource Product (annual "
            "average and annual bolometric maximum surface temperatures), not a time-resolved "
            "ground temperature curve: while sunlit, ground temperature is instantaneous "
            "radiative equilibrium capped by the Diviner annual maximum; while dark, the cold "
            "end holds the ground at 2.725 K (space) and the warm end holds it at the Diviner "
            "annual average."
        ),
        "dark_ground_k": {"lo": thermal.T_SPACE_K, "hi": ground.temp_avg_k.hi if ground else None},
        "lit_ground_cap_k": {
            "lo": ground.temp_max_k.lo if ground else None,
            "hi": ground.temp_max_k.hi if ground else None,
        },
    }
    if ground is not None:
        ground_out.update(
            n_triangles=ground.n_triangles,
            temp_avg_k=_stat(ground.temp_avg_k),
            temp_max_k=_stat(ground.temp_max_k),
            ice_depth_m=ground.ice_depth_m,
        )

    return {
        "site_id": r.site_id,
        "start": _utc(r.start, 0.0),
        "end": _utc(r.start, t_end),
        "step_s": r.step_s,
        "inputs": echo_inputs(figs),
        "model": {
            "thermal_model": (
                "single-node lumped bus heat balance coupled to battery state of charge, "
                "bounded by steady-state radiative equilibrium and Diviner annual average "
                "and bolometric maximum ground temperatures; a bounding range on entered "
                "figures, not a time-resolved prediction"
            ),
            "solar_irradiance": "1361 W/m2 at 1 au scaled by (1 au / Sun distance)^2, "
            "the distance taken from the track",
            "lit": "the Sun's centre above the skyline (the track's lit arcs); no partial-disc "
            "fraction is available",
            "substep_s": round(float(tf[2] - tf[0]), 3),
            "runs": "cold and warm ground ends" if ground is not None else "cold ground end only",
            "constants": {
                "solar_constant": q(
                    Quantity(
                        value=power.SOLAR_CONSTANT_W_M2,
                        unit="W/m2",
                        provenance="published",
                        pm=power.SOLAR_CONSTANT_PM_W_M2,
                        source=power.SOLAR_CONSTANT_SOURCE,
                    )
                ),
                "space_temperature": q(
                    Quantity(
                        value=thermal.T_SPACE_K,
                        unit="K",
                        provenance="published",
                        pm=0.0006,
                        source=thermal.T_SPACE_SOURCE,
                    )
                ),
            },
        },
        "ground": ground_out,
        "series": series,
        "key": key,
        "not_modelled": NOT_MODELLED,
        "meta": meta,
    }


def _stat(s: diviner.Stat) -> dict[str, float]:
    return {"median": s.median, "lo": s.lo, "hi": s.hi}
