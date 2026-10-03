"""Touchdown instants and surface geometry against NAIF CLPS reconstructions.

See ``app.validation.validate_landing`` for the derivation and full table.
"""

from __future__ import annotations

import pytest

from app.config import get_settings

pytestmark = [pytest.mark.requires_kernels, pytest.mark.requires_clps_spice]


@pytest.fixture(scope="module")
def landing_checks():
    from app.validation import validate_landing

    s = get_settings()
    for edl_rel, _, ls_rel, _, _ in validate_landing.LANDED_KERNELS.values():
        if not (s.data_dir / edl_rel).exists():
            pytest.skip(f"{edl_rel} not on disk (polar-data sync)")
        if not (s.data_dir / ls_rel).exists():
            pytest.skip(f"{ls_rel} not on disk (polar-data sync)")
    return {c.mission_id: c for c in validate_landing.results()}


def test_touchdown_instant_matches_edl_reconstruction(landing_checks) -> None:
    for mid in ("im-1", "im-2", "blue-ghost-m1"):
        c = landing_checks[mid]
        assert c.edl_diff_s <= 1.0, f"{mid}: EDL diff {c.edl_diff_s} s > 1.0 s"


def test_landing_site_matches_published_target_position(landing_checks) -> None:
    # IM-2 and Blue Ghost 1 targets were published to 4 decimal places (~10 m / 0.3 m)
    assert landing_checks["im-2"].horizontal_dist_m <= 1.0
    assert landing_checks["blue-ghost-m1"].horizontal_dist_m <= 15.0
    # IM-1 target in LROC 1360 was published to 2 decimal places (-80.13, 1.44),
    # 79 m from reconstructed
    assert landing_checks["im-1"].horizontal_dist_m <= 100.0


def test_touchdown_sun_and_earth_elevations_match_direct_spkcpo(landing_checks) -> None:
    for mid in ("im-1", "im-2", "blue-ghost-m1"):
        c = landing_checks[mid]
        assert c.sun_el_diff_deg <= 0.01, f"{mid}: Sun diff {c.sun_el_diff_deg}° > 0.01°"
        assert c.earth_el_diff_deg <= 0.01, f"{mid}: Earth diff {c.earth_el_diff_deg}° > 0.01°"
