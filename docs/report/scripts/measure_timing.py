"""Time the precompute path and the request path, and probe one sensitivity.

Run from ``backend/`` with a seeded database, loaded kernels and, for the HTTP
rows, the API listening on :8000:

    uv run python ../docs/report/scripts/measure_timing.py

Writes ``docs/report/scripts/data/timing.csv`` and ``docs/report/scripts/data/sensitivity.json``.
Every row states N, the median and the nearest-rank 95th percentile, in
milliseconds. Read-only against the database;
the HTTP rows populate the Redis cache under fresh keys, as any request would.
"""

from __future__ import annotations

import asyncio
import csv
import json
import math
import os
import platform
import statistics
import subprocess
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import orjson
import zstandard as zstd

from app.config import ENGINE_VERSION, get_settings
from app.core import horizon, metrics, spice, timeline, visibility
from app.core.spice import R_EARTH_M, R_MOON_M, R_SUN_M
from app.data.lola import DemTile
from app.db.repositories.sites import MaskRepository, SiteRepository
from app.db.session import dispose_engine, session_scope
from app.services import geometry_service, site_service
from app.workers.precompute import build_site_mask

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FOCUS = "connecting-ridge"
API = "http://127.0.0.1:8000/api/v1"
# First fresh window, in days after the reference start. A later run needs a new base, because
# Redis keeps the windows an earlier run asked for (its cache survives a restart).
BASE_DAYS = int(os.environ.get("TIMING_BASE_DAYS", "2600"))


def p95(xs: list[float]) -> float:
    s = sorted(xs)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def timed(fn: Callable[[], Any], n: int) -> list[float]:
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000.0)
    return out


def row(stage: str, path: str, xs: list[float], note: str = "") -> list[Any]:
    return [
        stage,
        path,
        len(xs),
        round(statistics.median(xs), 3),
        round(p95(xs), 3),
        round(min(xs), 3),
        round(max(xs), 3),
        note,
    ]


async def main() -> None:
    s = get_settings()
    spice.load(s.kernel_dir)
    start = s.reference_window_start
    end = start + timedelta(days=s.reference_window_days)
    rows: list[list[Any]] = []

    async with session_scope() as session:
        sites, _ = await SiteRepository(session).list_sites(limit=500, kind="candidate")
        site = await SiteRepository(session).get(FOCUS)
        rec = await MaskRepository(session).get(FOCUS, ENGINE_VERSION)
    await dispose_engine()
    assert site is not None and rec is not None

    # --- precompute path (worker) ------------------------------------------
    rows.append(
        row(
            "regional DEM load (80 m, whole product)",
            "precompute",
            timed(lambda: DemTile.load(s.regional_dem_path), 3),
        )
    )
    regional = DemTile.load(s.regional_dem_path)
    fine_loads: list[float] = []
    builds: list[float] = []
    per_site: dict[str, float] = {}
    for x in sites:
        fp = s.fine_dem_path(x.id)
        fine_loads += timed(lambda fp=fp: DemTile.load(fp), 3)
        fine = DemTile.load(fp)
        b = timed(lambda x=x, fine=fine: build_site_mask(x.lat_deg, x.lon_deg, fine, regional), 5)
        builds += b
        per_site[x.id] = statistics.median(b)
    rows.append(
        row(
            "fine DEM window load (20 m, one site)",
            "precompute",
            fine_loads,
            f"{len(sites)} sites x 3",
        )
    )
    rows.append(
        row(
            "horizon mask ray-march (1,440 bearings)",
            "precompute",
            builds,
            f"{len(sites)} sites x 5",
        )
    )

    # --- request path, in process (one site, reference window, 900 s) -------
    qs, qe, step = geometry_service.validate_window(start, end, s.default_step_s)
    iso = (qs.isoformat().replace("+00:00", "Z"), qe.isoformat().replace("+00:00", "Z"))
    n = 50
    rows.append(
        row(
            "window validation and quantisation",
            "request",
            timed(lambda: geometry_service.validate_window(start, end, 900), n),
        )
    )
    rows.append(
        row(
            "ephemeris: two bodies, hourly knots + spline",
            "request",
            timed(lambda: spice.ephemeris(iso[0], iso[1], float(step)), n),
        )
    )

    def direct() -> None:
        ets = spice.et_range(spice.utc_to_et(iso[0]), spice.utc_to_et(iso[1]), float(step))
        spice.body_vectors("sun", ets, knot_s=None)
        spice.body_vectors("earth", ets, knot_s=None)

    rows.append(
        row(
            "ephemeris: two bodies, spkpos at every epoch",
            "request (not used)",
            timed(direct, n),
            "comparison only",
        )
    )
    eph = spice.ephemeris(iso[0], iso[1], float(step))
    t_s = eph.ets - eph.ets[0]
    basis = visibility.enu_basis(site.lat_deg, site.lon_deg)
    pos = visibility.site_position(site.lat_deg, site.lon_deg, R_MOON_M + (site.elev_m or 0.0))
    mask = rec.mask
    rows.append(
        row(
            "Sun track: look angles, mask lookup, arcs, bisection",
            "request",
            timed(lambda: timeline.build_track("sun", t_s, eph.sun, mask, basis, pos, R_SUN_M), n),
        )
    )
    rows.append(
        row(
            "Earth track: look angles, mask lookup, arcs, bisection",
            "request",
            timed(
                lambda: timeline.build_track("earth", t_s, eph.earth, mask, basis, pos, R_EARTH_M),
                n,
            ),
        )
    )
    sun = timeline.build_track("sun", t_s, eph.sun, mask, basis, pos, R_SUN_M)
    earth = timeline.build_track("earth", t_s, eph.earth, mask, basis, pos, R_EARTH_M)
    rows.append(
        row(
            "four numbers, compound events, autonomy",
            "request",
            timed(
                lambda: metrics.autonomy(timeline.site_metrics_from_tracks(FOCUS, sun, earth)), n
            ),
        )
    )
    result = await geometry_service.compute_window_metrics(
        site_id=FOCUS,
        lat_deg=site.lat_deg,
        lon_deg=site.lon_deg,
        elev_m=site.elev_m,
        mask=mask,
        start=start,
        end=end,
        step_s=900,
    )
    cw = site_service.ComputedWindow(site=site, mask_record=rec, result=result)
    rows.append(
        row(
            "/metrics payload shaping",
            "request",
            timed(lambda: site_service.metrics_payload(cw), n),
        )
    )
    payload = site_service.metrics_payload(cw)
    cz, dz = zstd.ZstdCompressor(level=3), zstd.ZstdDecompressor()
    blob = cz.compress(orjson.dumps(payload))
    rows.append(
        row(
            "cache encode (orjson + zstd)",
            "request",
            timed(lambda: cz.compress(orjson.dumps(payload)), n),
        )
    )
    rows.append(
        row(
            "cache decode (zstd + orjson)",
            "request",
            timed(lambda: orjson.loads(dz.decompress(blob)), n),
        )
    )

    # --- request path, over HTTP --------------------------------------------
    http: dict[str, Any] = {}
    try:
        with httpx.Client(timeout=30.0) as c:
            c.get(f"{API}/sites/{FOCUS}/horizon").raise_for_status()
            for kind in ("metrics", "timeline"):
                cold: list[float] = []
                states: list[str] = []
                nbytes = 0
                for i in range(30):
                    # A fresh window each time: new Redis key, new memo key.
                    st = start + timedelta(days=BASE_DAYS + 11 * i, hours=7 + (kind == "timeline"))
                    params = {
                        "start": st.isoformat(),
                        "end": (st + (end - start)).isoformat(),
                        "step_s": 900,
                    }
                    t0 = time.perf_counter()
                    r = c.get(f"{API}/sites/{FOCUS}/{kind}", params=params)
                    ms = (time.perf_counter() - t0) * 1000.0
                    r.raise_for_status()
                    states.append(r.json()["meta"]["cache"])
                    nbytes = len(r.content)
                    # Only a true miss is a cold request; anything already
                    # cached under that key is excluded, and counted.
                    if states[-1] == "miss":
                        cold.append(ms)
                warm: list[float] = []
                wstates: list[str] = []
                params = {"start": start.isoformat(), "end": end.isoformat(), "step_s": 900}
                c.get(f"{API}/sites/{FOCUS}/{kind}", params=params).raise_for_status()
                for _ in range(30):
                    t0 = time.perf_counter()
                    r = c.get(f"{API}/sites/{FOCUS}/{kind}", params=params)
                    warm.append((time.perf_counter() - t0) * 1000.0)
                    wstates.append(r.json()["meta"]["cache"])
                rows.append(
                    row(
                        f"HTTP GET /{kind}, fresh window",
                        "http cold",
                        cold,
                        f"misses only ({len(cold)} of {len(states)}); body {nbytes} B",
                    )
                )
                rows.append(
                    row(
                        f"HTTP GET /{kind}, repeated window",
                        "http warm",
                        warm,
                        f"meta.cache {sorted(set(wstates))}",
                    )
                )
                http[kind] = {
                    "cold_states": sorted(set(states)),
                    "warm_states": sorted(set(wstates)),
                    "body_bytes": nbytes,
                }
            hz_ms = []
            for _ in range(30):
                t0 = time.perf_counter()
                c.get(f"{API}/sites/{FOCUS}/horizon").raise_for_status()
                hz_ms.append((time.perf_counter() - t0) * 1000.0)
            rows.append(row("HTTP GET /horizon (stored mask, 360 bins)", "http", hz_ms))
    except httpx.HTTPError as exc:
        http["error"] = f"{type(exc).__name__}: {exc}"

    header = ["stage", "path", "n", "median_ms", "p95_ms", "min_ms", "max_ms", "note"]
    with (DATA / "timing.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)

    # --- sensitivity: where the near-field rule starts trusting terrain -----
    fine = DemTile.load(s.fine_dem_path(FOCUS))
    sens: dict[str, Any] = {}
    original = horizon.RESOLVED_NOISE_DEG
    try:
        for thr in (0.125, 0.25, 0.5):
            horizon.RESOLVED_NOISE_DEG = thr
            m2, *_ = build_site_mask(site.lat_deg, site.lon_deg, fine, regional)
            res = await geometry_service.compute_window_metrics(
                site_id=FOCUS,
                lat_deg=site.lat_deg,
                lon_deg=site.lon_deg,
                elev_m=site.elev_m,
                mask=m2,
                start=start,
                end=end,
                step_s=900,
            )
            mm = res.metrics
            sens[f"{thr}"] = {
                "resolved_range_2m_m": round(2.0 / math.tan(math.radians(thr)), 1),
                "mask_mean_el_deg": round(float(np.mean(m2.el_deg)), 4),
                "sunlit_h": round(mm.sunlit_s / 3600, 3),
                "earth_contact_h": round(mm.earth_contact_s / 3600, 3),
                "longest_dark_h": round(mm.longest_dark_s / 3600, 3),
                "longest_blackout_h": round(mm.longest_blackout_s / 3600, 3),
            }
    finally:
        horizon.RESOLVED_NOISE_DEG = original

    env = {
        "cpu": subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
        ).stdout.strip(),
        "model": subprocess.run(
            ["sysctl", "-n", "hw.model"], capture_output=True, text=True
        ).stdout.strip(),
        "python": platform.python_version(),
        "os": platform.platform(),
        "per_site_mask_median_ms": {k: round(v, 2) for k, v in per_site.items()},
        "http": http,
    }
    (DATA / "sensitivity.json").write_text(
        json.dumps({"near_field_threshold": sens, "environment": env}, indent=2) + "\n"
    )
    for r in rows:
        print(r)
    print(json.dumps(sens, indent=2))
    print(json.dumps(env, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
