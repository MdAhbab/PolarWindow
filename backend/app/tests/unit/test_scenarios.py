"""What-if scenarios: how a value is chosen, canonical keys, the overlay, presets, the rule reader.

No database, no network, no model: the repositories and the job queue are replaced by fakes.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.agents import scenario_reader
from app.config import get_settings
from app.core import scenario as core
from app.core.scenario import Candidate, FlightRow
from app.db.repositories.missions import MissionRecord
from app.db.repositories.scenarios import ScenarioRecord
from app.services import audit_service, job_service, scenario_service
from app.services.auth_service import Claims
from app.workers import presets

NAMED = Claims(
    subject="pm", role="project_manager", issued_at=0, expires_at=9, user_id=7, name="Dana Reyes"
)
TODAY = date(2026, 11, 11)
VEHICLES = {"falcon-9": "Falcon 9 Block 5", "falcon-heavy": "Falcon Heavy"}
PADS = {"ksc-lc-39a": "Launch Complex 39A", "ccsfs-slc-40": "Space Launch Complex 40"}
RELAYS = {"lunar-pathfinder": "Lunar Pathfinder"}
NAMES = {"vehicles": VEHICLES, "pads": PADS, "relays": RELAYS, "sites": {}}


def mission(mission_id: str = "m1", **kw: Any) -> MissionRecord:
    base: dict[str, Any] = {
        "id": mission_id,
        "name": "Athena",
        "vehicle_name": None,
        "task_order": None,
        "provider": "Intuitive Machines",
        "lander": "Nova-C",
        "status": "planned",
        "outcome_note": "",
        "region": None,
        "target_name": None,
        "target": None,
        "ellipse": None,
        "launch": None,
        "landing": None,
        "end_of_mission": None,
        "planned_surface_days": None,
        "sort_at": None,
        "site_id": None,
        "sources": [],
        "unconfirmed_fields": [],
        "notes": [],
        "data_version": "v1",
    }
    base.update(kw)
    return MissionRecord(**base)


def flown(mission_id: str, when: str, vehicle: str, pad: str) -> MissionRecord:
    return mission(
        mission_id,
        name=mission_id.upper(),
        status="completed",
        landing={"date": f"{when}T00:00:00Z", "precision": "day", "as_published": when},
        lifecycle={"vehicle_id": vehicle, "pad_id": pad},
    )


def scenario_row(**kw: Any) -> ScenarioRecord:
    base: dict[str, Any] = {
        "id": "sc-1",
        "mission_id": "m1",
        "key": "k",
        "name": "n",
        "prompt": None,
        "given": {},
        "sections": ["launch"],
        "preset": False,
        "status": "queued",
        "progress": 0.0,
        "message": "",
        "assumptions": [],
        "phases": [],
        "summaries": {},
        "results": None,
        "error": None,
        "job_id": None,
        "created_by": None,
        "created_by_name": None,
        "created_at": datetime(2026, 11, 11, tzinfo=UTC),
        "finished_at": None,
    }
    base.update(kw)
    return ScenarioRecord(**base)


# --- fakes -------------------------------------------------------------------


class World:
    def __init__(self) -> None:
        self.missions: dict[str, MissionRecord] = {}
        self.scenarios: dict[str, ScenarioRecord] = {}
        self.mission_writes: list[str] = []
        self.enqueued: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self.requeued: list[str] = []


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    w = World()

    class FakeMissions:
        def __init__(self, _s: Any) -> None: ...

        async def get(self, mid: str) -> MissionRecord | None:
            return w.missions.get(mid)

        async def find(self, statuses: list[str] | None = None, **_k: Any) -> list[MissionRecord]:
            return [m for m in w.missions.values() if statuses is None or m.status in statuses]

        # Anything that would change a record is noted; a scenario must call none of it.
        async def replace_all(self, *_a: Any, **_k: Any) -> None:
            w.mission_writes.append("replace_all")

        async def save(self, *_a: Any, **_k: Any) -> None:
            w.mission_writes.append("save")

    class FakePm:
        def __init__(self, _s: Any) -> None: ...

        async def parameters(self) -> dict[str, dict[str, Any]]:
            return {}

    class FakeSites:
        def __init__(self, _s: Any) -> None: ...

        async def list_sites(self, **_k: Any) -> tuple[list[Any], int]:
            return [], 0

    class FakeScenarios:
        def __init__(self, _s: Any) -> None: ...

        async def create(self, **kw: Any) -> tuple[ScenarioRecord, bool]:
            if kw["scenario_id"] in w.scenarios:
                return w.scenarios[kw["scenario_id"]], False
            rec = scenario_row(
                id=kw["scenario_id"],
                mission_id=kw["mission_id"],
                key=kw["key"],
                name=kw["name"],
                prompt=kw["prompt"],
                given=kw["given"],
                sections=kw["sections"],
                preset=kw["preset"],
                phases=kw["phases"],
            )
            w.scenarios[rec.id] = rec
            return rec, True

        async def get(self, sid: str) -> ScenarioRecord | None:
            return w.scenarios.get(sid)

        async def set_job(self, sid: str, job_id: int) -> None: ...

        async def requeue(self, sid: str, _phases: Any = None) -> None:
            w.requeued.append(sid)
            w.scenarios[sid] = replace(w.scenarios[sid], status="queued", phases=[])

        async def by_key(self, key: str) -> ScenarioRecord | None:
            return next((r for r in w.scenarios.values() if r.key == key), None)

        async def for_mission(self, mid: str) -> list[ScenarioRecord]:
            return [r for r in w.scenarios.values() if r.mission_id == mid]

        async def delete(self, sid: str) -> None:
            w.scenarios.pop(sid, None)

    class FakeAssessments:
        def __init__(self, _s: Any) -> None: ...

        async def latest(self, *_a: Any) -> None:
            return None

    class FakeJobs:
        def __init__(self, _s: Any) -> None: ...

        async def latest_for(self, *_a: Any) -> None:
            return None

        async def queued_count(self) -> int:
            return 0

        async def enqueue(self, **kw: Any) -> dict[str, Any]:
            w.enqueued.append(kw)
            return {"job_id": len(w.enqueued), "status": "queued", "message": ""}

    async def no_ahead(*_a: Any, **_k: Any) -> int:
        return 0

    async def record_audit(_s: Any, who: Claims, **kw: Any) -> None:
        w.audit.append({"actor": who.actor, **kw})

    async def names(_s: Any) -> dict[str, dict[str, str]]:
        return NAMES

    monkeypatch.setattr(scenario_service, "MissionRepository", FakeMissions)
    monkeypatch.setattr(scenario_service, "PmRepository", FakePm)
    monkeypatch.setattr(scenario_service, "SiteRepository", FakeSites)
    monkeypatch.setattr(scenario_service, "ScenarioRepository", FakeScenarios)
    monkeypatch.setattr(scenario_service, "names", names)
    monkeypatch.setattr(job_service, "AssessmentRepository", FakeAssessments)
    monkeypatch.setattr(job_service, "JobRepository", FakeJobs)
    monkeypatch.setattr(job_service, "job_ref", lambda j, **_k: dict(j))
    monkeypatch.setattr(job_service, "_ahead", no_ahead)
    monkeypatch.setattr(audit_service, "record", record_audit)
    return w


# --- the order a value is chosen in -------------------------------------------

PUB = Candidate("falcon-9", "Mission record")
LIVE = Candidate("falcon-heavy", "Launch Library 2", "https://ll.example/", "2026-11-11T00:00:00Z")
DEFAULT = Candidate("vulcan-centaur", "As IM-2, a past flight")


def test_you_beat_published_live_and_default() -> None:
    r = core.resolve(
        "vehicle_id", given={"vehicle_id": "new-glenn"}, published=PUB, live=LIVE, default=DEFAULT
    )
    assert r is not None and (r.value, r.basis, r.source) == ("new-glenn", "you", None)


def test_published_beats_live_and_default() -> None:
    r = core.resolve("vehicle_id", given={}, published=PUB, live=LIVE, default=DEFAULT)
    assert r is not None and (r.value, r.basis) == ("falcon-9", "published")
    assert r.source == "Mission record"


def test_live_beats_default_and_keeps_where_and_when() -> None:
    r = core.resolve("vehicle_id", given={}, published=None, live=LIVE, default=DEFAULT)
    assert r is not None and r.basis == "live" and r.value == "falcon-heavy"
    assert r.url == "https://ll.example/" and r.fetched_at == "2026-11-11T00:00:00Z"


def test_default_is_last_and_names_its_precedent() -> None:
    r = core.resolve("vehicle_id", given={}, published=None, live=None, default=DEFAULT)
    assert r is not None and r.basis == "default" and r.source == "As IM-2, a past flight"


def test_a_feature_centre_site_reads_as_the_centre_not_a_landing_point() -> None:
    assert core.site_words("Reiner Gamma (feature centre)") == (
        "Centre of Reiner Gamma, not a landing point"
    )
    assert core.site_words("Connecting Ridge") == "Connecting Ridge"
    names = {"sites": {"feature-reiner-gamma": core.site_words("Reiner Gamma (feature centre)")}}
    assert core.display("site_id", "feature-reiner-gamma", names) == (
        "Centre of Reiner Gamma, not a landing point"
    )


def test_an_empty_value_falls_through_to_the_next_basis() -> None:
    r = core.resolve(
        "vehicle_id",
        given={"vehicle_id": ""},
        published=Candidate(None, "x"),
        live=Candidate("", "y"),
        default=DEFAULT,
    )
    assert r is not None and r.basis == "default"


def test_a_field_with_no_basis_is_a_gap_not_a_guess() -> None:
    assert core.resolve("vehicle_id", given={}, published=None, live=None, default=None) is None
    assert core.missing_for("launch", ["vehicle_id", "site_id"]) == ["pad_id"]
    assert core.missing_for("trip", []) == []


async def test_resolve_all_leaves_out_what_nothing_supplies(world: World) -> None:
    m = mission(provider=None, lander=None)  # no precedent, no site, no landing date
    world.missions[m.id] = m
    res = await scenario_service.resolve_all(None, m, {}, today=TODAY)  # type: ignore[arg-type]
    by = {r.field: r for r in res}
    for gap in ("vehicle_id", "pad_id", "site_id"):
        assert gap not in by
    # A landing day always has a stated example rule, so it is a default, never a gap.
    assert by["landing_date"].basis == "default" and "not a plan" in (by["landing_date"].note or "")
    assert by["transfer_type"].basis == "default" and by["surface_days"].basis == "default"
    assert not scenario_service.can_run("launch", res)
    assert not scenario_service.can_run("contact", res)


async def test_resolve_all_labels_each_basis(world: World) -> None:
    m = mission(
        site_id="shackleton",
        planned_surface_days=7,
        landing={"date": "2027-03-14T00:00:00Z", "precision": "day", "as_published": "14 March"},
    )
    world.missions[m.id] = m
    world.missions["old"] = flown("old", "2024-02-22", "falcon-9", "ksc-lc-39a")
    live = {"pad_id": Candidate("ccsfs-slc-40", "Launch Library 2")}
    res = await scenario_service.resolve_all(
        None,  # type: ignore[arg-type]
        m,
        {"vehicle_id": "falcon-heavy"},
        live,
        TODAY,
    )
    by = {r.field: r for r in res}
    assert by["vehicle_id"].basis == "you" and by["vehicle_id"].value == "falcon-heavy"
    assert by["pad_id"].basis == "live"
    assert by["site_id"].basis == "published" and by["surface_days"].value == 7.0
    assert by["landing_date"].basis == "published"
    assert by["transfer_type"].basis == "default"
    # With the same provider's earlier flight on record, an unset vehicle falls to a precedent.
    again = await scenario_service.resolve_all(None, m, {}, today=TODAY)  # type: ignore[arg-type]
    veh = {r.field: r for r in again}["vehicle_id"]
    assert veh.basis == "default" and veh.value == "falcon-9" and "OLD" in str(veh.source)


async def test_a_vague_landing_is_a_default_with_its_wording_kept(world: World) -> None:
    vague = mission(
        landing={"date": "2027-07-01T00:00:00Z", "precision": "quarter", "as_published": "Q3 2027"}
    )
    res = await scenario_service.resolve_all(None, vague, {}, today=TODAY)  # type: ignore[arg-type]
    land = {r.field: r for r in res}["landing_date"]
    assert land.basis == "default" and land.value == "2027-07-01" and "Q3 2027" in str(land.note)


# --- canonical keys -----------------------------------------------------------


def key(given: dict[str, Any], sections: list[str] | None = None, mission_id: str = "m1") -> str:
    return core.scenario_key(mission_id, sections or list(core.SECTIONS), given)


def test_near_equal_inputs_share_a_key() -> None:
    a = key({"landing_date": "2027-03-14", "surface_days": 10.0, "sun_el_min_deg": 5.0})
    b = key({"landing_date": "2027-03-14T18:30:00Z", "surface_days": 10.2, "sun_el_min_deg": 5.24})
    assert a == b
    assert core.canonical({"surface_days": 10.26}) == {"surface_days": 10.5}
    assert key({"relays": ["b", "a"]}) == key({"relays": ["a", "b", "a"]})
    assert key({}, ["launch", "trip"]) == key({}, ["trip", "launch", "trip"])


def test_genuinely_different_inputs_have_different_keys() -> None:
    base = {"landing_date": "2027-03-14", "surface_days": 10.0}
    assert key(base) != key({**base, "landing_date": "2027-03-15"})
    assert key(base) != key({**base, "surface_days": 10.5})
    assert key(base) != key({**base, "vehicle_id": "falcon-9"})
    assert key(base) != key(base, ["launch"])
    assert key(base) != key(base, mission_id="m2")
    assert core.scenario_id(key(base)).startswith("sc-")


def test_canonical_drops_empty_values_and_refuses_unknown_fields() -> None:
    assert core.canonical({"vehicle_id": " falcon-9 ", "pad_id": None, "relays": []}) == {
        "vehicle_id": "falcon-9"
    }
    with pytest.raises(KeyError):
        core.canonical({"verdict": "go"})
    assert core.validate({"surface_days": 100})  # outside 0.5 to 60
    assert core.validate({"launch_from": "2027-01-01", "launch_to": "2027-09-01"})  # > 180 days


# --- a scenario never writes the mission --------------------------------------


def test_the_overlay_is_a_copy_and_the_record_is_untouched() -> None:
    m = mission(lifecycle={"vehicle_id": "falcon-9"}, planned_surface_days=7)
    res = [
        core.Resolved("vehicle_id", "falcon-heavy", "you", None, None, None, None),
        core.Resolved("landing_date", "2027-03-14", "you", None, None, None, None),
        core.Resolved("surface_days", 10.0, "default", "rule", None, None, None),
    ]
    m2 = scenario_service.overlay(m, res, None)
    assert m2 is not m
    assert m2.lifecycle["vehicle_id"] == "falcon-heavy" and m2.planned_surface_days == 10.0
    assert m2.landing is not None and m2.landing["precision"] == "day"
    assert m.lifecycle == {"vehicle_id": "falcon-9"}
    assert m.landing is None and m.planned_surface_days == 7


async def test_starting_a_scenario_never_saves_a_mission(world: World) -> None:
    m = mission(site_id="shackleton", lifecycle={"vehicle_id": "falcon-9", "pad_id": "ksc-lc-39a"})
    world.missions[m.id] = m
    snapshot = repr(m)
    created, out = await scenario_service.start(
        None,  # type: ignore[arg-type]
        NAMED,
        "m1",
        {"assumptions": [{"field": "surface_days", "value": 10}], "sections": ["launch"]},
    )
    assert created and out["status"] == "queued"
    assert world.mission_writes == [] and repr(world.missions["m1"]) == snapshot
    assert world.audit and world.audit[0]["entity"] == "scenario"


async def test_a_second_equivalent_request_joins_the_first(world: World) -> None:
    world.missions["m1"] = mission(
        site_id="s", lifecycle={"vehicle_id": "falcon-9", "pad_id": "ksc-lc-39a"}
    )
    body = {"assumptions": [{"field": "surface_days", "value": 10.1}], "sections": ["launch"]}
    c1, a = await scenario_service.start(None, NAMED, "m1", body)  # type: ignore[arg-type]
    body2 = {"assumptions": [{"field": "surface_days", "value": 9.9}], "sections": ["launch"]}
    c2, b = await scenario_service.start(None, NAMED, "m1", body2)  # type: ignore[arg-type]
    assert c1 and not c2 and a["id"] == b["id"] and len(world.enqueued) == 1


async def test_a_stored_scenario_with_a_failed_step_runs_again_instead_of_joining(
    world: World,
) -> None:
    world.missions["m1"] = mission(
        site_id="s", lifecycle={"vehicle_id": "falcon-9", "pad_id": "ksc-lc-39a"}
    )
    body = {"assumptions": [{"field": "surface_days", "value": 10}], "sections": ["launch"]}
    _, first = await scenario_service.start(None, NAMED, "m1", body)  # type: ignore[arg-type]
    sid = first["id"]
    # It finished, but a step could not be worked out (as when the skyline was missing).
    world.scenarios[sid] = replace(
        world.scenarios[sid],
        status="done",
        phases=[{"id": "launch", "label": "Launch", "state": "failed", "detail": "x"}],
    )
    created, again = await scenario_service.start(None, NAMED, "m1", body)  # type: ignore[arg-type]
    assert not created and again["id"] == sid
    assert world.requeued == [sid] and len(world.enqueued) == 2
    assert again["status"] == "queued"


async def test_nothing_runnable_is_refused_in_plain_words(world: World) -> None:
    world.missions["m1"] = mission(provider=None, lander=None)
    with pytest.raises(scenario_service.BadScenario) as e:
        await scenario_service.start(None, NAMED, "m1", {"sections": ["launch"]})  # type: ignore[arg-type]
    assert "launch vehicle" in str(e.value)
    with pytest.raises(scenario_service.BadScenario):
        await scenario_service.start(
            None,  # type: ignore[arg-type]
            NAMED,
            "m1",
            {"assumptions": [{"field": "verdict", "value": "go"}]},
        )


async def test_a_preset_cannot_be_deleted(world: World) -> None:
    world.scenarios["sc-p"] = scenario_row(id="sc-p", preset=True)
    with pytest.raises(scenario_service.Refused):
        await scenario_service.delete(None, NAMED, "sc-p")  # type: ignore[arg-type]
    assert "sc-p" in world.scenarios


# --- presets and priority -----------------------------------------------------


async def test_presets_queue_below_every_real_job_and_below_asked_scenarios(world: World) -> None:
    m = mission(site_id="s", lifecycle={"vehicle_id": "falcon-9", "pad_id": "ksc-lc-39a"})
    world.missions[m.id] = m
    await scenario_service.create(
        None,  # type: ignore[arg-type]
        m,
        given={"surface_days": 10.0},
        sections=["launch"],
        name=None,
        prompt=None,
        who=None,
        preset=True,
    )
    await scenario_service.create(
        None,  # type: ignore[arg-type]
        m,
        given={"surface_days": 12.0},
        sections=["launch"],
        name=None,
        prompt="12 days",
        who=NAMED,
    )
    preset_job, asked_job = world.enqueued
    assert preset_job["kind"] == "scenario"
    assert preset_job["priority"] == scenario_service.PRIORITY_PRESET
    assert asked_job["priority"] == scenario_service.PRIORITY_ASKED
    assert preset_job["priority"] < asked_job["priority"] < min(job_service.PRIORITY.values())


async def test_queue_presets_makes_presets_for_upcoming_missions_only(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    world.missions["m1"] = mission()
    world.missions["done"] = mission("done", status="completed")
    made: list[dict[str, Any]] = []

    @contextlib.asynccontextmanager
    async def fake_scope() -> AsyncIterator[None]:
        yield None

    class Repo:
        def __init__(self, _s: Any) -> None: ...

        async def find(self, statuses: list[str] | None = None, **_k: Any) -> list[MissionRecord]:
            return [m for m in world.missions.values() if statuses is None or m.status in statuses]

    async def gaps(_s: Any, _mid: str) -> dict[str, Any]:
        return {"gaps": [{"can_explore": True}]}

    async def variants(*_a: Any) -> list[tuple[str, dict[str, Any]]]:
        return [("a", {}), ("b", {"surface_days": 5})]

    async def create(_s: Any, mm: MissionRecord, **kw: Any) -> tuple[None, bool]:
        made.append({"mission": mm.id, **kw})
        return None, True

    monkeypatch.setattr(presets, "session_scope", fake_scope)
    monkeypatch.setattr(presets, "MissionRepository", Repo)
    monkeypatch.setattr(presets, "variants", variants)
    monkeypatch.setattr(scenario_service, "gaps", gaps)
    monkeypatch.setattr(scenario_service, "create", create)
    n = await presets.queue_presets()
    assert n == 2 and {c["mission"] for c in made} == {"m1"}
    assert all(c["preset"] is True and c["who"] is None for c in made)


async def test_preset_variants_are_defaults_then_next_precedent_then_a_month_later(
    world: World,
) -> None:
    m = mission(
        site_id="s",
        lifecycle={"vehicle_id": "falcon-9", "pad_id": "ksc-lc-39a"},
        landing={"date": "2027-03-14T00:00:00Z", "precision": "day", "as_published": "14 Mar"},
    )
    world.missions[m.id] = m
    world.missions["old"] = flown("old", "2024-02-22", "falcon-heavy", "ccsfs-slc-40")
    out = await presets.variants(None, m, NAMES)
    assert [n.split(":")[0] for n, _ in out] == [
        "Defaults from past flights",
        "As the next flight of this lander",
        "A month later",
    ]
    assert out[0][1] == {}
    assert out[1][1] == {"vehicle_id": "falcon-heavy", "pad_id": "ccsfs-slc-40"}
    assert out[2][1] == {"landing_date": "2027-04-01"}
    assert len(out) <= presets.MAX_PER_MISSION


async def test_a_reading_that_equals_a_preset_matches_it(world: World) -> None:
    m = mission(site_id="s", lifecycle={"vehicle_id": "falcon-9", "pad_id": "ksc-lc-39a"})
    world.missions[m.id] = m
    preset, _ = await scenario_service.create(
        None,  # type: ignore[arg-type]
        m,
        given={"surface_days": 10.0},
        sections=list(core.SECTIONS),
        name=None,
        prompt=None,
        who=None,
        preset=True,
    )
    same = await scenario_service.interpreted(
        None,  # type: ignore[arg-type]
        "m1",
        core.Reading(values={"surface_days": 10.2}),
    )
    assert same["matches_preset"] == preset.id
    other = await scenario_service.interpreted(
        None,  # type: ignore[arg-type]
        "m1",
        core.Reading(values={"surface_days": 20}),
    )
    assert other["matches_preset"] is None


async def test_interpreted_drops_an_unusable_value_and_says_why(world: World) -> None:
    world.missions["m1"] = mission(site_id="s")
    out = await scenario_service.interpreted(
        None,  # type: ignore[arg-type]
        "m1",
        core.Reading(values={"surface_days": 500, "transfer_type": "direct"}),
    )
    assert any("Days on the surface" in u for u in out["unresolved"])
    assert out["method"] == "rules"
    assert not any(a["basis"] == "you" and a["field"] == "surface_days" for a in out["assumptions"])


# --- the rule-based reader ----------------------------------------------------


def parse(text: str) -> core.Reading:
    return core.parse_prompt(text, TODAY, vehicles=VEHICLES, pads=PADS, relays=RELAYS)


def test_prompt_vehicle_pad_month_and_surface_days() -> None:
    r = parse("Launch on Falcon Heavy from Launch Complex 39A in March, 10 days on the surface")
    assert r.values == {
        "vehicle_id": "falcon-heavy",
        "pad_id": "ksc-lc-39a",
        "launch_from": "2027-03-01",
        "launch_to": "2027-03-31",
        "surface_days": 10.0,
    }
    assert any("next one" in n for n in r.notes)  # the year was not said, and that is said


def test_prompt_exact_date_transfer_and_sun_height() -> None:
    r = parse("Land on 2027-05-12 with a direct transfer and the Sun at least 5 degrees up")
    assert r.values == {
        "landing_date": "2027-05-12",
        "transfer_type": "direct",
        "sun_el_min_deg": 5.0,
    }


def test_prompt_quarter_landing_and_launch_month_with_year() -> None:
    r = parse("launch in May 2027, land in Q4 2027")
    assert r.values["launch_from"] == "2027-05-01" and r.values["launch_to"] == "2027-05-31"
    assert r.values["landing_date"] == "2027-10-01"
    assert any("first day" in n for n in r.notes)


def test_prompt_flight_days_are_not_surface_days_and_vague_days_are_said() -> None:
    r = parse("a 4 day flight, then 12 days on the surface with Lunar Pathfinder")
    assert r.values["surface_days"] == 12.0 and r.values["relays"] == ["lunar-pathfinder"]
    vague = parse("take 6 days")
    assert "surface_days" not in vague.values and vague.unresolved


def test_prompt_with_a_date_but_no_launch_or_landing_is_said_not_guessed() -> None:
    r = parse("something in 2027-04-01")
    assert r.values == {} and any("launch or the landing" in u for u in r.unresolved)
    assert parse("hello there").values == {}


def test_the_verb_may_does_not_hide_a_month_named_later() -> None:
    assert parse("it may launch in June 2027").values.get("launch_from") == "2027-06-01"
    assert parse("launch in May 2027").values["launch_from"] == "2027-05-01"
    assert "launch_from" not in parse("it may launch soon").values


def test_two_vehicles_named_uses_the_first_and_says_so() -> None:
    r = parse("Falcon 9 or Falcon Heavy")
    assert r.values["vehicle_id"] in VEHICLES and r.unresolved


async def test_the_reader_without_a_model_says_it_used_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PW_GEMINI_API_KEY", "")
    get_settings.cache_clear()
    ctx = {
        "today": TODAY.isoformat(),
        "vehicles": VEHICLES,
        "pads": PADS,
        "relays": RELAYS,
        "months": [],
        "transfer_types": core.TRANSFER_TYPES,
        "mission_id": "m1",
    }
    try:
        if get_settings().agents_enabled:
            pytest.skip("a model key is configured")
        r = await scenario_reader.read(None, "stay 14 days on the surface", ctx)  # type: ignore[arg-type]
    finally:
        get_settings.cache_clear()
    assert r.method == "rules" and "rules" in r.interpreted_as
    assert r.values == {"surface_days": 14.0}


def test_model_values_are_checked_against_the_options_and_the_prompt() -> None:
    ctx = {
        "today": "2026-11-11",
        "vehicles": VEHICLES,
        "pads": PADS,
        "relays": RELAYS,
        "transfer_types": core.TRANSFER_TYPES,
        "months": [{"name": "March 2027", "first_day": "2027-03-01", "last_day": "2027-03-31"}],
    }
    items = [
        scenario_reader.ReadValue(field="vehicle_id", value="falcon-heavy"),
        scenario_reader.ReadValue(field="pad_id", value="made-up-pad"),
        scenario_reader.ReadValue(field="surface_days", value="30"),
        scenario_reader.ReadValue(field="launch_from", value="2027-03-01"),
        scenario_reader.ReadValue(field="landing_date", value="2027-03-09"),
    ]
    out, bad = scenario_reader.clean(items, "Falcon Heavy, 10 days, March", ctx)
    assert out == {"vehicle_id": "falcon-heavy", "launch_from": "2027-03-01"}
    assert len(bad) == 3


def test_precedents_prefer_the_same_lander_then_the_same_provider() -> None:
    rows = [
        FlightRow("a", "A", "IM", "Nova-C", "2024-02-22", "falcon-9", "ksc-lc-39a"),
        FlightRow("b", "B", "IM", "Other", "2025-03-06", "falcon-heavy", "ccsfs-slc-40"),
        FlightRow("c", "C", "Zed", "Nova-C", "2023-01-01", None, None),
    ]
    got = core.default_vehicle("IM", "Nova-C", rows)
    assert got is not None and got.value == "falcon-9" and "A" in got.source
    pad = core.default_pad("falcon-heavy", "IM", "Nova-C", rows)
    assert pad is not None and pad.value == "ccsfs-slc-40"
    assert core.default_vehicle(None, None, []) is None


async def test_a_section_may_report_progress_from_a_worker_thread() -> None:
    """The contact step reports from ``asyncio.to_thread``; that once failed the step."""
    import asyncio

    from app.db.repositories.jobs import JobRecord
    from app.workers.compute import HandlerResult, JobContext
    from app.workers.handlers import scenario as handler

    seen: list[tuple[str, str]] = []

    class Tracker:
        def phase(self, pid: str) -> dict[str, Any]:
            return {"detail": None}

        async def set(self, pid: str, state: str, detail: str, within: float = 0.0) -> None:
            seen.append((pid, detail))

    async def run(ctx: JobContext) -> HandlerResult:
        await asyncio.to_thread(ctx.progress, 0.5, "half way, from a thread")
        await asyncio.sleep(0.01)
        return HandlerResult(result={"data": {}})

    fields: dict[str, Any] = {f: None for f in JobRecord.__dataclass_fields__}
    ctx = JobContext(job=JobRecord(**(fields | {"kind": "scenario", "params": {}})))
    await handler._sub_run(ctx, run, {}, "contact", Tracker(), "contact")  # type: ignore[arg-type]
    assert seen == [("contact", "half way, from a thread")]


def _target(mid: str, provider: str | None, region: str, site: str, when: str) -> core.TargetRow:
    return core.TargetRow(mid, mid.upper(), provider, region, site, site.title(), when)


TARGETS = [
    _target("im-2", "IM", "south_polar", "site-a", "2025-03-06"),
    _target("im-4", "IM", "south_polar", "site-b", ""),
    _target("griffin-1", "Voyager", "south_polar", "site-c", "2026-01-01"),
    _target("bg-1", "Firefly", "nearside", "site-d", "2025-03-02"),
]


def test_an_example_site_is_the_providers_latest_target_in_the_region() -> None:
    c = core.default_site("ct-4", "IM", "south_polar", TARGETS)
    assert c is not None and c.value == "site-b"  # undated planned counts as latest
    assert "IM-4" in (c.note or "") and "this provider's" in (c.note or "")
    # No region published: the south pole. Another provider's: the latest CLPS polar target.
    other = core.default_site("cs-8", None, None, TARGETS)
    assert other is not None and other.value == "site-b"
    assert "the CLPS list's" in (other.note or "")


def test_an_example_site_keeps_a_published_region_and_never_makes_one_up() -> None:
    near = core.default_site("bg-3", "Firefly", "nearside", TARGETS)
    assert near is not None and near.value == "site-d"
    assert core.default_site("bg-2", "Firefly", "farside", TARGETS) is None
    assert core.default_site("im-4", "IM", "south_polar", TARGETS[1:2]) is None  # not itself


def test_an_example_landing_day_says_where_it_came_from() -> None:
    today = date(2026, 11, 13)
    year = {"date": "2028-01-01", "precision": "year", "as_published": "2028"}
    assert core.default_landing(year, None, today).value == "2028-01-01"  # type: ignore[union-attr]
    launch = core.default_landing(None, {"date": "2027-01-01", "as_published": "2027"}, today)
    assert launch is not None and launch.value == "2027-01-06" and "5 days" in (launch.note or "")
    none = core.default_landing(None, None, today)
    assert none is not None and none.value == "2027-01-01" and "not a plan" in (none.note or "")


def test_an_example_trip_is_a_named_flight_of_the_same_provider_first() -> None:
    rows = [
        FlightRow("im-2", "IM-2", "IM", "Nova-C", "2025-03-06", "falcon-9", "lc-39a"),
        FlightRow("bg-1", "BG-1", "Firefly", "Blue Ghost", "2025-03-02", "falcon-9", "lc-39a"),
    ]
    assert core.trip_precedent("Firefly", None, rows).mission_id == "bg-1"  # type: ignore[union-attr]
    assert core.trip_precedent("Voyager", None, rows).mission_id == "im-2"  # type: ignore[union-attr]
    assert core.trip_precedent(None, None, []) is None
