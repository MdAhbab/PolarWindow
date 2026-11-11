"""Solar generation and battery state of charge for a lander (ADR-21). Pure.

    P_gen(t) = eta * A_eff(az_sun, el_sun) * S(t) * lit(t) * (1 - delta_dust)

* ``S(t)`` is the solar constant, 1361 W/m^2 at 1 au (published, see
  ``SOLAR_CONSTANT_SOURCE``), scaled by ``(1 au / d)^2`` when the caller has the
  actual Sun distance, constant otherwise. The caller says which it did.
* ``lit(t)`` comes from the track's lit arcs (the Sun's centre above the
  skyline). The track carries no partial-disc fraction, so a step that an arc
  edge falls inside is lit for exactly the share of the step inside the arc.
* Array geometries: ``vertical_faces`` (N faces round a vertical axis,
  ``A_eff = sum max(0, n_i . s) A_face``), ``top_deck_flat`` (``A sin el``) and
  ``sun_tracking`` (``A`` whenever the Sun is up).

The battery is ``SoC(t+dt) = clamp(SoC + (P_gen - P_load) dt / 3600, 0, C)`` in
Wh. Heater power depends on the bus temperature, so the SoC that the product
reports comes from the coupled integrator in ``app.core.thermal``; the plain
integrator here is the same arithmetic for a load that does not.

Not modelled: panel temperature and degradation, shading of one face by another
or by the lander's own body, cell angle-of-incidence losses beyond the cosine,
charge and discharge efficiency, battery ageing.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

GEOMETRIES: Final[tuple[str, ...]] = ("vertical_faces", "top_deck_flat", "sun_tracking")

#: Total solar irradiance at 1 au, W/m^2. Kopp & Lean (2011) 1360.8 +/- 0.5;
#: rounded to the IAU 2015 nominal value of 1361.
SOLAR_CONSTANT_W_M2: Final[float] = 1361.0
SOLAR_CONSTANT_SOURCE: Final[str] = "https://doi.org/10.1029/2010GL045777"
SOLAR_CONSTANT_PM_W_M2: Final[float] = 0.5
AU_M: Final[float] = 149_597_870_700.0


def irradiance(sun_distance_m: FloatArray | None, n: int) -> FloatArray:
    """Solar irradiance at the lander, W/m^2: inverse-square when the distance is known."""
    if sun_distance_m is None:
        return np.full(n, SOLAR_CONSTANT_W_M2, dtype=np.float64)
    d = np.asarray(sun_distance_m, dtype=np.float64)
    return np.asarray(SOLAR_CONSTANT_W_M2 * (AU_M / d) ** 2, dtype=np.float64)


def effective_area(
    geometry: str,
    az_deg: FloatArray,
    el_deg: FloatArray,
    *,
    area_m2: float,
    face_count: int | None = None,
    face_offset_deg: float | None = None,
) -> FloatArray:
    """Area presented to the Sun, m^2. ``area_m2`` is one face for ``vertical_faces``."""
    az = np.asarray(az_deg, dtype=np.float64)
    el = np.asarray(el_deg, dtype=np.float64)
    if geometry == "top_deck_flat":
        return np.asarray(area_m2 * np.maximum(0.0, np.sin(np.radians(el))), dtype=np.float64)
    if geometry == "sun_tracking":
        return np.asarray(area_m2 * (el > 0.0), dtype=np.float64)
    if geometry == "vertical_faces":
        if face_count is None or face_count < 1 or face_offset_deg is None:
            raise ValueError("vertical_faces needs face_count and face_offset_deg")
        total = np.zeros_like(az)
        cos_el = np.cos(np.radians(el))
        for i in range(face_count):
            phi = face_offset_deg + 360.0 * i / face_count
            total += np.maximum(0.0, cos_el * np.cos(np.radians(az - phi)))
        return np.asarray(area_m2 * total, dtype=np.float64)
    raise ValueError(f"unknown array geometry {geometry!r}")


def generated_power(
    a_eff_m2: FloatArray,
    s_w_m2: FloatArray,
    lit: FloatArray,
    *,
    efficiency: float,
    dust_loss: float,
) -> FloatArray:
    """``eta * A_eff * S * lit * (1 - dust)``, W. ``lit`` is the lit share, 0 to 1."""
    return np.asarray(efficiency * a_eff_m2 * s_w_m2 * lit * (1.0 - dust_loss), dtype=np.float64)


def lit_share(t_s: FloatArray, arcs: list[tuple[float, float]]) -> FloatArray:
    """Share, 0 to 1, of each interval ``[t_k, t_k+1]`` that lies inside a lit arc.

    Returns ``len(t_s) - 1`` values. Exact for arcs whose edges fall inside a step.
    """
    t = np.asarray(t_s, dtype=np.float64)
    dt = np.diff(t)
    out = np.zeros_like(dt)
    for start, end in arcs:
        overlap = np.minimum(t[1:], end) - np.maximum(t[:-1], start)
        out += np.clip(overlap, 0.0, None)
    return np.asarray(np.clip(out / dt, 0.0, 1.0), dtype=np.float64)


def lit_at(t_s: FloatArray, arcs: list[tuple[float, float]]) -> FloatArray:
    """1.0 where ``t`` is inside a lit arc, else 0.0."""
    t = np.asarray(t_s, dtype=np.float64)
    out = np.zeros_like(t)
    for start, end in arcs:
        out[(t >= start) & (t < end)] = 1.0
    return out


def integrate_soc(
    p_net_w: FloatArray, dt_s: float, capacity_wh: float, soc0_wh: float
) -> FloatArray:
    """State of charge, Wh, at the ``len(p_net_w) + 1`` step edges, clamped to [0, C].

    ``p_net_w[k]`` is generation minus load, held over step ``k``.
    """
    if capacity_wh <= 0:
        raise ValueError("battery capacity must be positive")
    soc = np.empty(len(p_net_w) + 1, dtype=np.float64)
    soc[0] = min(max(soc0_wh, 0.0), capacity_wh)
    for k, p in enumerate(p_net_w):
        soc[k + 1] = min(max(soc[k] + float(p) * dt_s / 3600.0, 0.0), capacity_wh)
    return soc


def first_empty_time(t_s: FloatArray, soc_wh: FloatArray) -> float | None:
    """The time SoC first reaches 0 (linear within the step), or None if it never does."""
    idx = np.flatnonzero(soc_wh <= 0.0)
    if idx.size == 0:
        return None
    k = int(idx[0])
    if k == 0:
        return float(t_s[0])
    s0, s1 = float(soc_wh[k - 1]), float(soc_wh[k])
    frac = 1.0 if s0 == s1 else s0 / (s0 - s1)
    return float(t_s[k - 1] + frac * (t_s[k] - t_s[k - 1]))
