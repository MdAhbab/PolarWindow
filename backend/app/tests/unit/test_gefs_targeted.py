"""GEFS at the launch times of upcoming opportunities (B0, B3): which steps are asked for."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.feeds.adapters import nomads

RUN = datetime(2026, 10, 1, 12, tzinfo=UTC)


def test_gefs_lead_is_the_nearest_output_step() -> None:
    assert nomads.gefs_lead(RUN, RUN + timedelta(hours=25, minutes=10)) == 24
    assert nomads.gefs_lead(RUN, RUN + timedelta(hours=26)) == 27
    assert nomads.gefs_lead(RUN, RUN + timedelta(hours=250)) == 252  # 6-hourly past 240 h
    assert nomads.gefs_lead(RUN, RUN - timedelta(hours=1)) is None
    assert nomads.gefs_lead(RUN, RUN + timedelta(days=17)) is None


@pytest.mark.asyncio
async def test_no_launch_in_reach_asks_nothing() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(404)

    async def wanted(_region: str) -> list[datetime]:
        return []

    (p,) = [
        x
        for x in nomads.products(
            {"florida": [("ksc-lc-39a", 28.6, -80.6)]},
            hrrr_regions=set(),
            now=lambda: RUN + timedelta(hours=7),
            wanted=wanted,
        )
        if x.product == "gefs_launch"
    ]
    assert p.custom_fetch is not None
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        got = await p.custom_fetch(client, None, None)
    assert got.not_modified and calls == []


@pytest.mark.asyncio
async def test_the_steps_nearest_each_launch_are_asked_for(monkeypatch) -> None:
    monkeypatch.setattr(nomads, "PAUSE_S", 0.0)
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.params["file"])
        return httpx.Response(200, content=b"GRIB-body")

    async def wanted(region: str) -> list[datetime]:
        assert region == "florida"
        return [RUN + timedelta(hours=49), RUN + timedelta(hours=100, minutes=40)]

    (p,) = [
        x
        for x in nomads.products(
            {"florida": [("ksc-lc-39a", 28.6, -80.6)]},
            hrrr_regions=set(),
            now=lambda: RUN + timedelta(hours=7),
            wanted=wanted,
        )
        if x.product == "gefs_launch"
    ]
    assert p.custom_fetch is not None
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        got = await p.custom_fetch(client, None, None)
    # The 18 UTC run is the latest at 19 UTC: 43 h and 94.7 h ahead of it.
    leads = {f.rsplit(".f", 1)[1] for f in asked}
    assert leads == {"042", "096"}
    assert len(asked) == 1 + 2 * 2 * len(nomads.GEFS_MEMBERS)  # probe + a and b per member
    assert got.url.endswith("lead=42,96")
