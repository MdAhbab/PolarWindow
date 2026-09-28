"""Ready (T3) end to end: prefilled items, moves, history, parts, risks, lessons, sections."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.session import session_scope

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]

API = "/api/v1"
EV = "https://example.org/evidence/report-1.pdf"


@pytest.fixture(autouse=True)
async def clean():
    async with session_scope() as s:
        for t in (
            "readiness_items",
            "parts",
            "risks",
            "lesson_adoptions",
            "pm_parameters",
            "milestones",
        ):
            await s.execute(text(f"DELETE FROM {t}"))  # noqa: S608 -- fixed table names
    yield


async def test_a_flown_mission_shows_every_item_flew(anon_client) -> None:
    r = await anon_client.get(f"{API}/missions/im-2/ready")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    kinds = {i["kind"] for i in d["items"]}
    assert {"lander", "payload", "launch_vehicle", "range", "licence"} <= kinds
    assert all(i["state"] == "ready" and i["state_known"] for i in d["items"])
    assert d["counts"]["ready"] == len(d["items"]) and d["not_entered"] == 0
    lv = next(i for i in d["items"] if i["kind"] == "launch_vehicle")
    assert lv["name"] == "Falcon 9 Block 5"
    assert lv["evidence_url"].startswith("https://ll.thespacedevs.com")
    names = [m["name"] for m in d["milestones"]]
    assert names[:2] == ["Launch", "Landing"]
    launch = d["milestones"][0]["date"]
    assert launch["provenance"] == "published" and launch["pm"] == 30.0
    assert "percent" not in r.text.lower() and "score" not in r.text.lower()


async def test_a_planned_mission_says_no_state_is_entered(anon_client) -> None:
    d = (await anon_client.get(f"{API}/missions/griffin-1/ready")).json()["data"]
    assert d["not_entered"] == len(d["items"])
    assert sum(d["counts"].values()) == 0
    assert any(i["kind"] == "rover" and "FLIP" in i["name"] for i in d["items"])
    lv = next(i for i in d["items"] if i["kind"] == "launch_vehicle")
    assert lv["name"] == "Falcon Heavy" and not lv["state_known"]


async def test_moves_follow_the_ladder_and_are_recorded(client) -> None:
    iid = "griffin-1--lander"
    ok = await client.patch(
        f"{API}/ready/items/{iid}",
        json={"state": "in_build", "date": "2026-09-01", "evidence_url": EV},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["changed_by"] == "Test manager (QA)" and ok.json()["state_known"]
    skip = await client.patch(
        f"{API}/ready/items/{iid}",
        json={"state": "ready", "date": "2026-09-02", "evidence_url": EV},
    )
    assert skip.status_code == 409
    assert "in_test" in skip.json()["detail"]["allowed"]
    no_ev = await client.patch(
        f"{API}/ready/items/{iid}",
        json={"state": "in_test", "date": "2026-09-02", "evidence_url": "see my email"},
    )
    assert no_ev.status_code == 422
    block = await client.patch(
        f"{API}/ready/items/{iid}",
        json={
            "state": "blocked",
            "date": "2026-09-03",
            "evidence_url": EV,
            "blocked_reason": "Waiting for the thermal blanket supplier",
        },
    )
    assert block.status_code == 200 and block.json()["blocked_reason"].startswith("Waiting")
    # The history is append-only, so earlier runs' entries stay: read the last two.
    h = (await client.get(f"{API}/ready/items/{iid}/history")).json()["entries"][-2:]
    assert [e["after"]["state"] for e in h] == ["in_build", "blocked"]
    assert h[0]["before"]["state"] == "not_started" and h[0]["by"] == "Test manager (QA)"
    d = (await client.get(f"{API}/missions/griffin-1/ready")).json()["data"]
    assert d["counts"]["blocked"] == 1 and d["not_entered"] == len(d["items"]) - 1
    s = (await client.get(f"{API}/missions/griffin-1/sections")).json()["data"]
    assert s[0]["section"] == "ready" and "1 blocked" in s[0]["summary"]


async def test_writes_need_a_name(anon_client) -> None:
    r = await anon_client.patch(
        f"{API}/ready/items/griffin-1--lander",
        json={"state": "in_build", "date": "2026-09-01", "evidence_url": EV},
    )
    assert r.status_code == 401


async def test_add_an_item_and_record_a_test(client) -> None:
    r = await client.post(
        f"{API}/missions/griffin-1/ready/items",
        json={"kind": "payload", "name": "Spare camera", "organisation": "X"},
    )
    assert r.status_code == 201 and r.json()["source"] == "entered"
    iid = r.json()["id"]
    bad = await client.put(
        f"{API}/ready/items/{iid}/tests", json={"kind": "vibration", "result": "passed"}
    )
    assert bad.status_code == 422
    ok = await client.put(
        f"{API}/ready/items/{iid}/tests",
        json={"kind": "vibration", "result": "passed", "report_url": EV, "date": "2026-08-01"},
    )
    assert ok.json()["tests"][0]["result"] == "passed"


async def test_parts_and_what_stops_working(client) -> None:
    lander = await client.post(
        f"{API}/missions/griffin-1/parts",
        json={
            "name": "Radar altimeter",
            "status": "installed",
            "parent_item_id": "griffin-1--lander",
        },
    )
    assert lander.status_code == 201, lander.text
    pid = lander.json()["id"]
    imp = (await client.get(f"{API}/parts/{pid}/impact")).json()
    kinds = {x["kind"] for x in imp["stops_working"]}
    assert "lander" in kinds and "rover" in kinds and "payload" in kinds
    spare = await client.post(
        f"{API}/missions/griffin-1/parts", json={"name": "Spare altimeter", "status": "spare"}
    )
    assert (await client.get(f"{API}/parts/{spare.json()['id']}/impact")).json()[
        "stops_working"
    ] == []
    lost = await client.patch(f"{API}/parts/{pid}", json={"status": "lost"})
    assert lost.json()["status"] == "lost"
    d = (await client.get(f"{API}/missions/griffin-1/ready")).json()["data"]
    assert d["parts"] == {"total": 2, "spares": 1, "lost": 1, "damaged": 0, "failed": 0}
    hist = (await client.get(f"{API}/history", params={"entity": "part", "id": pid})).json()
    # A new part id each run, so its history is only this run's.
    assert [e["action"] for e in hist["entries"]] == ["create", "update"]


async def test_risks_keep_likelihood_and_consequence_apart(client) -> None:
    scales = (await client.get(f"{API}/risk-scales")).json()
    sid = scales["default_id"]
    body = {
        "title": "Altimeter noise at low Sun",
        "cause": "Long shadows at the pole",
        "consequence_text": "Hard landing",
        "scale_id": sid,
        "ratings": [{"category": "technical", "likelihood": 3, "consequence": 5}],
        "trend": "steady",
    }
    r = await client.post(f"{API}/missions/griffin-1/risks", json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["ratings"] == [{"category": "technical", "likelihood": 3, "consequence": 5}]
    assert "score" not in out and "product" not in out
    off = await client.post(
        f"{API}/missions/griffin-1/risks",
        json={**body, "ratings": [{"category": "technical", "likelihood": 9, "consequence": 5}]},
    )
    assert off.status_code == 422
    up = await client.patch(f"{API}/risks/{out['id']}", json={"trend": "falling"})
    assert up.json()["trend"] == "falling"


async def test_landing_history_is_counts_not_odds(anon_client) -> None:
    d = (await anon_client.get(f"{API}/landing-history")).json()
    c = d["counts"]
    assert c["attempts"] == c["landed_working"] + c["landed_tipped_or_partial"] + c["failed"]
    assert all(a["source_url"].startswith("https://") for a in d["attempts"])
    assert "chance" in d["note"] and "probability" not in str(c)


async def test_adopting_a_lesson_adds_a_checklist_item(client) -> None:
    lessons = (await client.get(f"{API}/lessons", params={"mission": "griffin-1"})).json()
    lid = lessons["lessons"][0]["id"]
    assert not lessons["lessons"][0]["adopted"]
    r = await client.post(f"{API}/missions/griffin-1/lessons/{lid}/adopt")
    assert r.status_code == 200 and r.json()["adopted"]
    again = (await client.get(f"{API}/lessons", params={"mission": "griffin-1"})).json()
    assert again["lessons"][0]["adopted"]
    d = (await client.get(f"{API}/missions/griffin-1/ready")).json()["data"]
    assert d["lessons_adopted"] == 1
    assert any(i["id"] == r.json()["item_id"] for i in d["items"])


async def test_parameters_are_missing_until_entered(client) -> None:
    p = {x["id"]: x for x in (await client.get(f"{API}/parameters")).json()["parameters"]}
    assert p["battery_limit_h"]["value"]["value"] is None
    assert p["battery_limit_h"]["value"]["missing_reason"]
    r = await client.put(f"{API}/parameters/battery_limit_h", json={"value": 120, "note": "EPS"})
    q = {x["id"]: x for x in r.json()["parameters"]}["battery_limit_h"]
    assert q["value"]["value"] == 120 and q["value"]["provenance"] == "entered"
    assert q["changed_by"].startswith("Test manager")
    bad = await client.put(f"{API}/parameters/battery_limit_h", json={"value": -3})
    assert bad.status_code == 422


async def test_sections_are_six_in_order_and_never_a_verdict(anon_client) -> None:
    for mid in ("im-2", "griffin-1", "apex-1"):
        r = await anon_client.get(f"{API}/missions/{mid}/sections")
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        assert [x["section"] for x in rows] == [
            "ready",
            "launch",
            "trip",
            "landing",
            "contact",
            "return",
        ]
        words = " ".join(x["summary"].lower() for x in rows)
        for bad in ("go/no-go", "no-go", "safe", "score", "%"):
            assert bad not in words, (mid, bad)
    apex = (await anon_client.get(f"{API}/missions/apex-1/sections")).json()["data"]
    assert all(x["state"] == "not_applicable" for x in apex if x["section"] != "landing")
    im2 = (await anon_client.get(f"{API}/missions/im-2/sections")).json()["data"]
    assert im2[1]["state"] == "available" and "27 Feb 2025 00:16 UTC" in im2[1]["summary"]
    assert (await anon_client.get(f"{API}/missions/nope/sections")).status_code == 404


async def test_a_section_with_a_stored_job_carries_its_time(anon_client) -> None:
    from app.services import job_service

    async with session_scope() as s:
        await s.execute(text("DELETE FROM jobs WHERE kind = 'trip' AND mission_id = 'im-2'"))
        await job_service.answer_or_enqueue(
            s, kind="trip", closure="traj-1", params={"regression": 1}, mission_id="im-2"
        )
    try:
        r = await anon_client.get(f"{API}/missions/im-2/sections")
        assert r.status_code == 200, r.text
        trip = {x["section"]: x for x in r.json()["data"]}["trip"]
        assert trip["state"] in ("computing", "available")
        assert isinstance(trip["as_of"], str) and trip["as_of"][:2] == "20"
    finally:
        async with session_scope() as s:
            await s.execute(text("DELETE FROM jobs WHERE kind = 'trip' AND mission_id = 'im-2'"))
