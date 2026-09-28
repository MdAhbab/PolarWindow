"""Chaos at the sections (plan track I): a feed that is down, slow, malformed or stale.

``test_feeds.py`` covers the feeds worker itself (one provider down leaves the
others recording, the breaker, a rejected body keeps the good one). These
cases check what a person sees: the section that uses the feed still answers,
the number the feed would give is missing with the reason, the other feeds in
that section and every other section are unaffected, and ``/healthz`` says
*degraded* for a failing feed and never *down*.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import text

from app.db.session import session_scope
from app.feeds import scheduler
from app.feeds.adapters import donki, swpc
from app.feeds.base import Product, ProviderSpec

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]

FX = Path(__file__).resolve().parents[1] / "fixtures" / "feeds"
API = "/api/v1"
#: Sections that use no live feed, or only through a stored answer: they must not change.
OTHERS = ("/missions/im-2/ready", "/missions/im-2/sections", "/missions/im-2/return")


@pytest.fixture(autouse=True)
async def clean():
    async with session_scope() as s:
        for t in ("assessment_inputs", "feed_snapshots", "feed_health", "feed_limits"):
            await s.execute(text(f"DELETE FROM {t}"))  # noqa: S608 -- fixed table names
    yield


def _kp() -> Product:
    return next(p for p in swpc.products() if p.product == "kp")


async def _record(tmp_path: Path, when: datetime, kp_response) -> None:
    """One run of the feeds worker at ``when``: Kp answers as given, DONKI fine."""
    kp = _kp()
    events = donki.products(when)
    sch = scheduler.Scheduler(
        products=[kp, *events],
        providers={"swpc": swpc.PROVIDER, "donki": ProviderSpec("donki", 10, 20)},
        raw_root=tmp_path,
        now=lambda: when,
        sleep=lambda _s: None,
    )
    await sch.sync()
    with respx.mock() as rx:
        route = rx.get(kp.url)
        if isinstance(kp_response, Exception):
            route.mock(side_effect=kp_response)
        else:
            route.mock(return_value=kp_response)
        for p in events:
            rx.get(url__startswith=p.url).mock(
                return_value=httpx.Response(
                    200, content=(FX / f"donki_{p.product}.json").read_bytes()
                )
            )
        await sch.run_once()


async def _others_unchanged(client) -> None:
    for path in OTHERS:
        r = await client.get(f"{API}{path}")
        assert r.status_code == 200, (path, r.text[:200])


@pytest.mark.parametrize(
    ("mode", "response"),
    [
        ("down", httpx.ConnectError("no route to host")),
        ("slow", httpx.ReadTimeout("timed out")),
        ("malformed", httpx.Response(200, content=b"<html>We are down for maintenance</html>")),
    ],
)
async def test_a_failing_feed_is_said_in_its_section_and_nowhere_else(
    anon_client, tmp_path, mode, response
) -> None:
    await _record(tmp_path, datetime.now(UTC), response)
    r = await anon_client.get(f"{API}/space-weather")
    assert r.status_code == 200, (mode, r.text[:200])
    now = r.json()["data"]["now"]
    assert now["kp"]["value"] is None
    assert "the last attempt to fetch it failed" in now["kp"]["missing_reason"], mode
    # The other feed in the same section still answers.
    donki_part = r.json()["data"]["donki"]
    assert donki_part["missing_reason"] is None and donki_part["cme"], mode
    await _others_unchanged(anon_client)
    h = await anon_client.get("/healthz")
    body = h.json()
    assert body["feeds"]["failing"] >= 1
    assert body["status"] != "down" or not body["kernels"]["loaded"] or body["db"] != "ok"
    if body["kernels"]["loaded"] and body["db"] == "ok":
        assert h.status_code == 200 and body["status"] == "degraded"


async def test_a_stale_feed_gives_no_number_and_says_how_old(anon_client, tmp_path) -> None:
    good = httpx.Response(200, content=(FX / "swpc_kp.json").read_bytes())
    await _record(tmp_path, datetime.now(UTC) - timedelta(days=3), good)
    r = await anon_client.get(f"{API}/space-weather")
    assert r.status_code == 200
    kp = r.json()["data"]["now"]["kp"]
    assert kp["value"] is None and "past its" in kp["missing_reason"]
    assert r.json()["meta"]["stale"] is True
    await _others_unchanged(anon_client)
    # Stale alone does not degrade the service: each number already says its age.
    body = (await anon_client.get("/healthz")).json()
    assert body["feeds"]["failing"] == 0 and body["feeds"]["stale"] >= 1


async def test_with_no_feed_recorded_every_section_still_answers(anon_client) -> None:
    """The worst case: the feeds worker never ran. Nothing is 5xx, and the numbers that
    need a feed say which one is missing."""
    paths = (
        "/space-weather",
        "/missions/griffin-1/launch/weather?opportunity=ksc-lc-39a-20261013T0918",
        "/missions/griffin-1/return",
        *OTHERS,
    )
    for path in paths:
        r = await anon_client.get(f"{API}{path}")
        assert r.status_code == 200, (path, r.status_code, r.text[:200])
    sw = (await anon_client.get(f"{API}/space-weather")).json()["data"]["now"]
    assert all(
        v["value"] is None and "No data" in v["missing_reason"]
        for v in sw.values()
        if isinstance(v, dict) and "value" in v
    )
    wx = (
        await anon_client.get(
            f"{API}/missions/griffin-1/launch/weather?opportunity=ksc-lc-39a-20261013T0918"
        )
    ).json()["data"]
    assert wx["rules"], "the rules are listed even with no forecast"
    sea = (await anon_client.get(f"{API}/missions/griffin-1/return")).json()["data"]["booster"]
    if sea["wave_height_m"] is not None:
        assert sea["wave_height_m"]["value"] is None and sea["wave_height_m"]["missing_reason"]


async def test_a_parser_fix_reaches_a_body_that_has_not_changed(tmp_path) -> None:
    from dataclasses import replace

    from app.feeds.http import Fetched
    from app.feeds.recorder import record

    alerts = next(p for p in swpc.products() if p.product == "alerts")
    body = (
        b'[{"product_id":"EF3A","issue_datetime":"2026-09-28 12:00:00.000",'
        b'"message":"Space Weather Message Code: ALTEF3\\r\\nSerial Number: 1\\r\\n'
        b"Issue Time: 2026 Sep 28 1200 UTC\\r\\n\\r\\n"
        b'CONTINUED ALERT: Electron 2MeV Integral Flux exceeded 1000pfu\\r\\n"}]'
    )
    got = Fetched("https://example.test/alerts.json", 200, body, None, None, None, False, 1)
    old = replace(alerts, parser_version="alerts-0")
    async with session_scope() as s:
        first = await record(s, old, got, raw_root=tmp_path)
        again = await record(s, old, got, raw_root=tmp_path)
        fixed = await record(s, alerts, got, raw_root=tmp_path)
        once_more = await record(s, alerts, got, raw_root=tmp_path)
        kept = (
            await s.execute(
                text(
                    "SELECT count(*), max(parser_version) FROM feed_snapshots "
                    "WHERE product = 'alerts'"
                )
            )
        ).one()
    assert (first.status, again.status) == ("new", "unchanged")
    assert fixed.status == "reparsed" and fixed.snapshot_id == first.snapshot_id
    assert once_more.status == "unchanged"
    assert tuple(kept) == (1, alerts.parser_version)


async def test_after_a_parser_change_the_worker_asks_for_the_whole_body(tmp_path) -> None:
    from dataclasses import replace

    alerts = next(p for p in swpc.products() if p.product == "alerts")
    body = b'[{"product_id":"EF3A","issue_datetime":"2026-09-28 12:00:00.000","message":"x"}]'
    t0 = datetime.now(UTC)
    sent: list[str | None] = []
    for product, when in (
        (replace(alerts, parser_version="alerts-0"), t0),
        (alerts, t0 + timedelta(hours=1)),
    ):
        sch = scheduler.Scheduler(
            products=[product],
            providers={"swpc": swpc.PROVIDER},
            raw_root=tmp_path,
            now=lambda when=when: when,
            sleep=lambda _s: None,
        )
        await sch.sync()
        with respx.mock() as rx:

            def answer(request: httpx.Request) -> httpx.Response:
                sent.append(request.headers.get("if-none-match"))
                return httpx.Response(200, content=body, headers={"ETag": '"v1"'})

            rx.get(alerts.url).mock(side_effect=answer)
            await sch.run_once()
    assert sent == [None, None]
    async with session_scope() as s:
        kept = (
            (
                await s.execute(
                    text("SELECT parser_version FROM feed_snapshots WHERE product = 'alerts'")
                )
            )
            .scalars()
            .all()
        )
    assert kept == [alerts.parser_version]
