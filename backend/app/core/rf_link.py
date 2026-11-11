"""The lander-to-Earth downlink budget (ADR-20). Pure: arrays in, arrays out.

    Eb/N0 = EIRP - FSPL - L_atm + G/T - 10 log10(k_B) - 10 log10(R)

* ``FSPL = 20 log10(d_km) + 20 log10(f_GHz) + 92.45`` dB.
* The atmosphere follows DSN 810-005 module 105 (Rev. E): the zenith
  attenuation of the station's complex, at a cumulative distribution (CD) of
  weather, is scaled by the number of air masses (flat Earth, ``1/sin(el)``,
  which module 105 gives as good to 1-3 % at 6 deg). Below 6 deg the factor is
  continued with the Kasten & Young (1989) round-Earth shape, scaled to meet
  the flat-Earth value at 6 deg, so it stays finite at the horizon.
* The atmosphere also warms the receiver (module 105, equations 1-5):
  ``T_atm = T_M (1 - 1/L)`` with ``T_M = 255 + 25 CD`` K, and the cosmic
  background is cut to ``2.725 K / L``. ``G/T`` is the antenna's published
  gain over ``T_AMW + T_atm + T_CMB/L``, so one atmosphere moves both the loss
  and the noise.
* The envelope is explicit. ``value`` is clear sky (CD 25 %, the handbook's
  "average clear weather") with nominal inputs; ``hi`` is clear sky with every
  tolerance favourable; ``lo`` is adverse weather (CD 99 %) with every
  tolerance adverse. For a loss the ``lo`` end is the clear sky.

Not modelled: pointing loss, polarisation loss, gain change with elevation,
DSN scheduling, the uplink, the lander's antenna pattern (the EIRP is taken
toward Earth). See ADR-20.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from app.core.quantity import Quantity

FloatArray = npt.NDArray[np.float64]

#: Boltzmann constant, exact in the 2019 SI.
K_B_J_PER_K: Final = 1.380649e-23
K_B_DBW_HZ_K: Final = 10.0 * math.log10(K_B_J_PER_K)
#: Cosmic microwave background, 810-005 module 105 equation 4.
T_CMB_K: Final = 2.725
#: Atmosphere mean radiating temperature, module 105 equation 1: 255 + 25 CD.
TM_BASE_K: Final = 255.0
TM_SLOPE_K: Final = 25.0
#: Module 105 section 2.1.2: the flat-Earth air mass is good to 1-3 % at this elevation.
FLAT_EARTH_VALID_DEG: Final = 6.0
#: The handbook's "average clear weather" and the adverse end used here.
CD_CLEAR: Final = 0.25
CD_ADVERSE: Final = 0.99

METHOD: Final = (
    "Free-space loss from range and frequency; atmosphere and sky noise from DSN 810-005 "
    "module 105 Rev. E (zenith attenuation at the station complex, flat-Earth air mass, "
    "continued below 6 degrees with the Kasten & Young 1989 shape); antenna gain and "
    "noise from modules 101 and 104."
)


@dataclass(frozen=True, slots=True)
class Envelope:
    """A value with the ends of its uncertainty, per sample of a pass (or one scalar)."""

    value: FloatArray
    lo: FloatArray
    hi: FloatArray

    def __post_init__(self) -> None:
        eps = 1e-9
        if not (np.all(self.lo <= self.value + eps) and np.all(self.value <= self.hi + eps)):
            raise ValueError("an envelope must satisfy lo <= value <= hi")


@dataclass(frozen=True, slots=True)
class Receiver:
    """A ground antenna at one band, from the DSN handbook; every tolerance is a size, >= 0."""

    gain_dbi: float
    #: How much lower the gain may be / higher it may be.
    gain_tol_adverse_db: float
    gain_tol_favourable_db: float
    #: Antenna-microwave noise temperature near zenith, no atmosphere.
    t_amw_k: float
    t_amw_tol_adverse_k: float
    t_amw_tol_favourable_k: float
    #: Zenith attenuation at the complex at CD 25 % and CD 99 %.
    zenith_clear_db: float
    zenith_adverse_db: float


@dataclass(frozen=True, slots=True)
class Transmitter:
    """The lander's side and the coding, each one published or entered."""

    eirp_dbw: float
    frequency_ghz: float
    required_ebn0_db: float
    eirp_tol_db: float = 0.0
    #: Margin the achievable rate must keep over the required Eb/N0.
    required_margin_db: float = 0.0


@dataclass(frozen=True, slots=True)
class Budget:
    """Everything that does not depend on the data rate, per sample."""

    range_km: FloatArray
    elevation_deg: FloatArray
    fspl_db: FloatArray
    atmosphere_db: Envelope
    g_over_t_dbk: Envelope
    #: Received signal power over noise density, EIRP - FSPL - L + G/T - 10 log10 k_B.
    pr_over_n0_dbhz: Envelope
    required_ebn0_db: float
    required_margin_db: float


def fspl_db(range_km: npt.ArrayLike, frequency_ghz: float) -> FloatArray:
    """Free-space path loss, dB."""
    d = np.asarray(range_km, dtype=np.float64)
    if np.any(d <= 0) or frequency_ghz <= 0:
        raise ValueError("range and frequency must be positive")
    return np.asarray(20.0 * np.log10(d) + 20.0 * math.log10(frequency_ghz) + 92.45)


def _kasten_young(el_deg: FloatArray) -> FloatArray:
    return np.asarray(1.0 / (np.sin(np.radians(el_deg)) + 0.50572 * (el_deg + 6.07995) ** -1.6364))


def air_mass(el_deg: npt.ArrayLike) -> FloatArray:
    """Atmospheric path relative to the zenith: ``1/sin(el)`` above 6 deg, finite below."""
    el = np.clip(np.asarray(el_deg, dtype=np.float64), 0.0, 90.0)
    edge = FLAT_EARTH_VALID_DEG
    flat = 1.0 / np.sin(np.radians(np.maximum(el, edge)))
    at_edge = 1.0 / math.sin(math.radians(edge))
    k_edge = float(_kasten_young(np.asarray(edge)))
    low = at_edge * _kasten_young(el) / k_edge
    return np.where(el >= edge, flat, low)


def atmosphere_db(el_deg: npt.ArrayLike, zenith_db: float) -> FloatArray:
    """Attenuation along the slant path, dB."""
    if zenith_db < 0:
        raise ValueError("zenith attenuation cannot be negative")
    return np.asarray(zenith_db * air_mass(el_deg))


def sky_noise_k(atten_db: FloatArray, cd: float) -> FloatArray:
    """Atmosphere plus attenuated cosmic background, module 105 equations 1-5."""
    loss = np.power(10.0, np.asarray(atten_db, dtype=np.float64) / 10.0)
    tm = TM_BASE_K + TM_SLOPE_K * cd
    return np.asarray(tm * (1.0 - 1.0 / loss) + T_CMB_K / loss)


def g_over_t_dbk(gain_dbi: float, t_amw_k: float, atten_db: FloatArray, cd: float) -> FloatArray:
    """Antenna gain over system noise temperature at this attenuation, dB/K."""
    t_sys = t_amw_k + sky_noise_k(atten_db, cd)
    return np.asarray(gain_dbi - 10.0 * np.log10(t_sys))


def evaluate(
    range_km: npt.ArrayLike, elevation_deg: npt.ArrayLike, rx: Receiver, tx: Transmitter
) -> Budget:
    """The rate-independent part of the budget over a pass (range and elevation arrays)."""
    d = np.atleast_1d(np.asarray(range_km, dtype=np.float64))
    el = np.atleast_1d(np.asarray(elevation_deg, dtype=np.float64))
    if d.shape != el.shape:
        raise ValueError("range and elevation must have the same shape")
    for name, v in (
        ("gain_tol_adverse_db", rx.gain_tol_adverse_db),
        ("gain_tol_favourable_db", rx.gain_tol_favourable_db),
        ("t_amw_tol_adverse_k", rx.t_amw_tol_adverse_k),
        ("t_amw_tol_favourable_k", rx.t_amw_tol_favourable_k),
        ("eirp_tol_db", tx.eirp_tol_db),
        ("required_margin_db", tx.required_margin_db),
    ):
        if v < 0:
            raise ValueError(f"{name} must not be negative")
    if rx.zenith_adverse_db < rx.zenith_clear_db:
        raise ValueError("adverse-weather attenuation must not be below clear sky")
    loss = fspl_db(d, tx.frequency_ghz)
    a_clear = atmosphere_db(el, rx.zenith_clear_db)
    a_bad = atmosphere_db(el, rx.zenith_adverse_db)
    gt_value = g_over_t_dbk(rx.gain_dbi, rx.t_amw_k, a_clear, CD_CLEAR)
    gt_hi = g_over_t_dbk(
        rx.gain_dbi + rx.gain_tol_favourable_db,
        rx.t_amw_k - rx.t_amw_tol_favourable_k,
        a_clear,
        CD_CLEAR,
    )
    gt_lo = g_over_t_dbk(
        rx.gain_dbi - rx.gain_tol_adverse_db,
        rx.t_amw_k + rx.t_amw_tol_adverse_k,
        a_bad,
        CD_ADVERSE,
    )

    def pr(eirp: float, atten: FloatArray, gt: FloatArray) -> FloatArray:
        return np.asarray(eirp - loss - atten + gt - K_B_DBW_HZ_K)

    return Budget(
        range_km=d,
        elevation_deg=el,
        fspl_db=loss,
        atmosphere_db=Envelope(a_clear, a_clear, a_bad),
        g_over_t_dbk=Envelope(gt_value, gt_lo, gt_hi),
        pr_over_n0_dbhz=Envelope(
            pr(tx.eirp_dbw, a_clear, gt_value),
            pr(tx.eirp_dbw - tx.eirp_tol_db, a_bad, gt_lo),
            pr(tx.eirp_dbw + tx.eirp_tol_db, a_clear, gt_hi),
        ),
        required_ebn0_db=tx.required_ebn0_db,
        required_margin_db=tx.required_margin_db,
    )


def _rate_db(rate_bps: float) -> float:
    if rate_bps <= 0:
        raise ValueError("a data rate must be positive")
    return 10.0 * math.log10(rate_bps)


def ebn0_db(b: Budget, rate_bps: float) -> Envelope:
    """Energy per bit over noise density at ``rate_bps``."""
    r = _rate_db(rate_bps)
    p = b.pr_over_n0_dbhz
    return Envelope(p.value - r, p.lo - r, p.hi - r)


def margin_db(b: Budget, rate_bps: float) -> Envelope:
    """Link margin at ``rate_bps``: Eb/N0 over the coding's required Eb/N0."""
    e = ebn0_db(b, rate_bps)
    q = b.required_ebn0_db
    return Envelope(e.value - q, e.lo - q, e.hi - q)


def max_rate_bps(b: Budget) -> Envelope:
    """The highest rate that still keeps the required margin over the required Eb/N0."""
    need = b.required_ebn0_db + b.required_margin_db
    p = b.pr_over_n0_dbhz

    def rate(x: FloatArray) -> FloatArray:
        return np.asarray(np.power(10.0, (x - need) / 10.0))

    return Envelope(rate(p.value), rate(p.lo), rate(p.hi))


def quantity(
    env: Envelope, i: int, unit: str, *, scale: float = 1.0, no_margin: str | None = None
) -> Quantity:
    """Sample ``i`` of an envelope as a computed ``Quantity`` with its range."""
    v, lo, hi = (float(x[i]) * scale for x in (env.value, env.lo, env.hi))
    if lo == hi == v:
        return Quantity(
            value=v,
            unit=unit,
            provenance="computed",
            no_margin_reason=no_margin or "Every input is taken at its stated value.",
        )
    return Quantity(value=v, unit=unit, provenance="computed", lo=lo, hi=hi)


def missing_inputs(
    *,
    eirp_dbw: float | None,
    frequency_mhz: float | None,
    required_ebn0_db: float | None,
) -> list[str]:
    """What the budget still needs, named for a sentence. Empty when it can run."""
    out: list[str] = []
    if eirp_dbw is None:
        out.append("the lander's radio power (EIRP)")
    if frequency_mhz is None:
        out.append("the downlink frequency")
    if required_ebn0_db is None:
        out.append("the required Eb/N0 of the coding")
    return out


#: The sentence the contact answer has always given while nothing is published.
LINE_OF_SIGHT_ONLY: Final = (
    "Line of sight only: the lander's radio power and data rate "
    "are not published, so no data rate or link margin is given."
)


def line_of_sight_note(missing: list[str]) -> str:
    """Why there is no budget. Without the EIRP it is the long-standing sentence."""
    if not missing or missing[0].startswith("the lander's radio power"):
        return LINE_OF_SIGHT_ONLY
    names = " and ".join(missing)
    verb = "is" if len(missing) == 1 else "are"
    return (
        f"Line of sight only: {names} {verb} neither published nor entered, so no data "
        "rate or link margin is given."
    )
