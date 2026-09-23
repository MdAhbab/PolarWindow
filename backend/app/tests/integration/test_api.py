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
    # Every coarse bin is the max of the fine bins *around* its bearing
    # (+-0.5 deg, wrapping at north), so never below their mean and never a
    # quarter-bin late.
    for i in range(0, 360, 37):
        group = [fine["el_deg"][(i * 4 + k) % 1440] for k in range(-2, 3)]
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


# --- window edges, survival, and the envelope for a set ---------------------


async def test_a_night_cut_by_the_window_says_so(client) -> None:
    """Malapert's reference window opens mid-night; the night continues past it.

    Measured on real data, a window phase can report 167 h for a 322 h night.
    The number is kept -- it is true for the window -- and flagged as a lower
    bound, rather than presented as the night itself.
    """
    m = (await client.get(f"{API}/sites/malapert-massif/metrics")).json()
    w = (await client.get(f"{API}/sites/malapert-massif/windows")).json()
    assert m["longest_dark_open"] is True
    assert w["sun"]["longest_down_open"] is True
    arcs = w["sun"]["arcs"]
    assert arcs[0]["open_start"] and arcs[-1]["open_end"]
    assert not any(a["open_start"] for a in arcs[1:]), "only the first arc can open early"
    assert not any(a["open_end"] for a in arcs[:-1]), "only the last arc can run on"
    assert any("lower bound" in n for n in m["meta"]["uncertainty"]["notes"])


async def test_survival_is_the_longest_night(client) -> None:
    """Malapert has no compound event; its battery still carries the night."""
    m = (await client.get(f"{API}/sites/malapert-massif/metrics")).json()
    assert m["autonomy"]["survival_needed_s"] == pytest.approx(m["longest_dark_s"])
    assert m["autonomy"]["survival_needed_s"] > 200 * 3600
    assert m["autonomy"]["survival_open"] is m["longest_dark_open"]
    assert 0.0 < m["autonomy"]["margin_fraction"] < 1.0


async def test_site_list_meta_is_derived_not_typed_in(client) -> None:
    """The /sites envelope used to be a block of literals dated 2027."""
    from datetime import UTC, datetime, timedelta

    body = (await client.get(f"{API}/sites")).json()
    meta = body["meta"]
    stamp = datetime.fromisoformat(meta["computed_at"].replace("Z", "+00:00"))
    assert stamp <= datetime.now(UTC) + timedelta(minutes=1), "computed_at is in the future"
    assert meta["uncertainty"]["dem_vertical_error_m"] >= 2.0
    assert "LOLA" in meta["resolution"]["dem_product"]
    summaries = [i["summary"] for i in body["items"] if i["summary"]]
    assert meta["uncertainty"]["grazing"] == any(s["grazing"] for s in summaries)


async def test_metric_filters_run_before_pagination(client) -> None:
    """Filtering a page after the database paginated it lost matching sites."""
    everything = (await client.get(f"{API}/sites?limit=500")).json()["items"]
    want = sorted(
        i["id"] for i in everything if i["summary"] and i["summary"]["sun_fraction_up"] >= 0.5
    )
    assert len(want) > 2, "sanity: the filter must select more than one page"
    page1 = (await client.get(f"{API}/sites?min_sun_fraction=0.5&limit=2")).json()
    page2 = (await client.get(f"{API}/sites?min_sun_fraction=0.5&limit=2&offset=2")).json()
    assert page1["total"] == len(want), "total counted one page, not the selection"
    assert len(page1["items"]) == 2
    got = {i["id"] for i in page1["items"] + page2["items"]}
    assert got <= set(want) and len(got) == min(4, len(want))


async def test_compare_ranks_are_competition_ranks(client) -> None:
    body = (
        await client.post(
            f"{API}/compare",
            json={
                "site_ids": ["connecting-ridge", "malapert-massif", "faustini-rim", "nobile-rim-1"],
                "rank_by": "earth_contact_s",
            },
        )
    ).json()
    items = body["items"]
    assert [i["position"] for i in items] == list(range(1, len(items) + 1))
    tied = {sid for g in body["ties"] for sid in g}
    for item in items:
        assert item["tied"] is (item["site_id"] in tied)
        assert item["rank"] <= item["position"]
    for group in body["ties"]:
        ranks = {i["rank"] for i in items if i["site_id"] in group}
        assert len(ranks) == 1, "tied sites were given different ranks"


async def test_compare_envelope_describes_every_site(client) -> None:
    """Least favourable value across the set, not the leader's own margin."""
    ids = ["connecting-ridge", "malapert-massif", "faustini-rim"]
    body = (await client.post(f"{API}/compare", json={"site_ids": ids})).json()
    per_site = [i["metrics"]["meta"]["uncertainty"] for i in body["items"]]
    u = body["meta"]["uncertainty"]
    assert u["coverage"] == min(p["coverage"] for p in per_site)
    assert u["grazing"] == any(p["grazing"] for p in per_site)
    if not u["grazing"]:
        assert u["edge_timing_s"] == max(p["edge_timing_s"] for p in per_site)


async def test_compare_does_not_hide_an_outage_behind_unavailable(client, monkeypatch) -> None:
    """A missing ephemeris is not a property of one site; it is a 503."""
    from app.core.kernels import KernelError
    from app.services import site_service

    async def no_kernels(*_a, **_k):
        raise KernelError("de440.bsp is not loaded")

    monkeypatch.setattr(site_service, "cached_payload", no_kernels)
    r = await client.post(f"{API}/compare", json={"site_ids": ["connecting-ridge", SITE]})
    assert r.status_code == 503
    assert r.json()["detail"]["ui"]["still_works"]


async def test_an_unhandled_failure_is_a_problem_detail_the_browser_can_read(
    client, monkeypatch
) -> None:
    """Inside CORS, and shaped like every other error.

    Starlette's own 500 handler runs outside CORS: the browser saw a network
    failure and the UI said "cannot reach the service" about a service that was
    up. And its body lacked the `detail` wrapper the error panel reads.
    """
    from app.services import site_service

    async def boom(*_a, **_k):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(site_service, "cached_payload", boom)
    r = await client.get(f"{API}/sites/{SITE}/metrics", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    detail = r.json()["detail"]
    assert detail["ui"]["still_works"]
    assert "synthetic" not in r.text, "internal exception text leaked to the client"


async def test_large_bodies_are_compressed(client) -> None:
    """~210 KB of timeline JSON is ~40 KB on the wire; the hand-off budgets on it."""
    r = await client.get(f"{API}/sites/{SITE}/timeline", headers={"accept-encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


async def test_openapi_document_in_docs_matches_the_app(client) -> None:
    """The frontend client is generated from docs/openapi.json.

    If the app's schema moves and the document does not, the generated types
    describe an API that no longer exists and nothing fails until runtime.
    Regenerate with `make codegen`.
    """
    import json
    from pathlib import Path

    live = (await client.get(f"{API}/openapi.json")).json()
    committed = json.loads((Path(__file__).parents[4] / "docs" / "openapi.json").read_text())
    assert live == committed, "docs/openapi.json is stale: run `make codegen`"


async def test_compare_declines_to_call_a_lower_bound_best(client) -> None:
    """D20, reproduced: de Gerlache rim's night is cut by the window (>= 112 h).

    Ranked against Connecting Ridge's measured ~122 h, the old ranking called de
    Gerlache best. Its place cannot be stated, and neither can the site it
    cannot be ordered against.
    """
    r = await client.post(
        f"{API}/compare",
        json={
            "site_ids": [SITE, "de-gerlache-rim", "malapert-massif"],
            "rank_by": "longest_dark_s",
        },
    )
    assert r.status_code == 200, r.text
    items = {it["site_id"]: it for it in r.json()["items"]}
    dg = items["de-gerlache-rim"]
    if not dg["metrics"]["longest_dark_open"]:
        pytest.skip("reference window no longer cuts de Gerlache rim's night")
    assert dg["censored"] is True
    assert dg["rank"] is None
    assert dg["rank_range"][0] < dg["rank_range"][1]
    assert not any(it["rank"] == 1 and it["incomparable_with"] for it in items.values())


async def test_list_provenance_names_each_product_once(client) -> None:
    """C6: the one line a reader uses to know what the numbers came from."""
    body = (await client.get(f"{API}/sites")).json()
    parts = [p.strip() for p in body["meta"]["resolution"]["dem_product"].split(" + ")]
    assert len(parts) == len(set(parts)), parts


async def test_a_payload_rebuilt_from_memoised_geometry_says_so(client) -> None:
    """C7: metrics and windows share one geometry; the second must not claim its cost."""
    import secrets

    # A window nobody has asked for, so the payload cache cannot answer first.
    year = 2028 + secrets.randbelow(3)
    day = 1 + secrets.randbelow(27)
    hour = secrets.randbelow(24)
    params = {
        "start": f"{year}-02-{day:02d}T{hour:02d}:00:00Z",
        "end": f"{year}-03-{day:02d}T{hour:02d}:00:00Z",
    }
    first = await client.get(f"{API}/sites/{SITE}/metrics", params=params)
    assert first.status_code == 200
    second = await client.get(f"{API}/sites/{SITE}/windows", params=params)
    assert second.status_code == 200
    meta = second.json()["meta"]
    if meta["cache"] == "hit":
        pytest.skip("payload cache already held this window")
    assert meta["cache"] == "memo"
    assert meta["compute_ms"] == 0.0
