"""Trip (T2, C0): flown trips from NASA's reconstructions, and why a planned one has none."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text

from app.db.session import session_scope
from app.workers import handlers  # noqa: F401 -- registers the trip job
from app.workers.compute import HANDLERS, Worker

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]
API = "/api/v1"


@pytest.fixture(autouse=True)
async def clean():
    async with session_scope() as s:
        for t in ("jobs", "assessment_inputs", "assessments"):
            await s.execute(text(f"DELETE FROM {t}"))  # noqa: S608 -- fixed table names
    yield


async def test_a_planned_mission_has_no_trip_and_says_why(anon_client) -> None:
    r = await anon_client.get(f"{API}/missions/griffin-1/trip")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["source"] == "none" and "launch" in d["none_reason"]
    assert d["numbers"]["sunlight_h"]["value"] is None


@pytest.mark.requires_kernels
@pytest.mark.requires_clps_spice
async def test_im2_flown_trip(anon_client, settings, monkeypatch) -> None:
    if not (settings.data_dir / "clps/clps_prime1_im2_cru_rec_250227_250306_v01.bsp").exists():
        pytest.skip("IM-2 reconstruction not on disk")
    from app.workers.handlers import trip as trip_handler

    monkeypatch.setattr(trip_handler, "BUDGET_RUNS", 40)  # the budget's size is a golden test
    r = await anon_client.get(f"{API}/missions/im-2/trip")
    assert r.status_code == 202
    assert await Worker(owner="t", handlers=HANDLERS).run_once() is not None
    r = await anon_client.get(f"{API}/missions/im-2/trip")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["source"] == "flown" and len(d["samples"]) <= 2000
    n = d["numbers"]
    span = datetime.fromisoformat(d["end"].replace("Z", "+00:00")) - datetime.fromisoformat(
        d["start"].replace("Z", "+00:00")
    )
    total_h = span.total_seconds() / 3600
    assert 0 < n["sunlight_h"]["value"] <= total_h
    assert n["longest_shadow_h"]["value"] < 1.0  # lunar-orbit shadows last under an hour
    assert len(d["shadow"]) >= 10
    # The Moon's pull overtook Earth's before landing, 30,000-45,000 km out.
    mp = d["moon_pull"]
    assert 30_000 < mp["equal_pull_km"] < 45_000 and mp["t_equal_pull"] is not None
    assert {s["light"] for s in d["samples"]} <= {"lit", "penumbral", "dark"}
    assert r.json()["meta"]["engines"] == {"ecl": "ecl-1", "traj": "traj-3"}
    assert len(d["covered"]) >= 1 and d["covered"][0]["start"] == d["start"]
    # Burns found in the reconstruction: corrections on the way, then lunar orbit.
    names = [b["name"] for b in d["burns"]]
    assert names[-1] == "Entering lunar orbit" and "Correction 1" in names
    assert 700 < d["burns"][-1]["dv_m_s"]["value"] < 900
    c = d["corrections"]
    assert c["runs"] == 40 and c["missed"] == 0 and "assumed" in c["label"]
    assert [b["name"].split(",")[0] for b in c["burns"]] == [
        "First correction",
        "Second correction",
        "Third correction",
    ]
    p99 = c["total_p99_m_s"]
    assert p99["lo"] <= p99["value"] <= p99["hi"] and c["assumptions"]
    assert d["corrections_note"] is None


@pytest.mark.requires_kernels
@pytest.mark.requires_clps_spice
async def test_im1_trip_exports_as_oem_and_csv_with_its_gaps(anon_client, settings) -> None:
    from app.core import oem

    if not (settings.data_dir / "clps/clps_to2im_im1_cru_rec_240216_240221_v01.bsp").exists():
        pytest.skip("IM-1 reconstruction not on disk")
    r = await anon_client.get(f"{API}/missions/im-1/trip/export?format=oem")
    assert r.status_code == 200, r.text
    assert "im-1-trip.oem" in r.headers["content-disposition"]
    blocks = oem.parse_oem(r.text)
    assert len(blocks) >= 2  # IM-1's reconstruction comes in separate stretches
    for _times, states in blocks:
        radius = (states[:, :3] ** 2).sum(axis=1) ** 0.5
        assert (radius > 6_000).all() and (radius < 500_000).all()  # km, Earth to beyond the Moon
    r = await anon_client.get(f"{API}/missions/im-1/trip/export?format=csv")
    assert r.status_code == 200 and r.text.splitlines()[1].startswith("time_utc,stretch")
    r = await anon_client.get(f"{API}/missions/griffin-1/trip/export")
    assert r.status_code == 409
