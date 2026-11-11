"""A file read into the project form: the rules reader, the model guard, and the service
fallback with no model key. No database, no network, no model."""

from __future__ import annotations

from typing import Any

import pytest

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
