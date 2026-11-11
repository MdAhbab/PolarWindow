"""Projects the team enters: validation, and the save, update and delete rules.

No database: the repositories and the change history are replaced by fakes.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from pydantic import ValidationError

from app.api.v1.schemas.projects import ProjectIn
from app.db.repositories.missions import CATALOGUE, PROJECT, MissionRecord
from app.services import audit_service, job_service, mission_service, project_service
from app.services.auth_service import Claims
from app.services.mission_service import MissionNotFound

NAMED = Claims(
    subject="pm", role="project_manager", issued_at=0, expires_at=9, user_id=7, name="Dana Reyes"
)
UNNAMED = Claims(subject="pm", role="project_manager", issued_at=0, expires_at=9)


def record(mission_id: str, origin: str, site_id: str | None = None) -> MissionRecord:
    return MissionRecord(
        id=mission_id,
        name="Athena",
        vehicle_name=None,
        task_order=None,
        provider=None,
        lander=None,
        status="planned",
        outcome_note="",
        region=None,
        target_name=None,
        target=None,
        ellipse=None,
        launch=None,
        landing=None,
        end_of_mission=None,
        planned_surface_days=None,
        sort_at=None,
        site_id=site_id,
        sources=[],
        unconfirmed_fields=[],
        notes=[],
        data_version="v",
        origin=origin,
    )


class World:
    """What the fakes saw."""

    def __init__(self) -> None:
        self.rows: dict[str, Any] = {}
        self.audit: list[dict[str, Any]] = []
        self.missions: dict[str, MissionRecord] = {}
        self.deleted: list[str] = []
        self.sites: dict[str, Any] = {}
        self.jobs: list[dict[str, Any]] = []
        self.intakes: dict[int, Any] = {}


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    w = World()

    class FakeProjects:
        def __init__(self, _s: Any) -> None: ...

        async def ids_starting(self, prefix: str) -> set[str]:
            return {i for i in w.rows if i.startswith(prefix)}

        async def insert(self, row: dict[str, Any], payloads: list[Any], owner: int) -> None:
            w.rows[row["id"]] = (row, payloads, owner)

        async def replace(self, mid: str, row: dict[str, Any], payloads: list[Any]) -> bool:
            w.rows[mid] = (row, payloads, None)
            return True

        async def delete(self, mid: str) -> bool:
            w.deleted.append(mid)
            return True

        async def get_intake(self, iid: int) -> Any:
            return w.intakes.get(iid)

        async def site_in_use(self, *_a: Any, **_k: Any) -> bool:
            return False

        async def delete_site(self, sid: str) -> None:
            w.sites.pop(sid, None)

        async def forget_site_numbers(self, _sid: str) -> None: ...

    class FakeMissions:
        def __init__(self, _s: Any) -> None: ...

        async def get(self, mid: str) -> MissionRecord | None:
            return w.missions.get(mid)

    class FakeSites:
        def __init__(self, _s: Any) -> None: ...

        async def get(self, sid: str) -> Any:
            return w.sites.get(sid)

        async def upsert_many(self, rows: list[dict[str, Any]]) -> None:
            for r in rows:
                w.sites[r["id"]] = type("S", (), r)()

    class FakeMasks:
        def __init__(self, _s: Any) -> None: ...

        async def get(self, *_a: Any) -> None:
            return None

        async def delete(self, *_a: Any) -> None: ...

    class FakeJobs:
        def __init__(self, _s: Any) -> None: ...

        async def enqueue(self, **kw: Any) -> dict[str, Any]:
            w.jobs.append(kw)
            return kw

    async def record_audit(_s: Any, who: Claims, **kw: Any) -> None:
        w.audit.append({"actor": who.actor, **kw})

    async def get_mission(_s: Any, mid: str) -> dict[str, Any]:
        return {"id": mid}

    monkeypatch.setattr(project_service, "ProjectRepository", FakeProjects)
    monkeypatch.setattr(project_service, "MissionRepository", FakeMissions)
    monkeypatch.setattr(project_service, "SiteRepository", FakeSites)
    monkeypatch.setattr(project_service, "MaskRepository", FakeMasks)
    monkeypatch.setattr(project_service, "JobRepository", FakeJobs)
    monkeypatch.setattr(audit_service, "record", record_audit)
    monkeypatch.setattr(mission_service, "get_mission", get_mission)
    monkeypatch.setattr(job_service, "job_ref", lambda j: {"kind": j["kind"]})
    return w


# --- the form ---------------------------------------------------------------


def test_only_the_name_is_required() -> None:
    p = ProjectIn(name="Athena 2")
    assert p.status == "planned" and p.launch is None and p.payloads == []
    with pytest.raises(ValidationError):
        ProjectIn()  # type: ignore[call-arg]


def test_a_target_is_a_site_or_a_coordinate_not_both() -> None:
    ProjectIn(name="x", target={"site_id": "shackleton"})
    ProjectIn(name="x", target={"lat_deg": -89.5, "lon_deg": 10})
    for bad in ({}, {"lat_deg": -89.5}, {"site_id": "a", "lat_deg": 1, "lon_deg": 2}):
        with pytest.raises(ValidationError):
            ProjectIn(name="x", target=bad)


def test_the_form_refuses_unknown_fields_and_bad_ranges() -> None:
    with pytest.raises(ValidationError):
        ProjectIn(name="x", verdict="go")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ProjectIn(name="x", planned_surface_days=-1)


def test_dates_are_cut_to_their_precision_and_worded() -> None:
    d = project_service.normalise_date({"date": "2027-08-19", "precision": "quarter"})
    assert d == {"date": "2027-07-01", "precision": "quarter", "as_published": "Q3 2027"}
    day = project_service.normalise_date({"date": "2027-03-14T10:30Z", "precision": "day"})
    assert day is not None and day["date"] == "2027-03-14"
    assert day["as_published"] == "14 March 2027"
    kept = project_service.normalise_date(
        {"date": "2027", "precision": "year", "as_published": "late 2027"}
    )
    assert kept is not None and kept["as_published"] == "late 2027"
    assert project_service.normalise_date(None) is None


def test_a_bad_date_names_its_field() -> None:
    with pytest.raises(project_service.BadProject) as e:
        project_service.normalise_date({"date": "soon", "precision": "day"}, "landing")
    assert e.value.errors[0]["field"] == "landing.date"


def build(data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return project_service.build_row(
        data, mission_id="p-x", target=None, site_id=None, sources=[], intake_id=None
    )


def test_unknown_facts_stay_unknown_and_are_listed() -> None:
    row, payloads = build({"name": "  Athena   2 "})
    assert row["name"] == "Athena 2"
    assert row["launch"] is None and row["landing"] is None and row["target"] is None
    assert row["lifecycle"]["vehicle_id"] is None
    assert row["planned_surface_days"] is None
    assert payloads == []
    assert "payloads" in row["unconfirmed_fields"]
    assert "landing" in row["unconfirmed_fields"]


def test_dates_out_of_order_are_refused_with_the_field() -> None:
    data = {
        "name": "x",
        "launch": {"date": "2027-05-10", "precision": "day"},
        "landing": {"date": "2027-05-01", "precision": "day"},
    }
    with pytest.raises(project_service.BadProject) as e:
        build(data)
    assert e.value.errors == [{"field": "landing.date", "message": "landing is before launch"}]


def test_a_coarse_date_is_not_compared() -> None:
    build(
        {
            "name": "x",
            "launch": {"date": "2027-05-10", "precision": "day"},
            "landing": {"date": "2027-04-01", "precision": "month"},
        }
    )


def test_sun_height_range_is_checked() -> None:
    with pytest.raises(project_service.BadProject) as e:
        build({"name": "x", "lifecycle": {"sun_el_min_deg": 9, "sun_el_max_deg": 2}})
    assert e.value.field == "lifecycle.sun_el_min_deg"


def test_ids_are_slugs_with_a_suffix_on_a_clash() -> None:
    assert project_service.project_id_base("Athena  2 / Café!") == "p-athena-2-cafe"
    assert project_service.free_id("p-a", {"p-a", "p-a-2"}) == "p-a-3"
    assert project_service.free_id("p-a", set()) == "p-a"


def test_unknown_catalogue_ids_are_refused_with_the_field() -> None:
    with pytest.raises(project_service.BadProject) as e:
        project_service._check_catalogue_ids({"vehicle_id": "no-such-rocket"})
    assert e.value.errors[0]["field"] == "lifecycle.vehicle_id"


# --- save, update, delete ---------------------------------------------------


async def test_saving_needs_a_named_session(world: World) -> None:
    for call in (
        project_service.create(None, UNNAMED, {"name": "x"}),  # type: ignore[arg-type]
        project_service.update(None, UNNAMED, "p-x", {"name": "x"}),  # type: ignore[arg-type]
        project_service.delete(None, UNNAMED, "p-x"),  # type: ignore[arg-type]
    ):
        with pytest.raises(audit_service.NotNamed):
            await call
    assert world.rows == {} and world.audit == []


async def test_create_saves_names_the_person_and_writes_the_audit_entry(world: World) -> None:
    out = await project_service.create(None, NAMED, {"name": "Athena 2"})  # type: ignore[arg-type]
    assert out["site_job"] is None and out["mission"] == {"id": "p-athena-2"}
    row, _payloads, owner = world.rows["p-athena-2"]
    assert owner == 7
    entered = row["sources"][0]
    assert entered["kind"] == "entered" and entered["url"] == ""
    assert entered["publisher"] == "Dana Reyes"
    assert [(a["action"], a["entity"], a["entity_id"]) for a in world.audit] == [
        ("create", "project", "p-athena-2")
    ]
    assert world.audit[0]["actor"] == "Dana Reyes"
    again = await project_service.create(None, NAMED, {"name": "Athena 2"})  # type: ignore[arg-type]
    assert again["mission"]["id"] == "p-athena-2-2"


async def test_a_file_source_carries_the_name_and_the_file(world: World) -> None:
    world.intakes[3] = type(
        "I", (), {"filename": "plan.pdf", "method": "rules", "created_at": dt.datetime(2026, 1, 2)}
    )()
    await project_service.create(None, NAMED, {"name": "x", "intake_id": 3})  # type: ignore[arg-type]
    src = world.rows["p-x"][0]["sources"][1]
    assert (src["kind"], src["url"], src["title"], src["publisher"]) == (
        "file",
        "",
        "plan.pdf",
        "Dana Reyes",
    )
    with pytest.raises(project_service.BadProject) as e:
        await project_service.create(None, NAMED, {"name": "y", "intake_id": 99})  # type: ignore[arg-type]
    assert e.value.field == "intake_id"


async def test_a_catalogue_record_cannot_be_changed_or_deleted(world: World) -> None:
    world.missions["im-3"] = record("im-3", CATALOGUE)
    with pytest.raises(project_service.NotAProject):
        await project_service.update(None, NAMED, "im-3", {"name": "x"})  # type: ignore[arg-type]
    with pytest.raises(project_service.NotAProject):
        await project_service.delete(None, NAMED, "im-3")  # type: ignore[arg-type]
    with pytest.raises(MissionNotFound):
        await project_service.delete(None, NAMED, "nope")  # type: ignore[arg-type]
    assert world.deleted == [] and world.audit == []


async def test_update_and_delete_a_project_are_audited(world: World) -> None:
    world.missions["p-a"] = record("p-a", PROJECT)
    await project_service.update(None, NAMED, "p-a", {"name": "Athena renamed"})  # type: ignore[arg-type]
    assert world.rows["p-a"][0]["name"] == "Athena renamed"
    out = await project_service.delete(None, NAMED, "p-a")  # type: ignore[arg-type]
    assert out == {"id": "p-a", "deleted": True} and world.deleted == ["p-a"]
    assert [a["action"] for a in world.audit] == ["update", "delete"]
    assert world.audit[0]["before"]["name"] == "Athena" and world.audit[1]["after"] is None


async def test_a_new_coordinate_becomes_a_site_and_queues_its_skyline(world: World) -> None:
    data = {"name": "Far", "target": {"lat_deg": -89.9, "lon_deg": -170.0, "name": None}}
    out = await project_service.create(None, NAMED, data)  # type: ignore[arg-type]
    site = world.sites["project-far"]
    assert site.kind == "mission_target" and site.lon_deg == 190.0
    assert out["site_job"] == {"kind": "site_build"}
    assert world.jobs[0]["params"] == {"site_id": "project-far"}
    row = world.rows["p-far"][0]
    assert row["site_id"] == "project-far" and row["target"]["lon_deg"] == 190.0


async def test_the_skyline_can_be_queued_again_for_a_project_with_a_target(world: World) -> None:
    world.missions["p-a"] = record("p-a", PROJECT, site_id="project-a")
    out = await project_service.rebuild_skyline(None, NAMED, "p-a")  # type: ignore[arg-type]
    assert out["site_job"] == {"kind": "site_build"}
    assert world.jobs[0]["params"] == {"site_id": "project-a"}


async def test_rebuilding_needs_a_target_and_a_project(world: World) -> None:
    world.missions["p-b"] = record("p-b", PROJECT)
    with pytest.raises(project_service.BadProject):
        await project_service.rebuild_skyline(None, NAMED, "p-b")  # type: ignore[arg-type]
    world.missions["m-c"] = record("m-c", CATALOGUE, site_id="s")
    with pytest.raises(project_service.NotAProject):
        await project_service.rebuild_skyline(None, NAMED, "m-c")  # type: ignore[arg-type]
