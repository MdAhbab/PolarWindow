"""Regenerate the golden fixtures.

Deliberately awkward to run: `make golden-update` refuses without
GOLDEN_UPDATE_REASON, and the reason is written into the manifest. A golden diff
in review is the signal that a refactor changed the physics, and it must be
impossible to produce by reflex.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).parent
DATA = HERE / "data"

#: Three sites chosen to exercise different physics, not three arbitrary ones.
SITES = {
    "connecting-ridge": "near-polar, high and open: terrain decides, not season",
    "malapert-massif": "far enough out that the Sun genuinely sets; seasonal",
    "faustini-rim": "sheltered and low: a long night no ridge is responsible for",
}

WINDOW_START = datetime(2027, 3, 14, tzinfo=UTC)
WINDOW_HOURS = 708.734
STEP_S = 900


async def main() -> None:
    reason = os.environ.get("GOLDEN_UPDATE_REASON")
    if not reason:
        sys.exit(
            "Refusing to regenerate goldens without GOLDEN_UPDATE_REASON.\n"
            "  A golden diff means the physics changed. Say why:\n"
            '  GOLDEN_UPDATE_REASON="..." make golden-update'
        )

    sys.path.insert(0, str(HERE.parents[2]))
    from app.config import ENGINE_VERSION, get_settings
    from app.core import spice
    from app.db.repositories.sites import MaskRepository, SiteRepository
    from app.db.session import dispose_engine, session_scope
    from app.services.geometry_service import compute_window_metrics

    s = get_settings()
    spice.load(s.kernel_dir)
    DATA.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "engine_version": ENGINE_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "reason": reason,
        "window": {
            "start": WINDOW_START.isoformat(),
            "hours": WINDOW_HOURS,
            "step_s": STEP_S,
        },
        "kernels": [
            {"name": p.name, "bytes": p.stat().st_size}
            for p in sorted(s.kernel_dir.glob("*"))
            if p.suffix in (".bsp", ".tls", ".tpc", ".bpc", ".tf")
        ],
        "tolerances": {
            "horizon_el_deg": 0.05,
            "az_el_deg": 0.01,
            "arc_edge_s": 72.0,
            "metric_abs_s": 360.0,
            "metric_rel": 0.001,
            "compound_abs_s": 180.0,
        },
        "sites": {},
    }

    async with session_scope() as session:
        for site_id, why in SITES.items():
            site = await SiteRepository(session).get(site_id)
            rec = await MaskRepository(session).get(site_id, ENGINE_VERSION)
            if site is None or rec is None:
                print(f"  skipping {site_id}: not seeded")
                continue

            np.savez_compressed(
                DATA / f"{site_id}.horizon.npz",
                el_deg=rec.mask.el_deg,
                range_m=rec.mask.range_m,
                tol_deg=rec.mask.tol_deg,
            )

            result = await compute_window_metrics(
                site_id=site_id,
                lat_deg=site.lat_deg,
                lon_deg=site.lon_deg,
                elev_m=site.elev_m,
                mask=rec.mask,
                start=WINDOW_START,
                end=WINDOW_START + timedelta(hours=WINDOW_HOURS),
                step_s=STEP_S,
            )
            np.savez_compressed(
                DATA / f"{site_id}.timeline.npz",
                sun_az=result.sun.az_deg,
                sun_el=result.sun.el_deg,
                sun_margin=result.sun.margin_deg,
                earth_az=result.earth.az_deg,
                earth_el=result.earth.el_deg,
                earth_margin=result.earth.margin_deg,
            )
            m = result.metrics
            (DATA / f"{site_id}.metrics.json").write_text(
                json.dumps(
                    {
                        "sunlit_s": m.sunlit_s,
                        "earth_contact_s": m.earth_contact_s,
                        "longest_dark_s": m.longest_dark_s,
                        "longest_blackout_s": m.longest_blackout_s,
                        "worst_compound_s": m.worst_compound_s,
                        "sun_fraction_up": m.sun.fraction_up,
                        "earth_fraction_up": m.earth.fraction_up,
                        "sun_arc_count": len(m.sun.arcs),
                        "earth_arc_count": len(m.earth.arcs),
                        "sun_arc_edges_s": [r.start for r in m.sun.arcs],
                        "earth_arc_edges_s": [r.start for r in m.earth.arcs],
                    },
                    indent=2,
                )
                + "\n"
            )
            manifest["sites"][site_id] = {
                "why": why,
                "lat_deg": site.lat_deg,
                "lon_deg": site.lon_deg,
                "elev_m": site.elev_m,
                "dem_product": rec.dem_product,
                "coverage": rec.mask.coverage,
            }
            print(f"  wrote {site_id}")

    (DATA / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    await dispose_engine()
    print(f"manifest: {DATA / 'MANIFEST.json'}")


if __name__ == "__main__":
    asyncio.run(main())
