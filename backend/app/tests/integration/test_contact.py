"""Contact (T1) end to end: 202 then the worker, then the numbers; bookings; exports."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

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
    assert body["meta"]["engines"] == {"link": "link-1", "net": "net-6", "vis": "vis-2"}
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
    assert csv_text.splitlines()[0] == "from,to,start_utc,end_utc,hours,basis"
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
    assert body["meta"]["engines"]["net"] == "net-6"


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


async def test_real_orbiters_are_passes_over_the_site_never_relays(anon_client, tmp_path) -> None:
    """LRO's recorded Horizons trajectory over IM-2's surface days: passes above the
    skyline, from the kernel the job writes; the others say what is missing."""
    from pathlib import Path

    from app.feeds import recorder
    from app.feeds.adapters import horizons
    from app.feeds.http import Fetched

    fx = Path(__file__).resolve().parents[1] / "fixtures" / "feeds" / "horizons_lro_im2.txt"
    p = horizons.products(
        [("lro", -85)],
        [
            (
                "im-2",
                datetime(2025, 3, 6, 17, 30, tzinfo=UTC),
                datetime(2025, 3, 7, 6, 15, tzinfo=UTC),
            )
        ],
    )[1]
    got = Fetched(p.url, 200, fx.read_bytes(), None, None, "text/plain", False, 1)
    async with session_scope() as s:
        await s.execute(text("DELETE FROM feed_snapshots WHERE provider = 'horizons'"))
        out = await recorder.record(s, p, got, raw_root=tmp_path)
    assert out.ok
    d = (await _answer(anon_client, "im-2"))["data"]
    assert d["orbiters_note"] and "not a service" in d["orbiters_note"]
    by = {o["id"]: o for o in d["orbiters"]}
    assert set(by) == {"lro", "danuri", "chandrayaan-2-orbiter", "capstone"}
    lro = by["lro"]
    assert lro["source"]["snapshot_id"] == out.snapshot_id
    assert lro["covered"]["open_start"] and lro["covered"]["open_end"]
    assert lro["pass_count"] >= 5  # a two-hour orbit over 12.75 h
    assert 0 < lro["in_view_h"]["value"] < 12.75
    assert len(lro["passes"]) == lro["pass_count"]
    for q_ in ("in_view_h", "longest_pass_min", "longest_gap_h"):
        assert lro[q_]["value"] is not None
    assert by["danuri"]["in_view_h"]["value"] is None
    assert "No JPL Horizons trajectory" in by["danuri"]["in_view_h"]["missing_reason"]
    assert not any(n["id"] == "lro" for n in d["nodes"])  # never a node of the network
    async with session_scope() as s:
        await s.execute(text("DELETE FROM feed_snapshots WHERE provider = 'horizons'"))


async def test_rover_line_of_sight_at_a_polar_site(anon_client) -> None:
    r = await anon_client.get(f"{API}/missions/im-2/contact/rover")
    assert r.status_code == 202, r.text
    ran = await Worker(owner="test", handlers=HANDLERS).run_once()
    assert ran is not None
    r = await anon_client.get(f"{API}/missions/im-2/contact/rover")
    assert r.status_code == 200, r.text
    body = r.json()
    d = body["data"]
    assert d["rover"] == {"id": "im-2/yaoki", "name": "Yaoki"}
    assert d["resolvable"] is True and d["share_basis"] == "ground" and d["radius_m"] == 500
    vs = d["viewshed"]
    assert len(vs["bearings_deg"]) == 72 and len(vs["ranges_m"]) == 20
    assert len(vs["sight"]) == 72 and all(len(row) == 20 for row in vs["sight"])
    states = {c for row in vs["sight"] + vs["radio"] for c in row}
    assert states <= {"clear", "blocked", "uncertain"}
    share = d["out_of_sight_share"]
    assert share["unit"] == "%" and 0.0 <= share["value"] <= 100.0
    radio = d["radio_not_clear_share"]
    # The radio path needs more than the line: never clearer than the sight.
    assert radio["value"] >= share["value"] - 1e-9
    assert d["longest_out_of_sight_m"]["value"] is None
    assert "No drive is published for Yaoki" in d["longest_out_of_sight_m"]["missing_reason"]
    a = d["assumptions"]
    assert a["lander_antenna_m"]["provenance"] == "assumed" and a["radio_mhz"]["value"] == 2400
    assert d["terrain"]["post_m"] == 20.0
    assert body["meta"]["engines"] == {"los": "los-2"}


async def test_rover_outside_the_polar_terrain_is_not_resolvable(anon_client) -> None:
    r = await anon_client.get(f"{API}/missions/im-3/contact/rover", params={"rover": "im-3/cadre"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["resolvable"] is False and "polar terrain" in d["reason"]
    assert d["viewshed"] is None and d["out_of_sight_share"]["missing_reason"]
    r = await anon_client.get(f"{API}/missions/im-1/contact/rover")
    assert r.status_code == 409 and r.json()["detail"]["type"].endswith("no-rover")
    r = await anon_client.get(f"{API}/missions/im-2/contact/rover", params={"rover": "x"})
    assert r.status_code == 422 and "im-2/yaoki" in r.json()["detail"]["detail"]


PLAN = f"{API}/missions/griffin-1/contact/plan"
DATES = {"start": "2027-03-20T00:00:00Z", "end": "2027-03-22T00:00:00Z"}


async def test_the_contact_plan_lists_a_relay_only_when_asked_and_says_it_is_planned(
    anon_client,
) -> None:
    """Griffin-1's pole site over two days: the plan has the direct contacts alone, and with
    ``?relay=`` also Lunar Pathfinder's, at one placement, marked planned."""
    await _answer(anon_client, "griffin-1", **DATES)
    body = await _answer(anon_client, "griffin-1", **DATES, relay="lunar-pathfinder")
    stations = {n["id"] for n in body["data"]["nodes"] if n["kind"] == "station"}

    # Not asked for: the same contacts as before, none through the relay, and the answer's
    # own shape does not carry the export's material.
    alone = await anon_client.get(PLAN, params={**DATES, "format": "csv"})
    assert alone.status_code == 200, alone.text
    rows = list(csv.DictReader(io.StringIO(alone.text)))
    assert list(rows[0]) == ["from", "to", "start_utc", "end_utc", "hours", "basis"]
    assert rows and {r["basis"] for r in rows} == {"direct"}
    assert {r["from"] for r in rows} == {"lander"} and {r["to"] for r in rows} <= stations
    assert "plan" not in body

    # Asked for: the direct contacts unchanged, then the relay's, in time order.
    both = await anon_client.get(
        PLAN, params={**DATES, "format": "csv", "relay": "lunar-pathfinder"}
    )
    assert both.status_code == 200, both.text
    all_rows = list(csv.DictReader(io.StringIO(both.text)))
    assert [r for r in all_rows if r["basis"] == "direct"] == rows
    via = [r for r in all_rows if r["basis"] != "direct"]
    up = [r for r in via if r["to"] == "lunar-pathfinder"]
    down = [r for r in via if r["from"] == "lunar-pathfinder"]
    assert up and down and len(up) + len(down) == len(via)
    assert {r["from"] for r in up} == {"lander"} and {r["to"] for r in down} <= stations
    assert all(r["basis"].startswith("planned relay; node ") for r in via)
    assert all("of 5184 placements" in r["basis"] for r in via)
    starts = [r["start_utc"] for r in all_rows]
    assert starts == sorted(starts)
    for r in via:
        assert DATES["start"] <= r["start_utc"] < r["end_utc"] <= DATES["end"]
        assert float(r["hours"]) > 0.0

    # ION: the same contacts as `a contact` lines, each with its `a range`, and comment lines
    # that say what the relay's lines are.
    ion = await anon_client.get(
        PLAN, params={**DATES, "format": "ion", "rate_bps": 2000, "relay": "lunar-pathfinder"}
    )
    assert ion.status_code == 200, ion.text
    lines = ion.text.splitlines()
    numbered = lines[1].removeprefix("# Node numbers: ").rstrip(".").split(", ")
    nodes = {k: int(v) for k, v in (x.split("=") for x in numbered)}
    comments = " ".join(x for x in lines if x.startswith("#"))
    assert "PLANNED relay Lunar Pathfinder" in comments
    assert "ONE placement of the 5184 tried" in comments and "not a forecast" in comments
    assert "if it flies as planned" in comments
    contacts = [x.split() for x in lines if x.startswith("a contact")]
    ranges = [x.split() for x in lines if x.startswith("a range")]
    assert len(contacts) == len(ranges) == len(all_rows)
    assert [c[2:6] for c in contacts] == [r[2:6] for r in ranges]  # same times and nodes
    lp = nodes["lunar-pathfinder"]
    assert {(int(c[4]), int(c[5])) for c in contacts if lp in (int(c[4]), int(c[5]))} >= {
        (nodes["lander"], lp)
    }
    assert sum(1 for c in contacts if lp in (int(c[4]), int(c[5]))) == len(via)

    # ION without the relay: no comment about one and no contact through it.
    plain = await anon_client.get(PLAN, params={**DATES, "format": "ion", "rate_bps": 2000})
    assert plain.status_code == 200 and "PLANNED" not in plain.text
    assert f" {lp} " not in " ".join(
        x for x in plain.text.splitlines() if x.startswith("a contact")
    )


async def test_the_contact_plan_takes_the_dates_and_refuses_a_relay_it_cannot_list(
    anon_client,
) -> None:
    # Dates that were never asked for are worked out first: the plan waits, it does not guess.
    r = await anon_client.get(PLAN, params={**DATES, "format": "csv"})
    assert r.status_code == 409 and "still being worked out" in r.json()["detail"]["detail"]
    r = await anon_client.get(PLAN, params={"format": "csv", "relay": "nope"})
    assert r.status_code == 422 and "lunar-pathfinder" in r.json()["detail"]["detail"]
    r = await anon_client.get(PLAN, params={"format": "csv", "relay": "lro"})
    assert r.status_code == 422 and "no relay service" in r.json()["detail"]["detail"]


def _png_size(blob: bytes) -> tuple[int, int]:
    assert blob[:8] == b"\x89PNG\r\n\x1a\n"
    return int.from_bytes(blob[16:20], "big"), int.from_bytes(blob[20:24], "big")


async def _rover_answer(client, mission: str, **params) -> dict:
    r = await client.get(f"{API}/missions/{mission}/contact/rover", params=params)
    if r.status_code == 202:
        assert await Worker(owner="test", handlers=HANDLERS).run_once() is not None
        r = await client.get(f"{API}/missions/{mission}/contact/rover", params=params)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_the_line_of_sight_is_served_as_map_tiles_over_the_terrain(anon_client) -> None:
    from app.config import get_settings
    from app.core.projections import local_frame
    from app.db.repositories.jobs import AssessmentRepository
    from app.services import contact_tiles

    d = await _rover_answer(anon_client, "im-2")
    template = d["viewshed_tile"]
    assert template.startswith("/tiles/viewshed/") and template.endswith("/{z}/{x}/{y}.png")
    # The answer says where the lander is, so a map can place the tiles.
    assert d["lander"]["lat_deg"] == pytest.approx(-84.79, abs=0.01)
    assert d["lander"]["lon_deg"] == pytest.approx(29.2, abs=0.01)
    aid = int(template.split("/")[3])
    async with session_scope() as s:
        rec = await AssessmentRepository(s).get(aid)
    assert rec is not None and rec.kind == "rover"
    f = local_frame(rec.params["lon_deg"], rec.params["lat_deg"])
    z = 10
    half = contact_tiles._half_extent_m(get_settings().regional_dem_path)
    size = 2 * half / 2**z
    tx, ty = int((f.x0_m + half) // size), int((half - f.y0_m) // size)

    def url(layer: str, z_: int = z, x: int = tx, y: int = ty) -> str:
        return f"{API}{template}".format(z=z_, x=x, y=y) + f"?layer={layer}"

    for layer in ("sight", "radio", "terrain"):
        r = await anon_client.get(url(layer))
        assert r.status_code == 200 and r.headers["content-type"] == "image/png", (layer, r.text)
        assert _png_size(r.content) == (256, 256)
    # The layer is the line of sight unless asked otherwise.
    plain = await anon_client.get(url("sight").split("?")[0])
    assert plain.content == (await anon_client.get(url("sight"))).content
    # An unchanged tile is not sent again; a tile with nothing in it is a 204, not a 404.
    tag = (await anon_client.get(url("sight"))).headers["etag"]
    again = await anon_client.get(url("sight"), headers={"if-none-match": tag})
    assert again.status_code == 304
    away = await anon_client.get(url("sight", x=0, y=0))
    assert away.status_code == 204
    # The terrain is drawn from the elevation model the answer used, not the coarse regional one.
    r = await anon_client.get(url("terrain"))
    assert r.headers["x-tile-source"] in ("static", "dynamic")

    # What cannot be drawn is said, and the answer is the one asked about.
    r = await anon_client.get(url("nope"))
    assert r.status_code == 404 and r.json()["detail"]["type"].endswith("unknown-layer")
    r = await anon_client.get(f"{API}/tiles/viewshed/{aid}/10/99999/0.png")
    assert r.status_code == 404 and r.json()["detail"]["type"].endswith("tile-out-of-scheme")
    r = await anon_client.get(f"{API}/tiles/viewshed/{aid}/13/0/0.png")
    assert r.status_code == 422  # deeper than the scheme goes
    r = await anon_client.get(f"{API}/tiles/viewshed/999999/10/0/0.png")
    assert r.status_code == 404 and r.json()["detail"]["type"].endswith("no-viewshed")
    await _answer(anon_client, "im-1")  # a contact answer is not a map
    async with session_scope() as s:
        other = (
            await s.execute(text("SELECT max(id) FROM assessments WHERE kind = 'contact'"))
        ).scalar_one()
    r = await anon_client.get(f"{API}/tiles/viewshed/{other}/10/0/0.png")
    assert r.status_code == 404 and r.json()["detail"]["type"].endswith("no-viewshed")


async def test_a_site_outside_the_polar_terrain_has_no_map_to_fetch(anon_client) -> None:
    d = await _rover_answer(anon_client, "im-3", rover="im-3/cadre")
    assert d["resolvable"] is False and d["viewshed"] is None and d["viewshed_tile"] is None
    assert d["lander"] is None
