"""Named sign-in and the append-only, hash-chained change history (ADR-17)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import session_scope
from app.services import audit_service, auth_service

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]

API = "/api/v1"


async def test_sign_in_with_a_name_names_the_session(anon_client) -> None:
    r = await anon_client.post(
        f"{API}/auth/demo", json={"name": "  Ada   Lovelace ", "team": "Ops"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["name"] == "Ada Lovelace" and body["user"]["team"] == "Ops"
    me = await anon_client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {body['token']}"}
    )
    assert me.json()["user"] == body["user"]
    # The same name and team is the same person.
    again = await anon_client.post(f"{API}/auth/demo", json={"name": "ada lovelace", "team": "ops"})
    assert again.json()["user"]["id"] == body["user"]["id"]


async def test_one_click_sign_in_without_a_name_still_works(anon_client) -> None:
    r = await anon_client.post(f"{API}/auth/demo")
    assert r.status_code == 200
    assert r.json()["user"]["name"] == auth_service.DEFAULT_DEMO_NAME


async def test_an_unnamed_session_can_read_but_not_change(anon_client) -> None:
    token, _ = auth_service.issue_demo()  # no user: a pre-ADR-17 token
    h = {"Authorization": f"Bearer {token}"}
    assert (await anon_client.get(f"{API}/settings", headers=h)).status_code == 200
    r = await anon_client.post(f"{API}/settings/ai/reset", headers=h)
    assert r.status_code == 403
    assert r.json()["detail"]["type"].endswith("/name-needed")


async def test_a_control_character_in_a_name_is_refused(anon_client) -> None:
    r = await anon_client.post(f"{API}/auth/demo", json={"name": "Eve\x07"})
    assert r.status_code == 422


async def _who() -> auth_service.Claims:
    async with session_scope() as s:
        _, claims = await auth_service.sign_in(s, "Chain Tester", None)
    return claims


async def test_the_history_is_chained_and_verifies() -> None:
    who = await _who()
    async with session_scope() as s:
        a = await audit_service.record(
            s,
            who,
            action="create",
            entity="risk",
            entity_id="r-1",
            before=None,
            after={"title": "x", "likelihood": 2},
        )
        b = await audit_service.record(
            s,
            who,
            action="update",
            entity="risk",
            entity_id="r-1",
            before={"likelihood": 2},
            after={"likelihood": 3},
            note="new test data",
        )
    assert b.seq == a.seq + 1
    async with session_scope() as s:
        hist = await audit_service.history(s, "risk", "r-1")
        check = await audit_service.verify(s)
    assert [h["action"] for h in hist][-2:] == ["create", "update"]
    assert hist[-1]["by"] == "Chain Tester"
    assert check.intact and check.checked >= 2


async def test_the_history_cannot_be_edited_or_deleted() -> None:
    who = await _who()
    async with session_scope() as s:
        await audit_service.record(
            s, who, action="create", entity="part", entity_id="p-1", before=None, after={}
        )
    for stmt in (
        "UPDATE audit_log SET note = 'rewritten'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with session_scope() as s:
                await s.execute(text(stmt))


async def test_a_tampered_entry_is_found_by_verify() -> None:
    who = await _who()
    async with session_scope() as s:
        e = await audit_service.record(
            s,
            who,
            action="create",
            entity="booking",
            entity_id="b-1",
            before=None,
            after={"station": "DSS-14"},
        )
    # Tamper as the database owner would have to: switch the guard off, edit,
    # check, and roll the whole thing back so the test database stays clean.
    async with session_scope() as s:
        await s.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_update"))
        await s.execute(
            text('UPDATE audit_log SET after = \'{"station": "DSS-43"}\' WHERE seq = :q'),
            {"q": e.seq},
        )
        check = await audit_service.verify(s)
        assert not check.intact and check.first_bad == e.seq
        await s.rollback()
    async with session_scope() as s:
        assert (await audit_service.verify(s)).intact


async def test_an_unnamed_session_cannot_write_history() -> None:
    _, claims = auth_service.issue_demo()
    async with session_scope() as s:
        with pytest.raises(audit_service.NotNamed):
            await audit_service.record(
                s, claims, action="create", entity="risk", entity_id="r-2", before=None, after={}
            )
