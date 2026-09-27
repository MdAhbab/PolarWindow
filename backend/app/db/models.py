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
    BigInteger,
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
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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
    #: Null where no elevation model covers the site (a CLPS target outside
    #: 80 deg S): an unknown height is not zero.
    elev_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    slope_deg: Mapped[float | None] = mapped_column(Float, nullable=True)

    note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # --- what kind of place this is (contract v2, ADR-6) --------------------
    #: 'candidate' (derived from the DEM) or 'mission_target' (a CLPS target).
    kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default="candidate", server_default="candidate", index=True
    )
    #: 'derived_open_sky' (searched) or 'published' (used as given).
    coordinate_rule: Mapped[str] = mapped_column(
        String(24), nullable=False, default="derived_open_sky", server_default="derived_open_sky"
    )
    #: False outside the polar DEM: the skyline is a smooth sphere, not terrain.
    terrain_modelled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

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


class Mission(Base):
    """One CLPS delivery, as sourced in ``data/missions.json`` (ADR-5).

    Dates are stored as they were published: a date, its precision and the
    verbatim phrase. ``sort_at`` is the start of the landing (or launch) period
    and exists only so the list can be filtered and ordered by time.
    """

    __tablename__ = "missions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    vehicle_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    task_order: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    lander: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    outcome_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    region: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    target_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    #: {name, lat_deg, lon_deg, coordinate_kind, source_url, feature_id} or null.
    target: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ellipse: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    launch: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    landing: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    end_of_mission: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    planned_surface_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    site_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    unconfirmed_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    data_version: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    payloads: Mapped[list[MissionPayload]] = relationship(
        back_populates="mission",
        cascade="all, delete-orphan",
        order_by="MissionPayload.position",
    )


class MissionPayload(Base):
    """One NASA payload on a mission, with its own source."""

    __tablename__ = "mission_payloads"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    mission_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    acronym: Mapped[str | None] = mapped_column(String(40), nullable=True)
    organisation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    instrument_types: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(400), nullable=False)
    unconfirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    mission: Mapped[Mission] = relationship(back_populates="payloads")

    __table_args__ = (Index("ix_payload_types", "instrument_types", postgresql_using="gin"),)


class AppSetting(Base):
    """A setting the project manager changes from the dashboard, by name.

    One row per setting, the value as JSON. Only what must survive a restart
    and apply to everyone lives here: today, the AI assistant's switch and its
    model order. Everything else stays in environment settings.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Lifecycle foundations (ADR-8, ADR-12, ADR-17)
# ---------------------------------------------------------------------------


class User(Base):
    """A named person who signs in (ADR-17). One role: the project manager.

    ``name_key`` is the name and team, trimmed and lower-cased, so signing in
    twice as "Ada Lovelace" of "Payloads" is the same person both times.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    team: Mapped[str | None] = mapped_column(String(120), nullable=True)
    name_key: Mapped[str] = mapped_column(String(250), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEntry(Base):
    """One change to a record a person entered: append-only and hash-chained.

    ``seq``, ``prev_hash`` and ``hash`` are set by a database trigger, under a
    lock, so the chain cannot fork however many writers there are. Another
    trigger rejects UPDATE, DELETE and TRUNCATE. ``audit_verify()`` (SQL)
    recomputes the chain with the same function the trigger uses.
    """

    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor: Mapped[str] = mapped_column(String(250), nullable=False)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    entity: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(160), nullable=False)
    mission_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (Index("ix_audit_entity", "entity", "entity_id"),)


class FeedSnapshot(Base):
    """One fetch of one product from one provider, kept as fetched (ADR-8)."""

    __tablename__ = "feed_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    location_key: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    raw_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parsed: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    parser_version: Mapped[str] = mapped_column(String(24), nullable=False)
    licence: Mapped[str] = mapped_column(String(200), nullable=False)
    #: ok | rejected
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    issues: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    of_record: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    __table_args__ = (Index("ix_feed_latest", "provider", "product", "location_key", "fetched_at"),)


class FeedHealth(Base):
    """What the Data sources panel shows for one product at one place."""

    __tablename__ = "feed_health"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    product: Mapped[str] = mapped_column(String(64), primary_key=True)
    location_key: Mapped[str] = mapped_column(String(64), primary_key=True, default="")
    licence: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    staleness_budget_s: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_s: Mapped[int] = mapped_column(Integer, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_snapshot_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeedLimit(Base):
    """Per-provider circuit breaker and request budget, kept across restarts."""

    __tablename__ = "feed_limits"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    #: closed | open | half_open
    breaker: Mapped[str] = mapped_column(String(12), nullable=False, default="closed")
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tokens: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[float] = mapped_column(Float, nullable=False)
    refill_per_s: Mapped[float] = mapped_column(Float, nullable=False)
    tokens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Assessment(Base):
    """One lifecycle answer and exactly what it was built from (ADR-12)."""

    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    mission_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    params_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    closure: Mapped[str] = mapped_column(String(128), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    code_version: Mapped[str] = mapped_column(String(64), nullable=False)
    of_record: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    compute_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_assessment_key", "kind", "params_hash", "closure", "created_at"),)


class AssessmentInput(Base):
    """One input an assessment used: a snapshot, a file version, an entry."""

    __tablename__ = "assessment_inputs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: feed_snapshot | catalogue | kernel_set | dataset | mission | terrain | entry | assessment
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    ref: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    snapshot_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("feed_snapshots.id"), nullable=True, index=True
    )


class Job(Base):
    """A piece of heavy work, leased by one compute worker at a time (ADR-12)."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    mission_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    params_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    closure: Mapped[str] = mapped_column(String(128), nullable=False)
    #: queued | running | done | failed
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="queued")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    lease_owner: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True
    )
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "uq_jobs_in_flight",
            "kind",
            "params_hash",
            "closure",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_jobs_claim", "status", "priority", "run_after"),
    )
