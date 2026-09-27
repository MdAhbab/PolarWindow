"""The feeds worker end to end against recorded responses (no network), and /feeds.

Also the chaos cases (plan, track I): a provider that is down, slow,
malformed or stale leaves every other product and provider working, and
``/healthz`` says *degraded*, never *down*.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import text

from app.db.repositories.feeds import FeedRepository
from app.db.session import session_scope
from app.feeds import scheduler
from app.feeds.adapters import donki, dsn_now, swpc
from app.feeds.base import Product, ProviderSpec
from app.services import feed_service

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]

FX = Path(__file__).resolve().parents[1] / "fixtures" / "feeds"
API = "/api/v1"
NOW = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
async def clean():
    async with session_scope() as s:
        for t in ("assessment_inputs", "feed_snapshots", "feed_health", "feed_limits"):
            await s.execute(text(f"DELETE FROM {t}"))  # noqa: S608 -- fixed table names
    yield


def _sched(tmp_path: Path, products, now=NOW) -> scheduler.Scheduler:
    return scheduler.Scheduler(
        products=products,
        providers={
            "swpc": swpc.PROVIDER,
            "dsn_now": dsn_now.PROVIDER,
            "donki": ProviderSpec("donki", 10, 20),
        },
        raw_root=tmp_path / "feeds" / "raw",
        now=lambda: now,
        secrets=("sekret-key",),
        sleep=lambda _s: None,
    )


def _kp_and_dsn() -> tuple[Product, Product]:
    kp = next(p for p in swpc.products() if p.product == "kp")
    return kp, dsn_now.products()[0]


async def test_a_run_records_one_snapshot_per_product(tmp_path) -> None:
    kp, dsn = _kp_and_dsn()
    sch = _sched(tmp_path, [kp, dsn])
    await sch.sync()
    with respx.mock(assert_all_mocked=True) as rx:
        rx.get(kp.url).mock(
            return_value=httpx.Response(
                200, content=(FX / "swpc_kp.json").read_bytes(), headers={"ETag": '"k1"'}
            )
        )
        rx.get(dsn.url).mock(
            return_value=httpx.Response(200, content=(FX / "dsn_now.xml").read_bytes())
        )
        res = await sch.run_once()
    assert sorted(r.status for r in res) == ["new", "new"]
    async with session_scope() as s:
        snap = await FeedRepository(s).latest_ok("swpc", "kp")
        assert snap is not None and snap.etag == '"k1"' and snap.parsed is not None
        assert snap.parsed["latest"]["kp"] >= 0
        assert snap.licence.startswith("NOAA SWPC")
        # Not due again until its interval has passed.
        assert await sch.due() == []


async def test_a_304_and_an_identical_body_add_no_snapshot(tmp_path) -> None:
    kp, _ = _kp_and_dsn()
    body = (FX / "swpc_kp.json").read_bytes()
    t = [NOW]
    sch = scheduler.Scheduler(
        products=[kp],
        providers={"swpc": swpc.PROVIDER},
        raw_root=tmp_path,
        now=lambda: t[0],
        sleep=lambda _s: None,
    )
    await sch.sync()
    with respx.mock() as rx:
        route = rx.get(kp.url).mock(
            side_effect=[
                httpx.Response(200, content=body, headers={"ETag": '"a"'}),
                httpx.Response(304),
                httpx.Response(200, content=body, headers={"ETag": '"b"'}),
            ]
        )
        await sch.run_once()
        t[0] = NOW + timedelta(hours=1)
        r2 = await sch.run_once()
        t[0] = NOW + timedelta(hours=2)
        r3 = await sch.run_once()
    assert route.calls[1].request.headers["If-None-Match"] == '"a"'
    assert r2[0].status == "unchanged" and r3[0].status == "unchanged"
    async with session_scope() as s:
        n = (await s.execute(text("SELECT count(*) FROM feed_snapshots"))).scalar_one()
    assert n == 1


async def test_a_malformed_body_is_kept_as_rejected_and_the_good_one_stays(tmp_path) -> None:
    kp, _ = _kp_and_dsn()
    t = [NOW]
    sch = scheduler.Scheduler(
        products=[kp],
        providers={"swpc": swpc.PROVIDER},
        raw_root=tmp_path,
        now=lambda: t[0],
        sleep=lambda _s: None,
    )
    await sch.sync()
    with respx.mock() as rx:
        rx.get(kp.url).mock(
            side_effect=[
                httpx.Response(200, content=(FX / "swpc_kp.json").read_bytes()),
                httpx.Response(200, content=b"<html>We are down for maintenance</html>"),
            ]
        )
        await sch.run_once()
        t[0] = NOW + timedelta(hours=1)
        res = await sch.run_once()
    assert res[0].status == "rejected" and not res[0].ok
    async with session_scope() as s:
        good = await FeedRepository(s).latest_ok("swpc", "kp")
        rows = (
            await s.execute(text("SELECT status, issues FROM feed_snapshots ORDER BY id"))
        ).all()
        health = (await FeedRepository(s).health("swpc"))[0]
    assert good is not None and good.status == "ok"
    assert [r.status for r in rows] == ["ok", "rejected"]
    assert "rejected" in rows[1].issues[0]
    assert health.consecutive_errors == 1


async def test_one_provider_down_leaves_the_others_working(tmp_path) -> None:
    kp, dsn = _kp_and_dsn()
    sch = _sched(tmp_path, [kp, dsn])
    await sch.sync()
    with respx.mock() as rx:
        rx.get(kp.url).mock(side_effect=httpx.ConnectError("no route to host"))
        rx.get(dsn.url).mock(
            return_value=httpx.Response(200, content=(FX / "dsn_now.xml").read_bytes())
        )
        res = {r.product[0]: r for r in await sch.run_once()}
    assert not res["swpc"].ok and "could not reach" in res["swpc"].message
    assert res["dsn_now"].ok
    async with session_scope() as s:
        summary = await feed_service.summary(s, now=NOW)
    assert summary["failing"] == 1 and summary["ok"] == 1


async def test_the_breaker_opens_and_stops_calling(tmp_path) -> None:
    kp, _ = _kp_and_dsn()
    t = [NOW]
    sch = scheduler.Scheduler(
        products=[kp],
        providers={"swpc": swpc.PROVIDER},
        raw_root=tmp_path,
        now=lambda: t[0],
        sleep=lambda _s: None,
    )
    await sch.sync()

    async def due_now() -> None:
        async with session_scope() as s:
            await s.execute(text("UPDATE feed_health SET next_run_at = :t"), {"t": t[0]})

    with respx.mock() as rx:
        route = rx.get(kp.url).mock(return_value=httpx.Response(500))
        for i in range(5):
            t[0] = NOW + timedelta(minutes=i)
            await due_now()
            await sch.run_once()
        assert route.call_count == 5 * 4  # five runs, each with its three retries
        t[0] = NOW + timedelta(minutes=6)
        await due_now()
        res = await sch.run_once()
        assert res[0].status == "skipped" and route.call_count == 20  # held: no request
        # After the cool-down, one trial request and no retries.
        t[0] = NOW + timedelta(minutes=30)
        await due_now()
        await sch.run_once()
        assert route.call_count == 21
    async with session_scope() as s:
        lim = await FeedRepository(s).get_limit("swpc")
    assert lim is not None and lim.breaker == "open"


async def test_secrets_never_reach_the_database(tmp_path) -> None:
    p = donki.products(NOW)[0]
    p = type(p)(
        **{
            **{f: getattr(p, f) for f in p.__dataclass_fields__},
            "params": {**p.params, "api_key": "sekret-key"},
        }
    )
    sch = _sched(tmp_path, [p])
    await sch.sync()
    with respx.mock() as rx:
        rx.get(url__startswith=p.url).mock(
            side_effect=[
                httpx.ConnectError("failed for https://api.nasa.gov/DONKI/CME?api_key=sekret-key")
            ]
            * 4
        )
        await sch.run_once()
        sch.now = lambda: NOW + timedelta(hours=5)
        rx.get(url__startswith=p.url).mock(
            return_value=httpx.Response(200, content=(FX / "donki_cme.json").read_bytes())
        )
        await sch.run_once()
    async with session_scope() as s:
        dump = (
            await s.execute(
                text("SELECT string_agg(url || coalesce(issues::text,''), ' ') FROM feed_snapshots")
            )
        ).scalar_one()
        errs = (
            await s.execute(
                text("SELECT string_agg(coalesce(last_error, ''), ' ') FROM feed_health")
            )
        ).scalar_one()
    assert "sekret-key" not in (dump or "") and "sekret-key" not in (errs or "")


async def test_stale_data_gives_no_number_and_says_why(tmp_path) -> None:
    kp, _ = _kp_and_dsn()
    sch = _sched(tmp_path, [kp])
    await sch.sync()
    with respx.mock() as rx:
        rx.get(kp.url).mock(
            return_value=httpx.Response(200, content=(FX / "swpc_kp.json").read_bytes())
        )
        await sch.run_once()
    async with session_scope() as s:
        fresh = await feed_service.latest(s, "swpc", "kp", now=NOW)
        old = await feed_service.latest(s, "swpc", "kp", now=NOW + timedelta(days=3))
        none = await feed_service.latest(s, "swpc", "goes_protons", now=NOW)
    assert not fresh.stale and fresh.values is not None
    assert (
        old.stale and old.values is None and "past its 6 hours limit" in (old.missing_reason or "")
    )
    assert none.values is None and "No data" in (none.missing_reason or "")


async def test_feeds_route_and_refresh_needs_a_name(anon_client, tmp_path) -> None:
    kp, _ = _kp_and_dsn()
    await _sched(tmp_path, [kp]).sync()
    r = await anon_client.get(f"{API}/feeds")
    assert r.status_code == 200
    row = r.json()["feeds"][0]
    assert row["provider"] == "swpc" and row["stale"] is True and row["age_s"] is None
    assert (await anon_client.post(f"{API}/feeds/swpc/refresh")).status_code == 401
    tok = (await anon_client.post(f"{API}/auth/demo", json={"name": "Test manager"})).json()
    client = anon_client
    client.headers["Authorization"] = f"Bearer {tok['token']}"
    ok = await client.post(f"{API}/feeds/swpc/refresh")
    assert ok.status_code == 200 and ok.json()["products"] == 1
    assert (await client.post(f"{API}/feeds/nobody/refresh")).status_code == 404
    h = await client.get(f"{API}/history", params={"entity": "feed", "id": "swpc"})
    if h.status_code == 200:  # the generic history route lands with T3
        assert h.json()["entries"][-1]["by"].startswith("Test manager")


async def test_healthz_reports_feeds_and_is_never_down_for_them(anon_client, tmp_path) -> None:
    kp, _ = _kp_and_dsn()
    sch = _sched(tmp_path, [kp])
    await sch.sync()
    with respx.mock() as rx:
        rx.get(kp.url).mock(side_effect=httpx.ConnectError("down"))
        await sch.run_once()
    r = await anon_client.get("/healthz")
    body = r.json()
    assert body["feeds"]["failing"] == 1
    assert body["status"] in ("degraded", "down")
    if body["kernels"]["loaded"] and body["db"] == "ok":
        assert body["status"] == "degraded" and r.status_code == 200
