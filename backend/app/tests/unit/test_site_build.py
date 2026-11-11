"""The site_build job, the honest skyline gate on the steps, and scenarios with failed steps.

No database and no terrain data: repositories, the DEM and the mask builder are fakes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.core import scenario as core
from app.core import spice
from app.data.lola import DemTile
from app.db.repositories.jobs import JobRecord
from app.db.repositories.missions import MissionRecord
from app.db.repositories.sites import SiteRecord
from app.services import sections_service
from app.services.site_service import MaskNotBuilt
from app.workers import precompute
from app.workers.compute import HANDLERS, JobContext
from app.workers.handlers import scenario as scenario_h
from app.workers.handlers import site_build

# --- the job -------------------------------------------------------------------


def site(**kw: Any) -> SiteRecord:
    base: dict[str, Any] = {f: None for f in SiteRecord.__dataclass_fields__}
    base.update(
        id="project-x",
        name="x",
        lat_deg=-89.45,
        lon_deg=222.7,
        terrain_modelled=True,
    )
    base.update(kw)
    return SiteRecord(**base)


def ctx_for(params: dict[str, Any]) -> tuple[JobContext, list[tuple[float, str | None]]]:
    seen: list[tuple[float, str | None]] = []
    fields: dict[str, Any] = {f: None for f in JobRecord.__dataclass_fields__}
    rec = JobRecord(**(fields | {"params": params}))
    ctx = JobContext(job=rec)

    def progress(fraction: float, message: str | None = None) -> None:
        seen.append((fraction, message))

    ctx.progress = progress  # type: ignore[method-assign]
    return ctx, seen


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    tile = DemTile(
        heights=np.zeros((10, 10), dtype=np.float32),
        origin_x_m=-500.0,
        origin_y_m=500.0,
        scale_m=100.0,
        product="t",
        vertical_error_m=1.0,
    )
    state: dict[str, Any] = {"site": site(), "built": [], "metrics": [], "tile": tile}

    @asynccontextmanager
    async def scope() -> AsyncIterator[None]:
        yield None

    class Sites:
        def __init__(self, _s: Any) -> None: ...

        async def get(self, _sid: str) -> SiteRecord | None:
            found: SiteRecord | None = state["site"]
            return found

    class Masks:
        def __init__(self, _s: Any) -> None: ...

        async def get(self, *_a: Any) -> Any:
            return SimpleNamespace(dem_product="LOLA")

    async def build(
        s: SiteRecord, _coarse: DemTile, on_phase: Callable[[str], None] | None = None
    ) -> Any:
        assert on_phase is not None
        on_phase("Fetching the elevation window around the spot.")
        on_phase("Tracing the skyline in every direction.")
        state["built"].append(s.id)
        return SimpleNamespace(max_el_deg=1.234567, coverage=1.0)

    async def metrics(s: SiteRecord, _mask: Any) -> None:
        state["metrics"].append(s.id)

    monkeypatch.setattr(site_build, "session_scope", scope)
    monkeypatch.setattr(site_build, "SiteRepository", Sites)
    monkeypatch.setattr(site_build, "MaskRepository", Masks)
    monkeypatch.setattr(site_build, "ensure_regional_dem", lambda: state["tile"])
    monkeypatch.setattr(spice, "load", lambda _p: None)
    monkeypatch.setattr(precompute, "build_and_store_mask", build)
    monkeypatch.setattr(precompute, "store_reference_metrics", metrics)
    # The site sits at the origin of the fake grid, inside the tile.
    monkeypatch.setattr(site_build, "geographic_to_polar", lambda lon, lat: (lon * 0.0, lat * 0.0))
    return state


async def test_the_job_builds_the_mask_through_the_shared_path_in_phases(
    fakes: dict[str, Any],
) -> None:
    ctx, seen = ctx_for({"site_id": "project-x"})
    out = await site_build.run(ctx)
    assert fakes["built"] == ["project-x"] and fakes["metrics"] == ["project-x"]
    assert out.result["dem_product"] == "LOLA" and out.result["reference_numbers"] is True
    fractions = [f for f, _ in seen]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0
    messages = [m for _, m in seen]
    assert "Tracing the skyline in every direction." in messages
    assert any("elevation" in (m or "") for m in messages)


async def test_a_coordinate_no_model_covers_fails_in_plain_words(fakes: dict[str, Any]) -> None:
    fakes["site"] = site(terrain_modelled=False, lat_deg=45.0)
    ctx, _ = ctx_for({"site_id": "project-x"})
    with pytest.raises(site_build.OutsideCoverage, match="No elevation model covers 45.000"):
        await site_build.run(ctx)
    assert fakes["built"] == []


async def test_a_polar_point_off_the_regional_grid_fails_before_any_work(
    fakes: dict[str, Any],
) -> None:
    # Off the fake tile: the sampler answers NaN there.
    fakes["tile"] = replace(fakes["tile"], origin_x_m=1e9)
    ctx, _ = ctx_for({"site_id": "project-x"})
    with pytest.raises(site_build.OutsideCoverage, match="has no posts"):
        await site_build.run(ctx)
    assert fakes["built"] == []


async def test_a_missing_site_is_refused(fakes: dict[str, Any]) -> None:
    fakes["site"] = None
    ctx, _ = ctx_for({"site_id": "gone"})
    with pytest.raises(ValueError, match="gone"):
        await site_build.run(ctx)


def test_the_kind_is_registered() -> None:
    assert HANDLERS["site_build"] is site_build.run


# --- the steps' honest state ---------------------------------------------------


def mission(site_id: str | None = "project-x") -> MissionRecord:
    fields: dict[str, Any] = {f: None for f in MissionRecord.__dataclass_fields__}
    fields.update(id="p-x", site_id=site_id, lifecycle={})
    return MissionRecord(**fields)


class FakeSession:
    def __init__(self, row: Any) -> None:
        self.row = row

    async def execute(self, *_a: Any, **_k: Any) -> Any:
        return SimpleNamespace(one_or_none=lambda: self.row)


def mask_ids(monkeypatch: pytest.MonkeyPatch, ids: set[str]) -> None:
    class Masks:
        def __init__(self, _s: Any) -> None: ...

        async def existing_site_ids(self, _v: str) -> set[str]:
            return ids

    monkeypatch.setattr(sections_service, "MaskRepository", Masks)


async def gate(row: Any, section: str, m: MissionRecord) -> dict[str, Any] | None:
    return await sections_service.skyline_gate(FakeSession(row), section, m)  # type: ignore[arg-type]


async def test_a_built_skyline_gates_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    mask_ids(monkeypatch, {"project-x"})
    assert await gate(None, "landing", mission()) is None
    mask_ids(monkeypatch, set())
    assert await gate(None, "landing", mission(None)) is None


async def test_a_skyline_being_built_is_computing_with_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mask_ids(monkeypatch, set())
    row = SimpleNamespace(id=37, status="running", error=None, last_at=datetime.now(UTC))
    got = await gate(row, "contact", mission())
    assert got is not None and got["state"] == "computing" and got["section"] == "contact"
    assert "still being mapped" in got["summary"] and "37" in got["summary"]


async def test_a_failed_skyline_says_why_without_the_exception_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mask_ids(monkeypatch, set())
    row = SimpleNamespace(
        id=37,
        status="failed",
        error="OutsideCoverage: No elevation model covers 45.000 deg.\ntraceback",
        last_at=None,
    )
    got = await gate(row, "launch", mission())
    assert got is not None and got["state"] == "no_data"
    assert "could not be mapped: No elevation model covers 45.000 deg." in got["summary"]
    assert "OutsideCoverage" not in got["summary"] and "traceback" not in got["summary"]


async def test_no_job_at_all_is_not_mapped_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    mask_ids(monkeypatch, set())
    got = await gate(None, "landing", mission())
    assert got is not None and got["state"] == "no_data" and "not been mapped" in got["summary"]


# --- a scenario with failed steps ----------------------------------------------


def phases(**states: str) -> list[dict[str, Any]]:
    out = core.phases(core.SECTIONS)
    for p in out:
        p["state"] = states.get(p["id"], "skipped")
    return out


def test_no_failed_step_keeps_the_message() -> None:
    assert core.outcome(phases(launch="done"), "Worked out.") == ("done", "Worked out.")


def test_a_few_failed_steps_are_named_in_the_message() -> None:
    status, msg = core.outcome(phases(launch="done", trip="done", contact="failed"), "Worked out.")
    assert status == "done" and "except" in msg and "could not be" in msg


def test_most_steps_failed_is_not_reported_as_success() -> None:
    p = phases(launch="failed", landing="failed", contact="failed", **{"return": "done"})
    status, msg = core.outcome(p, "Worked out.")
    assert status == "failed" and msg.startswith("Could not be worked out:")
    assert len(core.failed_phases(p)) == 3


def test_a_missing_skyline_reads_in_plain_words() -> None:
    why = scenario_h.plain_reason(MaskNotBuilt("project-x"))
    assert "skyline" in why and "MaskNotBuilt" not in why and "project-x" not in why
