"""Ask: the quick chat. The request shape, the answer built from tool results when no model
answers, and the grounding guard on every sentence. No database, no model."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.agents import chatter, tools
from app.api.v1.schemas.agents import ChatRequest, ChatResult


def msg(role: str, text: str) -> dict[str, str]:
    return {"role": role, "text": text}


def call(seq: int, tool: str, result: dict[str, Any]) -> tools.ToolCallLog:
    args = {"mission_id": result["mission_id"]} if "mission_id" in result else {}
    return tools.ToolCallLog(seq=seq, tool=tool, args=args, result=result)


MISSIONS = call(
    1, "list_missions", {"missions": [{"mission_id": "im-3", "name": "IM-3", "status": "planned"}]}
)
SECTIONS = call(
    2,
    "get_mission_sections",
    {
        "mission_id": "im-3",
        "sections": [
            {"section": "launch", "state": "available", "summary": "3 launch opportunities"},
            {"section": "trip", "state": "no_data", "summary": ""},
        ],
    },
)
REQ = {"question": "When can IM-3 launch?", "mission_id": "im-3", "section": "launch"}


def test_the_request_is_bounded_and_ends_with_a_question() -> None:
    ChatRequest.model_validate({"messages": [msg("user", "hi")]})
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"messages": [msg("user", "hi"), msg("assistant", "yo")]})
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"messages": [msg("user", "q")] * 13})
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"messages": []})
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"messages": [msg("user", "q")], "context": {"nope": 1}})


def test_the_answer_without_a_model_comes_from_the_measurements() -> None:
    out = chatter.deterministic_answer([MISSIONS, SECTIONS], "No model is configured.", REQ)
    assert out["status"] == "ok" and out["reason"] == "No model is configured."
    assert "Launch for IM-3: 3 launch opportunities." in out["answer"]
    assert "simple rules" in out["interpreted_as"]
    assert len(out["follow_ups"]) <= 3


def test_nothing_matched_is_an_answer_that_says_so_not_a_guess() -> None:
    out = chatter.deterministic_answer([], "No model.", {"question": "what is 2+2"})
    assert out["status"] == "insufficient_data" and out["answer"] is None
    assert out["reason"]


def test_the_guard_refuses_a_number_no_tool_returned() -> None:
    pool = chatter._pool([MISSIONS, SECTIONS], REQ)
    assert chatter._grounded("Launch for IM-3: 3 launch opportunities.", pool)
    assert not chatter._grounded("Launch for IM-3: 42 launch opportunities.", pool)
    assert not chatter._grounded("Launch is on 2031-01-05.", pool)


def test_an_ungrounded_sentence_is_dropped_from_the_fallback() -> None:
    lie = call(
        2,
        "get_mission_sections",
        {
            "mission_id": "im-3",
            "sections": [{"section": "launch", "state": "available", "summary": ""}],
        },
    )
    pool = chatter._pool([MISSIONS, lie], REQ)
    rows = chatter.mission_sentences(lie.result or {}, "IM-3", "launch", pool)
    assert rows and all(chatter._grounded(r, pool) for r in rows)


def test_actions_are_in_app_paths_and_at_most_three() -> None:
    intent = chatter.Intent(mission_id="im-3", mission_name="IM-3", section="launch")
    acts = chatter.actions([MISSIONS, SECTIONS], {"path": "/missions"}, intent)
    assert 1 <= len(acts) <= 3
    assert all(a["href"].startswith("/") and "://" not in a["href"] for a in acts)
    assert any(a["href"] == "/missions/im-3/launch" for a in acts)


def test_a_chat_result_matches_the_contract() -> None:
    intent = chatter.Intent(mission_id="im-3", mission_name="IM-3", section="launch")
    out = chatter.deterministic_answer([MISSIONS, SECTIONS], "No model.", REQ)
    outcome = type("O", (), {"result": out, "tool_calls": [MISSIONS, SECTIONS]})()
    res = chatter.result_of(outcome, {"path": "/missions/im-3/launch"}, intent)
    assert res is not None
    ChatResult.model_validate(res)
    assert set(res) == {"answer", "interpreted_as", "follow_ups", "actions"}


async def test_chat_degrades_to_the_tools_when_the_model_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def execute(_s: Any, name: str, _args: dict[str, Any], seq: int) -> tools.ToolCallLog:
        return {
            "list_missions": call(seq, name, MISSIONS.result or {}),
            "get_mission_sections": call(seq, name, SECTIONS.result or {}),
        }[name]

    seen: dict[str, Any] = {}

    async def run_agent(
        _s: Any, _spec: Any, _prompt: str, request: dict[str, Any], **kw: Any
    ) -> Any:
        seen["prefetched"] = kw["prefetched"]
        seen["request"] = request
        answer = chatter.deterministic_answer(kw["prefetched"], "No model.", request)
        return type("O", (), {"result": answer, "tool_calls": kw["prefetched"]})()

    monkeypatch.setattr(tools, "execute", execute)
    monkeypatch.setattr(chatter, "run_agent", run_agent)
    out = await chatter.chat(
        None,  # type: ignore[arg-type]
        [msg("user", "Ask about IM-3 launch"), msg("assistant", "x"), msg("user", "IM-3 launch?")],
        {"path": "/missions/im-3"},
    )
    assert out.result is not None and out.result["answer"]
    # Only the person's own earlier words can be quoted.
    assert seen["request"]["earlier_questions"] == ["Ask about IM-3 launch"]
    assert seen["request"]["mission_id"] == "im-3"
    assert [c.tool for c in seen["prefetched"]][:2] == ["list_missions", "get_mission_sections"]


def test_the_prompt_says_what_day_it_is_so_a_past_launch_is_not_called_upcoming() -> None:
    intent = chatter.Intent()
    asked = [{"role": "user", "text": "Which mission launches next?"}]
    text = chatter._prompt(asked, {"path": "/home"}, intent, [], "2026-11-11")
    assert text.startswith("Today is 2026-11-11 (UTC).")
    assert "Today is" not in chatter._prompt(asked, {"path": "/home"}, intent, [])
    assert "today's date" in chatter.SYSTEM
