"""The one HTTP layer every feed adapter uses (ADR-8 point 4).

* **Timeouts**: 5 s to connect, 20 s to read. A slow provider costs one
  product's freshness, never the worker.
* **Retries**: three, with full jitter on an exponential back-off, honouring
  ``Retry-After`` (seconds or an HTTP date, capped) on 429 and 503. Retried
  only on errors a retry can fix: connection failures, timeouts, 429, 5xx.
* **Conditional requests**: ``If-None-Match`` / ``If-Modified-Since`` from the
  previous snapshot, so an unchanged product costs a 304 and nothing else.
* **Circuit breaker** per provider: after ``FAILS_TO_OPEN`` consecutive
  failures it opens and no request is sent for ``OPEN_FOR_S``; then one trial
  request (half open) decides whether it closes again.
* **Token bucket** per provider, persisted by the caller in ``feed_limits`` so
  that a restart cannot overspend a 15-requests-an-hour allowance.

The breaker and the bucket are plain state machines with the clock passed in,
so they are tested without sleeping. The User-Agent names the project and its
contact address from settings, never a person's own email.
"""

from __future__ import annotations

import asyncio
import email.utils
import random
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Final, Literal

import httpx

from app.config import get_settings

CONNECT_S: Final[float] = 5.0
READ_S: Final[float] = 20.0
RETRIES: Final[int] = 3
BASE_BACKOFF_S: Final[float] = 1.0
MAX_BACKOFF_S: Final[float] = 30.0
MAX_RETRY_AFTER_S: Final[float] = 120.0
#: Responses larger than this are refused: a feed body this big is a mistake.
MAX_BODY_BYTES: Final[int] = 64 * 1024 * 1024

FAILS_TO_OPEN: Final[int] = 5
OPEN_FOR_S: Final[float] = 15 * 60.0

RETRY_STATUS: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})

BreakerState = Literal["closed", "open", "half_open"]


class FeedHttpError(Exception):
    """A fetch that did not produce a usable response, with the reason in words."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class BreakerOpen(FeedHttpError):
    pass


class OutOfBudget(FeedHttpError):
    pass


def user_agent() -> str:
    return f"POLAR WINDOW lunar mission planner ({get_settings().data_contact})"


# ---------------------------------------------------------------------------
# Circuit breaker and token bucket: pure state, clock passed in
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Limits:
    """One provider's breaker and bucket, as kept in ``feed_limits``."""

    provider: str
    breaker: BreakerState
    failures: int
    opened_at: datetime | None
    tokens: float
    capacity: float
    refill_per_s: float
    tokens_at: datetime

    @classmethod
    def fresh(cls, provider: str, capacity: float, per_hour: float, now: datetime) -> Limits:
        return cls(
            provider=provider,
            breaker="closed",
            failures=0,
            opened_at=None,
            tokens=capacity,
            capacity=capacity,
            refill_per_s=per_hour / 3600.0,
            tokens_at=now,
        )

    # --- bucket ------------------------------------------------------------

    def refilled(self, now: datetime) -> Limits:
        dt = max(0.0, (now - self.tokens_at).total_seconds())
        return replace(
            self, tokens=min(self.capacity, self.tokens + dt * self.refill_per_s), tokens_at=now
        )

    def take(self, now: datetime, cost: float = 1.0) -> Limits:
        """Spend ``cost`` tokens, or raise ``OutOfBudget`` saying when one is free."""
        r = self.refilled(now)
        if r.tokens + 1e-9 < cost:
            wait = (cost - r.tokens) / r.refill_per_s if r.refill_per_s > 0 else float("inf")
            raise OutOfBudget(
                f"{self.provider}: request allowance used up; the next request is allowed "
                f"in {wait:.0f} s"
            )
        return replace(r, tokens=r.tokens - cost)

    # --- breaker -----------------------------------------------------------

    def admit(self, now: datetime) -> Limits:
        """May a request go out now? Open -> half open after the cool-down."""
        if self.breaker == "open":
            assert self.opened_at is not None
            if (now - self.opened_at).total_seconds() < OPEN_FOR_S:
                left = OPEN_FOR_S - (now - self.opened_at).total_seconds()
                raise BreakerOpen(
                    f"{self.provider}: paused after {self.failures} failures in a row; "
                    f"trying again in {left:.0f} s"
                )
            return replace(self, breaker="half_open")
        return self

    def succeeded(self) -> Limits:
        return replace(self, breaker="closed", failures=0, opened_at=None)

    def failed(self, now: datetime) -> Limits:
        failures = self.failures + 1
        if self.breaker == "half_open" or failures >= FAILS_TO_OPEN:
            return replace(self, breaker="open", failures=failures, opened_at=now)
        return replace(self, failures=failures)


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Fetched:
    url: str
    status: int
    body: bytes
    etag: str | None
    last_modified: str | None
    content_type: str | None
    not_modified: bool
    attempts: int


def retry_after_s(value: str | None, now: datetime) -> float | None:
    """``Retry-After`` as seconds: an integer, or an HTTP date. Capped."""
    if not value:
        return None
    v = value.strip()
    if v.isdigit():
        return min(float(v), MAX_RETRY_AFTER_S)
    try:
        when = email.utils.parsedate_to_datetime(v)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, min((when - now).total_seconds(), MAX_RETRY_AFTER_S))


def backoff_s(attempt: int, rng: Callable[[], float] = random.random) -> float:
    """Full jitter: uniform in [0, min(cap, base * 2**attempt))."""
    return float(rng() * min(MAX_BACKOFF_S, BASE_BACKOFF_S * 2**attempt))


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(READ_S, connect=CONNECT_S),
        headers={"User-Agent": user_agent()},
        follow_redirects=True,
    )


async def fetch(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
    retries: int = RETRIES,
    sleep: Callable[[float], object] = asyncio.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Fetched:
    """GET with retries, jitter, Retry-After and conditional headers."""
    h = dict(headers or {})
    if etag:
        h["If-None-Match"] = etag
    if last_modified:
        h["If-Modified-Since"] = last_modified
    last_error = "no attempt made"
    for attempt in range(retries + 1):
        try:
            r = await client.get(url, params=params, headers=h)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                await _maybe_await(sleep(backoff_s(attempt)))
                continue
            raise FeedHttpError(f"could not reach {_host(url)} ({last_error})") from exc
        if r.status_code == 304:
            return Fetched(
                url=str(r.request.url),
                status=304,
                body=b"",
                etag=etag,
                last_modified=last_modified,
                content_type=None,
                not_modified=True,
                attempts=attempt + 1,
            )
        if r.status_code in RETRY_STATUS and attempt < retries:
            wait = retry_after_s(r.headers.get("Retry-After"), now())
            await _maybe_await(sleep(wait if wait is not None else backoff_s(attempt)))
            last_error = f"HTTP {r.status_code}"
            continue
        if r.status_code >= 400:
            raise FeedHttpError(f"{_host(url)} answered HTTP {r.status_code}", status=r.status_code)
        body = r.content
        if len(body) > MAX_BODY_BYTES:
            raise FeedHttpError(f"{_host(url)} sent {len(body)} bytes, more than allowed")
        return Fetched(
            url=str(r.request.url),
            status=r.status_code,
            body=body,
            etag=r.headers.get("ETag"),
            last_modified=r.headers.get("Last-Modified"),
            content_type=r.headers.get("Content-Type"),
            not_modified=False,
            attempts=attempt + 1,
        )
    raise FeedHttpError(f"{_host(url)}: gave up after {retries + 1} attempts ({last_error})")


async def _maybe_await(x: object) -> None:
    if asyncio.iscoroutine(x) or isinstance(x, asyncio.Future):
        await x


def _host(url: str) -> str:
    return httpx.URL(url).host or url
