"""The wire shapes the frontend relies on (experience.types.ts): what the services build must fit
the response schemas, a refused project save is a 422 with ``detail.errors``, and a scenario's
contact result always carries ``start`` and ``end``. No database, no network."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest

from app.api.v1.routes import projects as project_routes
from app.api.v1.schemas.scenarios import (
    ActivityItemOut,
    AssumptionOut,
    ScenarioBriefOut,
    ScenarioOut,
)
from app.core import scenario as core
from app.db.repositories.scenarios import ActivityRow
from app.services import activity_service, contact_service, scenario_service
from app.tests.unit.test_scenarios import scenario_row
from app.workers.compute import HandlerResult
from app.workers.handlers import scenario as handler


def test_a_refused_project_save_is_a_422_with_field_and_message() -> None:
    from app.services import project_service

    exc = project_routes._http(project_service.BadProject("not a date", "landing.date"))
    assert exc.status_code == 422
    detail: Any = exc.detail
    assert detail["errors"] == [{"field": "landing.date", "message": "not a date"}]
    assert detail["ui"]["still_works"]  # the same envelope as every other error


def test_a_scenario_row_fits_the_scenario_schema() -> None:
    res = core.Resolved("surface_days", 10.0, "default", "Surface window rule", None, None, "n")
    names: dict[str, dict[str, str]] = {"vehicles": {}, "pads": {}, "relays": {}, "sites": {}}
    a = scenario_service.assumption_dict(res, names)
    AssumptionOut.model_validate(a)
    assert a["source"] == {"name": "Surface window rule", "url": None, "fetched_at": None}
    mine = core.Resolved("surface_days", 10.0, "you", None, None, None, None)
    assert scenario_service.assumption_dict(mine, names)["source"] is None

    rec = scenario_row(
        status="done",
        assumptions=[a],
        phases=core.phases(["launch"]),
        summaries={"launch": "x"},
        results={"launch": {"data": {}, "meta": {}}},
    )
    out = ScenarioOut.model_validate(scenario_service.full(rec))
    assert out.results is not None and out.poll_after_s == 0.0
    queued = ScenarioOut.model_validate(scenario_service.full(scenario_row(results={"x": 1})))
    assert queued.results is None  # nothing is shown until done
    ScenarioBriefOut.model_validate(scenario_service.brief(rec))


def test_activity_items_fit_the_activity_schema() -> None:
    now = datetime(2026, 11, 11, tzinfo=UTC)
    for kind in ("launch", "trip", "contact", "rover", "site_build", "scenario"):
        row = ActivityRow(kind, "1", "m1", "Athena", "running", None, "", None, now, None, {})
        ActivityItemOut.model_validate(activity_service.item(row))


async def test_a_scenarios_contact_result_always_has_start_and_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Tracker:
        def __init__(self) -> None:
            self.steps: list[tuple[str, str]] = []

        async def set(self, pid: str, state: str, detail: str | None = None, **_k: Any) -> None:
            self.steps.append((pid, state))

    @contextlib.asynccontextmanager
    async def scope() -> AsyncIterator[None]:
        yield None

    async def params(*_a: Any) -> dict[str, Any]:
        return {"start": "2027-03-14T00:00:00+00:00", "end": "2027-03-28T00:00:00+00:00"}

    async def sub_run(*_a: Any) -> HandlerResult:
        return HandlerResult(result={"data": {"nodes": []}})  # a worker answer without them

    monkeypatch.setattr(handler, "session_scope", scope)
    monkeypatch.setattr(contact_service, "contact_params", params)
    monkeypatch.setattr(handler, "_sub_run", sub_run)
    from app.tests.unit.test_scenarios import mission

    tr = Tracker()
    got = await handler._contact(None, tr, mission(site_id="s"), {})  # type: ignore[arg-type]
    assert got is not None
    assert got["data"]["start"].startswith("2027-03-14") and got["data"]["end"].startswith(
        "2027-03-28"
    )
    assert ("contact", "done") in tr.steps
