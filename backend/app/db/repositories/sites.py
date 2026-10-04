"""Site and horizon-mask persistence.

Repositories return **domain objects** (dataclasses from ``app.core`` or plain
dicts), never ORM instances. That is what keeps the layering rule enforceable:
if a service cannot get hold of a ``Site`` model, it cannot accidentally trigger
a lazy load at serialisation time, and routes provably never see SQLAlchemy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.horizon import HorizonMask
from app.db.arrays import decode_f32, encode_f32
from app.db.models import HorizonMaskRow, Site


@dataclass(frozen=True, slots=True)
class SiteRecord:
    """A site, detached from the session."""

    id: str
    code: str
    name: str
    region: str
    lat_deg: float
    lon_deg: float
    elev_m: float | None
    slope_deg: float | None
    note: str
    anchor_lat_deg: float
    anchor_lon_deg: float
    search_kind: str
    search_inner_km: float
    search_outer_km: float
    offset_from_anchor_km: float
    source: str
    source_url: str
    source_note: str
    kind: str = "candidate"
    coordinate_rule: str = "derived_open_sky"
    terrain_modelled: bool = True


@dataclass(frozen=True, slots=True)
class MaskRecord:
    """A stored mask plus the provenance needed to report its uncertainty."""

    site_id: str
    engine_version: str
    mask: HorizonMask
    dem_product: str
    dem_resolution_m: float
    dem_vertical_error_m: float
    mean_el_deg: float
    computed_at: datetime


def _to_record(row: Site) -> SiteRecord:
    return SiteRecord(
        id=row.id,
        code=row.code,
        name=row.name,
        region=row.region,
        lat_deg=row.lat_deg,
        lon_deg=row.lon_deg,
        elev_m=row.elev_m,
        slope_deg=row.slope_deg,
        note=row.note,
        anchor_lat_deg=row.anchor_lat_deg,
        anchor_lon_deg=row.anchor_lon_deg,
        search_kind=row.search_kind,
        search_inner_km=row.search_inner_km,
        search_outer_km=row.search_outer_km,
        offset_from_anchor_km=row.offset_from_anchor_km,
        source=row.source,
        source_url=row.source_url,
        source_note=row.source_note,
        kind=row.kind,
        coordinate_rule=row.coordinate_rule,
        terrain_modelled=row.terrain_modelled,
    )


class SiteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert_many(self, sites: list[dict[str, object]]) -> int:
        """Idempotent seed. Re-running `make seed` must not duplicate or fail."""
        if not sites:
            return 0
        stmt = pg_insert(Site).values(sites)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Site.id],
            set_={c: stmt.excluded[c] for c in sites[0] if c not in ("id", "created_at")},
        )
        await self._s.execute(stmt)
        return len(sites)

    async def get(self, site_id: str) -> SiteRecord | None:
        row = await self._s.get(Site, site_id)
        return _to_record(row) if row is not None and row.is_active else None

    async def list_sites(
        self,
        *,
        q: str | None = None,
        region: str | None = None,
        lat_min: float | None = None,
        lat_max: float | None = None,
        limit: int = 100,
        offset: int = 0,
        kind: str | None = None,
        ids: list[str] | None = None,
    ) -> tuple[list[SiteRecord], int]:
        stmt = select(Site).where(Site.is_active.is_(True))
        if kind:
            stmt = stmt.where(Site.kind == kind)
        if ids is not None:
            stmt = stmt.where(Site.id.in_(ids))
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(func.lower(Site.name).like(like) | func.lower(Site.region).like(like))
        if region:
            stmt = stmt.where(Site.region == region)
        if lat_min is not None:
            stmt = stmt.where(Site.lat_deg >= lat_min)
        if lat_max is not None:
            stmt = stmt.where(Site.lat_deg <= lat_max)

        # Count in the database, not in Python. The previous version ran the
        # full query, hydrated every matching ORM object, took len() and threw
        # them away -- then ran the query again with limit/offset. Harmless at
        # 15 sites and quietly quadratic in transferred rows as the set grows.
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self._s.execute(count_stmt)).scalar_one())

        stmt = stmt.order_by(Site.code).limit(limit).offset(offset)
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [_to_record(r) for r in rows], total

    async def count_by_kind(self) -> dict[str, int]:
        stmt = select(Site.kind, func.count()).group_by(Site.kind)
        return {str(k): int(n) for k, n in (await self._s.execute(stmt)).all()}


class MaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert(
        self,
        site_id: str,
        engine_version: str,
        mask: HorizonMask,
        *,
        dem_product: str,
        dem_resolution_m: float,
        dem_vertical_error_m: float,
    ) -> None:
        values = {
            "site_id": site_id,
            "engine_version": engine_version,
            "azimuth_count": mask.azimuth_count,
            "azimuth_step_deg": mask.azimuth_step_deg,
            "max_range_m": mask.max_range_m,
            "el_deg": encode_f32(mask.el_deg),
            "range_m": encode_f32(mask.range_m),
            "tol_deg": encode_f32(mask.tol_deg),
            "max_el_deg": mask.max_el_deg,
            "max_el_bearing_deg": mask.max_el_bearing_deg,
            "mean_el_deg": float(np.mean(mask.el_deg)),
            "dem_product": dem_product,
            "dem_resolution_m": dem_resolution_m,
            "dem_vertical_error_m": dem_vertical_error_m,
            "coverage": mask.coverage,
            "compute_ms": mask.compute_ms,
        }
        stmt = pg_insert(HorizonMaskRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_mask_site_engine",
            set_={k: stmt.excluded[k] for k in values if k != "site_id"},
        )
        await self._s.execute(stmt)

    async def get(self, site_id: str, engine_version: str) -> MaskRecord | None:
        stmt = select(HorizonMaskRow).where(
            HorizonMaskRow.site_id == site_id,
            HorizonMaskRow.engine_version == engine_version,
        )
        row = (await self._s.execute(stmt)).scalars().first()
        return None if row is None else _mask_record(row)

    async def get_many(self, site_ids: list[str], engine_version: str) -> dict[str, MaskRecord]:
        """Several masks in one round trip, for responses that describe a set."""
        if not site_ids:
            return {}
        stmt = select(HorizonMaskRow).where(
            HorizonMaskRow.site_id.in_(site_ids),
            HorizonMaskRow.engine_version == engine_version,
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return {r.site_id: _mask_record(r) for r in rows}

    async def existing_site_ids(self, engine_version: str) -> set[str]:
        stmt = select(HorizonMaskRow.site_id).where(HorizonMaskRow.engine_version == engine_version)
        return set((await self._s.execute(stmt)).scalars().all())

    async def delete(self, site_id: str, engine_version: str | None = None) -> int:
        stmt = delete(HorizonMaskRow).where(HorizonMaskRow.site_id == site_id)
        if engine_version is not None:
            stmt = stmt.where(HorizonMaskRow.engine_version == engine_version)
        res = await self._s.execute(stmt)
        return getattr(res, "rowcount", 0) or 0


def _mask_record(row: HorizonMaskRow) -> MaskRecord:
    return MaskRecord(
        site_id=row.site_id,
        engine_version=row.engine_version,
        mask=HorizonMask(
            el_deg=decode_f32(row.el_deg),
            range_m=decode_f32(row.range_m),
            tol_deg=decode_f32(row.tol_deg),
            max_el_deg=row.max_el_deg,
            max_el_bearing_deg=row.max_el_bearing_deg,
            azimuth_step_deg=row.azimuth_step_deg,
            max_range_m=row.max_range_m,
            coverage=row.coverage,
            compute_ms=row.compute_ms,
        ),
        dem_product=row.dem_product,
        dem_resolution_m=row.dem_resolution_m,
        dem_vertical_error_m=row.dem_vertical_error_m,
        mean_el_deg=row.mean_el_deg,
        computed_at=row.computed_at,
    )
