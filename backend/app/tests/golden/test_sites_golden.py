"""The candidate-site rule, pinned (C5).

``ingest_sites.resolve_all`` decides every candidate coordinate the product
shows. A change to the search rule, the slope filter or the high-ground floor
moves sites, and that must be a reviewed diff here rather than a silent change
to fifteen coordinates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.requires_dem]

FIXTURE = Path(__file__).parent / "data" / "sites_resolved.json"


def test_resolve_all_matches_the_pinned_sites() -> None:
    from app.config import get_settings
    from app.data.ingest_sites import resolve_all
    from app.data.lola import DemTile

    tile = DemTile.load(get_settings().regional_dem_path)
    got = {s.id: s for s in resolve_all(tile)}
    want = json.loads(FIXTURE.read_text())["sites"]
    assert set(got) == {w["id"] for w in want}
    for w in want:
        s = got[w["id"]]
        assert s.lat_deg == pytest.approx(w["lat_deg"], abs=1e-5), w["id"]
        assert s.lon_deg == pytest.approx(w["lon_deg"], abs=1e-5), w["id"]
        assert s.elev_m == pytest.approx(w["elev_m"], abs=0.1), w["id"]
        assert s.slope_deg == pytest.approx(w["slope_deg"], abs=0.01), w["id"]
