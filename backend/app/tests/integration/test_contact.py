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
    assert n["longest_unheard_h"]["open"] is False  # a zero cannot be cut short
    wait_s = n["longest_message_wait_min"]["value"] * 60
    assert d["light_time_s"]["min"] - 1e-6 <= wait_s <= d["light_time_s"]["max"] + 1e-6
    assert n["via_relay_h"]["value"] is None and n["via_relay_h"]["missing_reason"]
    stations = [x for x in d["nodes"] if x["kind"] == "station"]
    assert len(stations) == 14
    assert d["link_budget_note"].startswith("Line of sight only")
    assert 1.1 < d["light_time_s"]["min"] < d["light_time_s"]["max"] < 1.5
    assert body["meta"]["engines"] == {"link": "link-1", "net": "net-4", "vis": "vis-2"}
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
    too_long = await client.post(
        f"{API}/missions/im-1/contact/bookings",
        json={"station": "dss-43", "start": "2024-02-23T10:00:00Z", "end": "2024-02-24T10:00:01Z"},
    )
    assert too_long.status_code == 422 and "24 hours" in too_long.json()["detail"]["detail"]


async def test_no_landing_spot_says_why(anon_client) -> None:
    r = await anon_client.get(f"{API}/missions/blue-ghost-m3/contact")
    assert r.status_code == 409
    assert "landing spot" in r.json()["detail"]["detail"]


async def test_a_lander_lost_before_landing_has_no_contact(anon_client) -> None:
    r = await anon_client.get(f"{API}/missions/peregrine-m1/contact")
    assert r.status_code == 409
    assert "lost before" in r.json()["detail"]["detail"]


async def test_a_planned_relay_added_to_a_south_pole_site(anon_client) -> None:
    """Griffin-1's pole site with Lunar Pathfinder added to compare: every number
    through the relay is a range over its unknown node and phase."""
    q = {"start": "2027-03-20T00:00:00Z", "end": "2027-03-22T00:00:00Z"}
    body = await _answer(anon_client, "griffin-1", **q, relay="lunar-pathfinder")
    d = body["data"]
    n = d["numbers"]
    (row,) = d["relays"]
    assert row["id"] == "lunar-pathfinder" and row["for_this_mission"] is False
    assert row["launch_status"] == "planned"
    assert row["orbit"]["periapsis_km"]["provenance"] == "published"
    assert row["orbit"]["periapsis_km"]["value"] == pytest.approx(673.4)
    inc = row["orbit"]["inclination_deg"]
    assert inc["provenance"] == "assumed" and (inc["lo"], inc["hi"]) == (46.8, 54.9)
    assert "5184 placements" in row["sweep_note"]
    for q_ in (row["adds_h"], row["via_h"], n["via_relay_h"], n["either_h"]):
        assert q_["provenance"] == "assumed"
        assert q_["lo"] <= q_["value"] <= q_["hi"]
    assert n["either_h"]["lo"] >= n["direct_h"]["value"] - 1e-9
    assert n["either_h"]["hi"] <= 48.0 + 1e-9
    # A relay can only shorten the time nobody hears the lander.
    alone = d["direct_only"]
    assert alone is not None and d["relay_note"]
    assert n["longest_unheard_h"]["hi"] <= alone["longest_unheard_h"]["value"] + 1e-9
    assert n["longest_message_wait_min"]["hi"] <= alone["longest_message_wait_min"]["value"] + 1e-6
    relay_node = next(x for x in d["nodes"] if x["kind"] == "relay")
    assert relay_node["orbit"] == "planned" and relay_node["launch_note"]
    assert body["meta"]["engines"]["net"] == "net-4"


async def test_a_mission_s_own_relay_over_a_near_side_site(anon_client) -> None:
    """IM-3's Altus-1 over Reiner Gamma, where Earth never sets: the relay adds nothing."""
    q = {"start": "2027-03-20T00:00:00Z", "end": "2027-03-21T00:00:00Z"}
    d = (await _answer(anon_client, "im-3", **q))["data"]
    (row,) = d["relays"]
    assert row["id"] == "altus-1" and row["for_this_mission"] is True
    assert row["orbit"]["periapsis_km"]["provenance"] == "assumed"
    assert row["adds_h"]["hi"] == pytest.approx(0.0, abs=1e-6)
    assert d["numbers"]["either_h"]["value"] == pytest.approx(d["numbers"]["direct_h"]["value"])


async def test_only_a_catalogued_relay_service_can_be_added(anon_client) -> None:
    r = await anon_client.get(f"{API}/missions/griffin-1/contact", params={"relay": "lro"})
    assert r.status_code == 422 and "no relay service" in r.json()["detail"]["detail"]
    r = await anon_client.get(f"{API}/missions/griffin-1/contact", params={"relay": "nope"})
    assert r.status_code == 422 and "lunar-pathfinder" in r.json()["detail"]["detail"]
