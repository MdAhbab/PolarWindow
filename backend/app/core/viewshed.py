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
from app.core.projections import LocalFrame

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


# ---------------------------------------------------------------------------
# The map layer: the same states as raster tiles
# ---------------------------------------------------------------------------

#: The tile style, the same in both themes (a tile is a picture): translucent so the relief
#: shows through, and the three states told apart by pattern as well as by tone, never by
#: colour alone: in sight is filled, blocked is dark with 45 degree stripes, uncertain is a
#: light wash with -45 degree stripes. The colours are the product's dark-theme tokens
#: (Earth's blue, the dark fill and its hatch, the uncertain grey).
CLEAR_RGBA: Final[tuple[int, int, int, int]] = (79, 198, 224, 150)
BLOCKED_RGBA: Final[tuple[int, int, int, int]] = (20, 24, 29, 225)
BLOCKED_STRIPE_RGBA: Final[tuple[int, int, int, int]] = (138, 149, 161, 255)
UNCERTAIN_RGBA: Final[tuple[int, int, int, int]] = (200, 208, 216, 95)
UNCERTAIN_STRIPE_RGBA: Final[tuple[int, int, int, int]] = (20, 24, 29, 235)
#: Stripes repeat every 8 pixels of the tile: 3 wide for blocked, 2 for uncertain.
HATCH_PERIOD_PX: Final[int] = 8
BLOCKED_STRIPE_PX: Final[int] = 3
UNCERTAIN_STRIPE_PX: Final[int] = 2


def cell_edges(ranges_m: FloatArray) -> FloatArray:
    """Where each range cell ends: half way between samples, the first cell starting at the
    lander and the last reaching half a step past the largest range. The frontend's table
    and sector drawing use the same edges, so the tiles and the twin agree."""
    r = np.asarray(ranges_m, dtype=np.float64)
    last = r[-1] + ((r[-1] - r[-2]) / 2.0 if r.size > 1 else r[-1])
    return np.concatenate([[0.0], (r[:-1] + r[1:]) / 2.0, [last]])


def tile_rgba(
    bounds: tuple[float, float, float, float],
    frame: LocalFrame,
    bearings_deg: FloatArray,
    ranges_m: FloatArray,
    states: IntArray,
    *,
    pixel_origin: tuple[int, int] = (0, 0),
    size_px: int = 256,
) -> npt.NDArray[np.uint8] | None:
    """One map tile of a viewshed as RGBA, or None where no cell of it lies inside the tile.

    ``bounds`` are the tile's ``(x_min, y_min, x_max, y_max)`` in the polar stereographic
    grid, sampled as the terrain tiles are (``size_px`` points from edge to edge), so a
    tile lines up with the hillshade under it. ``frame`` is the lander's local frame:
    each pixel is taken back from the grid to the ground east and north of the lander (the
    grid's north is not true north), then to a bearing and a range, and so to its cell.
    ``states`` is ``[bearing][range]``. ``pixel_origin`` is the tile's first pixel in the
    whole map at its zoom, so the stripes run on unbroken across tiles.
    """
    x_min, y_min, x_max, y_max = bounds
    gx, gy = np.meshgrid(np.linspace(x_min, x_max, size_px), np.linspace(y_max, y_min, size_px))
    dx, dy = gx - frame.x0_m, gy - frame.y0_m
    c = math.cos(frame.grid_convergence_rad) * frame.scale_factor
    s = math.sin(frame.grid_convergence_rad) * frame.scale_factor
    k2 = c * c + s * s  # LocalFrame.local_to_grid, inverted
    east = (dx * c - dy * s) / k2
    north = (dx * s + dy * c) / k2
    rng = np.hypot(east, north)
    edges = cell_edges(ranges_m)
    inside = rng < edges[-1]
    if not inside.any():
        return None
    k = np.clip(np.searchsorted(edges, rng, side="right") - 1, 0, edges.size - 2)
    b = np.asarray(bearings_deg, dtype=np.float64)
    step = float(b[1] - b[0]) if b.size > 1 else 360.0
    brg = np.degrees(np.arctan2(east, north)) % 360.0
    i = np.floor((brg - b[0] + step / 2.0) / step).astype(np.int64) % b.size
    state = np.asarray(states)[i, k]

    col, row = np.meshgrid(np.arange(size_px), np.arange(size_px))
    u = pixel_origin[0] + col
    v = pixel_origin[1] + row
    slash = ((u + v) % HATCH_PERIOD_PX) < BLOCKED_STRIPE_PX  # a line of constant x + y: "/"
    backslash = ((u - v) % HATCH_PERIOD_PX) < UNCERTAIN_STRIPE_PX  # constant x - y: "\"
    rgba = np.zeros((size_px, size_px, 4), dtype=np.uint8)
    rgba[inside & (state == CLEAR)] = CLEAR_RGBA
    blocked = inside & (state == BLOCKED)
    rgba[blocked] = BLOCKED_RGBA
    rgba[blocked & slash] = BLOCKED_STRIPE_RGBA
    unsure = inside & (state == UNCERTAIN)
    rgba[unsure] = UNCERTAIN_RGBA
    rgba[unsure & backslash] = UNCERTAIN_STRIPE_RGBA
    return rgba
