"""Horizon mask construction by ray-marching a terrain sampler.

Pure. The DEM never appears here: the ray-march takes a **callable**
``sample_h(x, y) -> z`` and knows nothing about rasterio, GeoTIFFs or
projections. That is what lets the same code be tested against analytic
surfaces whose horizon can be derived by hand (a cone, a wall, a ramp) and then
run unchanged against LOLA.

The method, as specified in the brief:

    for each azimuth A in 0..360 at 0.25 deg steps (1440 rays):
        march outward to R_max = 50 km, step fine near, coarse far
        at each distance d, bilinearly sample terrain height h(d)
        drop = d^2 / (2 * R_MOON)                 # lunar curvature
        theta = atan2(h(d) - h_site - drop, d)
        horizon[A] = max(theta over all d)

Two details that are easy to get wrong and expensive to get wrong:

* **The result is not clamped at zero.** On a flat surface the horizon sits
  *below* level, because the ground curves away: ``theta -> -atan(sqrt(2h/R))``.
  Clamping would erase that, and at the south pole -- where the Sun spends the
  whole month within a degree or so of level -- a tenth of a degree of horizon
  is hours of sunlight. The sign is load-bearing.
* **Step coarsening must not skip a near ridge.** Steps start at 5 m and grow
  with distance, but the growth is capped as a fraction of the current range so
  that a feature is never stepped over. A skipped 6 m ridge at 300 m is a
  silently missing blocker.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

import numpy as np
import numpy.typing as npt

log = logging.getLogger(__name__)

FloatArray = npt.NDArray[np.float64]
F32Array = npt.NDArray[np.float32]

#: Volumetric mean radius of the Moon, metres.
R_MOON_M: Final[float] = 1_737_400.0

#: Default angular resolution. 0.25 deg = 1440 rays. Justified in ADR-1: near
#: the pole the Sun's azimuth sweeps at ~0.51 deg/h, so one bin is ~29 minutes
#: of Sun motion, which sits just under the timing uncertainty the DEM's own
#: vertical error already implies. Refining either alone buys nothing.
DEFAULT_AZIMUTH_STEP_DEG: Final[float] = 0.25

#: How far terrain can still matter. At 50 km the curvature drop is 720 m,
#: which exceeds essentially all local polar relief above a site.
DEFAULT_MAX_RANGE_M: Final[float] = 50_000.0

#: Finest step, near the site.
DEFAULT_MIN_STEP_M: Final[float] = 5.0

#: Where the march STARTS, as a multiple of the DEM post spacing.
#:
#: Not a detail. Marching from 5 m out means the first few samples land inside
#: the site's own pixel, where bilinear interpolation returns the local ground
#: slope -- and a half-metre rise over 10 m is an apparent skyline of 2.9 deg.
#: The first version of this file did exactly that and reported Connecting
#: Ridge, an open site, as having a 2.96 deg skyline whose "blocker" was 10 m
#: away. A lander does not have a 3 deg horizon because it stands on a gentle
#: slope; the ground it sits on is flat at lander scale, and a 20 m DEM cannot
#: say otherwise. Starting at two posts is the smallest honest distance.
MIN_RANGE_POSTS: Final[float] = 2.0

#: The angular noise floor below which a sample is trusted unconditionally.
#: With a 2 m vertical error this is reached at 2 / tan(0.25 deg) = 458 m, so
#: everything beyond roughly half a kilometre is taken at face value and only
#: the near field has to prove itself.
RESOLVED_NOISE_DEG: Final[float] = 0.25

#: A step is never more than this fraction of the current range. This is the
#: guard that stops coarsening from stepping over a ridge: at range r the
#: angular size of one step stays bounded, so a feature subtending more than
#: ~0.6 deg in range is always sampled at least once.
STEP_RANGE_FRACTION: Final[float] = 0.01

#: Vertical accuracy of the elevation model, metres. PLACEHOLDER, matching the
#: frontend's DEM_VERTICAL_ERROR_M. Gridded LOLA polar products are usually
#: quoted at 1-3 m vertically; wire the real per-tile error here and every
#: uncertainty figure in the product follows automatically.
DEM_VERTICAL_ERROR_M: Final[float] = 2.0


class TerrainSampler(Protocol):
    """Bilinear height lookup in a site's local ENU frame, metres.

    ``x`` is east, ``y`` is north, origin at the site. Returns NaN where the
    DEM has no coverage -- which the ray-march treats as "no terrain known",
    not as "no terrain", and records so the response can say so.

    The parameters are positional-only so that any two-argument callable
    satisfies the protocol regardless of what it names its arguments. Without
    that, a perfectly good sampler is rejected for calling them `x_east_m` and
    `y_north_m`, which is a nonsense reason to fail a type check.
    """

    def __call__(self, x: FloatArray, y: FloatArray, /) -> FloatArray: ...


@dataclass(frozen=True, slots=True)
class HorizonMask:
    """A site's skyline: what it takes to block each bearing.

    Attributes
    ----------
    el_deg:
        Skyline elevation angle per azimuth bin. May be negative (see above).
    range_m:
        Ground range at which each bearing's skyline is set. Used to convert the
        DEM's vertical error into an angular one, and to tell the user *what*
        is blocking them rather than only *that* something is.
    tol_deg:
        Angular uncertainty per bearing, ``atan(dem_error / range)``.
    coverage:
        Fraction of samples that fell inside the DEM, 0..1. Below 1.0 the mask
        is partial and every response built on it says so.
    """

    el_deg: F32Array
    range_m: F32Array
    tol_deg: F32Array
    max_el_deg: float
    max_el_bearing_deg: float
    azimuth_step_deg: float
    max_range_m: float
    coverage: float
    compute_ms: float

    @property
    def azimuth_count(self) -> int:
        return int(self.el_deg.shape[0])

    def azimuths(self) -> FloatArray:
        return np.arange(self.azimuth_count, dtype=np.float64) * self.azimuth_step_deg


def ray_distances(
    max_range_m: float = DEFAULT_MAX_RANGE_M,
    min_step_m: float = DEFAULT_MIN_STEP_M,
    step_range_fraction: float = STEP_RANGE_FRACTION,
    min_range_m: float | None = None,
) -> FloatArray:
    """Distances to sample along every ray.

    The same schedule for all rays, computed once: it makes the march a pure
    array operation and lets every ray share one vectorised sampler call.

    Step grows as ``max(min_step, fraction * r)``, which is geometric -- so the
    *angular* resolution along the ray is constant rather than degrading with
    distance. A fixed-step march wastes 90 % of its samples in the far field
    where curvature has already won, and a naively-coarsened one skips near
    ridges. This does neither.
    """
    if min_step_m <= 0 or max_range_m <= min_step_m:
        raise ValueError("bad range/step configuration")
    start = min_step_m if min_range_m is None else max(min_step_m, min_range_m)
    out: list[float] = []
    r = start
    while r <= max_range_m:
        out.append(r)
        r += max(min_step_m, step_range_fraction * r)
    return np.asarray(out, dtype=np.float64)


def curvature_drop_m(distances_m: FloatArray, r_body_m: float = R_MOON_M) -> FloatArray:
    """How far the surface falls away over a ground range, metres.

    ``d^2 / 2R``. At 20 km that is 115 m; at 50 km, 720 m. This term is the
    reason distant mountains stop mattering, and omitting it is invisible for
    near blockers and badly wrong for far ones.
    """
    return distances_m * distances_m / (2.0 * r_body_m)


def build_mask(
    sample_h: TerrainSampler,
    *,
    site_height_m: float | None = None,
    azimuth_step_deg: float = DEFAULT_AZIMUTH_STEP_DEG,
    max_range_m: float = DEFAULT_MAX_RANGE_M,
    min_step_m: float = DEFAULT_MIN_STEP_M,
    dem_post_spacing_m: float = 20.0,
    dem_vertical_error_m: float = DEM_VERTICAL_ERROR_M,
    r_body_m: float = R_MOON_M,
) -> HorizonMask:
    """Ray-march a full horizon mask.

    Vectorised per-ray: one sampler call per azimuth with all distances at
    once. That shape matters because the sampler is backed by a windowed raster
    read, and 1440 calls of 600 points each is two orders of magnitude cheaper
    than 864,000 calls of one point.

    ``site_height_m`` defaults to the sampled height at the origin. Passing it
    explicitly is how the synthetic tests pin a site onto a known surface.
    """
    import time

    t0 = time.perf_counter()

    if not (0.0 < azimuth_step_deg <= 10.0):
        raise ValueError(f"azimuth_step_deg out of range: {azimuth_step_deg}")
    n_az = int(round(360.0 / azimuth_step_deg))
    if abs(n_az * azimuth_step_deg - 360.0) > 1e-9:
        raise ValueError(f"azimuth_step_deg must divide 360 exactly, got {azimuth_step_deg}")

    distances = ray_distances(
        max_range_m, min_step_m, min_range_m=MIN_RANGE_POSTS * dem_post_spacing_m
    )
    drop = curvature_drop_m(distances, r_body_m)
    # The angular noise floor at each range: the apparent elevation a pure
    # vertical DEM error would produce there.
    noise_floor_deg = np.degrees(np.arctan2(dem_vertical_error_m, distances))

    if site_height_m is None:
        h0_arr = sample_h(np.zeros(1), np.zeros(1))
        h0 = float(h0_arr[0])
        if not np.isfinite(h0):
            raise ValueError(
                "The site itself falls outside the elevation model. Either the "
                "coordinates are wrong or the DEM subset does not cover this "
                "site; both are errors worth failing on rather than guessing."
            )
    else:
        h0 = float(site_height_m)

    el_deg = np.empty(n_az, dtype=np.float32)
    range_m = np.empty(n_az, dtype=np.float32)
    inside_total = 0
    sample_total = 0

    azimuths = np.arange(n_az, dtype=np.float64) * azimuth_step_deg
    # Azimuth is measured from north, clockwise: east = sin(A), north = cos(A).
    sin_a = np.sin(np.radians(azimuths))
    cos_a = np.cos(np.radians(azimuths))

    for i in range(n_az):
        xs = sin_a[i] * distances
        ys = cos_a[i] * distances
        h = sample_h(xs, ys)

        valid = np.isfinite(h)
        inside_total += int(valid.sum())
        sample_total += valid.size

        if not valid.any():
            # No DEM anywhere along this ray. The honest horizon is the
            # spherical one -- the curvature-limited skyline of a smooth body --
            # and coverage will report that this bearing is unmodelled.
            el_deg[i] = np.float32(np.degrees(-np.arctan(np.sqrt(2.0 * max(h0, 0.0) / r_body_m))))
            range_m[i] = np.float32(max_range_m)
            continue

        theta = np.degrees(np.arctan2(np.where(valid, h, -np.inf) - h0 - drop, distances))

        # A blocker has to rise above the noise it could be confused with.
        #
        # The angular error a vertical DEM error induces at range r is
        # atan(sigma / r), which at 40 m with sigma = 2 m is 2.9 degrees -- larger
        # than almost any real skyline at these sites. Taking a plain argmax
        # therefore picks gridding noise in the first few samples and calls it
        # terrain: on Connecting Ridge it reported a 2.46 degree skyline whose
        # "blocker" was 40 m away and 1.7 m high, which is indistinguishable
        # from nothing at all.
        #
        # So a sample is only eligible to set the skyline if its own angle
        # exceeds its own noise floor. Far samples clear a floor near zero and
        # are almost always eligible; near samples must be genuinely steep --
        # a 10 degree rise at 100 m is real and is kept, a 2 degree one is not.
        # If nothing clears its floor, the bearing is genuinely open and the
        # skyline is whatever the far field says, which is the honest answer.
        # A sample may set the skyline if EITHER it stands clearly above the
        # noise that could be mistaken for it, OR it is far enough out that that
        # noise is negligible anyway. The second clause is what makes the rule
        # total: the far field is always eligible, so there is never a need to
        # fall back to "pick the loudest near-field sample", which is what an
        # earlier version did and which simply reinstated the bug.
        eligible = (theta > noise_floor_deg) | (noise_floor_deg < RESOLVED_NOISE_DEG)
        candidates = np.where(eligible & valid, theta, -np.inf)
        k = int(np.argmax(candidates))
        el_deg[i] = np.float32(theta[k])
        range_m[i] = np.float32(distances[k])

    tol_deg = np.degrees(
        np.arctan2(dem_vertical_error_m, np.maximum(range_m.astype(np.float64), 1.0))
    ).astype(np.float32)

    k_max = int(np.argmax(el_deg))
    coverage = inside_total / sample_total if sample_total else 0.0

    return HorizonMask(
        el_deg=el_deg,
        range_m=range_m,
        tol_deg=tol_deg,
        max_el_deg=float(el_deg[k_max]),
        max_el_bearing_deg=float(azimuths[k_max]),
        azimuth_step_deg=azimuth_step_deg,
        max_range_m=max_range_m,
        coverage=float(coverage),
        compute_ms=(time.perf_counter() - t0) * 1000.0,
    )


def downsample(mask_el_deg: F32Array, target_count: int) -> F32Array:
    """Reduce a mask to fewer bins by taking the **maximum** of each group.

    Never the mean. A skyline is an upper envelope: averaging it invents sky
    where a ridge is, and the ridge is the whole answer at these sites. This is
    the kind of one-word choice that silently adds hours of fictional sunlight.
    """
    n = mask_el_deg.shape[0]
    if target_count <= 0 or n % target_count != 0:
        raise ValueError(f"cannot downsample {n} bins to {target_count}")
    factor = n // target_count
    if factor == 1:
        return mask_el_deg.copy()
    return np.asarray(mask_el_deg.reshape(target_count, factor).max(axis=1), dtype=np.float32)


def spherical_horizon_deg(site_height_m: float, r_body_m: float = R_MOON_M) -> float:
    """Horizon depression for a smooth sphere, degrees (negative).

    The fallback when a site has no DEM coverage, and the analytic value the
    flat-plane unit test checks against.
    """
    h = max(site_height_m, 0.0)
    return -float(np.degrees(np.arccos(r_body_m / (r_body_m + h)))) if h > 0 else 0.0


def make_analytic_sampler(
    features: list[tuple[float, float, float, float]],
    *,
    base_height_m: float = 0.0,
) -> Callable[[FloatArray, FloatArray], FloatArray]:
    """A terrain sampler built from Gaussian bumps, for tests and for fallback.

    Each feature is ``(east_m, north_m, height_m, sigma_m)``. Used by the
    synthetic golden tests so that the full pipeline -- mask, timeline, metrics --
    can run on a machine with no DEM at all, which is what keeps the golden
    safety net alive during local development.
    """

    def sample(x: FloatArray, y: FloatArray) -> FloatArray:
        z = np.full(np.shape(x), base_height_m, dtype=np.float64)
        for ex, ny, hm, sigma in features:
            d2 = (x - ex) ** 2 + (y - ny) ** 2
            z = z + hm * np.exp(-d2 / (2.0 * sigma * sigma))
        return z

    return sample
