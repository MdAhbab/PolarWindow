"""What the feeds worker stored, as the API and the lifecycle answers read it (ADR-8).

The API never fetches. It reads the latest good snapshot of a product and
decides, from the product's staleness budget, whether its values may still
be shown. Past the budget there is no number, only the reason (invariant 11).

The age of a product is the age of its *data* (the model run, the issue
time or the newest observation it holds), not of the last fetch: a
forecast fetched a minute ago that NWS last updated six hours ago is six
hours old.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.feeds import FeedRepository, HealthRecord, SnapshotRecord
from app.services import audit_service
from app.services.auth_service import Claims

#: Plain names for the Data sources panel.
PROVIDER_NAMES: dict[str, str] = {
    "swpc": "NOAA Space Weather Prediction Center",
    "donki": "NASA space weather database (DONKI)",
    "dsn_now": "NASA Deep Space Network now",
    "nws": "US National Weather Service",
    "ndbc": "NOAA buoys (National Data Buoy Center)",
    "ll2": "Launch Library 2 launch schedule",
    "nomads": "NOAA weather models (GEFS, HRRR)",
}


class UnknownProvider(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class Latest:
    """The current snapshot of one product, or why there is none to use."""

    snapshot: SnapshotRecord | None
    age_s: float | None
    stale: bool
    missing_reason: str | None
    staleness_budget_s: int | None

    @property
    def values(self) -> dict[str, Any] | None:
        if self.snapshot is None or self.stale:
            return None
        return self.snapshot.parsed

    def source_ref(self, name: str) -> dict[str, Any] | None:
        s = self.snapshot
        if s is None:
            return None
        return {
            "name": name,
            "url": s.url,
            "issued_at": s.issued_at,
            "fetched_at": s.fetched_at,
            "licence": s.licence,
            "snapshot_id": s.id,
        }


def data_time(s: SnapshotRecord) -> datetime:
    return s.issued_at or s.fetched_at


def _age(s: SnapshotRecord | None, now: datetime) -> float | None:
    return None if s is None else max(0.0, (now - data_time(s)).total_seconds())


def _words(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} seconds"
    if seconds < 90 * 60:
        return f"{seconds / 60:.0f} minutes"
    if seconds < 48 * 3600:
        return f"{seconds / 3600:.0f} hours"
    return f"{seconds / 86400:.0f} days"


async def latest(
    session: AsyncSession,
    provider: str,
    product: str,
    location_key: str = "",
    *,
    now: datetime | None = None,
) -> Latest:
    now = now or datetime.now(UTC)
    repo = FeedRepository(session)
    snap = await repo.latest_ok(provider, product, location_key)
    health = next(
        (
            h
            for h in await repo.health(provider)
            if h.product == product and h.location_key == location_key
        ),
        None,
    )
    budget = health.staleness_budget_s if health else None
    name = PROVIDER_NAMES.get(provider, provider)
    if snap is None:
        reason = f"No data from {name} has been recorded yet" + (
            "; the last attempt to fetch it failed." if health and health.last_error else "."
        )
        return Latest(None, None, True, reason, budget)
    age = _age(snap, now)
    assert age is not None
    if budget is not None and age > budget:
        return Latest(
            snap,
            age,
            True,
            f"The latest data from {name} is {_words(age)} old, past its {_words(budget)} limit, "
            "so it is not shown.",
            budget,
        )
    return Latest(snap, age, False, None, budget)


def _row(
    h: HealthRecord, snap_time: datetime | None, breaker: str, now: datetime
) -> dict[str, Any]:
    age = None if snap_time is None else max(0.0, (now - snap_time).total_seconds())
    stale = age is None or age > h.staleness_budget_s
    return {
        "provider": h.provider,
        "provider_name": PROVIDER_NAMES.get(h.provider, h.provider),
        "product": h.product,
        "location": h.location_key or None,
        "last_ok": h.last_ok_at,
        "data_time": snap_time,
        "age_s": age,
        "stale": stale,
        "staleness_budget_s": h.staleness_budget_s,
        "next_run": h.next_run_at,
        "errors": h.consecutive_errors,
        "last_error": h.last_error,
        "licence": h.licence,
        "breaker": breaker,
    }


async def list_feeds(session: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    repo = FeedRepository(session)
    limits = await repo.limits()
    rows = []
    for h in await repo.health():
        snap = await repo.get_snapshot(h.last_snapshot_id) if h.last_snapshot_id else None
        rows.append(
            _row(
                h,
                data_time(snap) if snap else None,
                limits[h.provider].breaker if h.provider in limits else "closed",
                now,
            )
        )
    return {"feeds": rows}


async def summary(session: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """``{ok, stale, failing}`` for ``/healthz``."""
    feeds = (await list_feeds(session, now))["feeds"]
    failing = sum(1 for f in feeds if f["errors"] > 0 or f["breaker"] == "open")
    stale = sum(1 for f in feeds if f["stale"] and not (f["errors"] > 0 or f["breaker"] == "open"))
    return {"ok": len(feeds) - failing - stale, "stale": stale, "failing": failing}


async def request_refresh(session: AsyncSession, provider: str, who: Claims) -> int:
    repo = FeedRepository(session)
    if not await repo.health(provider):
        raise UnknownProvider(provider)
    n = await repo.request_refresh(provider)
    await audit_service.record(
        session,
        who,
        action="refresh",
        entity="feed",
        entity_id=provider,
        before=None,
        after={"products": n},
        note="Refresh requested from Settings",
    )
    return n
