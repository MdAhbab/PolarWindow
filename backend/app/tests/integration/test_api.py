"""API contract and behaviour, against a real Postgres and Redis.

Gemini is never reached: `conftest.no_live_gemini` blanks the key for every
test, so the agent endpoints exercise the degraded path rather than the network.
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = [pytest.mark.requires_db, pytest.mark.requires_kernels, pytest.mark.asyncio]

API = "/api/v1"
SITE = "connecting-ridge"

WINDOW_ENDPOINTS = ("timeline", "windows", "metrics")


# --- contract --------------------------------------------------------------


async def test_healthz_reports_every_dependency(client) -> None:
    r = await client.get("/healthz")
    assert r.status_code in (200, 503)
    body = r.json()
    assert set(body) >= {"status", "engine_version", "kernels", "db", "redis", "dem"}
    assert isinstance(body["kernels"]["loaded"], bool)


@pytest.mark.parametrize("endpoint", WINDOW_ENDPOINTS)
async def test_meta_is_present_and_uncertainty_is_never_null(client, endpoint: str) -> None:
    """A product rule, enforced mechanically rather than by review.

    The frontend carries an uncertainty state in every data-bound component; an
    endpoint that omits the margin forces the UI to invent one or hide it.
    """
    r = await client.get(f"{API}/sites/{SITE}/{endpoint}")
    assert r.status_code == 200, r.text
    meta = r.json()["meta"]
    assert meta["computed_at"]
    assert meta["engine_version"]
    unc = meta["uncertainty"]
    assert unc is not None and unc != {}
    for key in ("dem_vertical_error_m", "coverage", "grazing", "notes"):
        assert key in unc, f"{endpoint} meta.uncertainty is missing {key}"
    assert unc["notes"], "uncertainty carries no notes"
    res = meta["resolution"]
    assert res["azimuth_count"] > 0 and res["dem_product"]


async def test_durations_are_seconds_not_hours(client) -> None:
    """A units regression would be silent and catastrophic."""
    body = (await client.get(f"{API}/sites/{SITE}/metrics")).json()
    for key in ("sunlit_s", "earth_contact_s", "longest_dark_s", "longest_blackout_s"):
        assert key in body
        assert body[key] > 1000, f"{key}={body[key]} looks like hours, not seconds"
    assert not [k for k in body if k.endswith("_h")], "an hours field leaked into the API"


async def test_metrics_has_no_composite_score(client) -> None:
    body = (await client.get(f"{API}/sites/{SITE}/metrics")).json()
    for forbidden in ("score", "rating", "overall", "grade", "index"):
        assert forbidden not in body


async def test_openapi_is_emitted_and_complete(client) -> None:
    """The frontend client is generated from this; a gap here is a broken build."""
    spec = (await client.get(f"{API}/openapi.json")).json()
    paths = spec["paths"]
    for expected in (
        f"{API}/sites",
        f"{API}/sites/{{site_id}}",
        f"{API}/sites/{{site_id}}/horizon",
        f"{API}/sites/{{site_id}}/timeline",
        f"{API}/sites/{{site_id}}/windows",
        f"{API}/sites/{{site_id}}/metrics",
        f"{API}/compare",
        f"{API}/agents/explain",
        f"{API}/agents/advise",
        f"{API}/agents/brief",
        f"{API}/agents/ask",
        f"{API}/healthz",
    ):
        assert expected in paths, f"{expected} missing from the OpenAPI schema"
    assert "Meta" in spec["components"]["schemas"]
    assert "Uncertainty" in spec["components"]["schemas"]


# --- behaviour -------------------------------------------------------------


async def test_sites_summary_is_null_not_zero_when_absent(client) -> None:
    """Absence is not a measurement. The UI has a state for it."""
    body = (await client.get(f"{API}/sites?limit=50")).json()
    assert body["total"] >= 12, "the brief asks for 12 to 20 candidate sites"
    for item in body["items"]:
        assert item["summary"] is None or item["summary"]["sunlit_s"] >= 0
        if item["summary"] is None:
            continue
        assert item["summary"]["reference_window_start"]


async def test_window_is_quantised_so_the_slider_hits_cache(client) -> None:
    """The mechanism the whole slider budget rests on (ADR-1, system-design 6).

    Three starts seconds apart must collapse to one cache key. Untested, this
    regresses silently and the only symptom is that the demo feels slow.
    """
    base = f"{API}/sites/malapert-massif/metrics"
    first = (await client.get(f"{base}?start=2027-04-01T00:00:00Z")).json()
    assert first["start"].startswith("2027-04-01T00:00:00")

    for offset in ("00:00:41", "00:07:13", "00:14:59"):
        body = (await client.get(f"{base}?start=2027-04-01T{offset}Z")).json()
        assert body["start"] == first["start"], "window was not quantised to the step grid"
        assert body["sunlit_s"] == first["sunlit_s"]
        assert body["meta"]["cache"] in ("hit", "bypass")


async def test_step_out_of_range_explains_the_limit(client) -> None:
    r = await client.get(f"{API}/sites/{SITE}/metrics?step_s=10")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["ui"]["still_works"], "an error with no 'what still works' is a shrug"


async def test_unknown_site_404s_with_a_usable_message(client) -> None:
    r = await client.get(f"{API}/sites/not-a-site")
    assert r.status_code == 404
    d = r.json()["detail"]
    assert d["title"] and d["ui"]["still_works"]


async def test_horizon_downsamples_by_maximum(client) -> None:
    """Averaging a skyline invents sky where a ridge is."""
    fine = (await client.get(f"{API}/sites/{SITE}/horizon?step_deg=0.25")).json()
    coarse = (await client.get(f"{API}/sites/{SITE}/horizon?step_deg=1")).json()
    assert fine["azimuth_count"] == 1440
    assert coarse["azimuth_count"] == 360
    assert max(coarse["el_deg"]) == pytest.approx(max(fine["el_deg"]), abs=1e-4)
    # Every coarse bin is the max of its four fine bins, so never below their mean.
    for i in range(0, 360, 37):
        group = fine["el_deg"][i * 4 : i * 4 + 4]
        assert coarse["el_deg"][i] == pytest.approx(max(group), abs=1e-4)


async def test_timeline_arrays_are_parallel_and_complete(client) -> None:
    body = (await client.get(f"{API}/sites/{SITE}/timeline")).json()
    n = len(body["t_s"])
    assert n > 1000
    for body_key in ("sun", "earth"):
        for field in ("az_deg", "el_deg", "mask_el_deg", "margin_deg", "state"):
            assert len(body[body_key][field]) == n, f"{body_key}.{field} is ragged"
        assert set(body[body_key]["state"]) <= {0, 1, 2}


async def test_windows_arcs_partition_the_window(client) -> None:
    body = (await client.get(f"{API}/sites/{SITE}/windows")).json()
    for key in ("sun", "earth"):
        total = sum(a["duration_s"] for a in body[key]["arcs"])
        assert total == pytest.approx(body[key]["up_s"] + body[key]["down_s"], rel=1e-9)
    for arc in body["sun"]["arcs"]:
        if not arc["up"]:
            assert arc["blocked_by_bearing_deg"] is not None, "a blocked arc with no blocker"


async def test_compare_agrees_with_the_per_site_endpoint(client) -> None:
    """They share a service; this proves they stayed shared.

    A comparison table that contradicts the detail page it links to destroys
    trust in both.
    """
    ids = ["connecting-ridge", "malapert-massif", "faustini-rim"]
    cmp_body = (
        await client.post(f"{API}/compare", json={"site_ids": ids, "rank_by": "longest_dark_s"})
    ).json()
    for item in cmp_body["items"]:
        solo = (await client.get(f"{API}/sites/{item['site_id']}/metrics")).json()
        for key in ("sunlit_s", "earth_contact_s", "longest_dark_s", "longest_blackout_s"):
            assert item["metrics"][key] == pytest.approx(
                solo[key], rel=1e-9
            ), f"/compare and /metrics disagree about {item['site_id']}.{key}"


async def test_compare_ranks_in_the_right_direction(client) -> None:
    body = (
        await client.post(
            f"{API}/compare",
            json={"site_ids": ["connecting-ridge", "faustini-rim"], "rank_by": "sunlit_s"},
        )
    ).json()
    assert body["items"][0]["metrics"]["sunlit_s"] >= body["items"][1]["metrics"]["sunlit_s"]


async def test_compare_rejects_too_many_sites(client) -> None:
    r = await client.post(f"{API}/compare", json={"site_ids": [f"s{i}" for i in range(9)]})
    assert r.status_code == 422


async def test_compare_survives_one_unsurveyed_site(client) -> None:
    """One missing site must not blank the whole comparison."""
    r = await client.post(f"{API}/compare", json={"site_ids": ["connecting-ridge", "ghost-site"]})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["unavailable"][0]["site_id"] == "ghost-site"


async def test_concurrent_burst_is_consistent_and_fast(client) -> None:
    """A slider drag: many overlapping requests across several sites."""
    import time

    ids = ["connecting-ridge", "malapert-massif", "de-gerlache-rim"]
    urls = [
        f"{API}/sites/{sid}/metrics?start=2027-05-0{d}T00:00:00Z"
        for sid in ids
        for d in range(1, 6)
    ]
    await asyncio.gather(*(client.get(u) for u in urls))  # warm

    t0 = time.perf_counter()
    responses = await asyncio.gather(*(client.get(u) for u in urls))
    elapsed = time.perf_counter() - t0

    assert all(r.status_code == 200 for r in responses)
    assert all(r.json()["meta"]["cache"] in ("hit", "bypass") for r in responses)
    per_request = elapsed / len(urls)
    assert per_request < 0.5, f"warm requests averaged {per_request * 1000:.0f} ms"


async def test_tile_out_of_extent_is_204_not_404(client) -> None:
    """A wall of 404s in the network panel reads as a broken product."""
    r = await client.get(f"{API}/tiles/hillshade/3/0/0.png")
    assert r.status_code in (200, 204)
    r = await client.get(f"{API}/tiles/nope/0/0/0.png")
    assert r.status_code == 404


async def test_tile_etag_round_trip(client) -> None:
    r = await client.get(f"{API}/tiles/hillshade/0/0/0.png")
    if r.status_code != 200:
        pytest.skip("no tile rendered at z0")
    etag = r.headers["etag"]
    again = await client.get(f"{API}/tiles/hillshade/0/0/0.png", headers={"If-None-Match": etag})
    assert again.status_code == 304


async def test_cors_allows_the_vite_dev_server(client) -> None:
    """The single most common 'works in curl, fails in the browser' failure."""
    r = await client.get(f"{API}/sites", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
