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

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

import numpy as np
import numpy.typing as npt

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
        Angular uncertainty per bearing, ``atan(dem_error / range)``, where the
        error is that of the elevation model that actually supplied the
        blocking sample -- not one figure for the whole mask.
    coverage:
        Fraction of samples that fell inside the DEM, 0..1. Below 1.0 the mask
        is partial and every response built on it says so.
    blocker_sigma_m:
        Vertical error of the sample that set each bearing's skyline. Present
        only on a freshly built mask; it is summarised into the stored record
        rather than persisted, because ``tol_deg`` already carries its effect.
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
    blocker_sigma_m: F32Array | None = None

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
    sample_sigma: TerrainSampler | None = None,
    r_body_m: float = R_MOON_M,
    use_jit: bool = True,
) -> HorizonMask:
    """Ray-march a full horizon mask.

    Every ray is sampled in one vectorised call, and the per-sample skyline
    selection runs in ``skyline_reference`` -- compiled with numba when it is
    installed and ``use_jit`` is true, as plain Python otherwise. The two are
    the same source, and ``test_numba_and_python_agree`` pins them together.

    ``site_height_m`` defaults to the sampled height at the origin. Passing it
    explicitly is how the synthetic tests pin a site onto a known surface.

    ``sample_sigma`` returns the vertical error of the elevation model at each
    sample, for terrain assembled from more than one product. Without it every
    sample is taken to be as good as ``dem_vertical_error_m`` -- which, for a
    site whose far skyline comes from the 80 m regional model, understated the
    blocker's error by half on more than half of the bearings.
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

    azimuths = np.arange(n_az, dtype=np.float64) * azimuth_step_deg
    # Azimuth is measured from north, clockwise: east = sin(A), north = cos(A).
    sin_a = np.sin(np.radians(azimuths))
    cos_a = np.cos(np.radians(azimuths))

    # Every ray sampled in one call. The DEM sampler is vectorised bilinear
    # arithmetic, so 1440 rays of ~600 points is one 864k-point call rather
    # than 1440 small ones; the per-sample selection below is then a tight
    # loop, which is what the JIT is for.
    xs = (sin_a[:, None] * distances[None, :]).ravel()
    ys = (cos_a[:, None] * distances[None, :]).ravel()
    n_d = distances.size
    heights = np.asarray(sample_h(xs, ys), dtype=np.float64).reshape(n_az, n_d)
    if sample_sigma is not None:
        sig = np.asarray(sample_sigma(xs, ys), dtype=np.float64).reshape(n_az, n_d)
        sig = np.where(np.isfinite(sig), sig, dem_vertical_error_m)
    else:
        sig = np.full((n_az, n_d), dem_vertical_error_m, dtype=np.float64)

    select = _skyline_jit() if use_jit else None
    el_deg, range_m, sigma_m, inside_total = (select or skyline_reference)(
        heights,
        sig,
        distances,
        drop,
        h0,
        RESOLVED_NOISE_DEG,
        spherical_horizon_deg(h0, r_body_m),
        max_range_m,
        dem_vertical_error_m,
    )
    sample_total = n_az * n_d

    tol_deg = np.degrees(
        np.arctan2(sigma_m.astype(np.float64), np.maximum(range_m.astype(np.float64), 1.0))
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
        blocker_sigma_m=sigma_m,
    )


def skyline_reference(
    heights: FloatArray,
    sigma: FloatArray,
    distances: FloatArray,
    drop: FloatArray,
    h0: float,
    resolved_noise_deg: float,
    spherical_el_deg: float,
    max_range_m: float,
    default_sigma_m: float,
) -> tuple[F32Array, F32Array, F32Array, int]:
    """Pick each ray's skyline sample. Plain Python; also the JIT's source.

    For every bearing, a sample may set the skyline if it stands above the
    noise its own DEM error could produce, or is far enough out that the noise
    is negligible (see ``build_mask``). The highest such sample wins, first on
    a tie. A ray with no DEM at all takes the smooth-sphere horizon.

    Returns ``(el_deg, range_m, sigma_m, samples_inside_the_dem)``.
    """
    n_az, n_d = heights.shape
    el = np.empty(n_az, dtype=np.float32)
    rng = np.empty(n_az, dtype=np.float32)
    sgm = np.empty(n_az, dtype=np.float32)
    inside = 0
    to_deg = 180.0 / math.pi
    for i in range(n_az):
        best = -math.inf
        k = -1
        any_valid = False
        for j in range(n_d):
            h = heights[i, j]
            if not math.isfinite(h):
                continue
            any_valid = True
            inside += 1
            theta = math.atan2(h - h0 - drop[j], distances[j]) * to_deg
            floor = math.atan2(sigma[i, j], distances[j]) * to_deg
            if (theta > floor or floor < resolved_noise_deg) and theta > best:
                best = theta
                k = j
        if not any_valid:
            el[i] = spherical_el_deg
            rng[i] = max_range_m
            sgm[i] = default_sigma_m
        elif k < 0:
            # Nothing cleared its noise floor: the first sample stands, as the
            # array argmax this replaced returned for an all -inf row.
            h = heights[i, 0]
            el[i] = (
                math.atan2(h - h0 - drop[0], distances[0]) * to_deg
                if math.isfinite(h)
                else -math.inf
            )
            rng[i] = distances[0]
            sgm[i] = sigma[i, 0]
        else:
            el[i] = best
            rng[i] = distances[k]
            sgm[i] = sigma[i, k]
    return el, rng, sgm, inside


_JIT_CACHE: list[Callable[..., tuple[F32Array, F32Array, F32Array, int]] | None] = []


def _skyline_jit() -> Callable[..., tuple[F32Array, F32Array, F32Array, int]] | None:
    """``skyline_reference`` compiled by numba, or None where numba is absent.

    Compiled once per process and cached on disk (``cache=True``), so only the
    first mask build after an install pays the compile.
    """
    if not _JIT_CACHE:
        try:
            from numba import njit

            _JIT_CACHE.append(njit(cache=True)(skyline_reference))
        except ImportError:  # pragma: no cover - numba is a pinned dependency
            _JIT_CACHE.append(None)
    return _JIT_CACHE[0]


def _centred_windows(n: int, target_count: int) -> npt.NDArray[np.intp]:
    """Input-bin indices for each output bin, centred on the output azimuth.

    Output bin ``j`` sits at azimuth ``j * 360 / target_count`` -- the same
    convention every consumer interpolates with -- so it must summarise the
    input bins *around* that azimuth, not the ones after it. Grouping
    ``[4j, 4j + 3]`` instead describes ``[j, j + 0.75]`` deg and shifts the
    whole skyline 0.375 deg clockwise, which is a real bearing error at a
    resolution where 0.25 deg is half an hour of Sun motion.

    The window is ``+-half`` a factor wide and inclusive, so for an even factor
    the boundary bins belong to both neighbours. For an upper envelope that is
    the conservative choice: a ridge on the boundary shows up in both.
    """
    if target_count <= 0 or n % target_count != 0:
        raise ValueError(f"cannot downsample {n} bins to {target_count}")
    factor = n // target_count
    half = factor // 2
    offsets = np.arange(-half, half + 1, dtype=np.intp)
    centres = np.arange(target_count, dtype=np.intp) * factor
    return (centres[:, None] + offsets[None, :]) % n


def downsample_mask(mask: HorizonMask, target_count: int) -> tuple[F32Array, F32Array, F32Array]:
    """Reduce a mask to fewer bins by taking the **maximum** around each one.

    Never the mean. A skyline is an upper envelope: averaging it invents sky
    where a ridge is, and the ridge is the whole answer at these sites. This is
    the kind of one-word choice that silently adds hours of fictional sunlight.

    Elevation, range and tolerance are reduced together: range and tolerance are
    taken from the bin that *set* each output elevation, so all three describe
    the same blocker. Reducing them independently (nearest range, loosest
    tolerance) produced a triple that no single piece of terrain satisfies.
    """
    n = mask.azimuth_count
    idx = _centred_windows(n, target_count)
    if idx.shape[1] == 1:
        return mask.el_deg.copy(), mask.range_m.copy(), mask.tol_deg.copy()
    windows = mask.el_deg[idx]
    pick = idx[np.arange(target_count), np.argmax(windows, axis=1)]
    return (
        np.asarray(mask.el_deg[pick], dtype=np.float32),
        np.asarray(mask.range_m[pick], dtype=np.float32),
        np.asarray(mask.tol_deg[pick], dtype=np.float32),
    )


#: The product name a smooth-sphere mask carries. Everything downstream reads
#: ``terrain_modelled`` from this, so there is one source for the flag.
SMOOTH_SPHERE_PRODUCT: Final[str] = "none (smooth sphere)"


def is_terrain_modelled(dem_product: str) -> bool:
    return dem_product != SMOOTH_SPHERE_PRODUCT


def smooth_mask(
    *,
    azimuth_step_deg: float = DEFAULT_AZIMUTH_STEP_DEG,
    max_range_m: float = DEFAULT_MAX_RANGE_M,
) -> HorizonMask:
    """A skyline for a site no elevation model covers: a smooth sphere.

    Every bearing is 0 deg: on a sphere the local horizontal is the horizon
    (the curvature dip is below the bin size for any surface site). It carries
    zero coverage, because no terrain was sampled, and is always reported as
    ``terrain_modelled = false`` -- a mask this simple must never be read as a
    measured skyline (ADR-6).
    """
    n = int(round(360.0 / azimuth_step_deg))
    zeros = np.zeros(n, dtype=np.float32)
    return HorizonMask(
        el_deg=zeros,
        range_m=zeros.copy(),
        tol_deg=zeros.copy(),
        max_el_deg=0.0,
        max_el_bearing_deg=0.0,
        azimuth_step_deg=azimuth_step_deg,
        max_range_m=max_range_m,
        coverage=0.0,
        compute_ms=0.0,
    )


def spherical_horizon_deg(site_height_m: float, r_body_m: float = R_MOON_M) -> float:
    """Horizon depression for a smooth sphere, degrees (negative).

    The fallback when a site has no DEM coverage, and the analytic value the
    flat-plane unit test checks against.
    """
    h = max(site_height_m, 0.0)
    return -float(np.degrees(np.arccos(r_body_m / (r_body_m + h)))) if h > 0 else 0.0
