"""Slope and illumination across a landing ellipse (ADR-22).

Samples the entered 3-sigma ellipse, reads terrain at each point (PGDA 5 m where
a tile covers the whole ellipse, else the app's own DEM), and reports slope
percentiles, the share of points above the entered slope limit and above the
static tip-over angle, and the long-term average illumination from the PGDA
maps. Stores nothing and gives no verdict: physical quantities and shares with
their intervals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ENGINE_VERSION, get_settings
from app.core import dispersion, hazards, quantity
from app.core.projections import local_frame
from app.core.quantity import Quantity
from app.data import pgda
from app.data.lola import DemTile, DemUnavailable
from app.services import site_service
from app.services.lifecycle import missing, q, share

FloatArray = npt.NDArray[np.float64]

MAX_HEATMAP = 64
PGDA_LOLA_URL = "https://pgda.gsfc.nasa.gov/products/78"
PGDA_ILLUM_URL = "https://pgda.gsfc.nasa.gov/products/69"
LOLA_PDS_URL = "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/"

SOURCES: dict[str, dict[str, str]] = {
    "pgda_lola_5m": {
        "name": "PGDA 5 m LOLA elevation, slope and elevation uncertainty for south-pole sites",
        "citation": "Barker et al. (2021), Planetary and Space Science 203, 105119",
        "url": PGDA_LOLA_URL,
    },
    "pgda_illumination": {
        "name": "PGDA average Sun visibility, average Earth visibility and permanent shadow",
        "citation": "Mazarico et al. (2011), Icarus 211, 1066-1081",
        "url": PGDA_ILLUM_URL,
    },
    "app_dem": {
        "name": "LOLA polar gridded DEM (20 m near the site, 80 m regional), vertical error 2 m",
        "citation": "NASA PDS Geosciences Node, LRO LOLA gridded data records",
        "url": LOLA_PDS_URL,
    },
}

NOT_MODELLED = [
    "Rocks and craters smaller than the terrain model's resolution; the slope is the "
    "slope over its baseline, not the slope under each footpad.",
    "Touchdown dynamics: landing velocity, attitude at contact, leg stroke and sliding.",
    "Plume effects: the engine's erosion and ejecta, and the ground it leaves.",
    "Hours of sunlight at each point for the chosen dates; the illumination figures are "
    "the product's long-term average, not the dates in the window.",
    "Antenna pointing at a resting tilt: Earth visibility is the product's average at "
    "each point on level ground, not what an antenna sees on the slope.",
    "Tip-over by anything but the static criterion: dynamic tip-over, rolling and sliding.",
]


class NoTerrain(LookupError):
    """No elevation model covers the whole ellipse."""


@dataclass(frozen=True, slots=True)
class _Slope:
    name: str
    label: str
    grid: hazards.SlopeGrid
    origin_x_m: float
    origin_y_m: float
    vertical_error_m: float
    reason: str | None
    tile: str | None
    crs_wkt: str | None
    product_slope: tuple[Path, str] | None  # PGDA slp file, for the cross-check


def _app_slope(
    paths: list[Path], x0: float, y0: float, x1: float, y1: float
) -> tuple[_Slope, str] | None:
    """The finest app DEM tile that covers the box, with the slope grid over it."""
    for p in paths:
        try:
            t = DemTile.load(p)
        except DemUnavailable:
            continue
        h, w = t.heights.shape
        pad = 2.0 * t.scale_m
        if (
            x0 - pad < t.origin_x_m
            or x1 + pad > t.origin_x_m + (w - 1) * t.scale_m
            or y1 + pad > t.origin_y_m
            or y0 - pad < t.origin_y_m - (h - 1) * t.scale_m
        ):
            continue
        c0 = max(int(math.floor((x0 - pad - t.origin_x_m) / t.scale_m)), 0)
        c1 = min(int(math.ceil((x1 + pad - t.origin_x_m) / t.scale_m)) + 1, w)
        r0 = max(int(math.floor((t.origin_y_m - (y1 + pad)) / t.scale_m)), 0)
        r1 = min(int(math.ceil((t.origin_y_m - (y0 - pad)) / t.scale_m)) + 1, h)
        z = t.heights[r0:r1, c0:c1].astype(np.float64)
        grid = hazards.horn_slope(z, t.scale_m, t.vertical_error_m)
        # Node-centred origin -> outer corner of the top-left cell.
        ox = t.origin_x_m + c0 * t.scale_m - t.scale_m / 2.0
        oy = t.origin_y_m - r0 * t.scale_m + t.scale_m / 2.0
        return (
            _Slope(
                f"app_dem:{p.stem}",
                f"The app's own DEM ({t.product}, {t.scale_m:g} m)",
                grid,
                ox,
                oy,
                t.vertical_error_m,
                None,
                None,
                None,
                None,
            ),
            t.product,
        )
    return None


def _pgda_slope(root: Path, x0: float, y0: float, x1: float, y1: float) -> _Slope | None:
    tile = pgda.covering_tile(root, x0, y0, x1, y1, margin_m=3 * 5.0)
    if tile is None or not pgda.crs_matches_app(tile.crs_wkt):
        return None
    pad = 2.0 * tile.res_m
    z = pgda.read_window(tile.surf, x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    e = pgda.read_window(tile.toterr, x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    if z is None or e is None or z.values.shape != e.values.shape:
        return None
    grid = hazards.horn_slope(z.values, z.res_m, e.values)
    finite = e.values[np.isfinite(e.values)]
    ve = float(np.median(finite)) if finite.size else float("nan")
    return _Slope(
        f"pgda_lola_5m:{tile.name}",
        f"PGDA 5 m LOLA, {tile.name}",
        grid,
        z.origin_x_m,
        z.origin_y_m,
        ve,
        None,
        tile.name,
        z.crs_wkt,
        (tile.slp, tile.name),
    )


def _pct_quantity(
    vals: tuple[float, ...] | None, i: int, unit: str, pm: float | None, why: str
) -> dict[str, Any]:
    if vals is None:
        return missing(unit, "no point of the ellipse has a value")
    if pm is not None and math.isfinite(pm):
        return q(Quantity(vals[i], unit, "computed", pm=pm))
    return q(Quantity(vals[i], unit, "computed", no_margin_reason=why))


def _published_pct(vals: tuple[float, ...] | None, i: int, unit: str, url: str) -> dict[str, Any]:
    if vals is None:
        return missing(unit, "no point of the ellipse has a value", provenance="published")
    return q(
        Quantity(
            vals[i],
            unit,
            "published",
            no_margin_reason="the product publishes no uncertainty; the spread across the "
            "ellipse is the 10th to 90th percentile",
            source=url,
        )
    )


def _share(k: int, n: int) -> dict[str, Any] | None:
    if n <= 0:
        return None
    return share(quantity.share(k, n, checked=False))


def _illumination(
    root: Path, gx: FloatArray, gy: FloatArray, box: tuple[float, float, float, float]
) -> dict[str, Any]:
    basis = (
        "The product's long-term average over the LOLA data it was built from, "
        "not hours in the chosen dates."
    )
    base: dict[str, Any] = {
        "basis": basis,
        "epoch": pgda.ILLUM_EPOCH,
        "source": SOURCES["pgda_illumination"],
    }
    found = pgda.illumination_files(root, *box)
    if found is None:
        why = "no PGDA illumination map covers the whole ellipse"
        return {
            **base,
            "available": False,
            "reason": why,
            "sun": None,
            "earth": None,
            "permanent_shadow": None,
        }
    stem, files = found
    out: dict[str, Any] = {**base, "available": True, "reason": None, "product": stem}
    res = 0.0
    for key, name in (("sun", "average Sun visibility"), ("earth", "average Earth visibility")):
        if key not in files:
            out[key] = None
            continue
        v, res, wkt = pgda.sample_points(files[key], gx, gy, "bilinear")
        if not pgda.crs_matches_app(wkt):
            out[key] = None
            continue
        p = dispersion.weighted_percentiles(v)
        out[key] = {
            "name": name,
            "unit": "fraction of time",
            "p10": _published_pct(p, 0, "1", PGDA_ILLUM_URL),
            "p50": _published_pct(p, 1, "1", PGDA_ILLUM_URL),
            "p90": _published_pct(p, 2, "1", PGDA_ILLUM_URL),
            "n_points": int(np.count_nonzero(np.isfinite(v))),
        }
    out["resolution_m"] = res
    if "shadow" in files:
        v, _, wkt = pgda.sample_points(files["shadow"], gx, gy, "nearest")
        n = int(np.count_nonzero(np.isfinite(v)))
        k = int(np.count_nonzero(v[np.isfinite(v)] > 0.5))
        out["permanent_shadow"] = {"share": _share(k, n), "n_points": n}
    else:
        out["permanent_shadow"] = None
    return out


def run(
    site_id: str,
    lat_deg: float,
    lon_deg: float,
    ellipse: dict[str, float],
    lander: dict[str, float],
    n: int,
    *,
    data_dir: Path,
    app_dems: list[Path],
    seed: int = 0,
) -> dict[str, Any]:
    t0 = datetime.now(UTC)
    a, b, psi = ellipse["semi_major_m"], ellipse["semi_minor_m"], ellipse["azimuth_deg"]
    frame = local_frame(lon_deg, lat_deg)
    pts = dispersion.sample_ellipse(a, b, psi, n, seed)
    ring_e, ring_n = dispersion.outline(a, b, psi)
    e_min, e_max = float(ring_e.min()), float(ring_e.max())
    n_min, n_max = float(ring_n.min()), float(ring_n.max())

    # Heat-map grid in local east/north, at most 64 x 64, never finer than the terrain.
    root = data_dir / "external"
    ext = max(e_max - e_min, n_max - n_min)
    bx, by = frame.local_to_grid(
        np.array([e_min, e_min, e_max, e_max]), np.array([n_min, n_max, n_min, n_max])
    )
    x0, x1 = float(bx.min()), float(bx.max())
    y0, y1 = float(by.min()), float(by.max())
    # Heat-map cells may reach a little past the box; the pad covers them.
    cell0 = ext / MAX_HEATMAP
    x0, x1, y0, y1 = x0 - cell0, x1 + cell0, y0 - cell0, y1 + cell0

    fell_back = False
    reason: str | None = None
    src = _pgda_slope(root, x0, y0, x1, y1)
    app_product = ""
    if src is None:
        got = _app_slope(app_dems, x0, y0, x1, y1)
        if got is None:
            raise NoTerrain(
                "no elevation model covers the whole ellipse: neither a PGDA 5 m tile nor "
                "the app's DEM"
            )
        src, app_product = got
        fell_back = True
        tiles = pgda.lola_tiles(root)
        reason = (
            "no PGDA 5 m tile covers the whole ellipse" if tiles else "no PGDA 5 m tile is on disk"
        )

    g = src.grid
    spacing = g.spacing_m
    gx, gy = frame.local_to_grid(pts.east_m, pts.north_m)
    slope = hazards.lookup_nearest(g.slope_deg, src.origin_x_m, src.origin_y_m, spacing, gx, gy)
    sigma = hazards.lookup_nearest(g.sigma_deg, src.origin_x_m, src.origin_y_m, spacing, gx, gy)
    ok = np.isfinite(slope)
    sigma_med = (
        float(np.median(sigma[ok & np.isfinite(sigma)]))
        if (ok & np.isfinite(sigma)).any()
        else float("nan")
    )
    why_no_pm = "the terrain model gives no elevation uncertainty here"
    pct = dispersion.weighted_percentiles(slope, pts.weights)

    tip = hazards.tip_over_deg(lander["footprint_diameter_m"], lander["cg_height_m"])
    limit = lander["slope_limit_deg"]
    k_lim, n_s = hazards.exceedance(slope, limit)
    k_tip, _ = hazards.exceedance(slope, tip)
    k_lim_hi, n_hi = hazards.exceedance(slope + sigma, limit)
    k_tip_hi, _ = hazards.exceedance(slope + sigma, tip)

    # Cross-check against the product's own slope raster, where there is one.
    cross: dict[str, Any] | None = None
    if src.product_slope is not None:
        pv, _, _ = pgda.sample_points(src.product_slope[0], gx, gy, "nearest")
        pp = dispersion.weighted_percentiles(pv, pts.weights)
        if pp is not None:
            cross = {
                "what": "the product's own slope raster, nearest cell, 10th/50th/90th percentile",
                "p10_deg": round(pp[0], 2),
                "p50_deg": round(pp[1], 2),
                "p90_deg": round(pp[2], 2),
            }

    # Heat-map.
    cell = max(spacing, ext / MAX_HEATMAP)
    nx = max(1, min(MAX_HEATMAP, int(math.ceil((e_max - e_min) / cell))))
    ny = max(1, min(MAX_HEATMAP, int(math.ceil((n_max - n_min) / cell))))
    ee = e_min + (np.arange(nx) + 0.5) * cell
    nn = n_min + (np.arange(ny) + 0.5) * cell
    EE, NN = np.meshgrid(ee, nn)
    hx, hy = frame.local_to_grid(EE.ravel(), NN.ravel())
    hv = hazards.lookup_nearest(g.slope_deg, src.origin_x_m, src.origin_y_m, spacing, hx, hy)
    heat = [
        [None if not math.isfinite(v) else round(float(v), 1) for v in row]
        for row in hv.reshape(ny, nx)
    ]

    illum = _illumination(root, gx, gy, (x0, y0, x1, y1))

    slope_source: dict[str, Any] = {
        "name": src.name,
        "label": src.label,
        "pgda_5m": not fell_back,
        "fell_back": fell_back,
        "fallback_reason": reason,
        "tile": src.tile,
        "method": "Horn 3x3 weighted gradient on the elevation posts",
        "spacing_m": spacing,
        "baseline_m": g.baseline_m,
        "baseline_note": "The slope is taken over this distance. Slopes from different "
        "baselines are not comparable and are never combined.",
        "vertical_error_m": None
        if not math.isfinite(src.vertical_error_m)
        else src.vertical_error_m,
        "vertical_error_note": "median of the product's per-post uncertainty"
        if not fell_back
        else "the product's stated vertical error",
        "crs": src.crs_wkt or "south polar stereographic, R = 1737.4 km, scale true at the pole",
        "source": SOURCES["pgda_lola_5m" if not fell_back else "app_dem"],
        "cross_check": cross,
    }

    sources = [SOURCES["pgda_illumination"], SOURCES["app_dem" if fell_back else "pgda_lola_5m"]]
    n_ok = int(ok.sum())
    dem_res = spacing
    meta = {
        "computed_at": t0.isoformat().replace("+00:00", "Z"),
        "resolution": {
            "azimuth_deg": 0.0,
            "azimuth_count": 0,
            "time_step_s": 0,
            "max_range_m": ext / 2.0,
            "dem_product": src.name,
            "dem_resolution_m": dem_res,
            "ephemeris": "none: no Sun position is used",
            "frame": "local east/north at the site; south polar stereographic grid",
        },
        "uncertainty": {
            "kind": "terrain",
            "dem_vertical_error_m": src.vertical_error_m
            if math.isfinite(src.vertical_error_m)
            else 0.0,
            "dem_resolution_m": dem_res,
            "coverage": n_ok / n,
            "horizon_el_deg": 0.0,
            "edge_timing_s": None,
            "grazing": False,
            "penumbra_sun_deg": 0.0,
            "penumbra_earth_deg": 0.0,
            "terrain_modelled": True,
            "notes": [
                "Dispersion: the horizon, penumbra and edge-timing fields do not apply to a "
                "slope result and are zero or null.",
                "The shares carry a sampling interval for the number of points drawn; they do "
                "not include the slope's own error. The sensitivity shares add one sigma to "
                "every slope.",
                "Slope uncertainty assumes independent elevation errors, which is the larger "
                "figure.",
            ],
        },
        "engine_version": ENGINE_VERSION,
        "cache": "bypass",
        "compute_ms": round((datetime.now(UTC) - t0).total_seconds() * 1000.0, 1),
    }
    return {
        "site_id": site_id,
        "inputs": {
            "ellipse": {
                **{
                    k: {"value": v, "unit": u, "provenance": "entered"}
                    for k, v, u in (
                        ("semi_major_m", a, "m"),
                        ("semi_minor_m", b, "m"),
                        ("azimuth_deg", psi, "deg"),
                    )
                },
                "note": "3-sigma half-axes; azimuth is the major axis's bearing from true north",
            },
            "lander": {
                k: {"value": lander[k], "unit": u, "provenance": "entered"}
                for k, u in (
                    ("footprint_diameter_m", "m"),
                    ("cg_height_m", "m"),
                    ("slope_limit_deg", "deg"),
                )
            },
            "samples": n,
            "seed": seed,
        },
        "slope_source": slope_source,
        "slope": {
            "unit": "deg",
            "baseline_m": g.baseline_m,
            "n_points": n,
            "n_with_slope": n_ok,
            "p10": _pct_quantity(pct, 0, "deg", sigma_med, why_no_pm),
            "p50": _pct_quantity(pct, 1, "deg", sigma_med, why_no_pm),
            "p90": _pct_quantity(pct, 2, "deg", sigma_med, why_no_pm),
            "margin_note": "The ± is one sigma from the elevation error over the baseline.",
        },
        "tip_over": {
            "angle": q(
                Quantity(
                    tip,
                    "deg",
                    "computed",
                    no_margin_reason="the entered footprint and centre-of-gravity height "
                    "carry no margin",
                )
            ),
            "formula": "atan(D / (2 h_CG)), static",
        },
        "shares": {
            "above_slope_limit": {
                "limit_deg": limit,
                "baseline_m": g.baseline_m,
                "share": _share(k_lim, n_s),
                "if_slopes_one_sigma_higher": _share(k_lim_hi, n_hi),
            },
            "above_tip_over": {
                "limit_deg": tip,
                "baseline_m": g.baseline_m,
                "share": _share(k_tip, n_s),
                "if_slopes_one_sigma_higher": _share(k_tip_hi, n_hi),
            },
            "basis": "Share of the landing points drawn from the ellipse's distribution, "
            "with the exact 95 % interval for that many points.",
        },
        "illumination": illum,
        "heatmap": {
            "frame": "local east/north metres from the ellipse centre",
            "east_min_m": round(e_min, 2),
            "north_min_m": round(n_min, 2),
            "cell_m": round(cell, 3),
            "nx": nx,
            "ny": ny,
            "slope_deg": heat,
            "row_0": "southernmost row",
            "baseline_m": g.baseline_m,
            "outline": {
                "east_m": [round(float(v), 2) for v in ring_e],
                "north_m": [round(float(v), 2) for v in ring_n],
            },
            "points": {
                "east_m": [round(float(v), 1) for v in pts.east_m],
                "north_m": [round(float(v), 1) for v in pts.north_m],
                "slope_deg": [None if not math.isfinite(v) else round(float(v), 2) for v in slope],
            },
        },
        "sources": sources,
        "not_modelled": NOT_MODELLED,
        "meta": meta,
    }


async def dispersion_at(
    session: AsyncSession,
    site_id: str,
    ellipse: dict[str, float],
    lander: dict[str, float],
    n: int,
    seed: int = 0,
) -> dict[str, Any]:
    site = await site_service.require_site(session, site_id)
    s = get_settings()
    return run(
        site_id,
        site.lat_deg,
        site.lon_deg,
        ellipse,
        lander,
        n,
        data_dir=s.data_dir,
        app_dems=[s.fine_dem_path(site_id), s.regional_dem_path],
        seed=seed,
    )
