"""The readiness state machine (ADR-17)."""

from __future__ import annotations

import pytest

from app.core import readiness as r

EV = "https://example.org/report.pdf"


def move(to: str, **k: str) -> r.Move:
    return r.Move(
        to=to,  # type: ignore[arg-type]
        date=k.get("date", "2026-09-27"),
        evidence_url=k.get("ev", EV),
        note=k.get("note"),
        blocked_reason=k.get("reason"),
    )


def test_forward_one_step_only() -> None:
    assert r.check("payload", "in_build", None, move("in_test")) is None
    with pytest.raises(r.IllegalMove) as e:
        r.check("payload", "in_build", None, move("ready"))
    assert "in_test" in e.value.allowed and "ready" not in e.value.allowed


def test_back_needs_a_note() -> None:
    with pytest.raises(ValueError, match="note"):
        r.check("payload", "in_test", None, move("in_build"))
    assert (
        r.check("payload", "in_test", None, move("in_build", note="vibration test failed")) is None
    )


def test_blocked_needs_a_reason_and_remembers_where_it_was() -> None:
    with pytest.raises(ValueError, match="reason"):
        r.check("payload", "integrated", None, move("blocked"))
    assert (
        r.check("payload", "integrated", None, move("blocked", reason="connector damaged"))
        == "integrated"
    )
    allowed = r.allowed_moves("payload", "blocked", "integrated")
    assert allowed[-1] == "integrated" and "verified_on_lander" not in allowed


def test_every_change_needs_a_date_and_evidence() -> None:
    with pytest.raises(ValueError, match="date"):
        r.check("payload", "not_started", None, r.Move(to="in_build", date=None, evidence_url=EV))
    with pytest.raises(ValueError, match="evidence"):
        r.check(
            "payload",
            "not_started",
            None,
            r.Move(to="in_build", date="2026-01-01", evidence_url=None),
        )
    with pytest.raises(ValueError, match="evidence"):
        r.check(
            "payload",
            "not_started",
            None,
            r.Move(to="in_build", date="2026-01-01", evidence_url="see email"),
        )


def test_agreements_have_a_short_ladder() -> None:
    assert r.ladder("licence") == ("not_started", "in_build", "ready")
    with pytest.raises(r.IllegalMove):
        r.check("licence", "in_build", None, move("in_test"))
    assert r.check("licence", "in_build", None, move("ready")) is None


def test_the_lander_is_not_delivered_to_itself() -> None:
    assert "delivered" not in r.ladder("lander")
    assert "verified_on_lander" not in r.ladder("lander")


def test_moving_to_the_same_state_is_refused() -> None:
    with pytest.raises(r.IllegalMove, match="already"):
        r.check("payload", "in_build", None, move("in_build"))


def test_counts_include_every_state_and_no_percentage() -> None:
    c = r.counts(["ready", "ready", "blocked"])
    assert set(c) == set(r.STATES)
    assert c["ready"] == 2 and c["blocked"] == 1 and c["in_build"] == 0
    assert all(isinstance(v, int) for v in c.values())


@pytest.mark.parametrize("kind", sorted(r.LADDERS))
def test_every_ladder_can_reach_ready_one_step_at_a_time(kind: str) -> None:
    state: str = "not_started"
    for nxt in r.ladder(kind)[1:]:
        r.check(kind, state, None, move(nxt))  # type: ignore[arg-type]
        state = nxt
    assert state == "ready"
