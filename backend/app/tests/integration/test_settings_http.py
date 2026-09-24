"""Sign-in and the project manager's settings, over HTTP."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.requires_db, pytest.mark.requires_kernels, pytest.mark.asyncio]

API = "/api/v1"
SITE = "connecting-ridge"


async def test_one_click_sign_in_gives_a_project_managers_session(anon_client) -> None:
    r = await anon_client.post(f"{API}/auth/demo")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "project_manager"
    assert body["role_name"] == "Project manager"
    assert body["token_type"] == "bearer"

    me = await anon_client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {body['token']}"}
    )
    assert me.status_code == 200
    assert me.json()["subject"] == body["subject"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/settings"),
        ("delete", "/settings/cache"),
        ("delete", "/settings/agent-runs"),
        ("post", "/settings/ai/reset"),
        ("get", "/auth/me"),
    ],
)
async def test_settings_need_a_session(anon_client, method: str, path: str) -> None:
    r = await getattr(anon_client, method)(f"{API}{path}")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.json()["detail"]["ui"]["still_works"]


async def test_the_ai_panels_need_a_session(anon_client) -> None:
    r = await anon_client.post(f"{API}/agents/explain", json={"site_id": SITE})
    assert r.status_code == 401


async def test_reading_stays_public(anon_client) -> None:
    assert (await anon_client.get(f"{API}/sites?limit=1")).status_code == 200
    assert (await anon_client.get(f"{API}/missions")).status_code == 200
    assert (await anon_client.get(f"{API}/agents/runs?limit=1")).status_code == 200


async def test_a_bad_token_says_the_session_ended(anon_client) -> None:
    r = await anon_client.get(f"{API}/settings", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert r.json()["detail"]["title"] == "Your session has ended"


async def test_settings_show_the_system_and_the_model_order(client, settings) -> None:
    r = await client.post(f"{API}/settings/ai/reset")
    assert r.status_code == 200
    body = (await client.get(f"{API}/settings")).json()
    assert body["ai"]["enabled"] is True
    assert body["ai"]["customised"] is False
    assert [m["model"] for m in body["ai"]["models"]] == list(settings.agent_models)
    assert body["system"]["database"] is True
    assert body["system"]["counts"]["candidate_sites"] > 0


async def test_the_model_order_is_saved_and_reset(client, settings) -> None:
    order = list(reversed(settings.agent_models))
    r = await client.put(
        f"{API}/settings/ai",
        json={"enabled": True, "models": order, "models_light": list(settings.agent_models_light)},
    )
    assert r.status_code == 200, r.text
    assert [m["model"] for m in r.json()["ai"]["models"]] == order
    assert r.json()["ai"]["customised"] is True

    r = await client.post(f"{API}/settings/ai/reset")
    assert [m["model"] for m in r.json()["ai"]["models"]] == list(settings.agent_models)


@pytest.mark.parametrize(
    "models",
    [["gemini-1.0-pro"], ["gemini-2.5-flash", "gemini-2.5-flash"]],
)
async def test_a_model_list_that_is_not_the_configured_one_is_refused(
    client, settings, models: list[str]
) -> None:
    r = await client.put(
        f"{API}/settings/ai",
        json={"enabled": True, "models": models, "models_light": list(settings.agent_models_light)},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["ui"]["still_works"] == "The previous settings are still in force."


async def test_turning_the_ai_off_answers_from_the_measurements(
    client, settings, fake_gemini
) -> None:
    calls = fake_gemini({"status": "ok", "site_id": SITE, "paragraph": "x", "numbers_used": []})
    await client.put(
        f"{API}/settings/ai",
        json={
            "enabled": False,
            "models": list(settings.agent_models),
            "models_light": list(settings.agent_models_light),
        },
    )
    try:
        r = await client.post(f"{API}/agents/explain", json={"site_id": SITE})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "degraded"
        assert "turned off in Settings" in body["reason"]
        assert calls["calls"] == 0
    finally:
        await client.post(f"{API}/settings/ai/reset")


async def test_the_run_log_and_the_cache_can_be_cleared(client) -> None:
    await client.post(f"{API}/agents/explain", json={"site_id": SITE})
    before = (await client.get(f"{API}/settings")).json()["system"]["counts"]["agent_runs"]
    assert before >= 1

    r = await client.delete(f"{API}/settings/agent-runs")
    assert r.status_code == 200
    assert r.json()["removed"] == before
    assert (await client.get(f"{API}/settings")).json()["system"]["counts"]["agent_runs"] == 0

    await client.get(f"{API}/sites/{SITE}/metrics")
    r = await client.delete(f"{API}/settings/cache")
    assert r.status_code == 200
    assert r.json()["what"] == "cache"
