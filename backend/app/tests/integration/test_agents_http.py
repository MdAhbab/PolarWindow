"""The agent loop through the real google-genai SDK, with Gemini scripted by respx.

`test_agents.py` scripts `_generate` directly, which is fast and exercises the
loop's logic. These tests keep the SDK in the path: request building, response
parsing, the async client, timeouts, outages and thought signatures are all
real, and only the network is replaced (docs/test-plan.md 10.7).
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

pytestmark = [pytest.mark.requires_db, pytest.mark.requires_kernels, pytest.mark.asyncio]

API = "/api/v1"
SITE = "connecting-ridge"
SIGNATURE = base64.b64encode(b"model-reasoning-signature").decode()

GROUNDED = {
    "status": "ok",
    "site_id": SITE,
    "paragraph": (
        "This site is sunlit for about 81% of the window, with Earth in view 61% "
        "of the time. The longest unbroken darkness is roughly 122 hours."
    ),
    "numbers_used": [],
}
HALLUCINATED = {**GROUNDED, "paragraph": "This site is sunlit for about 93% of the window."}


def _reply(parts: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 40},
        },
    )


def text(payload: object) -> httpx.Response:
    return _reply([{"text": payload if isinstance(payload, str) else json.dumps(payload)}])


def call(name: str, args: dict[str, Any]) -> httpx.Response:
    return _reply([{"functionCall": {"name": name, "args": args}, "thoughtSignature": SIGNATURE}])


NOTHING_MORE = text("I have what I need.")


async def explain(client) -> dict[str, Any]:
    r = await client.post(f"{API}/agents/explain", json={"site_id": SITE})
    assert r.status_code == 200, r.text
    return r.json()


async def test_grounded_answer_through_the_sdk(client, gemini_http) -> None:
    script, route = gemini_http
    script(NOTHING_MORE, text(GROUNDED))
    body = await explain(client)
    assert body["status"] == "ok", body.get("reason")
    assert body["provenance"]
    assert route.called


async def test_hallucinated_number_is_rejected_then_repaired(client, gemini_http) -> None:
    script, _ = gemini_http
    script(NOTHING_MORE, text(HALLUCINATED), text(GROUNDED))
    body = await explain(client)
    assert body["status"] == "ok", body.get("reason")
    assert body["attempts"] == 2


async def test_schema_invalid_output_is_retried(client, gemini_http) -> None:
    script, _ = gemini_http
    script(NOTHING_MORE, text("this is not json"), text(GROUNDED))
    body = await explain(client)
    assert body["status"] == "ok", body.get("reason")


async def test_a_timeout_degrades_to_the_measurements(client, gemini_http) -> None:
    script, _ = gemini_http
    script(httpx.ReadTimeout("model did not answer"))
    body = await explain(client)
    assert body["status"] == "degraded"
    assert body["result"]["paragraph"]


async def test_an_outage_degrades_rather_than_failing(client, gemini_http) -> None:
    script, _ = gemini_http
    script(httpx.Response(503, json={"error": {"code": 503, "status": "UNAVAILABLE"}}))
    body = await explain(client)
    assert body["status"] == "degraded"


async def test_thought_signature_round_trip(client, gemini_http) -> None:
    """Gemini 3 rejects a follow-up that drops the signature on a function call."""
    script, route = gemini_http
    script(call("get_horizon_profile", {"site_id": SITE}), NOTHING_MORE, text(GROUNDED))
    body = await explain(client)
    assert body["status"] == "ok", body.get("reason")
    follow_up = json.loads(route.calls[1].request.content)
    sent = [p for c in follow_up["contents"] for p in c.get("parts", [])]
    assert any(p.get("thoughtSignature") == SIGNATURE for p in sent), "signature was dropped"


def _over_quota(per_day: bool = True) -> httpx.Response:
    quota = "GenerateRequestsPerDayPerProjectPerModel-FreeTier" if per_day else "PerMinute"
    return httpx.Response(
        429,
        json={
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "message": "You exceeded your current quota.",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [{"quotaId": quota}],
                    }
                ],
            }
        },
    )


def _model_of(call: Any) -> str:
    return str(call.request.url).split("/models/")[1].split(":")[0]


async def test_a_model_over_its_quota_hands_the_run_to_the_next(client, gemini_http) -> None:
    from app.config import get_settings

    script, route = gemini_http
    script(_over_quota(), NOTHING_MORE, text(GROUNDED))
    body = await explain(client)
    chain = get_settings().agent_models_light
    assert body["status"] == "ok", body.get("reason")
    assert [_model_of(c) for c in route.calls[:2]] == [chain[0], chain[1]]
    assert body["meta"]["model"] == chain[1]
    skipped = [g for g in body["guard_failures"] if g["kind"] == "model_unavailable"]
    assert skipped == [
        {"kind": "model_unavailable", "model": chain[0], "detail": "daily quota used up"}
    ]

    # The used-up model is not asked again until its quota resets.
    before = route.call_count
    script(NOTHING_MORE, text(GROUNDED))
    body = await explain(client)
    assert body["status"] == "ok"
    assert chain[0] not in [_model_of(c) for c in route.calls[before:]]


async def test_every_model_over_quota_degrades_without_asking_again(client, gemini_http) -> None:
    from app.config import get_settings

    script, route = gemini_http
    script(_over_quota())
    body = await explain(client)
    assert body["status"] == "degraded"
    assert body["run_status"] == "degraded"
    assert "over its quota" in body["reason"]
    assert route.call_count == len(get_settings().agent_models_light)

    body = await explain(client)
    assert body["status"] == "degraded"
    assert route.call_count == len(get_settings().agent_models_light), "a cooled model was asked"
