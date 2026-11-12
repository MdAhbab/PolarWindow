"""Ask: the quick chat. The request shape, the answer built from tool results when no model
answers, and the grounding guard on every sentence. No database, no model."""

from __future__ import annotations

import re
from typing import Any

import pytest
from pydantic import ValidationError

from app.agents import chatter, tools
from app.api.v1.schemas.agents import ChatRequest, ChatResult
from app.tests.unit.test_ask_tools import fake_services


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


# ---------------------------------------------------------------------------
# O1: the page's context, hours with margins, names for links, the open scenario
# ---------------------------------------------------------------------------

#: A field name or any other snake_case word: never in words a person reads.
SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")
#: Words that never appear (`docs/design-glossary.md`).
NEVER = re.compile(r"\b(best|safest|recommended|score|likely|chance|overall rank)\b", re.I)


def test_the_context_takes_the_compared_sites_the_order_and_a_figure() -> None:
    ok = ChatRequest.model_validate(
        {
            "messages": [msg("user", "Which keeps contact longest?")],
            "context": {
                "path": "/compare",
                "compare_ids": ["connecting-ridge", "malapert-massif"],
                "rank_by": "earth_contact_s",
                "figure_key": "data.longest_dark_s",
            },
        }
    )
    assert ok.context is not None and ok.context.compare_ids == [
        "connecting-ridge",
        "malapert-massif",
    ]
    ChatRequest.model_validate({"messages": [msg("user", "q")], "context": {"path": "/x"}})
    for bad in (
        {"compare_ids": [f"s{i}" for i in range(9)]},  # more than eight
        {"compare_ids": [""]},
        {"compare_ids": ["x" * 161]},
        {"rank_by": "score"},
        {"figure_key": "x" * 65},
        {"figure_key": "longest dark; drop"},
    ):
        with pytest.raises(ValidationError):
            ChatRequest.model_validate(
                {"messages": [msg("user", "q")], "context": {"path": "/x", **bad}}
            )


def test_a_figure_key_is_read_as_the_figure_it_names() -> None:
    assert chatter.figure_of("longest_dark") == "longest_dark"
    assert chatter.figure_of("data.longest_dark_s") == "longest_dark"
    assert chatter.figure_of("data.heard_h.value") == "heard"
    assert chatter.figure_of("sunlit_tolerance_s") == "sunlit"
    assert chatter.figure_of("") is None and chatter.figure_of(None) is None
    assert chatter.figure_words("longest_blackout") == "Longest time without contact"
    assert chatter.figure_words("wave_height_m") == "Wave height"


async def _route(
    monkeypatch: pytest.MonkeyPatch, question: str, ctx: dict[str, Any]
) -> tuple[chatter.Intent, list[tools.ToolCallLog], dict[str, Any]]:
    """Rules read the question against canned services; the answer without a model."""
    fake_services(monkeypatch)
    intent, calls = await chatter.route(None, question, ctx)  # type: ignore[arg-type]
    req = {
        "question": question,
        "earlier_questions": [],
        "context": ctx,
        "mission_id": intent.mission_id,
        "section": intent.section,
    }
    return intent, calls, chatter.deterministic_answer(calls, "No model.", req)


def _readable(out: dict[str, Any]) -> str:
    return " ".join([out["answer"] or "", out["interpreted_as"] or "", *out["follow_ups"]])


async def test_the_longest_night_here_is_in_hours_with_its_margin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = {"path": "/site", "site_id": "connecting-ridge"}
    intent, calls, out = await _route(monkeypatch, "How long is the longest night here?", ctx)
    assert [c.tool for c in calls] == ["list_missions", "get_site", "get_metrics"]
    assert out["status"] == "ok"
    assert out["answer"].startswith(
        "Longest night at Connecting Ridge, 14 Mar 2027, 00:00 UTC to 12 Apr 2027, 12:45 UTC: "
        "122 h ± 17.1 h, worked out."
    )
    assert "Also worked out there, longest time without contact: 278 h ± 5.3 h" in out["answer"]
    text = _readable(out)
    assert "second" not in text.lower() and not SNAKE.search(text)
    assert "connecting-ridge" not in text
    assert out["interpreted_as"].endswith("about Connecting Ridge.")
    acts = chatter.actions(calls, ctx, intent)
    assert acts == [{"label": "Connecting Ridge", "href": "/site?site=connecting-ridge"}]
    # No mission on a site page: "night" names a number, not a step.
    prompt = chatter._prompt(
        [msg("user", "How long is the longest night here?")], ctx, intent, calls
    )
    assert "step Surface" not in prompt and "site Connecting Ridge" in prompt


async def test_when_the_night_starts_reads_the_stretches(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = {"path": "/plan", "site_id": "connecting-ridge"}
    _i, calls, out = await _route(monkeypatch, "When does the longest night start?", ctx)
    assert "get_windows" in [c.tool for c in calls]
    assert "The longest night is 122 h ± 17.1 h, from 20 Mar 2027, 06:00 UTC" in out["answer"]


async def test_an_open_scenario_is_read_named_and_never_told_as_the_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = {
        "path": "/missions/im-3/launch",
        "mission_id": "im-3",
        "section": "launch",
        "scenario_id": "sc-6e203e416683",
    }
    intent, calls, out = await _route(monkeypatch, "When can it launch?", ctx)
    tools_called = [c.tool for c in calls]
    assert "get_scenario" in tools_called
    assert next(c for c in calls if c.tool == "get_scenario").args == {
        "scenario_id": "sc-6e203e416683",
        "section": "launch",
    }
    # The step is told from the scenario, not the mission's record.
    assert "get_mission_sections" not in tools_called
    assert intent.scenario_name and intent.scenario_name.startswith("Defaults from past flights")
    a = out["answer"]
    assert a.startswith('This is about the scenario "Defaults from past flights:')
    assert "never the mission's record" in a
    assert "Launch in this scenario: 12 launch opportunities" in a
    assert "Days on the surface 15 days (You)" in a
    assert "(Default)" in a
    assert "The scenario as a whole: worked out, except trip" in a
    assert 'in the scenario "Defaults from past flights' in out["interpreted_as"]
    assert out["follow_ups"][0] == (
        "What does this scenario assume, and where does each value come from?"
    )
    acts = chatter.actions(calls, ctx, intent)
    assert acts[0] == {
        "label": "IM-3 · Launch in this scenario",
        "href": "/missions/im-3/launch?scenario=sc-6e203e416683",
    }
    prompt = chatter._prompt([msg("user", "When can it launch?")], ctx, intent, calls)
    assert 'the scenario "Defaults from past flights' in prompt and "name it" in prompt


async def test_what_a_scenario_assumes_lists_every_value_with_its_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = {"path": "/missions/im-3/launch", "mission_id": "im-3", "section": "launch"}
    ctx["scenario_id"] = "sc-6e203e416683"
    _i, _c, out = await _route(
        monkeypatch, "What does this scenario assume, and where does each value come from?", ctx
    )
    a = out["answer"]
    assert "It assumes: Launch vehicle Falcon 9 Block 5 (Default, Precedent: IM-2)" in a
    assert "Landing spot Reiner Gamma (Published, NASA CLPS page)" in a


async def test_the_scenario_surface_is_in_hours_and_a_missing_step_says_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = {"path": "/missions/im-3", "mission_id": "im-3", "scenario_id": "sc-6e203e416683"}
    _i, _c, out = await _route(
        monkeypatch, "How long is the night?", {**base, "section": "landing"}
    )
    assert (
        "Surface in this scenario, 1 Jan 2027 to 15 Jan 2027, worked out from its assumed "
        "values, longest night: at least 360 h (no margin is worked out" in out["answer"]
    )
    _i, _c, out = await _route(monkeypatch, "What about contact?", {**base, "section": "contact"})
    assert "Contact in this scenario: not worked out, needs a landing date." in out["answer"]


async def test_a_scenario_that_cannot_be_read_is_said_so_not_passed_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = {
        "path": "/missions/im-3/launch",
        "mission_id": "im-3",
        "section": "launch",
        "scenario_id": "sc-gone",
    }
    intent, calls, out = await _route(monkeypatch, "When can it launch?", ctx)
    assert intent.scenario_unread and intent.scenario_id is None
    assert "get_mission_sections" in [c.tool for c in calls]
    assert out["answer"].startswith(
        "The scenario open on the page could not be read, so this answer is from the "
        "mission's record. Launch for IM-3: 12 launch opportunities."
    )
    prompt = chatter._prompt([msg("user", "When?")], ctx, intent, calls)
    assert "could not be read: answer from the mission's record" in prompt


async def test_a_scenario_of_another_mission_is_not_read_when_the_question_names_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = {"path": "/missions/im-3/launch", "mission_id": "im-3", "scenario_id": "sc-6e203e416683"}
    _i, calls, _o = await _route(monkeypatch, "When did IM-2 launch?", ctx)
    assert "get_scenario" not in [c.tool for c in calls]


async def test_compare_answers_about_the_compared_sites_by_one_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = {
        "path": "/compare",
        "site_id": "feature-reiner-gamma",  # the last site opened: not what is asked about
        "compare_ids": ["connecting-ridge", "malapert-massif"],
        "rank_by": "longest_dark_s",
    }
    intent, calls, out = await _route(
        monkeypatch, "Which of these has the shortest longest night?", ctx
    )
    assert [c.tool for c in calls] == ["list_missions", "compare_sites"]
    assert calls[1].args["site_ids"] == ["connecting-ridge", "malapert-massif"]
    assert calls[1].args["rank_by"] == "longest_dark_s"
    assert intent.compare_names == ["Connecting Ridge", "Malapert massif"]
    a = out["answer"]
    # The dates are the comparison's own (the reference dates when the page sends none).
    assert a.startswith("Ordered by longest night, shortest first (")
    assert "): Connecting Ridge, 122 h ± 17.1 h; Malapert massif, at least 288 h" in a
    assert "(somewhere from place 1 to 2 in this order)" in a
    assert "Connecting Ridge and Malapert massif are too close to call" in a
    assert not NEVER.search(_readable(out)) and "Reiner Gamma" not in a
    assert out["interpreted_as"].endswith("comparing Connecting Ridge and Malapert massif.")
    acts = chatter.actions(calls, ctx, intent)
    assert acts == [
        {
            "label": "Compare by longest night",
            "href": "/compare?sites=connecting-ridge,malapert-massif&rank=night",
        }
    ]
    prompt = chatter._prompt([msg("user", "Which?")], ctx, intent, calls)
    assert "comparing Connecting Ridge and Malapert massif" in prompt
    assert "answer about these sites" in prompt and "step Surface" not in prompt


async def test_compare_orders_by_the_number_the_question_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = {"path": "/compare", "compare_ids": ["connecting-ridge", "malapert-massif"]}
    _i, calls, out = await _route(monkeypatch, "Which keeps contact with Earth longest?", ctx)
    assert calls[1].args["rank_by"] == "earth_contact_s"
    _i, calls, _o = await _route(monkeypatch, "Why is it too close to call?", ctx)
    assert calls[1].args["rank_by"] == "longest_dark_s"  # neither the words nor the page say
    ctx["rank_by"] = "longest_blackout_s"
    _i, calls, _o = await _route(monkeypatch, "Why is it too close to call?", ctx)
    assert calls[1].args["rank_by"] == "longest_blackout_s"


async def test_a_figure_from_a_step_tile_reads_that_step(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = {
        "path": "/missions/im-2/contact",
        "mission_id": "im-2",
        "section": "contact",
        "figure_key": "heard",
    }
    intent, calls, out = await _route(monkeypatch, "How sure is this number?", ctx)
    sec = next(c for c in calls if c.tool == "get_mission_section")
    assert sec.args == {"mission_id": "im-2", "section": "contact"}
    # Whole hours from ten up, as the tiles write them, with the margin to a tenth.
    assert out["answer"].startswith(
        "Time a ground station can hear the lander for IM-2: 120 h ± 0.3 h, worked out."
    )
    prompt = chatter._prompt([msg("user", "How sure?")], ctx, intent, calls)
    assert 'one figure from its tile: "Time a ground station can hear the lander"' in prompt


async def test_a_figure_without_a_margin_says_why_not(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = {"path": "/missions/im-2/contact", "mission_id": "im-2", "section": "contact"}
    ctx["figure_key"] = "data.longest_message_wait_h.value"
    _i, _c, out = await _route(monkeypatch, "What sets this?", ctx)
    assert out["answer"].startswith(
        "Longest message wait for IM-2: 6.2 h (Relay passes are timed to the minute), worked out."
    )


async def test_a_site_figure_on_a_mission_reads_its_landing_spot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = {
        "path": "/missions/im-2/surface",
        "mission_id": "im-2",
        "section": "landing",
        "figure_key": "longest_blackout",
    }
    _i, calls, out = await _route(monkeypatch, "How sure is this?", ctx)
    metrics = next(c for c in calls if c.tool == "get_metrics")
    assert metrics.args["site_id"] == "connecting-ridge"  # IM-2's landing spot
    assert out["answer"].startswith("Longest time without contact at Connecting Ridge")


def test_link_labels_are_names_and_a_place_with_no_name_is_left_out() -> None:
    nameless = call(1, "list_missions", {"missions": [{"mission_id": "im-9", "status": "planned"}]})
    sections = call(2, "get_mission_sections", {"mission_id": "im-9", "sections": []})
    site = tools.ToolCallLog(3, "get_metrics", {"site_id": "x-ridge"}, {"site_id": "x-ridge"})
    intent = chatter.Intent(mission_id="im-9", section="launch")
    assert chatter.actions([nameless, sections, site], {"mission_id": "im-9"}, intent) == []
    acts = chatter.actions([MISSIONS, SECTIONS], {"path": "/missions"}, chatter.Intent())
    assert {a["label"] for a in acts} <= {"IM-3", "IM-3 · Launch"}
    assert all(not re.search(r"\b[a-z]+-[a-z0-9-]+\b", a["label"]) for a in acts)


def test_space_weather_is_in_plain_words_and_links_where_it_is_shown() -> None:
    weather = tools.ToolCallLog(
        2,
        "get_space_weather",
        {},
        {
            "data": {
                "now": {
                    "kp": {"value": 2.7},
                    "proton_10mev_pfu": {"value": 0.12},
                    "xray_class": "B",
                    "alerts": [],
                }
            }
        },
    )
    out = chatter.deterministic_answer(
        [MISSIONS, weather], "No model.", {"question": "What is the space weather now?"}
    )
    assert out["answer"] == (
        "Space weather now (NOAA): magnetic storm level 2.7 of 9 (Kp), fast protons 0.12 pfu, "
        "X-ray flares class B."
    )
    home = chatter.actions([weather], {"path": "/home"}, chatter.Intent())
    assert home == [{"label": "Space weather now", "href": "/home#home-live"}]
    planned = chatter.Intent(mission_id="im-3", names={"im-3": "IM-3"})
    acts = chatter.actions([MISSIONS, weather], {"path": "/missions/im-3"}, planned)
    assert acts[0] == {"label": "IM-3 · Launch: space weather now", "href": "/missions/im-3/launch"}


def test_follow_ups_use_the_glossary_and_a_flown_mission_looks_back() -> None:
    names = {"im-2": "IM-2", "im-3": "IM-3"}
    flown = chatter.follow_ups(names, {"mission_id": "im-2"}, status="partial_success")
    assert "When did IM-2 launch?" in flown
    assert "How long could NASA's deep-space dishes (Deep Space Network) hear IM-2?" in flown
    planned = chatter.follow_ups(names, {"mission_id": "im-3"}, status="planned")
    assert "When are IM-3's next launch opportunities?" in planned
    assert not chatter.follow_ups(names, {"mission_id": "im-3"}, status="cancelled")[0].startswith(
        "When"
    )
    site = chatter.follow_ups({}, {}, site=True)
    assert "How sure are these numbers?" in site
    for q in [*flown, *planned, *site, *chatter.follow_ups({}, {}, compare=True)]:
        # No figure in a question (a mission's name may hold a digit).
        assert q.endswith("?") and not re.search(r"\d", re.sub(r"IM-\d", "", q))
        assert not NEVER.search(q) and "blackout" not in q and "uncertainty" not in q


def test_the_system_prompt_speaks_the_glossary() -> None:
    s = " ".join(chatter.SYSTEM.split())
    assert "SECONDS" not in s and "Never write seconds" in s
    for words in (
        "steps (not sections)",
        "Time in contact with Earth",
        "launch opportunity",
        "Longest time without contact (not blackout)",
        'margin, or "how sure" (not uncertainty)',
        "never by their ids",
        "best, safest, recommended, score, likely, chance",
        "You, Published, Live or Default",
    ):
        assert words in s, words
    assert chatter.SPEC.tool_names == chatter.CHAT_TOOLS


async def test_chat_sends_the_new_context_through_to_the_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_services(monkeypatch)
    seen: dict[str, Any] = {}

    async def run_agent(
        _s: Any, _spec: Any, prompt: str, request: dict[str, Any], **kw: Any
    ) -> Any:
        seen["prompt"], seen["request"] = prompt, request
        answer = chatter.deterministic_answer(kw["prefetched"], "No model.", request)
        return type("O", (), {"result": answer, "tool_calls": kw["prefetched"]})()

    monkeypatch.setattr(chatter, "run_agent", run_agent)
    ctx = {"path": "/compare", "compare_ids": ["connecting-ridge", "malapert-massif"]}
    out = await chatter.chat(None, [msg("user", "Which has the shortest night?")], ctx)  # type: ignore[arg-type]
    assert out.result is not None
    ChatResult.model_validate(out.result)
    assert out.result["actions"][0]["label"] == "Compare by longest night"
    assert seen["request"]["context"]["compare_ids"] == ["connecting-ridge", "malapert-massif"]
    assert "Already retrieved:" in seen["prompt"] and "[2] compare_sites(" in seen["prompt"]
