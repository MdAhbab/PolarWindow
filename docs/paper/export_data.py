"""Export every number the paper and its figures use, from the running engine.

Run from ``backend/`` against a seeded database and loaded kernels:

    uv run python ../docs/paper/export_data.py

Writes ``docs/paper/data/*.csv`` (for the figure prompts) and
``docs/paper/*.dat`` (for pgfplots) from the same arrays, plus
``docs/paper/data/facts.json`` with the scalars quoted in the text. Nothing is
typed in: each value is read from the services the API itself calls. Read-only.
"""

from __future__ import annotations

import asyncio
import csv
import json
import math
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np

from app.config import ENGINE_VERSION, get_settings
from app.core import metrics, spice, visibility
from app.core.horizon import (
    RESOLVED_NOISE_DEG,
    curvature_drop_m,
    ray_distances,
    spherical_horizon_deg,
)
from app.core.projections import geographic_to_polar
from app.data.lola import DemTile, make_samplers
from app.db.repositories.sites import MaskRepository, SiteRepository
from app.db.session import dispose_engine, session_scope
from app.services import site_service
from app.workers.precompute import build_site_mask

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FOCUS = "connecting-ridge"
CONTRAST = ("connecting-ridge", "malapert-massif", "faustini-rim")
H = 3600.0


def write_csv(name: str, header: list[str], rows: list[list[Any]]) -> None:
    with (DATA / name).open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def write_dat(name: str, header: list[str], rows: list[list[Any]]) -> None:
    """Whitespace-separated, one header row: what pgfplots' \\addplot table reads."""
    with (HERE / name).open("w") as fh:
        fh.write(" ".join(header) + "\n")
        for r in rows:
            fh.write(" ".join(str(v) for v in r) + "\n")


def r6(x: float | None) -> float | None:
    return None if x is None else round(float(x), 6)


async def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    s = get_settings()
    spice.load(s.kernel_dir)
    start = s.reference_window_start
    end = start + timedelta(days=s.reference_window_days)
    facts: dict[str, Any] = {
        "engine_version": ENGINE_VERSION,
        "kernels_loaded_ktotal": spice.state().count,
        "reference_window_requested": [start.isoformat(), end.isoformat()],
        "step_s": s.default_step_s,
    }

    async with session_scope() as session:
        sites, total = await SiteRepository(session).list_sites(limit=500, kind="candidate")
        facts["candidate_sites"] = total
        rows: list[list[Any]] = []
        payloads: dict[str, dict[str, Any]] = {}
        windows: dict[str, dict[str, Any]] = {}
        computed: dict[str, site_service.ComputedWindow] = {}
        for site in sites:
            cw = await site_service.compute(session, site.id, start, end, s.default_step_s)
            p = site_service.metrics_payload(cw)
            payloads[site.id] = p
            windows[site.id] = site_service.windows_payload(cw)
            computed[site.id] = cw
            u = p["meta"]["uncertainty"]

            def hrs(v: float | None) -> float | None:
                return None if v is None else round(v / H, 4)

            rows.append(
                [
                    site.id,
                    site.code,
                    site.name,
                    round(site.lat_deg, 5),
                    round(site.lon_deg, 5),
                    site.elev_m,
                    round(site.offset_from_anchor_km, 3),
                    hrs(p["sunlit_s"]),
                    hrs(p["sunlit_tolerance_s"]),
                    r6(p["sun_fraction_up"]),
                    hrs(p["earth_contact_s"]),
                    hrs(p["earth_contact_tolerance_s"]),
                    r6(p["earth_fraction_up"]),
                    hrs(p["longest_dark_s"]),
                    hrs(p["longest_dark_tolerance_s"]),
                    int(p["longest_dark_open"]),
                    int(p["longest_dark_grazing"]),
                    hrs(p["longest_blackout_s"]),
                    hrs(p["longest_blackout_tolerance_s"]),
                    int(p["longest_blackout_open"]),
                    int(p["longest_blackout_grazing"]),
                    hrs(p["worst_compound_s"]),
                    p["meta"]["resolution"]["dem_product"],
                    u["dem_vertical_error_m"],
                    u["coverage"],
                    u["edge_timing_s"],
                    int(u["grazing"]),
                ]
            )
        rows.sort(key=lambda r: -r[7])
        write_csv(
            "sites_four_numbers.csv",
            [
                "site_id",
                "code",
                "name",
                "lat_deg",
                "lon_deg",
                "elev_m",
                "offset_from_anchor_km",
                "sunlit_h",
                "sunlit_tol_h",
                "sun_fraction",
                "earth_contact_h",
                "earth_contact_tol_h",
                "earth_fraction",
                "longest_dark_h",
                "longest_dark_tol_h",
                "longest_dark_open",
                "longest_dark_grazing",
                "longest_blackout_h",
                "longest_blackout_tol_h",
                "longest_blackout_open",
                "longest_blackout_grazing",
                "worst_compound_h",
                "dem_product",
                "dem_vertical_error_m",
                "coverage",
                "edge_timing_s",
                "grazing",
            ],
            rows,
        )
        p0 = payloads[FOCUS]
        facts["window_computed"] = [p0["start"], p0["end"]]
        facts["window_hours"] = round(
            (computed[FOCUS].result.end - computed[FOCUS].result.start).total_seconds() / H, 4
        )

        # Figure (c): three contrasting sites, value and bound in long form.
        long_rows: list[list[Any]] = []
        for sid in CONTRAST:
            p = payloads[sid]
            for metric, tol, open_key in (
                ("sunlit_s", "sunlit_tolerance_s", None),
                ("earth_contact_s", "earth_contact_tolerance_s", None),
                ("longest_dark_s", "longest_dark_tolerance_s", "longest_dark_open"),
                ("longest_blackout_s", "longest_blackout_tolerance_s", "longest_blackout_open"),
            ):
                is_bound = bool(open_key and p[open_key])
                t = p[tol]
                long_rows.append(
                    [
                        sid,
                        metric.removesuffix("_s"),
                        round(p[metric] / H, 4),
                        None if t is None else round(t / H, 4),
                        "lower_bound" if is_bound else ("grazing" if t is None else "measured"),
                    ]
                )
        write_csv(
            "four_numbers_three_sites.csv",
            ["site_id", "metric", "value_h", "tolerance_h", "kind"],
            long_rows,
        )

        # The focus site: mask, tracks, crossings.
        site = await SiteRepository(session).get(FOCUS)
        rec = await MaskRepository(session).get(FOCUS, ENGINE_VERSION)
    await dispose_engine()
    assert site is not None and rec is not None

    mask = rec.mask
    az = mask.azimuths()
    write_csv(
        "horizon_connecting_ridge.csv",
        ["az_deg", "el_deg", "range_m", "tol_deg"],
        [
            [round(float(a), 2), round(float(e), 5), round(float(r), 1), round(float(t), 5)]
            for a, e, r, t in zip(az, mask.el_deg, mask.range_m, mask.tol_deg, strict=True)
        ],
    )

    # Rebuild the mask from the DEM on disk, as the golden test does, to get
    # which tier set each bearing (not persisted) and the drift from storage.
    regional = DemTile.load(s.regional_dem_path)
    fine = DemTile.load(s.fine_dem_path(FOCUS))
    rebuilt, product, res_m, err_m = build_site_mask(site.lat_deg, site.lon_deg, fine, regional)
    sig = rebuilt.blocker_sigma_m
    assert sig is not None
    facts["focus"] = {
        "id": FOCUS,
        "lat_deg": site.lat_deg,
        "lon_deg": site.lon_deg,
        "elev_m": site.elev_m,
        "anchor": [site.anchor_lat_deg, site.anchor_lon_deg],
        "offset_from_anchor_km": site.offset_from_anchor_km,
        "dem_product_stored": rec.dem_product,
        "dem_vertical_error_stored_m": rec.dem_vertical_error_m,
        "mask_max_el_deg": round(mask.max_el_deg, 4),
        "mask_max_el_bearing_deg": mask.max_el_bearing_deg,
        "mask_mean_el_deg": round(float(np.mean(mask.el_deg)), 4),
        "mask_min_el_deg": round(float(np.min(mask.el_deg)), 4),
        "mask_range_median_m": round(float(np.median(mask.range_m)), 1),
        "mask_range_min_m": round(float(np.min(mask.range_m)), 1),
        "mask_range_max_m": round(float(np.max(mask.range_m)), 1),
        "mask_tol_min_deg": round(float(np.min(mask.tol_deg)), 5),
        "mask_tol_max_deg": round(float(np.max(mask.tol_deg)), 5),
        "mask_tol_mean_deg": round(float(np.mean(mask.tol_deg)), 5),
        "coverage": mask.coverage,
        "bearings_set_by_80m_tier": int(np.count_nonzero(sig > fine.vertical_error_m + 1e-6)),
        "bearings_total": int(sig.size),
        "rebuilt_vs_stored_max_abs_el_diff_deg": float(
            np.max(np.abs(rebuilt.el_deg.astype(float) - mask.el_deg.astype(float)))
        ),
        "rebuilt_product": product,
        "rebuilt_vertical_error_m": err_m,
        "spherical_dip_deg_at_elev": round(spherical_horizon_deg(site.elev_m or 0.0), 4),
    }

    cw = computed[FOCUS]
    sun, earth = cw.result.sun, cw.result.earth
    t_h = sun.t_s / H
    track_rows = [
        [
            round(float(t_h[i]), 4),
            round(float(sun.az_deg[i]), 4),
            round(float(sun.el_deg[i]), 4),
            round(float(sun.mask_el_deg[i]), 4),
            round(float(sun.margin_deg[i]), 4),
            int(sun.state[i]),
            round(float(earth.az_deg[i]), 4),
            round(float(earth.el_deg[i]), 4),
            round(float(earth.mask_el_deg[i]), 4),
            round(float(earth.margin_deg[i]), 4),
            int(earth.state[i]),
        ]
        for i in range(t_h.size)
    ]
    header = [
        "t_h",
        "sun_az_deg",
        "sun_el_deg",
        "sun_skyline_deg",
        "sun_margin_deg",
        "sun_state",
        "earth_az_deg",
        "earth_el_deg",
        "earth_skyline_deg",
        "earth_margin_deg",
        "earth_state",
    ]
    write_csv("tracks_connecting_ridge.csv", header, track_rows)
    write_dat("sun_vs_skyline.dat", header, track_rows)

    for name, tr in (("sun", sun), ("earth", earth)):
        n = tr.state.size
        facts["focus"][f"{name}_el_min_deg"] = round(float(np.min(tr.el_deg)), 4)
        facts["focus"][f"{name}_el_max_deg"] = round(float(np.max(tr.el_deg)), 4)
        facts["focus"][f"{name}_samples"] = int(n)
        facts["focus"][f"{name}_state_counts"] = {
            "dark": int(np.sum(tr.state == visibility.DARK)),
            "penumbral": int(np.sum(tr.state == visibility.PENUMBRAL)),
            "lit": int(np.sum(tr.state == visibility.LIT)),
        }
        facts["focus"][f"{name}_angular_radius_deg"] = {
            "min": round(float(np.min(tr.angular_radius_deg)), 4),
            "mean": round(float(np.mean(tr.angular_radius_deg)), 4),
            "max": round(float(np.max(tr.angular_radius_deg)), 4),
        }
        facts["focus"][f"{name}_margin_positive_fraction"] = round(
            float(np.mean(tr.margin_deg > 0.0)), 4
        )

    # Figure (e): the state thresholds and how often each state occurs.
    write_csv(
        "states_connecting_ridge.csv",
        [
            "body",
            "angular_radius_min_deg",
            "angular_radius_mean_deg",
            "angular_radius_max_deg",
            "samples",
            "lit",
            "penumbral",
            "dark",
        ],
        [
            [
                name,
                facts["focus"][f"{name}_angular_radius_deg"]["min"],
                facts["focus"][f"{name}_angular_radius_deg"]["mean"],
                facts["focus"][f"{name}_angular_radius_deg"]["max"],
                facts["focus"][f"{name}_samples"],
                facts["focus"][f"{name}_state_counts"]["lit"],
                facts["focus"][f"{name}_state_counts"]["penumbral"],
                facts["focus"][f"{name}_state_counts"]["dark"],
            ]
            for name in ("sun", "earth")
        ],
    )

    # Crossings: each arc edge that is a real crossing, with where it happens.
    cross_rows: list[list[Any]] = []
    for name, tr in (("sun", sun), ("earth", earth)):
        unwrapped = np.degrees(np.unwrap(np.radians(tr.az_deg)))
        for i, arc in enumerate(tr.arcs):
            ts, te = tr.arc_edge_tolerance_s[i]
            for edge_t, tol, which in ((arc.start, ts, "start"), (arc.end, te, "end")):
                if tol is None:
                    continue
                a = float(np.mod(np.interp(edge_t, tr.t_s, unwrapped), 360.0))
                e = float(np.interp(edge_t, tr.t_s, tr.el_deg))
                sky_tol = float(
                    visibility.interp_horizon(
                        mask.tol_deg.astype(np.float64), np.array([a], dtype=np.float64)
                    )[0]
                )
                cross_rows.append(
                    [
                        name,
                        i,
                        which,
                        "rise" if (which == "start") == arc.value else "set",
                        round(edge_t / H, 4),
                        round(tol / H, 4),
                        round(a, 3),
                        round(e, 4),
                        round(sky_tol, 5),
                        int(tr.arc_grazing[i]),
                    ]
                )
    # An interior crossing ends one arc and starts the next; keep it once.
    seen: set[tuple[str, float]] = set()
    unique: list[list[Any]] = []
    for r in cross_rows:
        key = (r[0], r[4])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    write_csv(
        "crossings_connecting_ridge.csv",
        [
            "body",
            "arc_index",
            "edge",
            "direction",
            "t_h",
            "timing_tol_h",
            "az_deg",
            "el_deg",
            "skyline_tol_deg",
            "arc_grazing",
        ],
        unique,
    )

    arc_rows: list[list[Any]] = []
    for name in ("sun", "earth"):
        for a in windows[FOCUS][name]["arcs"]:
            arc_rows.append(
                [
                    name,
                    int(a["up"]),
                    a["start"],
                    a["end"],
                    round(a["duration_s"] / H, 4),
                    round(a["tolerance_s"] / H, 4),
                    None
                    if a["start_tolerance_s"] is None
                    else round(a["start_tolerance_s"] / H, 4),
                    None if a["end_tolerance_s"] is None else round(a["end_tolerance_s"] / H, 4),
                    int(a["grazing"]),
                    int(a["open_start"]),
                    int(a["open_end"]),
                    a["blocked_by_bearing_deg"],
                    a["blocked_by_el_deg"],
                ]
            )
    write_csv(
        "arcs_connecting_ridge.csv",
        [
            "body",
            "up",
            "start_utc",
            "end_utc",
            "duration_h",
            "tolerance_h",
            "start_tol_h",
            "end_tol_h",
            "grazing",
            "open_start",
            "open_end",
            "blocked_by_bearing_deg",
            "blocked_by_el_deg",
        ],
        arc_rows,
    )

    # Figure (a): the real terrain profile along two bearings of the focus site.
    sampler, sigma = make_samplers(site.lat_deg, site.lon_deg, fine, regional)
    d = ray_distances(s.max_range_m, 5.0, min_range_m=2.0 * fine.scale_m)
    drop = curvature_drop_m(d)
    h0 = float(sampler(np.zeros(1), np.zeros(1))[0])
    k_hi = int(np.argmax(mask.el_deg))
    k_lo = int(np.argmin(mask.el_deg))
    prof_rows: list[list[Any]] = []
    for label, k in (("highest_skyline", k_hi), ("lowest_skyline", k_lo)):
        b = float(az[k])
        xs, ys = np.sin(np.radians(b)) * d, np.cos(np.radians(b)) * d
        hh = sampler(xs, ys)
        sg = sigma(xs, ys)
        theta = np.degrees(np.arctan2(hh - h0 - drop, d))
        floor = np.degrees(np.arctan2(sg, d))
        elig = (theta > floor) | (floor < RESOLVED_NOISE_DEG)
        for j in range(d.size):
            prof_rows.append(
                [
                    label,
                    round(b, 2),
                    round(float(d[j]), 1),
                    round(float(hh[j] - h0), 2),
                    round(float(drop[j]), 3),
                    round(float(theta[j]), 5),
                    round(float(floor[j]), 5),
                    int(elig[j]),
                    int(j == int(np.argmin(np.abs(d - mask.range_m[k])))),
                ]
            )
        facts["focus"][f"profile_{label}"] = {
            "bearing_deg": b,
            "skyline_el_deg": round(float(mask.el_deg[k]), 4),
            "set_at_range_m": round(float(mask.range_m[k]), 1),
        }
    write_csv(
        "raymarch_profile_connecting_ridge.csv",
        [
            "bearing",
            "bearing_deg",
            "d_m",
            "h_minus_site_m",
            "curvature_drop_m",
            "theta_deg",
            "noise_floor_deg",
            "eligible",
            "sets_skyline",
        ],
        prof_rows,
    )
    facts["ray_samples_per_bearing"] = int(d.size)
    facts["curvature_drop_m"] = {
        "at_20km": round(float(curvature_drop_m(np.array([20_000.0]))[0]), 2),
        "at_50km": round(float(curvature_drop_m(np.array([50_000.0]))[0]), 2),
    }

    # The near-field noise floor, analytic in r, for sigma = 2 m and 4 m.
    nf_rows: list[list[Any]] = []
    for r in np.unique(np.concatenate([np.geomspace(20.0, 5000.0, 160), [40.0]])):
        nf_rows.append(
            [
                round(float(r), 3),
                round(math.degrees(math.atan2(2.0, r)), 5),
                round(math.degrees(math.atan2(4.0, r)), 5),
            ]
        )
    write_csv("noise_floor.csv", ["range_m", "floor_2m_deg", "floor_4m_deg"], nf_rows)
    write_dat("noise_floor.dat", ["range_m", "floor2", "floor4"], nf_rows)
    facts["noise_floor"] = {
        "floor_2m_at_40m_deg": round(math.degrees(math.atan2(2.0, 40.0)), 4),
        "resolved_threshold_deg": RESOLVED_NOISE_DEG,
        "resolved_range_2m_m": round(2.0 / math.tan(math.radians(RESOLVED_NOISE_DEG)), 1),
        "resolved_range_4m_m": round(4.0 / math.tan(math.radians(RESOLVED_NOISE_DEG)), 1),
    }

    # Crater floors: the IAU-anchored centre of each named crater, sampled on the 80 m model.
    anchors = {
        "shackleton": (-89.66, 129.20),
        "haworth": (-87.45, 355.0),
        "shoemaker": (-88.10, 44.90),
    }
    floors: dict[str, float] = {}
    for name, (lat, lon) in anchors.items():
        x, y = geographic_to_polar(np.array([lon]), np.array([lat]))
        floors[name] = round(float(regional.sample_grid(x, y)[0]), 1)
    facts["crater_anchor_height_80m_m"] = floors

    # Tolerance and censoring summary across all fifteen sites.
    facts["sites_longest_dark_open"] = [k for k, p in payloads.items() if p["longest_dark_open"]]
    facts["sites_longest_blackout_open"] = [
        k for k, p in payloads.items() if p["longest_blackout_open"]
    ]
    facts["sites_any_grazing"] = [
        k for k, p in payloads.items() if p["meta"]["uncertainty"]["grazing"]
    ]
    pen = []
    for sid, cwx in computed.items():
        for tr in (cwx.result.sun, cwx.result.earth):
            pen.append(float(np.mean(tr.state == visibility.PENUMBRAL)))
    facts["penumbral_sample_fraction_all_sites"] = {
        "min": round(min(pen), 4),
        "median": round(float(np.median(pen)), 4),
        "max": round(max(pen), 4),
    }

    # The censored-ranking example the text quotes, through the ranking /compare runs.
    example = ("connecting-ridge", "de-gerlache-rim", "malapert-massif")
    ranked = metrics.rank_with_uncertainty(
        [
            metrics.RankInput(
                id=sid,
                value=payloads[sid]["longest_dark_s"],
                uncertainty=(
                    math.inf
                    if payloads[sid]["longest_dark_tolerance_s"] is None
                    else payloads[sid]["longest_dark_tolerance_s"]
                ),
                censored=payloads[sid]["longest_dark_open"],
            )
            for sid in example
        ],
        higher_is_better=False,
    )
    facts["ranking_longest_dark_example"] = {
        r.id: {"rank": r.rank, "rank_range": [r.rank_min, r.rank_max], "censored": r.censored}
        for r in ranked
    }

    (DATA / "facts.json").write_text(json.dumps(facts, indent=2, default=str) + "\n")
    print(json.dumps(facts, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
