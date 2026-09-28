"""Rover-to-lander line of sight over the terrain (T1, F5). Pure.

Like :mod:`app.core.horizon`, this never sees a DEM: it takes a height
sampler and a vertical-error sampler in the lander's local east/north frame,
so the same code runs on analytic surfaces (a wall, a ramp) and on LOLA.

For each bearing a ray is sampled outward from the lander. A rover at range
``d`` on that ray is:

* **in clear sight** when no terrain between them rises to the straight line
  from the lander's antenna to the rover's -- found with the running maximum
  of the terrain's elevation angle seen from the lander's antenna;
* **on a clear radio path** when the terrain also stays out of the first
  Fresnel zone around that line (radius ``sqrt(lambda s (d - s) / d)``), the
  usual condition for a radio link to lose nothing to the ground.

Each is one of three states, never a bare yes or no. The elevation model's
vertical error at each blocker, as an angle ``atan(sigma / distance)`` (and the
rover's own ground height error, the same way), makes a band: **clear** when
the terrain stays below the line by more than it, **blocked** when it rises
above by more than it, **uncertain** in between. With a 2 m error at 50 m that
band is over two degrees: the elevation model cannot say, and the answer says so.

The noise rule of the skyline is kept at both ends: terrain within two DEM
posts of the lander or of the rover is the ground each stands on, flat at
their scale, and never a blocker (a 20 m model cannot resolve a rock).
Curvature: heights drop by ``s^2 / 2R`` with ground range, as for the skyline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from app.core.horizon import R_MOON_M, TerrainSampler, curvature_drop_m

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int8]

BLOCKED: Final[int] = 0
UNCERTAIN: Final[int] = 1
CLEAR: Final[int] = 2
STATE_WORDS: Final[tuple[str, str, str]] = ("blocked", "uncertain", "clear")
C_M_S: Final[float] = 299_792_458.0


@dataclass(frozen=True, slots=True)
class Viewshed:
    bearings_deg: FloatArray  # (nb,)
    ranges_m: FloatArray  # (nr,)
    sight: IntArray  # (nb, nr): BLOCKED / UNCERTAIN / CLEAR
    radio: IntArray  # (nb, nr)
    covered: npt.NDArray[np.bool_]  # (nb, nr): the elevation model has the rover's ground


def _states(worst_low: FloatArray, worst_high: FloatArray) -> IntArray:
    """From the smallest clearance with the error taken against (``worst_low``)
    and with it taken for (``worst_high``): clear, blocked or uncertain."""
    out = np.full(worst_low.shape, UNCERTAIN, dtype=np.int8)
    out[worst_low > 0.0] = CLEAR
    out[worst_high < 0.0] = BLOCKED
    return out


def compute(
    sample_h: TerrainSampler,
    sample_sigma: TerrainSampler,
    *,
    bearings_deg: FloatArray,
    ranges_m: FloatArray,
    lander_antenna_m: float,
    rover_antenna_m: float,
    frequency_hz: float,
    post_m: float,
    step_m: float | None = None,
    site_height_m: float | None = None,
    r_body_m: float = R_MOON_M,
) -> Viewshed:
    """Sight and radio-path states for a rover at every (bearing, range)."""
    b = np.asarray(bearings_deg, dtype=np.float64)
    rk = np.asarray(ranges_m, dtype=np.float64)
    if rk.size == 0 or float(rk.min()) <= 0.0:
        raise ValueError("ranges must be positive")
    step = float(step_m if step_m is not None else max(1.0, post_m / 4.0))
    near = 2.0 * post_m  # the noise rule: two posts at either end are the ground itself
    s = np.arange(step, float(rk.max()) + step / 2, step)
    sin_b, cos_b = np.sin(np.radians(b)), np.cos(np.radians(b))

    def at(dist: FloatArray) -> tuple[FloatArray, FloatArray]:
        x = (sin_b[:, None] * dist[None, :]).ravel()
        y = (cos_b[:, None] * dist[None, :]).ravel()
        z = np.asarray(sample_h(x, y), dtype=np.float64).reshape(b.size, dist.size)
        sg = np.asarray(sample_sigma(x, y), dtype=np.float64).reshape(b.size, dist.size)
        return z - curvature_drop_m(dist, r_body_m)[None, :], sg

    if site_height_m is None:
        h0 = float(np.asarray(sample_h(np.zeros(1), np.zeros(1)), dtype=np.float64)[0])
        if not math.isfinite(h0):
            raise ValueError("the lander's own spot is outside the elevation model")
    else:
        h0 = float(site_height_m)
    eye = h0 + lander_antenna_m
    zs, sig_s = at(s)  # terrain along each ray, curvature applied
    zk, sig_k = at(rk)  # the rover's ground at each target range
    covered = np.isfinite(zk)
    tip = zk + rover_antenna_m  # the rover's antenna
    # Unknown terrain (outside the model) can neither block nor clear: it is
    # taken as the worst case in both directions through a huge error.
    unknown = ~np.isfinite(zs)
    zs = np.where(unknown, eye, zs)
    sig_s = np.where(unknown | ~np.isfinite(sig_s), 1.0e6, sig_s)
    sig_k = np.where(np.isfinite(sig_k), sig_k, 1.0e6)

    # --- Sight: running maximum of the terrain's elevation angle ------------
    theta_s = np.arctan2(zs - eye, s[None, :])
    tol_s = np.arctan2(sig_s, s[None, :])
    usable = s >= near  # beyond the lander's own ground
    hi = np.where(usable[None, :], theta_s + tol_s, -np.inf)
    lo = np.where(usable[None, :], theta_s - tol_s, -np.inf)
    run_hi = np.maximum.accumulate(hi, axis=1)
    run_lo = np.maximum.accumulate(lo, axis=1)
    # For the rover at rk, blockers are samples short of its own ground.
    idx = np.searchsorted(s, rk - near, side="left") - 1  # last sample < rk - near
    has = idx >= 0
    ii = np.clip(idx, 0, s.size - 1)
    m_hi = np.where(has[None, :], run_hi[:, ii], -np.inf)
    m_lo = np.where(has[None, :], run_lo[:, ii], -np.inf)
    theta_k = np.arctan2(tip - eye, rk[None, :])
    tol_k = np.arctan2(sig_k, rk[None, :])
    sight = _states((theta_k - tol_k) - m_hi, (theta_k + tol_k) - m_lo)

    # --- Radio: the first Fresnel zone, per rover position -------------------
    lam = C_M_S / frequency_hz
    radio = np.empty_like(sight)
    for k, d in enumerate(rk):
        sel = usable & (s < d - near)
        if not sel.any():
            radio[:, k] = sight[:, k]
            continue
        sk = s[sel]
        line = eye + (tip[:, k : k + 1] - eye) * (sk[None, :] / d)
        f1 = np.sqrt(lam * sk * (d - sk) / d)
        clear = line - f1[None, :] - zs[:, sel]
        err = sig_s[:, sel] + sig_k[:, k : k + 1] * (sk[None, :] / d)
        radio[:, k] = _states((clear - err).min(axis=1), (clear + err).min(axis=1))
    # A path the line itself cannot clear cannot have a clear zone around it.
    radio = np.minimum(radio, sight).astype(np.int8)
    return Viewshed(bearings_deg=b, ranges_m=rk, sight=sight, radio=radio, covered=covered)


def ground_share(v: Viewshed, states: IntArray) -> tuple[float, float] | None:
    """Share of the ground within the largest range out of sight, as ``(lo, hi)``:
    ``lo`` counts only blocked cells, ``hi`` blocked and uncertain ones. Each cell
    stands for its annulus, so it is weighted by its range; cells the elevation
    model does not cover are left out. None when no cell is covered."""
    w = np.broadcast_to(v.ranges_m[None, :], states.shape)
    w = np.where(v.covered, w, 0.0)
    total = float(w.sum())
    if total <= 0.0:
        return None
    lo = float(w[states == BLOCKED].sum()) / total
    hi = float(w[states != CLEAR].sum()) / total
    return lo, hi
