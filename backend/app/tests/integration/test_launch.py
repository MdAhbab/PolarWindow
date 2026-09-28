"""Launch (T2, D1/D2): the launch a mission flew, and a calendar for a planned one."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.db.session import session_scope
from app.services import lifecycle
from app.workers import handlers  # noqa: F401 -- registers the launch job
from app.workers.compute import HANDLERS, Worker

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]
API = "/api/v1"


@pytest.fixture(autouse=True)
async def clean():
    async with session_scope() as s:
        for t in ("jobs", "assessment_inputs", "assessments"):
            await s.execute(text(f"DELETE FROM {t}"))  # noqa: S608 -- fixed table names
    yield


async def _answer(client, path: str) -> dict:
    r = await client.get(path)
    if r.status_code == 202:
        assert await Worker(owner="t", handlers=HANDLERS).run_once() is not None
        r = await client.get(path)
    assert r.status_code == 200, r.text
    return r.json()


async def test_no_pad_says_why_at_once(anon_client) -> None:
    r = await anon_client.get(f"{API}/missions/blue-ghost-m3/launch")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["opportunities"] == [] and "not published" in d["none_reason"]
    assert d["landing_rule"]["sun_elevation_min_deg"]["missing_reason"]


async def test_dates_are_checked(anon_client) -> None:
    r = await anon_client.get(
        f"{API}/missions/griffin-1/launch?from=2026-10-01T00:00:00Z&to=2027-06-01T00:00:00Z"
    )
    assert r.status_code == 422


@pytest.mark.requires_kernels
@pytest.mark.requires_clps_spice
async def test_im2_launch_worked_out_again_from_its_trajectory(anon_client, settings) -> None:
    if not (settings.data_dir / "clps/clps_prime1_im2_cru_rec_250227_250306_v01.bsp").exists():
        pytest.skip("IM-2 reconstruction not on disk")
    body = await _answer(anon_client, f"{API}/missions/im-2/launch")
    d = body["data"]
    (o,) = d["opportunities"]
    assert o["basis"] == "reconstructed"
    # Within two minutes of the published liftoff (the plan's acceptance for IM-2).
    assert abs(o["t0"]["value"] - d["published_t0"]["value"]) < 120
    assert o["transfer"]["type"] == "direct" and 4.0 < o["transfer"]["flight_days"]["value"] < 5.0
    assert 30 < o["coast_min"]["value"] < 45 and 3000 < o["dv_tli_m_s"]["value"] < 3300
    assert o["landing"]["earth_up"] is True
    assert "inside the times the landing rule allows" in o["note"]
    assert body["meta"]["engines"] == {"lw": "lw-4", "traj": "traj-3", "vis": "vis-2"}


@pytest.mark.requires_kernels
@pytest.mark.requires_clps_spice
async def test_peregrine_shows_the_published_liftoff(anon_client, settings) -> None:
    if not (settings.data_dir / "clps/clps_to2ab_apm1_cru_rec_240108_240118_v02.bsp").exists():
        pytest.skip("Peregrine reconstruction not on disk")
    d = (await _answer(anon_client, f"{API}/missions/peregrine-m1/launch"))["data"]
    (o,) = d["opportunities"]
    assert o["basis"] == "published" and o["transfer"]["flight_days"]["value"] is None
    assert o["landing"]["time"]["missing_reason"]


@pytest.mark.requires_kernels
@pytest.mark.requires_clps_spice
async def test_griffin_calendar_backed_out_from_the_landing(anon_client) -> None:
    body = await _answer(
        anon_client,
        f"{API}/missions/griffin-1/launch?from=2026-10-01T00:00:00Z&to=2026-12-01T00:00:00Z",
    )
    d = body["data"]
    assert d["none_reason"] is None, d["none_reason"]
    assert d["opportunities"]
    for o in d["opportunities"]:
        t0 = datetime.fromtimestamp(o["t0"]["value"])
        assert datetime(2026, 9, 30) < t0 < datetime(2026, 12, 2)
        assert o["basis"] == "designed" and o["t0"]["pm"] > 0
        assert 3.5 <= o["transfer"]["flight_days"]["value"] <= 6.5
        assert o["landing"]["earth_up"] is True
        assert o["landing"]["time"]["value"] > o["t0"]["value"]
        assert "Falcon 9" in o["note"]  # Falcon Heavy's climb is taken from Falcon 9's
        assert "TLI" not in json.dumps(o)
        assert o["weather_note"]
        wait = o["transfer"]["orbit_wait_days"]
        assert wait["provenance"] == "assumed" and wait["lo"] is None and wait["hi"] is None
    # One opportunity per sweep of the climb plane past the Moon: two of any three in a
    # row are of the same sweep, and those are at least half a day apart.
    t0s = sorted(o["t0"]["value"] for o in d["opportunities"])
    assert all(c - a >= 12 * 3600 for a, c in zip(t0s, t0s[2:], strict=False))


@pytest.mark.requires_kernels
@pytest.mark.requires_clps_spice
@pytest.mark.parametrize("mission", ["im-1", "blue-ghost-m1"])
async def test_flown_landings_fall_inside_the_landing_rule(anon_client, mission) -> None:
    from app.services import ascent

    if not ascent.spk_path(mission).exists():
        pytest.skip(f"{mission} reconstruction not on disk")
    d = (await _answer(anon_client, f"{API}/missions/{mission}/launch"))["data"]
    (o,) = d["opportunities"]
    assert "inside the times the landing rule allows" in o["note"]
    assert abs(o["t0"]["value"] - d["published_t0"]["value"]) < (120 if mission == "im-1" else 300)


@pytest.mark.requires_kernels
@pytest.mark.requires_clps_spice
@pytest.mark.parametrize(
    ("mission", "start", "end", "wait_from"),
    [
        ("im-1", datetime(2024, 2, 5, tzinfo=UTC), datetime(2024, 2, 28, tzinfo=UTC), "im-2"),
        ("im-2", datetime(2025, 2, 15, tzinfo=UTC), datetime(2025, 3, 10, tzinfo=UTC), "im-1"),
    ],
)
async def test_flown_launch_days_are_inside_the_backed_out_calendar(
    mission, start, end, wait_from
) -> None:
    """D2 acceptance: design the calendar as if the mission had not flown (its own flight
    left out of the climb, the other Nova-C's time in lunar orbit) and find its launch day."""
    from datetime import timedelta

    from app.core import landing_windows, spice
    from app.db.repositories.missions import MissionRepository
    from app.services import ascent, launch_service
    from app.workers.handlers import launch as job

    async with session_scope() as s:
        flights, _ = await launch_service.reconstructed_flights(s)
        m = await MissionRepository(s).get(mission)
    if not all(ascent.spk_path(f[0]).exists() for f in flights):
        pytest.skip("reconstructions not on disk")
    assert m is not None and m.site_id is not None and m.target is not None
    measured = await spice.run_async(ascent.measure, tuple(tuple(f) for f in flights))
    others = {k: v for k, v in measured.items() if k != mission}
    asc = await spice.run_async(ascent.ascent, "falcon-9", others, spice.gm_m3_s2("EARTH"))
    fl = measured[wait_from].launch
    landing = lifecycle.published_date((await _mission(wait_from)).landing, "x")
    wait_d = (landing["value"] - job._epoch(fl.t_arrive)) / 86_400.0
    tr = await job._track(m.site_id, start + timedelta(days=3.5), end + timedelta(days=30))
    rule = landing_windows.Rule(None, None, None)
    wins = landing_windows.windows(tr.t_s, tr.sun_el, tr.sun_margin, tr.sun_up, tr.earth_up, rule)
    p = {"pad_id": m.lifecycle["pad_id"], "site_lat_deg": m.target["lat_deg"]}
    found = await spice.run_async(
        job._design_all, p, asc, tr, wins, wait_d, start.timestamp(), end.timestamp()
    )
    actual = lifecycle.parse_time(m.lifecycle["t0"]["date"])
    days = {datetime.fromtimestamp(o["t0"], UTC).date() for o in found}
    assert actual.date() in days


async def _mission(mid: str):
    from app.db.repositories.missions import MissionRepository

    async with session_scope() as s:
        return await MissionRepository(s).get(mid)
