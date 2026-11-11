"""A file read into the project form: the rules reader, the model guard, and the service
fallback with no model key. No database, no network, no model."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents import base
from app.agents import intake as reader
from app.agents.base import GeminiUnavailable
from app.config import get_settings
from app.services import audit_service, intake_service, settings_service
from app.services.auth_service import Claims

# The keys the form relies on (the fields dict has one entry per form field looked for).
EXPECTED_KEYS = {
    "name",
    "provider",
    "lander",
    "vehicle_name",
    "task_order",
    "status",
    "target",
    "target.site_id",
    "target.name",
    "target.lat_deg",
    "target.lon_deg",
    "launch.date",
    "landing.date",
    "end_of_mission.date",
    "planned_surface_days",
    "lifecycle.vehicle_id",
    "lifecycle.pad_id",
    "lifecycle.transfer_type",
    "lifecycle.flight_days",
    "lifecycle.mass_kg",
    "lifecycle.relays",
    "payloads",
    "notes",
}

TEXT = """\
Mission: Athena Two
Provider: Intuitive Machines
Landing date: 14 March 2027
Landing site: lat -84.5 lon 30.25
Days on the surface: 12 days
Lander mass: 1,900 kg
Payloads:
- Neutron spectrometer
"""
LEX = reader.Lexicon(providers=("Intuitive Machines",))
NAMED = Claims(
    subject="pm", role="project_manager", issued_at=0, expires_at=9, user_id=7, name="Dana"
)


def test_rules_read_what_the_file_says_and_leave_the_rest_unknown() -> None:
    r = reader.read_rules(reader.Doc.from_text(TEXT), LEX)
    assert r.draft["name"] == "Athena Two"
    assert r.draft["provider"] == "Intuitive Machines"
    assert r.draft["landing"]["date"].startswith("2027-03-14")
    assert r.draft["target"]["lat_deg"] == -84.5
    assert r.fields["name"]["confidence"] == "stated"
    assert r.fields["name"]["evidence"] and len(r.fields["name"]["evidence"]) <= 240
    # Nothing the file does not say is guessed.
    assert "launch" not in r.draft and "lander" not in r.draft
    assert r.fields["launch.date"]["confidence"] == "not_found"
    assert r.fields["launch.date"]["note"]


def test_every_form_field_has_an_entry_in_fields() -> None:
    r = reader.read_rules(reader.Doc.from_text(TEXT), LEX)
    assert set(r.fields) >= EXPECTED_KEYS
    assert r.fields["target.lat_deg"]["confidence"] == "stated"
    assert r.fields["target.site_id"]["confidence"] == "not_found"
    empty = reader.assemble([], [])
    assert set(empty.fields) >= EXPECTED_KEYS
    assert all(f["confidence"] == "not_found" for f in empty.fields.values())


def test_the_draft_is_kept_inside_what_the_form_takes() -> None:
    r = reader.assemble(
        [
            reader.Found("planned_surface_days", 99999.0, "stated", "99999 days", 1),
            reader.Found("name", "N" * 400, "stated", "N", 1),
        ],
        [],
    )
    r = intake_service.fit(r)
    assert "planned_surface_days" not in r.draft
    assert r.fields["planned_surface_days"]["confidence"] == "not_found"
    assert len(r.draft["name"]) == 160


def test_the_model_guard_drops_a_value_the_file_does_not_contain() -> None:
    doc = reader.Doc.from_text(TEXT)
    said = reader.ModelReading.model_validate(
        {
            "name": {"value": "Athena Two", "evidence": "Mission: Athena Two"},
            "provider": {"value": "Lunar Corp", "evidence": "Provider: Lunar Corp"},
            "mass_kg": {"value": 1234.0, "evidence": "Lander mass: 1,234 kg"},
        }
    )
    r = reader.verify(said, doc, LEX)
    assert r.draft["name"] == "Athena Two"
    assert "provider" not in r.draft
    assert "mass_kg" not in r.draft.get("lifecycle", {})
    assert r.fields["provider"]["confidence"] == "not_found"


def test_decoding_and_extensions() -> None:
    assert intake_service.extension("Plan.PDF") == "pdf"
    with pytest.raises(intake_service.BadFile):
        intake_service.extension("plan.exe")
    assert intake_service.clean_filename("C:\\x\\..\\plan.txt") == "plan.txt"
    text, note = intake_service.decode("caf\u00e9".encode("cp1252"))
    assert text == "caf\u00e9" and note
    with pytest.raises(intake_service.BadFile):
        intake_service.extract(b"", "txt")
    with pytest.raises(intake_service.BadFile):
        intake_service.extract(b"not a pdf", "pdf")


def test_csv_and_json_become_labelled_lines() -> None:
    got = intake_service.extract(b"Mission,Athena\nProvider,Acme\n", "csv")
    assert "Mission: Athena" in got.doc.text
    got = intake_service.extract(b'{"mission_name": "Athena", "payloads": ["A", "B"]}', "json")
    assert "mission name: Athena" in got.doc.text and "payloads: A, B" in got.doc.text


async def test_with_no_model_key_the_file_is_read_by_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    saved: dict[str, Any] = {}

    class FakeRepo:
        def __init__(self, _s: Any) -> None: ...

        async def save_intake(self, **kw: Any) -> int:
            saved.update(kw)
            return 5

    async def lexicon(_s: Any) -> reader.Lexicon:
        return LEX

    async def ai(_s: Any) -> Any:
        return type("AI", (), {"enabled": False, "models": [], "models_light": []})()

    async def audit(*_a: Any, **kw: Any) -> None:
        saved["audit"] = kw

    async def never(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("the model must not be called")

    monkeypatch.setattr(intake_service, "ProjectRepository", FakeRepo)
    monkeypatch.setattr(intake_service, "lexicon", lexicon)
    monkeypatch.setattr(settings_service, "ai_settings", ai)
    monkeypatch.setattr(audit_service, "record", audit)
    monkeypatch.setattr(reader, "read_with_model", never)
    out = await intake_service.read_file(None, NAMED, TEXT.encode(), "plan.txt", None)  # type: ignore[arg-type]
    assert out["method"] == "rules" and out["model"] is None
    assert out["intake_id"] == 5 and out["media_type"] == "text/plain"
    assert out["draft"]["name"] == "Athena Two"
    assert set(out["fields"]) >= EXPECTED_KEYS
    assert out["characters_read"] == len(TEXT.rstrip("\n").replace("\r", ""))
    assert saved["audit"]["entity"] == "intake"


async def test_an_unnamed_session_cannot_read_a_file() -> None:
    from app.services import audit_service

    nobody = Claims(subject="pm", role="project_manager", issued_at=0, expires_at=9)
    with pytest.raises(audit_service.NotNamed):
        await intake_service.read_file(None, nobody, b"x", "a.txt", None)  # type: ignore[arg-type]


async def test_a_model_that_is_unavailable_falls_back_to_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRepo:
        def __init__(self, _s: Any) -> None: ...

        async def save_intake(self, **_kw: Any) -> int:
            return 1

    async def lexicon(_s: Any) -> reader.Lexicon:
        return LEX

    async def ai(_s: Any) -> Any:
        return type("AI", (), {"enabled": True, "models": ["m"], "models_light": ["m"]})()

    async def unavailable(*_a: Any, **_k: Any) -> Any:
        raise GeminiUnavailable("no key")

    async def audit(*_a: Any, **_k: Any) -> None: ...

    monkeypatch.setattr(intake_service, "ProjectRepository", FakeRepo)
    monkeypatch.setattr(intake_service, "lexicon", lexicon)
    monkeypatch.setattr(settings_service, "ai_settings", ai)
    monkeypatch.setattr(audit_service, "record", audit)
    monkeypatch.setattr(reader, "read_with_model", unavailable)
    real = get_settings()
    monkeypatch.setattr(
        intake_service,
        "get_settings",
        lambda: real.model_copy(update={"agents_enabled": True}),
    )
    out = await intake_service.read_file(None, NAMED, TEXT.encode(), "plan.md", None)  # type: ignore[arg-type]
    assert out["method"] == "rules" and out["draft"]["name"] == "Athena Two"


# ---------------------------------------------------------------------------
# A live test's file: dates bound to their own cue, provider, name, payloads, site
# ---------------------------------------------------------------------------

BRIEF = """\
Mission brief: Aurora Scout 1
Provider: Intuitive Machines. Lander: Nova-C.
Launch vehicle: Falcon 9 from LC-39A, Kennedy Space Center.
Planned launch: 14 March 2028. Landing planned for 21 March 2028.
Landing site: Shackleton rim, near 89.45 S, 137.3 W.
Surface operations: 10 days.
Payloads: a neutron spectrometer (4.2 kg) and a laser retroreflector (0.3 kg).
"""
BRIEF_LEX = reader.Lexicon(
    vehicles=(reader.vehicle_names("falcon-9-block-5", "Falcon 9 Block 5"),),
    pads=(reader.pad_names("lc-39a", "Launch Complex 39A"),),
    providers=("Intuitive Machines",),
    landers=("Nova-C",),
    sites=(reader.SiteName("shackleton-rim", "Shackleton rim", -89.45, 222.7),),
)


def _brief() -> reader.Reading:
    return reader.read_rules(reader.Doc.from_text(BRIEF), BRIEF_LEX)


def test_each_date_binds_to_its_own_cue() -> None:
    r = _brief()
    assert r.draft["launch"]["date"] == "2028-03-14"
    assert r.draft["landing"]["date"] == "2028-03-21"
    assert r.draft["landing"]["precision"] == "day"
    assert r.fields["landing.date"]["confidence"] == "stated"
    assert "21 March 2028" in r.fields["landing.date"]["evidence"]
    assert "14 March 2028" in r.fields["launch.date"]["evidence"]
    assert r.draft["planned_surface_days"] == 10.0


def test_dates_without_a_cue_each_stay_not_found() -> None:
    for text in (
        "The dates are 14 March 2028 and 21 March 2028.",
        "Launch and landing planned for 14 March 2028 and 21 March 2028.",
        "Dates: 14 March 2028 and 21 March 2028.",
    ):
        r = reader.read_rules(reader.Doc.from_text(text), BRIEF_LEX)
        assert "launch" not in r.draft and "landing" not in r.draft, text
        assert r.fields["launch.date"]["confidence"] == "not_found", text
        assert r.fields["landing.date"]["confidence"] == "not_found", text


def test_a_date_after_its_cue_in_one_clause_and_one_per_clause() -> None:
    r = reader.read_rules(reader.Doc.from_text("Launch: 14 Mar. 2028; landing: 21 Mar. 2028."), LEX)
    assert r.draft["launch"]["date"] == "2028-03-14"
    assert r.draft["landing"]["date"] == "2028-03-21"
    r = reader.read_rules(reader.Doc.from_text("On 21 March 2028 the lander lands."), LEX)
    assert r.draft["landing"]["date"] == "2028-03-21"


def test_provider_stops_at_the_sentence_end_and_takes_the_catalogue_spelling() -> None:
    r = _brief()
    assert r.draft["provider"] == "Intuitive Machines"
    assert r.draft["lander"] == "Nova-C"
    lower = reader.read_rules(
        reader.Doc.from_text("Provider: intuitive machines, Inc. Lander: Nova-C."), BRIEF_LEX
    )
    assert lower.draft["provider"] == "Intuitive Machines"
    assert lower.fields["provider"]["confidence"] == "stated"


def test_the_mission_name_comes_from_its_label_or_a_title_line() -> None:
    r = _brief()
    assert r.draft["name"] == "Aurora Scout 1"
    assert r.fields["name"]["confidence"] == "stated"
    for text in ("Mission name: Aurora Scout 1", "Mission: Aurora Scout 1"):
        got = reader.read_rules(reader.Doc.from_text(text), LEX)
        assert got.draft["name"] == "Aurora Scout 1"
        assert got.fields["name"]["confidence"] == "stated"
    title = reader.read_rules(
        reader.Doc.from_text("# Aurora Scout 1\nPlanned launch: 14 March 2028."), LEX
    )
    assert title.draft["name"] == "Aurora Scout 1"
    assert title.fields["name"]["confidence"] == "inferred"
    sentence = reader.read_rules(reader.Doc.from_text("The lander is planned for 2028."), LEX)
    assert sentence.draft["name"] == ""
    assert sentence.fields["name"]["confidence"] == "not_found"


def test_payloads_on_one_line_come_with_their_masses() -> None:
    r = _brief()
    pays = r.draft["payloads"]
    assert [p["name"] for p in pays] == ["Neutron spectrometer", "Laser retroreflector"]
    assert "4.2 kg" in pays[0]["purpose"] and "0.3 kg" in pays[1]["purpose"]
    assert r.fields["payloads"]["confidence"] == "stated"
    kept = intake_service.fit(r).draft["payloads"]
    assert [p["name"] for p in kept] == ["Neutron spectrometer", "Laser retroreflector"]
    one = reader.read_rules(
        reader.Doc.from_text("Payloads: neutron and gamma-ray spectrometer, Alpha, Beta"), LEX
    )
    assert [p["name"] for p in one.draft["payloads"]] == [
        "Neutron and gamma-ray spectrometer",
        "Alpha",
        "Beta",
    ]


def test_a_named_site_and_coordinates_keep_the_coordinates_and_offer_the_site() -> None:
    r = _brief()
    t = r.draft["target"]
    assert "site_id" not in t  # the form takes a site or a coordinate, not both
    assert t["lat_deg"] == -89.45 and round(t["lon_deg"], 3) == 222.7
    assert t["name"] == "Shackleton rim"
    site = r.fields["target.site_id"]
    assert site["confidence"] == "inferred" and "shackleton-rim" in site["note"]
    assert "Shackleton rim" in site["evidence"]
    assert r.fields["target.lat_deg"]["confidence"] == "stated"
    # The form's own schema takes the draft as it is.
    from app.api.v1.schemas.projects import ProjectDraft

    ProjectDraft.model_validate(intake_service.fit(r).draft)


def test_a_named_site_alone_matches_the_catalogue_by_name() -> None:
    lex = reader.Lexicon(
        sites=(
            reader.SiteName("shackleton-east", "Shackleton rim, east shoulder", -89.5, 120.0),
            reader.SiteName("connecting-ridge", "Connecting Ridge", -89.4, 0.0),
        )
    )
    r = reader.read_rules(reader.Doc.from_text("Landing site: Shackleton rim."), lex)
    assert r.draft["target"] == {"site_id": "shackleton-east"}
    assert r.fields["target"]["confidence"] == "inferred"  # a part of the name, said so
    exact = reader.read_rules(reader.Doc.from_text("Landing site: Connecting Ridge."), lex)
    assert exact.draft["target"] == {"site_id": "connecting-ridge"}
    assert exact.fields["target"]["confidence"] == "stated"


def test_the_catalogue_names_in_the_brief_are_found_too() -> None:
    r = _brief()
    assert r.draft["lifecycle"]["vehicle_id"] == "falcon-9-block-5"
    assert r.draft["lifecycle"]["pad_id"] == "lc-39a"


# ---------------------------------------------------------------------------
# The model chain: a timeout on one model moves on to the next
# ---------------------------------------------------------------------------


async def _noop_run(*_a: Any, **_k: Any) -> None: ...


def _chains(monkeypatch: pytest.MonkeyPatch) -> None:
    base.reset_model_cooldowns()
    monkeypatch.setattr(reader, "record_run", _noop_run)


async def _read(models: tuple[str, ...], light: tuple[str, ...]) -> tuple[reader.Reading, str]:
    rt = base.AgentRuntime(enabled=True, models=models, models_light=light)
    with base.agent_runtime(rt):
        return await reader.read_with_model(
            None,  # type: ignore[arg-type]
            reader.Doc.from_text(BRIEF),
            BRIEF_LEX,
            filename="brief.txt",
            data=BRIEF.encode(),
            media_type="text/plain",
            is_pdf=False,
        )


async def test_a_model_that_times_out_hands_over_to_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _chains(monkeypatch)
    asked: list[tuple[str, float]] = []

    async def fake(model: str, *_a: Any, timeout_s: float, **_k: Any) -> dict[str, Any]:
        asked.append((model, timeout_s))
        if model == "slow":
            raise TimeoutError
        return {
            "text": json.dumps({"name": {"value": "Aurora Scout 1", "evidence": BRIEF[:29]}}),
            "prompt_tokens": 1,
            "completion_tokens": 1,
        }

    monkeypatch.setattr(base, "_generate", fake)
    reading, model = await _read(("slow", "fast"), ("light",))
    assert model == "fast" and [m for m, _ in asked] == ["slow", "fast"]
    assert all(t <= reader.MODEL_TIMEOUT_S for _, t in asked)
    assert reading.draft["name"] == "Aurora Scout 1"


async def test_the_light_chain_is_tried_when_the_main_chain_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _chains(monkeypatch)
    asked: list[str] = []

    async def fake(model: str, *_a: Any, **_k: Any) -> dict[str, Any]:
        asked.append(model)
        if model == "light":
            return {"text": "{}", "prompt_tokens": 1, "completion_tokens": 1}
        raise TimeoutError

    monkeypatch.setattr(base, "_generate", fake)
    _, model = await _read(("a", "b"), ("light",))
    assert asked == ["a", "b", "light"] and model == "light"


async def test_every_model_timing_out_stops_within_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _chains(monkeypatch)
    clock = [0.0]
    asked: list[str] = []

    async def fake(model: str, *_a: Any, timeout_s: float, **_k: Any) -> dict[str, Any]:
        asked.append(model)
        clock[0] += timeout_s  # each call uses up all it was allowed
        raise TimeoutError

    monkeypatch.setattr(base, "_generate", fake)
    fake_time = SimpleNamespace(monotonic=lambda: clock[0], perf_counter=lambda: 0.0)
    monkeypatch.setattr(reader, "time", fake_time)
    with pytest.raises(reader.ModelFailed, match="did not answer in time"):
        await _read(tuple(f"m{i}" for i in range(10)), ())
    assert 2 <= len(asked) <= 4
    assert clock[0] <= reader.MODEL_BUDGET_S
