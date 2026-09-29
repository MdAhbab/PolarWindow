"""The launch weather's cross-provider check: NWS and HRRR beside GEFS, and when they disagree."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, insert

from app.db.models import FeedSnapshot
from app.db.session import session_scope

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]
API = "/api/v1"
T0 = (datetime.now(UTC) + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
RULE = "f9-wind-162ft"  # 30 mph at 162 ft


def _iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _member(u80: float) -> dict[str, float]:
    return {"u10_m_s": u80 * 0.8, "v10_m_s": 0.0, "u80_m_s": u80, "v80_m_s": 0.0}


async def _snap(provider: str, product: str, key: str, parsed: dict) -> None:
    async with session_scope() as s:
        await s.execute(
            insert(FeedSnapshot).values(
                provider=provider,
                product=product,
                location_key=key,
                issued_at=datetime.now(UTC),
                fetched_at=datetime.now(UTC),
                url=f"https://example.test/{provider}/{product}",
                http_status=200,
                parsed=parsed,
                parser_version="test",
                licence="test",
                status="ok",
                issues=[],
            )
        )


@pytest.fixture(autouse=True)
async def clean():
    async with session_scope() as s:
        await s.execute(delete(FeedSnapshot))
    yield


async def _feeds(gefs_u80: float, hrrr_u80: float, nws_m_s: float) -> dict:
    valid = _iso(T0 + timedelta(hours=1))
    members = {str(i): _member(gefs_u80) for i in range(31)}
    await _snap(
        "nomads",
        "gefs_launch",
        "florida",
        {
            "model": "GEFS",
            "points": {"ksc-lc-39a": {"leads": {"48": {"valid": valid, "members": members}}}},
        },
    )
    await _snap(
        "nomads",
        "hrrr",
        "florida",
        {
            "model": "HRRR",
            "points": {
                "ksc-lc-39a": {
                    "leads": {"18": {"valid": valid, "members": {"0": _member(hrrr_u80)}}}
                }
            },
        },
    )
    hours = [_iso(T0 + timedelta(hours=h)) for h in (-1, 0, 1)]
    await _snap(
        "nws",
        "grid",
        "ksc-lc-39a",
        {
            "times": hours,
            "wind_speed_m_s": [nws_m_s] * 3,
            "height_m": {"wind": 10.0, "temperature": 2.0},
        },
    )
    return {}


async def _row(anon_client) -> dict:
    r = await anon_client.get(
        f"{API}/missions/im-2/launch/weather", params={"t0": T0.isoformat(), "pad": "ksc-lc-39a"}
    )
    assert r.status_code == 200, r.text
    return {x["id"]: x for x in r.json()["data"]["rules"]}[RULE]


async def test_forecasts_that_split_on_the_limit_are_flagged_with_who_and_how(anon_client) -> None:
    # 30 mph is 13.4 m/s. GEFS: every run at 3 m/s (none breaks it); HRRR 20 m/s (over);
    # NWS 10 m wind 12 m/s, which is 15 m/s at 49 m on a neutral profile (over).
    await _feeds(gefs_u80=3.0, hrrr_u80=20.0, nws_m_s=12.0)
    row = await _row(anon_client)
    by = {f["system"]: f for f in row["one_forecast"]}
    assert set(by) == {"HRRR", "NWS"} and by["HRRR"]["over"] and by["NWS"]["over"]
    assert by["NWS"]["value"]["unit"] == "mph" and by["NWS"]["value"]["provenance"] == "computed"
    assert by["NWS"]["value"]["value"] == pytest.approx(12.0 * 1.2757 / 0.44704, rel=0.01)
    assert "no archive" in by["NWS"]["note"]
    assert by["HRRR"]["note"]  # how it did against the station, or that it is not checked yet
    assert row["per_system"][0]["share"]["k"] == 0
    assert row["disagreement"] is True
    note = row["disagreement_note"]
    assert "NWS puts the wind at" in note and "HRRR puts the wind at" in note
    assert "0 of 31 GEFS runs break it" in note


async def test_forecasts_that_agree_are_not_flagged(anon_client) -> None:
    await _feeds(gefs_u80=3.0, hrrr_u80=3.0, nws_m_s=2.0)
    row = await _row(anon_client)
    assert [f["over"] for f in row["one_forecast"]] == [False, False]
    assert row["disagreement"] is False and row["disagreement_note"] is None


async def test_without_a_national_weather_service_wind_only_hrrr_is_listed(anon_client) -> None:
    await _feeds(gefs_u80=3.0, hrrr_u80=3.0, nws_m_s=2.0)
    async with session_scope() as s:
        await s.execute(delete(FeedSnapshot).where(FeedSnapshot.provider == "nws"))
    row = await _row(anon_client)
    assert [f["system"] for f in row["one_forecast"]] == ["HRRR"]
    assert row["disagreement"] is False
