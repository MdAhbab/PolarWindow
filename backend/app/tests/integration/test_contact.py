"""Contact (T1) end to end: 202 then the worker, then the numbers; bookings; exports."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.session import session_scope
from app.workers import handlers  # noqa: F401 -- registers the contact job
from app.workers.compute import HANDLERS, Worker

pytestmark = [pytest.mark.requires_db, pytest.mark.requires_kernels, pytest.mark.asyncio]

API = "/api/v1"


@pytest.fixture(autouse=True)
async def clean():
    async with session_scope() as s:
        for t in ("jobs", "assessment_inputs", "assessments", "contact_bookings"):
            await s.execute(text(f"DELETE FROM {t}"))  # noqa: S608 -- fixed table names
    yield


async def _answer(client, mission: str, **params: str) -> dict:
    r = await client.get(f"{API}/missions/{mission}/contact", params=params)
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] == "queued" and job["poll_after_s"] > 0
    ran = await Worker(owner="test", handlers=HANDLERS).run_once()
    assert ran is not None
    j = (await client.get(f"{API}/jobs/{job['job_id']}")).json()
    assert j["status"] == "done", j
    r = await client.get(f"{API}/missions/{mission}/contact", params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_im1_contact_over_its_surface_days(anon_client) -> None:
    body = await _answer(anon_client, "im-1")
    d = body["data"]
    n = d["numbers"]
    direct = n["direct_h"]["value"]
    hears = n["station_hears_h"]["value"]
    assert 0 < hears <= direct + 1e-9  # a station can hear only while Earth is up
    # Earth stayed up over IM-1's week and the three DSN complexes cover the Moon
    # between them, so a station could always hear it: no gap, and a message
    # waits only the light time to Earth.
    assert n["longest_unheard_h"]["value"] == pytest.approx(0.0)
    wait_s = n["longest_message_wait_min"]["value"] * 60
    assert d["light_time_s"]["min"] - 1e-6 <= wait_s <= d["light_time_s"]["max"] + 1e-6
    assert n["via_relay_h"]["value"] is None and n["via_relay_h"]["missing_reason"]
    stations = [x for x in d["nodes"] if x["kind"] == "station"]
    assert len(stations) == 14
    assert d["link_budget_note"].startswith("Line of sight only")
    assert 1.1 < d["light_time_s"]["min"] < d["light_time_s"]["max"] < 1.5
    assert body["meta"]["engines"] == {"link": "link-1", "net": "net-1", "vis": "vis-2"}
    assert any("mask" in p["source"].lower() for p in body["meta"]["uncertainty"]["parts"])


async def test_a_station_pass_is_inside_earth_up_time(anon_client) -> None:
    d = (await _answer(anon_client, "blue-ghost-m1"))["data"]
    total = (
        sum((_t(s["end"]) - _t(s["start"])) for link in d["links"] for s in link["stretches"])
        / 3600
    )
    # Overlapping stations are counted once in station_hears_h, so the sum is larger or equal.
    assert total >= d["numbers"]["station_hears_h"]["value"] - 1e-6


def _t(s: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


async def test_bookings_and_exports(client) -> None:
    await _answer(client, "im-1")
    r = await client.post(
        f"{API}/missions/im-1/contact/bookings",
        json={"station": "dss-43", "start": "2024-02-23T10:00:00Z", "end": "2024-02-23T14:00:00Z"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["entered_by"].startswith("Test manager")
    d = (await client.get(f"{API}/missions/im-1/contact")).json()["data"]
    assert d["bookings"][0]["station"] == "dss-43"
    csv_text = (
        await client.get(f"{API}/missions/im-1/contact/plan", params={"format": "csv"})
    ).text
    assert csv_text.splitlines()[0] == "from,to,start_utc,end_utc,hours"
    no_rate = await client.get(f"{API}/missions/im-1/contact/plan", params={"format": "ion"})
    assert no_rate.status_code == 422 and "not published" in no_rate.json()["detail"]["detail"]
    ion = await client.get(
        f"{API}/missions/im-1/contact/plan", params={"format": "ion", "rate_bps": 2000}
    )
    lines = [x for x in ion.text.splitlines() if not x.startswith("#")]
    assert lines and all(x.startswith(("a contact +", "a range +")) for x in lines)
    bad = await client.post(
        f"{API}/missions/im-1/contact/bookings",
        json={"station": "nowhere", "start": "2024-02-23T10:00:00Z", "end": "2024-02-23T14:00:00Z"},
    )
    assert bad.status_code == 422


async def test_no_landing_spot_says_why(anon_client) -> None:
    r = await anon_client.get(f"{API}/missions/blue-ghost-m3/contact")
    assert r.status_code == 409
    assert "landing spot" in r.json()["detail"]["detail"]
