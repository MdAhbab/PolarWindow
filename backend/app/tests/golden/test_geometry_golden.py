"""Golden tests: any change that moves the physics must be seen and signed for.

Two layers, deliberately:

* **Real-data goldens** (this file) need SPICE kernels, a seeded database and
  the LOLA subset. They are the authoritative check, and they are skipped
  rather than failed when those inputs are absent.
* **Synthetic goldens** (`test_synthetic_golden.py`) exercise the same code
  paths against analytic surfaces and a stub ephemeris, and run everywhere. They
  are what keeps the safety net alive on a laptop with no kernels, and they
  catch most refactor drift, because most refactors are not ephemeris-specific.

A failure here reports the worst offending index, where it is, both values and
the tolerance -- not "arrays differ". A golden test that is annoying to read
gets `--update`d reflexively, which destroys its value.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

DATA = Path(__file__).parent / "data"
MANIFEST = DATA / "MANIFEST.json"

pytestmark = [pytest.mark.requires_kernels, pytest.mark.requires_dem, pytest.mark.requires_db]

if not MANIFEST.exists():  # pragma: no cover
    pytest.skip("no golden fixtures; run make golden-update", allow_module_level=True)

manifest = json.loads(MANIFEST.read_text())
TOL = manifest["tolerances"]
SITE_IDS = sorted(manifest["sites"])


def report(
    name: str, got: np.ndarray, want: np.ndarray, tol: float, labels: np.ndarray | None = None
) -> None:
    """Fail with the offending index, its label, both values and the tolerance."""
    assert got.shape == want.shape, f"{name}: shape {got.shape} != golden {want.shape}"
    diff = np.abs(got - want)
    k = int(np.argmax(diff))
    if diff[k] > tol:
        where = f"index {k}" if labels is None else f"{labels[k]}"
        raise AssertionError(
            f"{name} drifted beyond tolerance.\n"
            f"  worst at   : {where}\n"
            f"  golden     : {want[k]:.6f}\n"
            f"  computed   : {got[k]:.6f}\n"
            f"  difference : {diff[k]:.6f}\n"
            f"  tolerance  : {tol}\n"
            f"  {int((diff > tol).sum())} of {diff.size} values exceed it.\n"
            f"  If this change is intended:\n"
            f'    GOLDEN_UPDATE_REASON="why" make golden-update'
        )


@pytest.fixture(scope="module")
def loaded():
    from app.config import get_settings
    from app.core import spice
    from app.core.kernels import KernelError

    try:
        spice.load(get_settings().kernel_dir)
    except KernelError as exc:
        pytest.skip(f"kernels unavailable: {exc}")
    return True


@pytest.mark.parametrize("site_id", SITE_IDS)
@pytest.mark.asyncio
async def test_horizon_matches_golden(site_id: str, loaded: bool) -> None:
    from app.config import ENGINE_VERSION
    from app.db.repositories.sites import MaskRepository
    from app.db.session import session_scope

    golden = np.load(DATA / f"{site_id}.horizon.npz")
    async with session_scope() as session:
        rec = await MaskRepository(session).get(site_id, ENGINE_VERSION)
    if rec is None:
        pytest.skip(f"{site_id} not seeded")

    bearings = np.arange(rec.mask.azimuth_count) * rec.mask.azimuth_step_deg
    labels = np.array([f"bearing {b:.2f} deg" for b in bearings])
    report(
        f"{site_id} horizon elevation",
        rec.mask.el_deg.astype(float),
        golden["el_deg"].astype(float),
        TOL["horizon_el_deg"],
        labels,
    )


@pytest.mark.parametrize("site_id", SITE_IDS)
@pytest.mark.asyncio
async def test_timeline_and_metrics_match_golden(site_id: str, loaded: bool) -> None:
    from app.config import ENGINE_VERSION
    from app.db.repositories.sites import MaskRepository, SiteRepository
    from app.db.session import session_scope
    from app.services.geometry_service import compute_window_metrics

    w = manifest["window"]
    start = datetime.fromisoformat(w["start"]).replace(tzinfo=UTC)
    end = start + timedelta(hours=w["hours"])

    async with session_scope() as session:
        site = await SiteRepository(session).get(site_id)
        rec = await MaskRepository(session).get(site_id, ENGINE_VERSION)
    if site is None or rec is None:
        pytest.skip(f"{site_id} not seeded")

    result = await compute_window_metrics(
        site_id=site_id,
        lat_deg=site.lat_deg,
        lon_deg=site.lon_deg,
        elev_m=site.elev_m,
        mask=rec.mask,
        start=start,
        end=end,
        step_s=w["step_s"],
    )

    g = np.load(DATA / f"{site_id}.timeline.npz")
    stamps = np.array([f"t+{h:.2f} h" for h in result.sun.t_s / 3600.0])
    for body, track in (("sun", result.sun), ("earth", result.earth)):
        report(
            f"{site_id} {body} elevation",
            track.el_deg,
            g[f"{body}_el"].astype(float),
            TOL["az_el_deg"],
            stamps,
        )
        report(
            f"{site_id} {body} margin",
            track.margin_deg,
            g[f"{body}_margin"].astype(float),
            TOL["az_el_deg"],
            stamps,
        )
        # Azimuth is compared through the wrap: 359.99 and 0.01 differ by 0.02.
        d = np.abs(((track.az_deg - g[f"{body}_az"].astype(float)) + 180) % 360 - 180)
        report(f"{site_id} {body} azimuth", d, np.zeros_like(d), TOL["az_el_deg"], stamps)

    want = json.loads((DATA / f"{site_id}.metrics.json").read_text())
    m = result.metrics
    for key, got in (
        ("sunlit_s", m.sunlit_s),
        ("earth_contact_s", m.earth_contact_s),
        ("longest_dark_s", m.longest_dark_s),
        ("longest_blackout_s", m.longest_blackout_s),
    ):
        tol = max(TOL["metric_abs_s"], abs(want[key]) * TOL["metric_rel"])
        assert got == pytest.approx(want[key], abs=tol), (
            f"{site_id}.{key} drifted: golden {want[key] / 3600:.3f} h, "
            f"computed {got / 3600:.3f} h, tolerance {tol / 3600:.3f} h"
        )

    assert m.worst_compound_s == pytest.approx(want["worst_compound_s"], abs=TOL["compound_abs_s"])
    assert len(m.sun.arcs) == want["sun_arc_count"], "the number of sun arcs changed"
    assert len(m.earth.arcs) == want["earth_arc_count"], "the number of earth arcs changed"

    edges = np.array([r.start for r in m.sun.arcs])
    want_edges = np.array(want["sun_arc_edges_s"])
    report(f"{site_id} sun arc edges", edges, want_edges, TOL["arc_edge_s"])


def test_manifest_records_its_provenance() -> None:
    """A golden set that cannot say what produced it is not evidence."""
    assert manifest["reason"], "no GOLDEN_UPDATE_REASON recorded"
    assert manifest["engine_version"]
    assert manifest["kernels"], "no kernel set recorded"
    assert {k["name"] for k in manifest["kernels"]} >= {"de440.bsp", "naif0012.tls"}
