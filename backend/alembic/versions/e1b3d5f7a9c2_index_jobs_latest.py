"""index jobs latest

The latest_for lookup in JobRepository queries jobs by (kind, params_hash, closure)
ordered by id DESC limit 1. uq_jobs_in_flight is a partial index only covering
status IN ('queued', 'running'), causing completed/failed jobs lookup to fall back
to a sequential scan. Adding ix_jobs_latest provides an index scan for all statuses.

Revision ID: e1b3d5f7a9c2
Revises: c2e4a6b8d0f1
Create Date: 2026-10-04 11:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "e1b3d5f7a9c2"
down_revision: str | None = "c2e4a6b8d0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_jobs_latest",
        "jobs",
        ["kind", "params_hash", "closure", sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_latest", table_name="jobs")
