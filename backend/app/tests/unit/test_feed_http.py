"""The shared HTTP layer: retries, Retry-After, conditional GETs, breaker, bucket."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from app.feeds import http

URL = "https://example.test/data.json"
T0 = datetime(2026, 9, 26, 12, tzinfo=UTC)


class Sleeps:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, s: float) -> None:
        self.calls.append(s)


async def test_retries_a_server_error_then_succeeds() -> None:
    sleeps = Sleeps()
    with respx.mock(assert_all_called=True) as rx:
        rx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(200, json={"a": 1})])
        async with httpx.AsyncClient() as c:
            got = await http.fetch(c, URL, sleep=sleeps)
    assert got.status == 200 and got.attempts == 2
    assert len(sleeps.calls) == 1


async def test_honours_retry_after_seconds() -> None:
    sleeps = Sleeps()
    with respx.mock() as rx:
        rx.get(URL).mock(
            side_effect=[httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200)]
        )
        async with httpx.AsyncClient() as c:
            await http.fetch(c, URL, sleep=sleeps)
    assert sleeps.calls == [7.0]


def test_retry_after_as_a_date_and_capped() -> None:
    when = (T0 + timedelta(seconds=30)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert http.retry_after_s(when, T0) == pytest.approx(30.0)
    assert http.retry_after_s("99999", T0) == http.MAX_RETRY_AFTER_S
    assert http.retry_after_s("soon", T0) is None


async def test_gives_up_after_the_retries_with_the_reason() -> None:
    with respx.mock() as rx:
        rx.get(URL).mock(return_value=httpx.Response(502))
        async with httpx.AsyncClient() as c:
            with pytest.raises(http.FeedHttpError, match="502"):
                await http.fetch(c, URL, sleep=Sleeps())


async def test_a_client_error_is_not_retried() -> None:
    sleeps = Sleeps()
    with respx.mock() as rx:
        route = rx.get(URL).mock(return_value=httpx.Response(404))
        async with httpx.AsyncClient() as c:
            with pytest.raises(http.FeedHttpError) as e:
                await http.fetch(c, URL, sleep=sleeps)
    assert e.value.status == 404 and route.call_count == 1 and not sleeps.calls


async def test_a_timeout_is_retried() -> None:
    with respx.mock() as rx:
        rx.get(URL).mock(side_effect=[httpx.ConnectTimeout("slow"), httpx.Response(200)])
        async with httpx.AsyncClient() as c:
            got = await http.fetch(c, URL, sleep=Sleeps())
    assert got.attempts == 2


async def test_sends_etag_and_reads_a_304() -> None:
    with respx.mock() as rx:
        route = rx.get(URL).mock(return_value=httpx.Response(304))
        async with httpx.AsyncClient() as c:
            got = await http.fetch(
                c, URL, etag='"abc"', last_modified="Sat, 26 Sep 2026 19:00:00 GMT"
            )
    req = route.calls.last.request
    assert req.headers["If-None-Match"] == '"abc"'
    assert req.headers["If-Modified-Since"].startswith("Sat")
    assert got.not_modified and got.body == b""


def test_user_agent_names_the_project_not_a_person() -> None:
    ua = http.user_agent()
    assert "POLAR WINDOW" in ua and "@" not in ua


def test_token_bucket_spends_refills_and_says_when() -> None:
    lim = http.Limits.fresh("ll2", capacity=15, per_hour=15, now=T0)
    for _ in range(15):
        lim = lim.take(T0)
    with pytest.raises(http.OutOfBudget, match="240 s"):
        lim.take(T0)
    lim = lim.take(T0 + timedelta(seconds=240))
    assert lim.tokens == pytest.approx(0.0, abs=1e-9)


def test_breaker_opens_after_repeated_failures_then_half_opens() -> None:
    lim = http.Limits.fresh("x", 10, 60, T0)
    for _ in range(http.FAILS_TO_OPEN):
        lim = lim.failed(T0)
    assert lim.breaker == "open"
    with pytest.raises(http.BreakerOpen):
        lim.admit(T0 + timedelta(seconds=60))
    trial = lim.admit(T0 + timedelta(seconds=http.OPEN_FOR_S + 1))
    assert trial.breaker == "half_open"
    # One failure while half open opens it again at once.
    assert trial.failed(T0).breaker == "open"
    assert trial.succeeded().breaker == "closed"


def test_backoff_is_jittered_and_capped() -> None:
    assert http.backoff_s(0, rng=lambda: 1.0) == 1.0
    assert http.backoff_s(10, rng=lambda: 1.0) == http.MAX_BACKOFF_S
    assert http.backoff_s(3, rng=lambda: 0.0) == 0.0
