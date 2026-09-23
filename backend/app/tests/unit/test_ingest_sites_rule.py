"""The site-selection rule the API serves must be the rule the code runs (C4)."""

from __future__ import annotations

import numpy as np

from app.core.projections import geographic_to_polar
from app.data.ingest_sites import HIGH_GROUND_PERCENTILE, SiteSeed, resolve
from app.data.lola import DemTile


def _tile_around(lat: float, lon: float, *, size: int = 401, scale_m: float = 80.0) -> DemTile:
    x, y = geographic_to_polar(np.array([lon]), np.array([lat]))
    half = size // 2 * scale_m
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    # A broad dome: high ground everywhere near the centre, so every rule
    # (slope, high-ground floor, openness) has candidates to choose from.
    r = np.hypot(xx - size / 2, yy - size / 2) * scale_m
    heights = (2000.0 * np.exp(-((r / 12_000.0) ** 2))).astype(np.float32)
    return DemTile(
        heights=heights,
        origin_x_m=float(x[0]) - half,
        origin_y_m=float(y[0]) + half,
        scale_m=scale_m,
        product="synthetic",
        vertical_error_m=2.0,
    )


def test_source_note_states_the_rule_the_code_runs() -> None:
    seed = SiteSeed(
        id="t",
        code="T",
        name="Test massif",
        region="test",
        anchor_lat_deg=-88.0,
        anchor_lon_deg=40.0,
        search="massif",
        inner_km=0.0,
        outer_km=5.0,
        note="",
    )
    site = resolve(seed, _tile_around(-88.0, 40.0))
    note = site.source_note
    assert "most open sky" in note
    assert f"top {100 - HIGH_GROUND_PERCENTILE:.0f}%" in note
    assert "highest post" not in note
    assert site.offset_from_anchor_km <= 5.0 + 0.1
