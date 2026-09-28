"""Decide which product to fetch next, fetch it within its provider's limits, record it.

State lives in the database, not in this process: when each product is next
due (``feed_health.next_run_at``), each provider's circuit breaker and
request budget (``feed_limits``). A restarted worker therefore resumes where
the last one stopped, and "Refresh now" from Settings is simply setting a
product's next run to now and sending ``NOTIFY pw_feeds``.

A failure delays the product's next attempt with an exponential back-off
(capped at its normal interval) and counts against the provider's breaker;
it never stops the other products or providers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from app.db.repositories.feeds import FeedRepository, LimitRecord
from app.db.session import session_scope
from app.feeds import http, recorder
from app.feeds.base import Product, ProviderSpec

log = logging.getLogger("polar_window.feeds")


def _limits_from(rec: LimitRecord) -> http.Limits:
    return http.Limits(
        provider=rec.provider,
        breaker=rec.breaker,  # type: ignore[arg-type]
        failures=rec.failures,
        opened_at=rec.opened_at,
        tokens=rec.tokens,
        capacity=rec.capacity,
        refill_per_s=rec.refill_per_s,
        tokens_at=rec.tokens_at,
    )


def _limits_to(lim: http.Limits) -> LimitRecord:
    return LimitRecord(
        provider=lim.provider,
        breaker=lim.breaker,
        failures=lim.failures,
        opened_at=lim.opened_at,
        tokens=lim.tokens,
        capacity=lim.capacity,
        refill_per_s=lim.refill_per_s,
        tokens_at=lim.tokens_at,
    )


def retry_delay_s(consecutive_errors: int, interval_s: int) -> float:
    """1, 2, 4 ... minutes after a failure, never longer than the product's own interval."""
    return float(min(interval_s, 60 * 2 ** max(0, consecutive_errors)))


@dataclass
class RunResult:
    product: tuple[str, str, str]
    ok: bool
    status: str
    message: str
    snapshot_id: int | None = None


@dataclass
class Scheduler:
    products: list[Product]
    providers: dict[str, ProviderSpec]
    raw_root: Path
    client_factory: Callable[[], httpx.AsyncClient] = http.make_client
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    #: Values scrubbed from any error text before it is stored (API keys).
    secrets: tuple[str, ...] = ()
    #: How the HTTP layer waits between retries (tests pass a no-op).
    sleep: Callable[[float], object] = asyncio.sleep

    def _scrub(self, text: str) -> str:
        for s in self.secrets:
            if s and s != "DEMO_KEY":
                text = text.replace(s, "***")
        return text

    async def sync(self) -> None:
        """Make sure every product has a health row (new products are due at once)."""
        async with session_scope() as s:
            repo = FeedRepository(s)
            for p in self.products:
                await repo.ensure_health(
                    p.provider,
                    p.product,
                    p.location_key,
                    licence=p.licence,
                    staleness_budget_s=p.staleness_s,
                    interval_s=p.interval_s,
                )

    async def due(self) -> list[Product]:
        now = self.now()
        async with session_scope() as s:
            rows = {
                (h.provider, h.product, h.location_key): h for h in await FeedRepository(s).health()
            }
        out = []
        for p in self.products:
            h = rows.get(p.key)
            if h is None or h.next_run_at is None or h.next_run_at <= now:
                out.append(p)
        return out

    async def _limits(self, provider: str) -> http.Limits:
        spec = self.providers.get(provider) or ProviderSpec(provider, 10, 60)
        async with session_scope() as s:
            rec = await FeedRepository(s).get_limit(provider)
        if rec is None:
            return http.Limits.fresh(provider, spec.capacity, spec.per_hour, self.now())
        lim = _limits_from(rec)
        # The allowance itself follows the code (a key added raises it).
        if lim.capacity != spec.capacity or abs(lim.refill_per_s - spec.per_hour / 3600) > 1e-12:
            lim = http.Limits(
                provider=lim.provider,
                breaker=lim.breaker,
                failures=lim.failures,
                opened_at=lim.opened_at,
                tokens=min(lim.tokens, spec.capacity),
                capacity=spec.capacity,
                refill_per_s=spec.per_hour / 3600.0,
                tokens_at=lim.tokens_at,
            )
        return lim

    async def _save_limits(self, lim: http.Limits) -> None:
        async with session_scope() as s:
            await FeedRepository(s).put_limit(_limits_to(lim))

    async def run_product(self, p: Product, client: httpx.AsyncClient) -> RunResult:
        now = self.now()
        lim = await self._limits(p.provider)
        try:
            lim = lim.admit(now)
            lim = lim.take(now, p.cost)
        except (http.BreakerOpen, http.OutOfBudget) as exc:
            await self._save_limits(lim)
            await self._attempted(p, ok=False, snapshot_id=None, error=str(exc), soft=True)
            return RunResult(p.key, False, "skipped", str(exc))
        await self._save_limits(lim)

        async with session_scope() as s:
            last = await FeedRepository(s).latest_ok(p.provider, p.product, p.location_key)
        # A kept body read by an older parser is asked for in full, so the recorder can
        # read it again (a 304 carries no body to read).
        current = last is not None and last.parser_version == p.parser_version
        etag = last.etag if current and last else None
        lm = last.last_modified if current and last else None
        try:
            if p.custom_fetch is not None:
                got = await p.custom_fetch(client, etag, lm)
            else:
                got = await http.fetch(
                    client,
                    p.url,
                    params=p.params or None,
                    headers=p.headers or None,
                    etag=etag,
                    last_modified=lm,
                    sleep=self.sleep,
                    # A half-open breaker gets one trial request, not a burst.
                    retries=0 if lim.breaker == "half_open" else http.RETRIES,
                )
        except (http.FeedHttpError, httpx.HTTPError) as exc:
            msg = self._scrub(str(exc) or type(exc).__name__)
            await self._save_limits((await self._limits(p.provider)).failed(self.now()))
            await self._attempted(p, ok=False, snapshot_id=None, error=msg)
            return RunResult(p.key, False, "error", msg)

        async with session_scope() as s:
            out = await recorder.record(s, p, got, raw_root=self.raw_root, now=self.now())
        lim = await self._limits(p.provider)
        await self._save_limits(lim.succeeded() if out.ok else lim)
        await self._attempted(
            p, ok=out.ok, snapshot_id=out.snapshot_id, error=None if out.ok else out.message
        )
        return RunResult(p.key, out.ok, out.status, out.message, out.snapshot_id)

    async def _attempted(
        self,
        p: Product,
        *,
        ok: bool,
        snapshot_id: int | None,
        error: str | None,
        soft: bool = False,
    ) -> None:
        async with session_scope() as s:
            repo = FeedRepository(s)
            errors = await self._errors(repo, p)
            if ok:
                nxt = self.now() + timedelta(seconds=p.interval_s)
            elif soft:
                nxt = self.now() + timedelta(seconds=min(p.interval_s, 300))
            else:
                nxt = self.now() + timedelta(seconds=retry_delay_s(errors, p.interval_s))
            await repo.record_attempt(
                p.provider,
                p.product,
                p.location_key,
                ok=ok,
                snapshot_id=snapshot_id,
                error=error,
                next_run_at=nxt,
            )

    @staticmethod
    async def _errors(repo: FeedRepository, p: Product) -> int:
        for h in await repo.health(p.provider):
            if (h.provider, h.product, h.location_key) == p.key:
                return h.consecutive_errors
        return 0

    async def run_once(self) -> list[RunResult]:
        """Fetch every due product once; providers run side by side, products in turn."""
        due = await self.due()
        if not due:
            return []
        by: dict[str, list[Product]] = {}
        for p in due:
            by.setdefault(p.provider, []).append(p)
        async with self.client_factory() as client:

            async def run_provider(ps: list[Product]) -> list[RunResult]:
                res = []
                for p in ps:
                    try:
                        res.append(await self.run_product(p, client))
                    except Exception as exc:  # one product's bug never stops the rest
                        log.exception("feed %s failed", p.key)
                        res.append(RunResult(p.key, False, "error", self._scrub(repr(exc))))
                return res

            groups = await asyncio.gather(*(run_provider(ps) for ps in by.values()))
        results = [r for g in groups for r in g]
        for r in results:
            log.info("feed %s/%s/%s: %s %s", *r.product, r.status, r.message)
        return results
