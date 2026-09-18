"""SQLAlchemy 2.x declarative models.

Float arrays (horizon masks, coarse visibility tracks) are stored as ``bytea``
holding little-endian float32, not as ``float[]`` or JSONB. A 1440-entry mask is
5.7 KB raw against ~20 KB as JSON text, and nothing ever queries inside these
arrays -- they are always read whole. The encode/decode pair lives in
``app.db.arrays`` so the representation is in one place.

Durations are seconds (``double precision``) everywhere. "Hours" is a
presentation unit and the conversion happens once, in the frontend adapter.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Site(Base):
    """A candidate landing site.

    The primary key is a slug rather than a surrogate id: it appears in every
    URL, in cache keys, in agent tool arguments and in the frontend's store, and
    a human-readable one makes all of those debuggable at a glance.
    """

    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(4), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    lat_deg: Mapped[float] = mapped_column(Float, nullable=False)
    lon_deg: Mapped[float] = mapped_column(Float, nullable=False)
    elev_m: Mapped[float] = mapped_column(Float, nullable=False)
    slope_deg: Mapped[float] = mapped_column(Float, nullable=False)

    note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # --- provenance: how this coordinate came to exist ---------------------
    anchor_lat_deg: Mapped[float] = mapped_column(Float, nullable=False)
    anchor_lon_deg: Mapped[float] = mapped_column(Float, nullable=False)
    search_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    search_inner_km: Mapped[float] = mapped_column(Float, nullable=False)
    search_outer_km: Mapped[float] = mapped_column(Float, nullable=False)
    offset_from_anchor_km: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(160), nullable=False)
    source_url: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    source_note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    masks: Mapped[list[HorizonMaskRow]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_sites_lat", "lat_deg"),)


class HorizonMaskRow(Base):
    """A precomputed skyline for one site at one engine version."""

    __tablename__ = "horizon_masks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)

    azimuth_count: Mapped[int] = mapped_column(Integer, nullable=False)
    azimuth_step_deg: Mapped[float] = mapped_column(Float, nullable=False)
    max_range_m: Mapped[float] = mapped_column(Float, nullable=False)

    el_deg: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    range_m: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    tol_deg: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    max_el_deg: Mapped[float] = mapped_column(Float, nullable=False)
    max_el_bearing_deg: Mapped[float] = mapped_column(Float, nullable=False)
    mean_el_deg: Mapped[float] = mapped_column(Float, nullable=False)

    dem_product: Mapped[str] = mapped_column(String(64), nullable=False)
    dem_resolution_m: Mapped[float] = mapped_column(Float, nullable=False)
    dem_vertical_error_m: Mapped[float] = mapped_column(Float, nullable=False)
    #: Fraction of ray samples that fell inside the DEM. Below 1.0 the mask is
    #: partial and every response built on it must say so.
    coverage: Mapped[float] = mapped_column(Float, nullable=False)

    compute_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    site: Mapped[Site] = relationship(back_populates="masks")

    __table_args__ = (
        UniqueConstraint("site_id", "engine_version", "azimuth_count", name="uq_mask_site_engine"),
    )


class SiteWindowMetrics(Base):
    """Memoised four-numbers for a quantised window.

    Serves ``/sites`` summaries and the coarse ``/compare`` ranking. The window
    bounds are quantised to the step grid before insert, which is what makes the
    unique constraint an effective cache key rather than a near-miss generator.
    """

    __tablename__ = "site_window_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    step_s: Mapped[int] = mapped_column(Integer, nullable=False)

    sunlit_s: Mapped[float] = mapped_column(Float, nullable=False)
    earth_contact_s: Mapped[float] = mapped_column(Float, nullable=False)
    longest_dark_s: Mapped[float] = mapped_column(Float, nullable=False)
    longest_blackout_s: Mapped[float] = mapped_column(Float, nullable=False)
    worst_compound_s: Mapped[float] = mapped_column(Float, nullable=False)
    sun_fraction_up: Mapped[float] = mapped_column(Float, nullable=False)
    earth_fraction_up: Mapped[float] = mapped_column(Float, nullable=False)
    #: At least one crossing was too shallow to time. The numbers stand; their
    #: edges do not.
    grazing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: The longest night / blackout touches a window edge, so the stored value
    #: is a lower bound on the stretch it belongs to. See
    #: ``core.metrics.BodyMetrics.longest_down_open``.
    longest_dark_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    longest_blackout_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "site_id",
            "engine_version",
            "window_start",
            "window_end",
            "step_s",
            name="uq_metrics_window",
        ),
    )


class AgentRun(Base):
    """One agent invocation, whatever its outcome.

    Every exit path writes a row -- success, guard rejection, timeout, total
    outage. That completeness is the point: this table is shown in the demo as
    evidence the AI layer is real and bounded, and a missing row for a failure
    would make it evidence of something else.
    """

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    agent: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    #: ok | insufficient_data | guard_rejected | timeout | degraded | error
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)

    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    #: [{kind, detail}] for every guard that fired, including ones a retry then
    #: fixed. Keeping the fixed ones is what lets the demo show the guard working
    #: rather than just claiming it exists.
    guard_failures: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    tool_calls: Mapped[list[AgentToolCall]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentToolCall.seq"
    )


class AgentToolCall(Base):
    """One tool invocation inside an agent run."""

    __tablename__ = "agent_tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    tool: Mapped[str] = mapped_column(String(48), nullable=False)
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    #: Every numeric leaf of the result, flattened at write time.
    #:
    #: Materialised rather than derived on demand because the grounding guard
    #: asks "is 63.2 present in any tool output?" on every attempt, and doing
    #: that against a float array beats re-walking nested JSON each time. It
    #: also makes the guard auditable from SQL alone after the fact, which is
    #: what lets the demo *show* the check instead of asserting it.
    numbers: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[AgentRun] = relationship(back_populates="tool_calls")

    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_toolcall_seq"),)
