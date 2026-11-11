"""scenarios: what-if answers for steps a mission has no published data for

A scenario keeps the values a person set and the values resolved around them
(each with its basis), and the answer. Nothing here is ever written to the
mission's record. ``key`` is the hash of the mission, the steps and the
canonical assumptions, so a similar prompt finds the same scenario.

Revision ID: a7c9e1b3d5f8
Revises: f3a5c7e9b1d2
Create Date: 2026-11-10 10:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a7c9e1b3d5f8"
down_revision: str | None = "f3a5c7e9b1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("mission_id", sa.String(64), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("given", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("sections", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("preset", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("assumptions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("phases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("summaries", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("results", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("job_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by_name", sa.String(250), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_scenarios_status"
        ),
    )
    op.create_index("uq_scenarios_key", "scenarios", ["key"], unique=True)
    op.create_index("ix_scenarios_mission", "scenarios", ["mission_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_scenarios_mission", table_name="scenarios")
    op.drop_index("uq_scenarios_key", table_name="scenarios")
    op.drop_table("scenarios")
