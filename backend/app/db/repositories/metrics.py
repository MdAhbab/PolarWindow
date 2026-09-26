"""Memoised window metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SiteWindowMetrics


@dataclass(frozen=True, slots=True)
class WindowMetricsRecord:
    site_id: str
    window_start: datetime
    window_end: datetime
    step_s: int
    sunlit_s: float
    earth_contact_s: float
    longest_dark_s: float
    longest_blackout_s: float
    worst_compound_s: float
    sun_fraction_up: float
    earth_fraction_up: float
    grazing: bool
    computed_at: datetime
    longest_dark_open: bool = False
    longest_blackout_open: bool = False


class WindowMetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert(self, engine_version: str, rec: WindowMetricsRecord) -> None:
        values = {
            "site_id": rec.site_id,
            "engine_version": engine_version,
            "window_start": rec.window_start,
            "window_end": rec.window_end,
            "step_s": rec.step_s,
            "sunlit_s": rec.sunlit_s,
            "earth_contact_s": rec.earth_contact_s,
            "longest_dark_s": rec.longest_dark_s,
            "longest_blackout_s": rec.longest_blackout_s,
            "worst_compound_s": rec.worst_compound_s,
            "sun_fraction_up": rec.sun_fraction_up,
            "earth_fraction_up": rec.earth_fraction_up,
            "grazing": rec.grazing,
            "longest_dark_open": rec.longest_dark_open,
            "longest_blackout_open": rec.longest_blackout_open,
        }
        stmt = pg_insert(SiteWindowMetrics).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_metrics_window",
            set_={
                k: stmt.excluded[k]
                for k in values
                if k not in ("site_id", "engine_version", "window_start", "window_end", "step_s")
            },
        )
        await self._s.execute(stmt)

    async def site_ids_with_rows(self, engine_version: str) -> set[str]:
        """Sites that have at least one stored window for this engine version."""
        stmt = select(SiteWindowMetrics.site_id).where(
            SiteWindowMetrics.engine_version == engine_version
        )
        return set((await self._s.execute(stmt)).scalars().all())

    async def get_many(
        self,
        site_ids: list[str],
        engine_version: str,
        window_start: datetime,
        window_end: datetime,
        step_s: int,
    ) -> dict[str, WindowMetricsRecord]:
        if not site_ids:
            return {}
        stmt = select(SiteWindowMetrics).where(
            SiteWindowMetrics.site_id.in_(site_ids),
            SiteWindowMetrics.engine_version == engine_version,
            SiteWindowMetrics.window_start == window_start,
            SiteWindowMetrics.window_end == window_end,
            SiteWindowMetrics.step_s == step_s,
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return {
            r.site_id: WindowMetricsRecord(
                site_id=r.site_id,
                window_start=r.window_start,
                window_end=r.window_end,
                step_s=r.step_s,
                sunlit_s=r.sunlit_s,
                earth_contact_s=r.earth_contact_s,
                longest_dark_s=r.longest_dark_s,
                longest_blackout_s=r.longest_blackout_s,
                worst_compound_s=r.worst_compound_s,
                sun_fraction_up=r.sun_fraction_up,
                earth_fraction_up=r.earth_fraction_up,
                grazing=r.grazing,
                computed_at=r.computed_at,
                longest_dark_open=r.longest_dark_open,
                longest_blackout_open=r.longest_blackout_open,
            )
            for r in rows
        }
