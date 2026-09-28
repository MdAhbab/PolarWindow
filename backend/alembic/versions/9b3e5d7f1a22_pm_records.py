"""the project manager's records: readiness, milestones, parts, risks, lessons,
parameters, bookings, official forecasts and team limits (ADR-17)

Every change to these rows is also written to audit_log in the same
transaction by the service layer. Additive.

Revision ID: 9b3e5d7f1a22
Revises: 8d4f1a2b6c90
Create Date: 2026-09-27 04:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9b3e5d7f1a22"
down_revision: str | None = "8d4f1a2b6c90"
branch_labels = None
depends_on = None

_TS = sa.DateTime(timezone=True)


def _now(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, _TS, server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "readiness_items",
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column("mission_id", sa.String(64), nullable=False, index=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("organisation", sa.String(200), nullable=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("blocked_from", sa.String(24), nullable=True),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("changed_on", sa.String(32), nullable=True),
        sa.Column("changed_by", sa.String(250), nullable=True),
        sa.Column("evidence_url", sa.Text(), nullable=True),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("tests", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1000"),
        _now("updated_at"),
        sa.CheckConstraint(
            "state IN ('not_started','in_build','in_test','test_passed','delivered',"
            "'integrated','verified_on_lander','ready','blocked')",
            name="ck_readiness_state",
        ),
    )
    op.create_table(
        "milestones",
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column("mission_id", sa.String(64), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("on_date", sa.String(32), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("entered_by", sa.String(250), nullable=False),
        _now("entered_at"),
    )
    op.create_table(
        "parts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("mission_id", sa.String(64), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("part_number", sa.String(120), nullable=True),
        sa.Column("serial", sa.String(120), nullable=True),
        sa.Column("parent_item_id", sa.String(160), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("location", sa.String(200), nullable=True),
        _now("changed_at"),
        sa.Column("changed_by", sa.String(250), nullable=False),
        sa.CheckConstraint(
            "status IN ('installed','spare','in_test','damaged','failed','lost')",
            name="ck_parts_status",
        ),
    )
    op.create_table(
        "risks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("mission_id", sa.String(64), nullable=False, index=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("consequence_text", sa.Text(), nullable=False),
        sa.Column("scale_id", sa.String(64), nullable=False),
        sa.Column("ratings", postgresql.JSONB(), nullable=False),
        sa.Column("trend", sa.String(12), nullable=False),
        sa.Column("owner", sa.String(200), nullable=True),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("links", postgresql.JSONB(), nullable=False),
        _now("changed_at"),
        sa.Column("changed_by", sa.String(250), nullable=False),
    )
    op.create_table(
        "lesson_adoptions",
        sa.Column("mission_id", sa.String(64), primary_key=True),
        sa.Column("lesson_id", sa.String(120), primary_key=True),
        sa.Column("item_id", sa.String(160), nullable=False),
        sa.Column("adopted_by", sa.String(250), nullable=False),
        _now("adopted_at"),
    )
    op.create_table(
        "pm_parameters",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(250), nullable=False),
        _now("changed_at"),
    )
    op.create_table(
        "contact_bookings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("mission_id", sa.String(64), nullable=False, index=True),
        sa.Column("station", sa.String(64), nullable=False),
        sa.Column("start", _TS, nullable=False),
        sa.Column("end", _TS, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("entered_by", sa.String(250), nullable=False),
        _now("entered_at"),
        sa.CheckConstraint('"end" > start', name="ck_booking_order"),
    )
    op.create_table(
        "official_forecasts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("mission_id", sa.String(64), nullable=False, index=True),
        sa.Column("probability_pct", sa.Float(), nullable=False),
        sa.Column("concerns", postgresql.JSONB(), nullable=False),
        sa.Column("pdf_url", sa.Text(), nullable=False),
        sa.Column("entered_by", sa.String(250), nullable=False),
        _now("entered_at"),
        sa.CheckConstraint(
            "probability_pct >= 0 AND probability_pct <= 100", name="ck_forecast_pct"
        ),
    )
    op.create_table(
        "vehicle_limits",
        sa.Column("vehicle_id", sa.String(64), primary_key=True),
        sa.Column("rule_id", sa.String(120), primary_key=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("entered_by", sa.String(250), nullable=False),
        _now("entered_at"),
    )
    op.create_table(
        "return_limits",
        sa.Column("mission_id", sa.String(64), primary_key=True),
        sa.Column("booster", postgresql.JSONB(), nullable=False),
        sa.Column("capsule", postgresql.JSONB(), nullable=False),
        sa.Column("entered_by", sa.String(250), nullable=False),
        _now("entered_at"),
    )


def downgrade() -> None:
    for t in (
        "return_limits",
        "vehicle_limits",
        "official_forecasts",
        "contact_bookings",
        "pm_parameters",
        "lesson_adoptions",
        "risks",
        "parts",
        "milestones",
        "readiness_items",
    ):
        op.drop_table(t)
