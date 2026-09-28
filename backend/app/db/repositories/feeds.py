"""Feed snapshots, their health and each provider's request budget (ADR-8).

Snapshots are immutable: this repository inserts them and reads them, and
the only update it makes to one is marking it *of record* when an answer
the project keeps depends on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FeedHealth, FeedLimit, FeedSnapshot

#: The channel the feeds worker LISTENs on; "refresh now" NOTIFYs it.
FEEDS_CHANNEL = "pw_feeds"


@dataclass(frozen=True, slots=True)
class SnapshotRecord:
    id: int
    provider: str
    product: str
    location_key: str
    issued_at: datetime | None
    valid_from: datetime | None
    valid_to: datetime | None
    fetched_at: datetime
    url: str
    http_status: int
    etag: str | None
    last_modified: str | None
    content_sha256: str | None
    parsed: dict[str, Any] | None
    parser_version: str
    licence: str
    status: str
    issues: list[Any]


@dataclass(frozen=True, slots=True)
class HealthRecord:
    provider: str
    product: str
    location_key: str
    licence: str
    staleness_budget_s: int
    interval_s: int
    last_attempt_at: datetime | None
    last_ok_at: datetime | None
    last_snapshot_id: int | None
    next_run_at: datetime | None
    consecutive_errors: int
    last_error: str | None


@dataclass(frozen=True, slots=True)
class LimitRecord:
    provider: str
    breaker: str
    failures: int
    opened_at: datetime | None
    tokens: float
    capacity: float
    refill_per_s: float
    tokens_at: datetime


def _snap(r: FeedSnapshot) -> SnapshotRecord:
    return SnapshotRecord(
        id=int(r.id),
        provider=r.provider,
        product=r.product,
        location_key=r.location_key,
        issued_at=r.issued_at,
        valid_from=r.valid_from,
        valid_to=r.valid_to,
        fetched_at=r.fetched_at,
        url=r.url,
        http_status=int(r.http_status),
        etag=r.etag,
        last_modified=r.last_modified,
        content_sha256=r.content_sha256,
        parsed=r.parsed,
        parser_version=r.parser_version,
        licence=r.licence,
        status=r.status,
        issues=list(r.issues or []),
    )


def _health(r: FeedHealth) -> HealthRecord:
    return HealthRecord(
        provider=r.provider,
        product=r.product,
        location_key=r.location_key,
        licence=r.licence,
        staleness_budget_s=int(r.staleness_budget_s),
        interval_s=int(r.interval_s),
        last_attempt_at=r.last_attempt_at,
        last_ok_at=r.last_ok_at,
        last_snapshot_id=None if r.last_snapshot_id is None else int(r.last_snapshot_id),
        next_run_at=r.next_run_at,
        consecutive_errors=int(r.consecutive_errors),
        last_error=r.last_error,
    )


def _limit(r: FeedLimit) -> LimitRecord:
    return LimitRecord(
        provider=r.provider,
        breaker=r.breaker,
        failures=int(r.failures),
        opened_at=r.opened_at,
        tokens=float(r.tokens),
        capacity=float(r.capacity),
        refill_per_s=float(r.refill_per_s),
        tokens_at=r.tokens_at,
    )


class FeedRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- snapshots ---------------------------------------------------------

    async def insert_snapshot(self, values: dict[str, Any]) -> int | None:
        """Insert one snapshot. None when an identical good body is already kept."""
        stmt = (
            insert(FeedSnapshot)
            .values(**values)
            .on_conflict_do_nothing()
            .returning(FeedSnapshot.id)
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return None if row is None else int(row)

    async def find_same_body(
        self, provider: str, product: str, location_key: str, sha: str
    ) -> tuple[int, str] | None:
        """The newest good snapshot with this body, and the parser version that read it."""
        row = (
            await self._s.execute(
                select(FeedSnapshot.id, FeedSnapshot.parser_version)
                .where(
                    FeedSnapshot.provider == provider,
                    FeedSnapshot.product == product,
                    FeedSnapshot.location_key == location_key,
                    FeedSnapshot.content_sha256 == sha,
                    FeedSnapshot.status == "ok",
                )
                .order_by(FeedSnapshot.id.desc())
                .limit(1)
            )
        ).one_or_none()
        return None if row is None else (int(row.id), str(row.parser_version))

    async def reparse_snapshot(self, snapshot_id: int, values: dict[str, Any]) -> None:
        """Replace a kept snapshot's reading after its parser changed; the body stays as fetched."""
        await self._s.execute(
            update(FeedSnapshot).where(FeedSnapshot.id == snapshot_id).values(**values)
        )

    async def latest_ok(
        self, provider: str, product: str, location_key: str = ""
    ) -> SnapshotRecord | None:
        row = (
            await self._s.execute(
                select(FeedSnapshot)
                .where(
                    FeedSnapshot.provider == provider,
                    FeedSnapshot.product == product,
                    FeedSnapshot.location_key == location_key,
                    FeedSnapshot.status == "ok",
                )
                .order_by(FeedSnapshot.fetched_at.desc(), FeedSnapshot.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return None if row is None else _snap(row)

    async def latest_ok_span(
        self, provider: str, product: str, location_key: str = ""
    ) -> tuple[int, datetime | None, datetime | None, datetime] | None:
        """``(id, valid_from, valid_to, fetched_at)`` of the newest good snapshot,
        without reading its body (a trajectory's is megabytes)."""
        row = (
            await self._s.execute(
                select(
                    FeedSnapshot.id,
                    FeedSnapshot.valid_from,
                    FeedSnapshot.valid_to,
                    FeedSnapshot.fetched_at,
                )
                .where(
                    FeedSnapshot.provider == provider,
                    FeedSnapshot.product == product,
                    FeedSnapshot.location_key == location_key,
                    FeedSnapshot.status == "ok",
                )
                .order_by(FeedSnapshot.fetched_at.desc(), FeedSnapshot.id.desc())
                .limit(1)
            )
        ).first()
        return None if row is None else (row[0], row[1], row[2], row[3])

    async def get_snapshot(self, snapshot_id: int) -> SnapshotRecord | None:
        row = await self._s.get(FeedSnapshot, snapshot_id)
        return None if row is None else _snap(row)

    async def raw_of(self, snapshot_id: int) -> tuple[bytes | None, str | None]:
        row = (
            await self._s.execute(
                select(FeedSnapshot.raw, FeedSnapshot.raw_ref).where(FeedSnapshot.id == snapshot_id)
            )
        ).one_or_none()
        return (None, None) if row is None else (row.raw, row.raw_ref)

    async def mark_of_record(self, ids: list[int]) -> None:
        if ids:
            await self._s.execute(
                update(FeedSnapshot).where(FeedSnapshot.id.in_(ids)).values(of_record=True)
            )

    async def gc_raw(self, older_than_days: int) -> int:
        """Drop raw bodies of old snapshots nothing of record depends on."""
        res = await self._s.execute(
            text(
                """
                UPDATE feed_snapshots s SET raw = NULL
                WHERE s.raw IS NOT NULL AND NOT s.of_record
                  AND s.fetched_at < now() - make_interval(days => :days)
                  AND NOT EXISTS (
                    SELECT 1 FROM assessment_inputs i JOIN assessments a ON a.id = i.assessment_id
                    WHERE i.snapshot_id = s.id AND a.of_record)
                """
            ),
            {"days": older_than_days},
        )
        return int(getattr(res, "rowcount", 0) or 0)

    # --- health ------------------------------------------------------------

    async def ensure_health(
        self,
        provider: str,
        product: str,
        location_key: str,
        *,
        licence: str,
        staleness_budget_s: int,
        interval_s: int,
    ) -> None:
        stmt = (
            insert(FeedHealth)
            .values(
                provider=provider,
                product=product,
                location_key=location_key,
                licence=licence,
                staleness_budget_s=staleness_budget_s,
                interval_s=interval_s,
                consecutive_errors=0,
            )
            .on_conflict_do_update(
                index_elements=[FeedHealth.provider, FeedHealth.product, FeedHealth.location_key],
                set_={
                    "licence": licence,
                    "staleness_budget_s": staleness_budget_s,
                    "interval_s": interval_s,
                },
            )
        )
        await self._s.execute(stmt)

    async def health(self, provider: str | None = None) -> list[HealthRecord]:
        q = select(FeedHealth).order_by(
            FeedHealth.provider, FeedHealth.product, FeedHealth.location_key
        )
        if provider is not None:
            q = q.where(FeedHealth.provider == provider)
        return [_health(r) for r in (await self._s.execute(q)).scalars()]

    async def record_attempt(
        self,
        provider: str,
        product: str,
        location_key: str,
        *,
        ok: bool,
        snapshot_id: int | None,
        error: str | None,
        next_run_at: datetime,
    ) -> None:
        key = and_(
            FeedHealth.provider == provider,
            FeedHealth.product == product,
            FeedHealth.location_key == location_key,
        )
        values: dict[str, Any] = {"last_attempt_at": text("now()"), "next_run_at": next_run_at}
        if ok:
            values |= {"last_ok_at": text("now()"), "consecutive_errors": 0, "last_error": None}
            if snapshot_id is not None:
                values["last_snapshot_id"] = snapshot_id
        else:
            values |= {
                "consecutive_errors": FeedHealth.consecutive_errors + 1,
                "last_error": (error or "unknown error")[:2000],
            }
        await self._s.execute(update(FeedHealth).where(key).values(**values))

    async def request_refresh(self, provider: str) -> int:
        res = await self._s.execute(
            update(FeedHealth)
            .where(FeedHealth.provider == provider)
            .values(next_run_at=text("now()"))
        )
        await self._s.execute(text(f"NOTIFY {FEEDS_CHANNEL}"))
        return int(getattr(res, "rowcount", 0) or 0)

    # --- limits ------------------------------------------------------------

    async def get_limit(self, provider: str) -> LimitRecord | None:
        row = await self._s.get(FeedLimit, provider)
        return None if row is None else _limit(row)

    async def limits(self) -> dict[str, LimitRecord]:
        rows = (await self._s.execute(select(FeedLimit))).scalars()
        return {r.provider: _limit(r) for r in rows}

    async def put_limit(self, rec: LimitRecord) -> None:
        values = {
            "provider": rec.provider,
            "breaker": rec.breaker,
            "failures": rec.failures,
            "opened_at": rec.opened_at,
            "tokens": rec.tokens,
            "capacity": rec.capacity,
            "refill_per_s": rec.refill_per_s,
            "tokens_at": rec.tokens_at,
        }
        stmt = (
            insert(FeedLimit)
            .values(**values)
            .on_conflict_do_update(index_elements=[FeedLimit.provider], set_=values)
        )
        await self._s.execute(stmt)
