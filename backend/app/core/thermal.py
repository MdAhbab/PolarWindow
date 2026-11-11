"""A one-node bus thermal model, coupled to the battery (ADR-21). Pure.

This is a single-node lumped-heat-capacity balance bounded by steady-state ground
temperature limits from the LRO Diviner Polar Resource Product (annual mean and
annual bolometric maximum); it computes a bounding range on entered lander figures,
never a time-resolved lunar surface temperature forecast or flight thermal prediction.

    C dT/dt = Q_solar + Q_regolith + P_dissipated - Q_space

* ``Q_solar = alpha * A_proj(el) * S * lit``, with ``A_proj = A_side cos el + A_top sin el``.
* ``Q_regolith = sigma eps_bus eps_reg F A_base (T_surf^4 - T^4)``.
* ``Q_space = sigma eps_rad A_rad (T^4 - T_space^4)``.
* ``T_surf`` is the bounding ground temperature: while the Sun is up, instantaneous
  steady-state radiative equilibrium from its elevation,
  ``(alpha_reg S sin el / (eps_reg sigma))^(1/4)``, never above a cap (Diviner's
  annual bolometric maximum); while it is down, whatever bounding constant the caller
  passes (from ``T_space`` up to Diviner's annual mean -- see ``app.services.energy_service``).
* The heater is a thermostat, on when ``T < setpoint`` (decided once per
  sub-step). Its power comes from the battery and is dissipated in the bus; with
  an empty battery only what the arrays generate can be spent, and nothing the
  arrays do not generate is dissipated.

The state ``(T, SoC)`` is integrated together with RK4 on a fixed sub-step.
Not modelled: regolith thermal inertia and diurnal ground cooling curves, a second
node (panels, payload), multi-layer insulation detail, conduction through the legs,
light reflected from sunlit terrain, the heat capacity of the battery as a separate node.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

#: Stefan-Boltzmann constant, W/m^2/K^4 (CODATA 2018 exact).
SIGMA: Final[float] = 5.670374419e-8
#: Cosmic microwave background, K. Fixsen (2009), 2.7255 +/- 0.0006.
T_SPACE_K: Final[float] = 2.725
T_SPACE_SOURCE: Final[str] = "https://doi.org/10.1088/0004-637X/707/2/916"
ZERO_C_K: Final[float] = 273.15


@dataclass(frozen=True, slots=True)
class BusParams:
    absorptivity: float
    side_area_m2: float
    top_area_m2: float
    bus_emissivity: float
    regolith_emissivity: float
    view_factor: float
    base_area_m2: float
    radiator_emissivity: float
    radiator_area_m2: float
    heat_capacity_j_per_k: float
    t_space_k: float = T_SPACE_K


@dataclass(frozen=True, slots=True)
class PowerParams:
    capacity_wh: float
    avionics_w: float
    payload_w: float
    #: Share of the avionics and payload power that ends up as heat in the bus.
    load_dissipation_fraction: float
    heater_w: float
    heater_setpoint_k: float


@dataclass(frozen=True, slots=True)
class Drive:
    """Forcing on a fixed sub-step grid, sampled at every half sub-step.

    Arrays have ``2 n + 1`` entries: ``t0 + j h / 2``. RK4 reads the start,
    middle and end of each sub-step from them.
    """

    h_s: float
    p_gen_w: FloatArray
    q_solar_w: FloatArray
    t_surf_k: FloatArray

    @property
    def n(self) -> int:
        return (len(self.p_gen_w) - 1) // 2


@dataclass(frozen=True, slots=True)
class Coupled:
    """Result at each sub-step edge (``n + 1`` entries)."""

    t_bus_k: FloatArray
    soc_wh: FloatArray
    #: Power the heater dissipated in the bus, averaged over the sub-step ending here.
    heater_w: FloatArray
    #: Electrical energy the loads could not be given because the battery was
    #: empty and the arrays were not generating enough, Wh.
    unserved_wh: float


def projected_area(el_deg: FloatArray, side_m2: float, top_m2: float) -> FloatArray:
    el = np.radians(np.asarray(el_deg, dtype=np.float64))
    return np.asarray(
        side_m2 * np.abs(np.cos(el)) + top_m2 * np.maximum(0.0, np.sin(el)), dtype=np.float64
    )


def solar_heat(p: BusParams, el_deg: FloatArray, s_w_m2: FloatArray, lit: FloatArray) -> FloatArray:
    return np.asarray(
        p.absorptivity * projected_area(el_deg, p.side_area_m2, p.top_area_m2) * s_w_m2 * lit,
        dtype=np.float64,
    )


def ground_temperature(
    el_deg: FloatArray,
    s_w_m2: FloatArray,
    lit: FloatArray,
    *,
    regolith_absorptivity: float,
    regolith_emissivity: float,
    cap_k: float,
    dark_k: float,
) -> FloatArray:
    """Bounding ground temperature, K: instantaneous steady-state radiative equilibrium while lit
    (capped at ``cap_k``, e.g. Diviner annual bolometric maximum), and constant ``dark_k``
    otherwise (not a time-resolved diurnal regolith curve)."""
    sin_el = np.maximum(0.0, np.sin(np.radians(np.asarray(el_deg, dtype=np.float64))))
    t_eq = (regolith_absorptivity * s_w_m2 * sin_el / (regolith_emissivity * SIGMA)) ** 0.25
    return np.asarray(np.where(lit > 0.5, np.minimum(t_eq, cap_k), dark_k), dtype=np.float64)


def steady_state_temperature(
    p: BusParams, *, q_in_w: float, t_surf_k: float, dissipated_w: float = 0.0
) -> float:
    """The T at which dT/dt = 0 for constant forcing (closed form)."""
    k_reg = SIGMA * p.bus_emissivity * p.regolith_emissivity * p.view_factor * p.base_area_m2
    k_sp = SIGMA * p.radiator_emissivity * p.radiator_area_m2
    num = q_in_w + dissipated_w + k_reg * t_surf_k**4 + k_sp * p.t_space_k**4
    return float((num / (k_reg + k_sp)) ** 0.25)


def integrate_coupled(
    bus: BusParams, pw: PowerParams, drive: Drive, t0_k: float, soc0_wh: float
) -> Coupled:
    """RK4 on ``(T, SoC)`` together; the heater and the battery are one system."""
    n, h = drive.n, drive.h_s
    k_reg = SIGMA * bus.bus_emissivity * bus.regolith_emissivity * bus.view_factor
    k_reg *= bus.base_area_m2
    k_sp = SIGMA * bus.radiator_emissivity * bus.radiator_area_m2
    t_sp4 = bus.t_space_k**4
    base = pw.avionics_w + pw.payload_w
    cap = pw.capacity_wh
    cj = bus.heat_capacity_j_per_k

    def rhs(
        temp: float, soc: float, pg: float, qs: float, ts: float, heater_cmd: float
    ) -> tuple[float, float, float, float]:
        if soc > 0.0:
            served_base, heat = base, heater_cmd
        else:
            avail = max(pg, 0.0)
            served_base = min(base, avail)
            heat = min(heater_cmd, avail - served_base)
        d_soc = (pg - served_base - heat) / 3600.0
        if soc >= cap and d_soc > 0.0:
            d_soc = 0.0
        q_diss = pw.load_dissipation_fraction * served_base + heat
        t4 = temp**4
        d_t = (qs + k_reg * (ts**4 - t4) + q_diss - k_sp * (t4 - t_sp4)) / cj
        return d_t, d_soc, heat, base - served_base

    temp_out = np.empty(n + 1)
    soc_out = np.empty(n + 1)
    heat_out = np.zeros(n + 1)
    temp, soc = float(t0_k), float(min(max(soc0_wh, 0.0), cap))
    temp_out[0], soc_out[0] = temp, soc
    pgs, qss, tss = drive.p_gen_w, drive.q_solar_w, drive.t_surf_k
    unserved = 0.0
    for i in range(n):
        j = 2 * i
        cmd = pw.heater_w if temp < pw.heater_setpoint_k else 0.0
        k1 = rhs(temp, soc, pgs[j], qss[j], tss[j], cmd)
        k2 = rhs(
            temp + 0.5 * h * k1[0], soc + 0.5 * h * k1[1], pgs[j + 1], qss[j + 1], tss[j + 1], cmd
        )
        k3 = rhs(
            temp + 0.5 * h * k2[0], soc + 0.5 * h * k2[1], pgs[j + 1], qss[j + 1], tss[j + 1], cmd
        )
        k4 = rhs(temp + h * k3[0], soc + h * k3[1], pgs[j + 2], qss[j + 2], tss[j + 2], cmd)
        temp += h * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]) / 6.0
        soc += h * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]) / 6.0
        soc = min(max(soc, 0.0), cap)
        heat_out[i + 1] = (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]) / 6.0
        unserved += h * (k1[3] + 2 * k2[3] + 2 * k3[3] + k4[3]) / 6.0 / 3600.0
        temp_out[i + 1], soc_out[i + 1] = temp, soc
    return Coupled(temp_out, soc_out, heat_out, unserved)


def hours_below(t_s: FloatArray, temp_k: FloatArray, threshold_k: float) -> float:
    """Hours the temperature is below ``threshold_k`` (linear between samples)."""
    total = 0.0
    for k in range(len(t_s) - 1):
        a, b = float(temp_k[k]), float(temp_k[k + 1])
        dt = float(t_s[k + 1] - t_s[k])
        if a < threshold_k and b < threshold_k:
            total += dt
        elif a != b and (a < threshold_k <= b or b < threshold_k <= a):
            frac = abs(threshold_k - a) / abs(b - a)
            total += dt * (frac if a < threshold_k else 1.0 - frac)
    return total / 3600.0


def first_below(t_s: FloatArray, temp_k: FloatArray, threshold_k: float) -> float | None:
    """The first time the temperature drops below ``threshold_k`` (linear), or None."""
    idx = np.flatnonzero(temp_k < threshold_k)
    if idx.size == 0:
        return None
    k = int(idx[0])
    if k == 0:
        return float(t_s[0])
    a, b = float(temp_k[k - 1]), float(temp_k[k])
    frac = (a - threshold_k) / (a - b)
    return float(t_s[k - 1] + frac * (t_s[k] - t_s[k - 1]))
