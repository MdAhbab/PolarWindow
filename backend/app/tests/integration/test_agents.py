"""Agent orchestration: guard retries, degradation, and the run log.

No test reaches the real Gemini API. `respx` intercepts the SDK's HTTP
transport, and `conftest.no_live_gemini` blanks the key so a forgotten mock
fails loudly rather than costing money and flaking.

The scripted responses below are the interesting cases, not the happy path:
a hallucinated number, a schema violation, a timeout, a total outage. The happy
path is the one that would pass even if the guard did nothing.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

pytestmark = [pytest.mark.requires_db, pytest.mark.requires_kernels, pytest.mark.asyncio]

API = "/api/v1"
SITE = "connecting-ridge"
GEMINI = respx.patterns.M(
    host__in=["generativelanguage.googleapis.com", "aiplatform.googleapis.com"]
)


def gemini_text(payload: dict[str, Any]) -> httpx.Response:
    """A Gemini generateContent response carrying a JSON answer."""
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(payload)}], "role": "model"}}
            ],
            "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 60},
        },
    )


GROUNDED = {
    "status": "ok",
    "site_id": SITE,
    "paragraph": (
        "This site is sunlit for about 81% of the window, with Earth in view 61% "
        "of the time. The longest unbroken darkness is roughly 122 hours."
    ),
    "numbers_used": [],
}

HALLUCINATED = {
    "status": "ok",
    "site_id": SITE,
    "paragraph": "This site is sunlit for about 93% of the window, an unusually high figure.",
    "numbers_used": [],
}


async def test_agents_degrade_without_a_key(client) -> None:
    """The four numbers must work on a laptop with no API key at all.

    Not configuring the model is a degraded state, not an outage: the answer is
    generated from the measurements and labelled so nobody mistakes it for the
    written one.
    """
    r = await client.post(f"{API}/agents/explain", json={"site_id": SITE})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["reason"]
    assert body["result"]["paragraph"], "the degraded path produced nothing"
    assert body["run_id"], "a degraded run was not recorded"
    # The fallback is assembled from tool output, so it is grounded by construction.
    assert body["tool_calls"], "no tools were called before degrading"


async def test_happy_path_records_a_run_and_its_tools(client, fake_gemini) -> None:
    fake_gemini(GROUNDED)

    r = await client.post(f"{API}/agents/explain", json={"site_id": SITE})
    body = r.json()
    assert body["status"] == "ok", body.get("reason")
    assert body["result"]["paragraph"]
    assert body["provenance"], "a grounded answer produced no citations"
    assert body["run_id"]

    runs = (await client.get(f"{API}/agents/runs?limit=5")).json()["items"]
    assert runs[0]["id"] == body["run_id"]
    assert runs[0]["tool_calls"], "tool calls were not persisted"


async def test_guard_rejects_then_the_retry_succeeds(client, fake_gemini) -> None:
    """The mechanism the brief calls the most important guard, end to end."""
    fake_gemini(HALLUCINATED, GROUNDED)

    body = (await client.post(f"{API}/agents/explain", json={"site_id": SITE})).json()
    assert body["status"] == "ok", body.get("reason")
    assert body["attempts"] == 2, "the retry did not happen"
    assert body["guard_failures"], "the rejection was not recorded"
    assert any("93" in (g.get("detail") or "") for g in body["guard_failures"])
    assert "93" not in json.dumps(body["result"]), "the hallucinated figure survived"


async def test_two_rejections_degrade_and_never_render_the_bad_text(client, fake_gemini) -> None:
    """The strongest assertion in this file.

    If the guard fails twice, the ungrounded number must appear nowhere in the
    response -- not in the result, not in a partial, not anywhere a UI could
    render it.
    """
    fake_gemini(HALLUCINATED)

    body = (await client.post(f"{API}/agents/explain", json={"site_id": SITE})).json()
    assert body["status"] == "degraded"
    assert body["attempts"] == 2
    assert "93" not in json.dumps(body["result"])
    assert body["result"]["paragraph"], "degrading produced no answer at all"
    assert len(body["guard_failures"]) >= 2


async def test_schema_violation_is_retried(client, fake_gemini) -> None:
    fake_gemini("not json at all", GROUNDED)

    body = (await client.post(f"{API}/agents/explain", json={"site_id": SITE})).json()
    assert body["status"] == "ok", body.get("reason")
    assert body["attempts"] == 2
    assert any(g["kind"] == "schema_invalid" for g in body["guard_failures"])


async def test_timeout_degrades_within_the_budget(client, fake_gemini) -> None:
    """A demo that hangs on a model call is a failed demo."""
    fake_gemini(TimeoutError("model did not respond"))

    body = (await client.post(f"{API}/agents/explain", json={"site_id": SITE})).json()
    assert body["status"] == "degraded"
    assert body["result"]["paragraph"]
    assert body["latency_ms"] < 25_000


async def test_total_outage_degrades_rather_than_500s(client, fake_gemini) -> None:
    """Every other endpoint is unaffected; this one still answers."""
    fake_gemini(httpx.ConnectError("no route to host"))

    r = await client.post(f"{API}/agents/explain", json={"site_id": SITE})
    assert r.status_code == 200, "an LLM outage must not become an API error"
    body = r.json()
    assert body["status"] == "degraded"
    assert body["result"]["paragraph"]


async def test_advisor_must_state_a_negative_result(client, fake_gemini) -> None:
    """The named requirement in the brief: say plainly when nothing qualifies."""
    ranked_without_saying_so = {
        "status": "ok",
        "requirement_summary": "600 hours of continuous sunlight",
        "any_satisfies": False,
        "nothing_satisfies_message": None,
        "ranked": [
            {
                "site_id": SITE,
                "rank": 1,
                "satisfies_all": False,
                "checks": [{"requirement": "600 h sunlight", "satisfied": False}],
                "why": "closest available",
            }
        ],
    }
    honest = dict(
        ranked_without_saying_so,
        nothing_satisfies_message="No site in this set meets the requirement.",
    )
    fake_gemini(ranked_without_saying_so, honest)

    body = (
        await client.post(
            f"{API}/agents/advise", json={"requirement": "600 hours of continuous sunlight"}
        )
    ).json()
    assert body["attempts"] == 2, "the missing negative statement was not caught"
    assert any(g["kind"] == "missing_negative_statement" for g in body["guard_failures"])
    assert body["result"]["nothing_satisfies_message"]


async def test_asker_can_refuse_what_the_dataset_does_not_know(client, fake_gemini) -> None:
    fake_gemini(
        {
            "status": "insufficient_data",
            "reason": "This dataset holds no soil or regolith measurements.",
            "question": "which site has the best soil?",
            "interpreted_as": "a question about regolith properties",
        }
    )
    body = (
        await client.post(f"{API}/agents/ask", json={"question": "which site has the best soil?"})
    ).json()
    assert body["status"] == "insufficient_data"
    assert body["result"]["reason"]


async def test_tool_calls_are_executed_and_fed_back(client, fake_gemini) -> None:
    """A round of tool calls runs, is logged, and reaches the grounding pool."""
    fake_gemini(
        [{"name": "search_sites", "args": {"limit": 50}}],
        {
            "status": "ok",
            "question": "how many sites are there?",
            "answer": "There are 15 sites in this dataset.",
            "interpreted_as": "a count of all seeded sites",
            "rows": [],
        },
    )
    body = (await client.post(f"{API}/agents/ask", json={"question": "how many sites?"})).json()
    assert body["status"] == "ok", body.get("reason")
    assert any(c["tool"] == "search_sites" for c in body["tool_calls"])
    counts = [c["value"] for c in body["provenance"]]
    assert 15 in counts, f"the site count was not traced to a tool result: {counts}"


async def test_every_exit_path_persists_a_run(client) -> None:
    """The demo shows this table; a missing row for a failure would make it
    evidence of something other than what it claims."""
    before = len((await client.get(f"{API}/agents/runs?limit=200")).json()["items"])
    await client.post(f"{API}/agents/explain", json={"site_id": SITE})
    await client.post(f"{API}/agents/ask", json={"question": "which site is sunniest?"})
    after = (await client.get(f"{API}/agents/runs?limit=200")).json()["items"]
    assert len(after) >= before + 2
    for run in after[:2]:
        assert run["status"] in (
            "ok",
            "insufficient_data",
            "guard_rejected",
            "timeout",
            "degraded",
            "error",
        )
        assert run["model"]


async def test_tool_arguments_are_validated(client) -> None:
    """A model cannot reach the database with an arbitrary string."""
    from app.agents import tools
    from app.db.session import session_scope

    async with session_scope() as session:
        entry = await tools.execute(session, "get_site", {"site_id": "'; DROP TABLE sites;--"}, 1)
    assert entry.error is not None
    assert entry.result and "error" in entry.result

    async with session_scope() as session:
        still_there = await tools.execute(session, "search_sites", {"limit": 5}, 2)
    assert still_there.error is None
    assert still_there.result is not None
    assert still_there.result["count"] > 0, "the sites table did not survive"


async def test_unknown_tool_is_refused(client) -> None:
    from app.agents import tools
    from app.db.session import session_scope

    async with session_scope() as session:
        entry = await tools.execute(session, "rm_rf", {}, 1)
    assert entry.error and "unknown tool" in entry.error


async def test_tool_results_carry_their_numbers(client) -> None:
    """The grounding pool is exactly what the tools returned, not a summary."""
    from app.agents import tools
    from app.db.session import session_scope

    async with session_scope() as session:
        entry = await tools.execute(session, "get_metrics", {"site_id": SITE}, 1)
    assert entry.error is None
    assert entry.numbers, "no numeric leaves were flattened"
    assert entry.result is not None
    assert entry.result["sunlit_s"] in entry.numbers


async def test_agents_declare_exactly_six_tools() -> None:
    """The complete, auditable surface area an LLM can reach."""
    from app.agents.tools import TOOL_NAMES

    assert {
        "get_site",
        "get_metrics",
        "get_windows",
        "get_horizon_profile",
        "search_sites",
        "compare_sites",
    } == TOOL_NAMES


async def test_user_supplied_numbers_are_grounded_but_attributed(client, fake_gemini) -> None:
    """Quoting the requirement back is not a claim about the data.

    Before this rule the advisor could not restate the requirement it was given
    without failing its own guard. The number is allowed, and its provenance
    entry says `user_request` rather than naming a measurement, so a reader can
    still tell the difference.

    The figure is 96 rather than 4 deliberately: small integers are exempt from
    the grounding check as ordinals and counts, so a "4" would pass for the
    wrong reason and prove nothing about this rule.
    """
    fake_gemini(
        {
            "status": "ok",
            "requirement_summary": "at least 96 hours of Earth contact in the window",
            "any_satisfies": False,
            "nothing_satisfies_message": "No site in this set meets it.",
            "ranked": [],
        }
    )
    body = (
        await client.post(
            f"{API}/agents/advise",
            json={"requirement": "at least 96 hours of Earth contact in the window"},
        )
    ).json()
    assert body["status"] == "ok", body.get("reason")
    assert body["attempts"] == 1, "restating the requirement should not need a retry"
    assert any(p["tool"] == "user_request" for p in body["provenance"])
